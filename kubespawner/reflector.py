# specifically use concurrent.futures for threadsafety
# asyncio Futures cannot be used across threads (uh oh)
import asyncio
import json
import threading
import time
from concurrent.futures import Future
from functools import partial

from kubernetes_asyncio import client
from kubernetes_asyncio import config
from kubernetes_asyncio import watch
from kubernetes_asyncio.client.api_client import ApiClient
from traitlets import Any
from traitlets import Bool
from traitlets import Dict
from traitlets import Int
from traitlets import Unicode
from traitlets.config import LoggingConfigurable
from urllib3.exceptions import ReadTimeoutError

from .clients import shared_client, set_k8s_client_configuration

# This is kubernetes client implementation specific, but we need to know
# whether it was a network or watch timeout.


class ResourceReflector(LoggingConfigurable):
    """Base class for keeping a local up-to-date copy of a set of
    kubernetes resources.

    Must be subclassed once per kind of resource that needs watching.
    """

    labels = Dict(
        {},
        config=True,
        help="""
        Labels to reflect onto local cache
        """,
    )

    fields = Dict(
        {},
        config=True,
        help="""
        Fields to restrict the reflected objects
        """,
    )

    resources = Dict(
        {},
        help="""
        Dictionary of resource names to the appropriate resource objects.

        Let's not pretend it's threadsafe.  It is as long as the keys don't
        change, but c'mon, the lock isn't gonna kill us.
        """,
    )

    kind = Unicode(
        'resource',
        help="""
        Human readable name for kind of object we're watching for.

        Used for diagnostic messages.
        """,
    )

    omit_namespace = Bool(
        False,
        config=True,
        help="""
        Set this to true if the reflector is to operate across
        multiple namespaces.
        """,
    )

    namespace = Unicode(
        None,
        allow_none=True,
        help="""
        Namespace to watch for resources in; leave at 'None' for
        multi-namespace reflectors.
        """,
    )

    list_method_name = Unicode(
        "",
        help="""
        Name of function (on apigroup respresented by
        `api_group_name`) that is to be called to list resources.

        This will be passed a a label selector.

        If self.omit_namespace is False you want something of the form
        list_namespaced_<resource> - for example,
        `list_namespaced_pod` will give you a PodReflector.  It will
        take its namespace from self.namespace (which therefore should
        not be None).

        If self.omit_namespace is True, you want
        list_<resource>_for_all_namespaces.

        This must be set by a subclass.

        It is not necessary to set it for pod or event reflectors, because
        __init__ will figure it out.  If you create your own reflector
        subclass you probably want to add the logic to choose the method
        name to that class's __init__().
        """,
    )

    api_group_name = Unicode(
        'CoreV1Api',
        help="""
        Name of class that represents the apigroup on which
        `list_method_name` is to be found.

        Defaults to CoreV1Api, which has everything in the 'core' API group. If you want to watch Ingresses,
        for example, you would have to use ExtensionsV1beta1Api
        """,
    )

    request_timeout = Int(
        60,
        config=True,
        help="""
        Network timeout for kubernetes watch.

        Trigger watch reconnect when a given request is taking too long,
        which can indicate network issues.
        """,
    )

    timeout_seconds = Int(
        10,
        config=True,
        help="""
        Timeout for kubernetes watch.

        Trigger watch reconnect when no watch event has been received.
        This will cause a full reload of the currently existing resources
        from the API server.
        """,
    )

    restart_seconds = Int(
        30,
        config=True,
        help="""
        Maximum time before restarting a watch.

        The watch will be restarted at least this often,
        even if events are still arriving.
        Avoids trusting kubernetes watch to yield all events,
        which seems to not be a safe assumption.
        """,
    )

    on_failure = Any(help="""Function to be called when the reflector gives up.""")

    @classmethod
    async def reflector(cls, *args, **kwargs):
        """
        You should generally use this classmethod to get a new reflector,
        with its watch started.
        """
        inst=cls(*args, **kwargs)
        await set_k8s_client_configuration()
        await inst.start()
        return inst
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # FIXME: Protect against malicious labels?
        self.label_selector = ','.join(
            ['{}={}'.format(k, v) for k, v in self.labels.items()]
        )
        self.field_selector = ','.join(
            ['{}={}'.format(k, v) for k, v in self.fields.items()]
        )

        self.first_load_future = Future()
        self._stop_event = threading.Event()
        self.resource_lock = threading.Lock()

        # Make sure that we know kind, whether we should omit the
        #  namespace, and what our list_method_name is.  For the things
        #  we already know about, we can derive list_method_name from
        #  those two things.  New reflector types should also update
        #  their __init__() methods to derive list_method_name, but you
        #  could just set it directly in the subclass.
        if not self.list_method_name:
            plural_to_singular = {
                "endpoints": "endpoints",
                "events": "event",
                "ingresses": "ingress",
                "pods": "pod",
                "services": "service",
            }

            if self.kind in plural_to_singular:
                if self.omit_namespace:
                    self.list_method_name = (
                        f"list_{plural_to_singular[self.kind]}_for_all_namespaces"
                    )
                else:
                    self.list_method_name = (
                        f"list_namespaced_{plural_to_singular[self.kind]}"
                    )

        # Make sure we have the required values.
        if not self.kind:
            raise RuntimeError("Reflector kind must be set!")
        if not self.list_method_name:
            raise RuntimeError("Reflector list_method_name must be set!")

    async def __del__(self):
        if self.watch_task and not self.watch_task.done():
            try:
                await self.watch_task.cancel()
            except asyncio.CancelledError:
                self.log.debug("watch task cancelled")
        await self.stop()

    async def _list_and_update(self):
        """
        Update current list of resources by doing a full fetch.

        Overwrites all current resource info.
        """
        initial_resources = None
        kwargs = dict(
            label_selector=self.label_selector,
            field_selector=self.field_selector,
            _request_timeout=self.request_timeout,
            _preload_content=True,
        )
        if not self.omit_namespace:
            kwargs["namespace"] = self.namespace

        async with ApiClient() as api_client:
            grp=getattr(client, self.api_group_name)
            api=grp(api_client)
            res_fut = getattr(api, self.list_method_name)
            initial_resources = await ((res_fut)(**kwargs))
            self.resource_lock.acquire()
            self.resources = {
                f'{p.metadata.namespace}/{p.metadata.name}': p
                for p in initial_resources.items
            }
            self.resource_lock.release()
            # return the resource version so we can hook up a watch
            return initial_resources.metadata.resource_version

    def retrieve_resource_copy(self):
        """Instead of fretting about whether it's threadsafe, let's
        lock the resources, make a shallow copy, unlock the resources,
        and return the copy.
        """
        self.resource_lock.acquire()
        copy = dict(self.resources)
        self.resource_lock.release()
        return copy
        
    async def _watch_and_update(self):
        """
        Keeps the current list of resources up-to-date

        This method is to be run not on the main thread!

        We first fetch the list of current resources, and store that. Then we
        register to be notified of changes to those resources, and keep our
        local store up-to-date based on these notifications.

        We also perform exponential backoff, giving up after we hit 32s
        wait time. This should protect against network connections dropping
        and intermittent unavailability of the api-server. Every time we
        recover from an exception we also do a full fetch, to pick up
        changes that might've been missed in the time we were not doing
        a watch.

        Rather than tempting fate and decisions about weakening the GIL, let's
        just lock the object before updating it, huh?
        """
        selectors = []
        log_name = ""
        if self.label_selector:
            selectors.append("label selector=%r" % self.label_selector)
        if self.field_selector:
            selectors.append("field selector=%r" % self.field_selector)
        log_selector = ', '.join(selectors)
        
        cur_delay = 0.1

        if self.omit_namespace:
            ns_str = "all namespaces"
        else:
            ns_str = "namespace {}".format(self.namespace)

        self.log.info(
            "watching for %s with %s in %s",
            self.kind,
            log_selector,
            ns_str,
        )
        while True:
            self.log.debug("Connecting %s watcher", self.kind)
            start = time.monotonic()
            w = watch.Watch()
            try:
                resource_version = await self._list_and_update()
                if not self.first_load_future.done():
                    # signal that we've loaded our initial data
                    self.first_load_future.set_result(None)
                watch_args = {
                    "resource_version": resource_version,
                }
                if self.label_selector:
                    watch_args["label_selector"] = self.label_selector
                if self.field_selector:
                    watch_args["field_selector"] = self.field_selector
                if not self.omit_namespace:
                    watch_args["namespace"] = self.namespace
                if self.request_timeout:
                    # set network receive timeout
                    watch_args['_request_timeout'] = self.request_timeout
                if self.timeout_seconds:
                    # set watch timeout
                    watch_args['timeout_seconds'] = self.timeout_seconds
                # asyncio does the partial application inside w.stream
                async with ApiClient() as api_client:
                    grp=getattr(client, self.api_group_name)
                    api=grp(api_client)
                    method = getattr(api, self.list_method_name)

                    # in case of timeout_seconds, the w.stream just exits
                    # (no exception thrown)
                    # -> we stop the watcher and start a new one
                    async for watch_event in w.stream(method, **watch_args):
                        # Remember that these events are k8s api related WatchEvents
                        # objects, not k8s Event or Pod representations, they will
                        # reside in the WatchEvent's object field depending on what
                        # kind of resource is watched.
                        #
                        # ref: https://kubernetes.io/docs/reference/generated/kubernetes-api/v1.20/#watchevent-v1-meta
                        # ref: https://kubernetes.io/docs/reference/generated/kubernetes-api/v1.20/#event-v1-core
                        cur_delay = 0.1
                        resource = watch_event['object']
                        ref_key = "{}/{}".format(
                            resource.metadata.namespace,
                            resource.metadata.name
                        )
                        wtype = watch_event['type']
                        if watch_event['type'] == 'DELETED':
                            self.resource_lock.acquire()
                            self.resources.pop(ref_key, None)
                            self.resource_lock.release()
                            self.log.info(
                                f"{self.kind} watcher deleted {ref_key}")
                        else:
                            self.resource_lock.acquire()
                            self.resources[ref_key] = resource
                            self.resource_lock.release()
                            verbed = wtype.lower()
                            self.log.info(
                                f"{self.kind} watcher {verbed} {ref_key}")
                        if self._stop_event.is_set():
                            self.log.info("%s watcher stopped", self.kind)
                            break
                        watch_duration = time.monotonic() - start
                        if watch_duration >= self.restart_seconds:
                            self.log.debug(
                                "Restarting %s watcher after %i seconds",
                                self.kind,
                                watch_duration,
                            )
                            break
            except ReadTimeoutError:
                # network read time out, just continue and restart the watch
                # this could be due to a network problem or just low activity
                self.log.warning("Read timeout watching %s, reconnecting", self.kind)
                continue
            except Exception as exc:
                cur_delay = cur_delay * 2
                if cur_delay > 30:
                    self.log.exception("Watching resources never recovered, giving up")
                    if self.on_failure:
                        self.on_failure()
                    return
                self.log.exception(
                    f"Error {exc} when watching resources, retrying in {cur_delay}s"
                )
                await asyncio.sleep(cur_delay)
                continue
            else:
                # no events on watch, reconnect
                self.log.debug("%s watcher timeout", self.kind)
            finally:
                await w.stop()
                if self._stop_event.is_set():
                    self.log.info("%s watcher stopped", self.kind)
                    break
        self.log.warning("%s watcher finished", self.kind)


    async def start_or_restart(self):
        """
        We want to end up with a new watch, whatever happens.
        """
        try:
            await self.start()
        except ValueError:
            # It was already running, so kill the watch task and restart
            try:
                await self.watch_task.cancel()
            except asyncio.CancelledError:
                self.log.debug("watch task cancelled")
                await self.start()
            

    async def start(self):
        """
        Start the reflection process!

        We'll do a blocking read of all resources first, so that we don't
        race with any operations that are checking the state of the pod
        store - such as polls. This should be called only once per object
        (which means once per class, since it's a singleton) and not
        afterwards!
        """
        if hasattr(self, 'watch_task'):
            if self.watch_task:
                if not self.watch_task.done():
                    raise ValueError(
                        'Thread watching for resources is already running')
        await self._list_and_update()
        self.watch_task = asyncio.create_task(self._watch_and_update())

    async def stop(self):
        self._stop_event.set()

    def stopped(self):
        return self._stop_event.is_set()


class NamespacedResourceReflector(ResourceReflector):
    """
    Watches for resources in a particular namespace.  The list_methods
    want both a method name and a namespace.
    """

    omit_namespace = False


class MultiNamespaceResourceReflector(ResourceReflector):
    """
    Watches for resources across all namespaces.  The list_methods
    want only a method name.  Note that this requires the service account
    to be significantly more powerful, since it must be bound to ClusterRoles
    rather than just Roles, and therefore this is inherently more
    dangerous.

    It's also a really bad idea to use it for Events in a multi-namespace
    world, because then you get every single event in the whole cluster.
    That's why we've switched to a per-spawn event-watcher.
    """

    omit_namespace = True
