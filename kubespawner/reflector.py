# specifically use concurrent.futures for threadsafety
# asyncio Futures cannot be used across threads
from concurrent.futures import Future

import time
import threading

from traitlets.config import LoggingConfigurable
from traitlets import Any, Dict, Int, Unicode
from kubernetes import config, watch
# This is kubernetes client implementation specific, but we need to know
# whether it was a network or watch timeout.
from urllib3.exceptions import ReadTimeoutError

from .clients import shared_client

class NamespacedResourceReflector(LoggingConfigurable):
    """
    Base class for keeping a local up-to-date copy of a set of kubernetes resources.

    Must be subclassed once per kind of resource that needs watching.
    """
    labels = Dict(
        {},
        config=True,
        help="""
        Labels to reflect onto local cache
        """
    )

    fields = Dict(
        {},
        config=True,
        help="""
        Fields to restrict the reflected objects
        """
    )

    namespace = Unicode(
        None,
        allow_none=True,
        help="""
        Namespace to watch for resources in
        """
    )

    resources = Dict(
        {},
        help="""
        Dictionary of resource names to the appropriate resource objects.

        This can be accessed across threads safely.
        """
    )

    kind = Unicode(
        'resource',
        help="""
        Human readable name for kind of object we're watching for.

        Used for diagnostic messages.
        """
    )

    list_method_name = Unicode(
        "",
        help="""
        Name of function (on apigroup respresented by `api_group_name`) that is to be called to list resources.

        This will be passed a namespace & a label selector. You most likely want something
        of the form list_namespaced_<resource> - for example, `list_namespaced_pod` will
        give you a PodReflector.

        This must be set by a subclass.
        """
    )

    api_group_name = Unicode(
        'CoreV1Api',
        help="""
        Name of class that represents the apigroup on which `list_method_name` is to be found.

        Defaults to CoreV1Api, which has everything in the 'core' API group. If you want to watch Ingresses,
        for example, you would have to use ExtensionsV1beta1Api
        """
    )

    request_timeout = Int(
        60,
        config=True,
        help="""
        Network timeout for kubernetes watch.

        Trigger watch reconnect when a given request is taking too long,
        which can indicate network issues.
        """
    )

    timeout_seconds = Int(
        10,
        config=True,
        help="""
        Timeout for kubernetes watch.

        Trigger watch reconnect when no watch event has been received.
        This will cause a full reload of the currently existing resources
        from the API server.
        """
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
        """)

    on_failure = Any(help="""Function to be called when the reflector gives up.""")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Load kubernetes config here, since this is a Singleton and
        # so this __init__ will be run way before anything else gets run.
        try:
            config.load_incluster_config()
        except config.ConfigException:
            config.load_kube_config()
        self.api = shared_client(self.api_group_name)

        # FIXME: Protect against malicious labels?
        self.label_selector = ','.join(['{}={}'.format(k, v) for k, v in self.labels.items()])
        self.field_selector = ','.join(['{}={}'.format(k, v) for k, v in self.fields.items()])

        self.first_load_future = Future()
        self._stop_event = threading.Event()

        self.start()

    def __del__(self):
        self.stop()

    def _list_and_update(self):
        """
        Update current list of resources by doing a full fetch.

        Overwrites all current resource info.
        """
        initial_resources = getattr(self.api, self.list_method_name)(
            self.namespace,
            label_selector=self.label_selector,
            field_selector=self.field_selector,
            _request_timeout=self.request_timeout,
        )
        # This is an atomic operation on the dictionary!
        self.resources = {p.metadata.name: p for p in initial_resources.items}
        # return the resource version so we can hook up a watch
        return initial_resources.metadata.resource_version

    def _watch_and_update(self):
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

        Note that we're playing a bit with fire here, by updating a dictionary
        in this thread while it is probably being read in another thread
        without using locks! However, dictionary access itself is atomic,
        and as long as we don't try to mutate them (do a 'fetch / modify /
        update' cycle on them), we should be ok!
        """
        selectors = []
        log_name = ""
        if self.label_selector:
            selectors.append("label selector=%r" % self.label_selector)
        if self.field_selector:
            selectors.append("field selector=%r" % self.field_selector)
        log_selector = ', '.join(selectors)

        cur_delay = 0.1

        self.log.info(
            "watching for %s with %s in namespace %s",
            self.kind, log_selector, self.namespace,
        )
        while True:
            self.log.debug("Connecting %s watcher", self.kind)
            start = time.monotonic()
            w = watch.Watch()
            try:
                resource_version = self._list_and_update()
                if not self.first_load_future.done():
                    # signal that we've loaded our initial data
                    self.first_load_future.set_result(None)
                watch_args = {
                    'namespace': self.namespace,
                    'label_selector': self.label_selector,
                    'field_selector': self.field_selector,
                    'resource_version': resource_version,
                }
                if self.request_timeout:
                    # set network receive timeout
                    watch_args['_request_timeout'] = self.request_timeout
                if self.timeout_seconds:
                    # set watch timeout
                    watch_args['timeout_seconds'] = self.timeout_seconds
                # in case of timeout_seconds, the w.stream just exits (no exception thrown)
                # -> we stop the watcher and start a new one
                for ev in w.stream(
                        getattr(self.api, self.list_method_name),
                        **watch_args
                ):
                    cur_delay = 0.1
                    resource = ev['object']
                    if ev['type'] == 'DELETED':
                        # This is an atomic delete operation on the dictionary!
                        self.resources.pop(resource.metadata.name, None)
                    else:
                        # This is an atomic operation on the dictionary!
                        self.resources[resource.metadata.name] = resource
                    if self._stop_event.is_set():
                        self.log.info("%s watcher stopped", self.kind)
                        break
                    watch_duration = time.monotonic() - start
                    if watch_duration >= self.restart_seconds:
                        self.log.debug(
                            "Restarting %s watcher after %i seconds",
                            self.kind, watch_duration,
                        )
                        break
            except ReadTimeoutError:
                # network read time out, just continue and restart the watch
                # this could be due to a network problem or just low activity
                self.log.warning("Read timeout watching %s, reconnecting", self.kind)
                continue
            except Exception:
                cur_delay = cur_delay * 2
                if cur_delay > 30:
                    self.log.exception("Watching resources never recovered, giving up")
                    if self.on_failure:
                        self.on_failure()
                    return
                self.log.exception("Error when watching resources, retrying in %ss", cur_delay)
                time.sleep(cur_delay)
                continue
            else:
                # no events on watch, reconnect
                self.log.debug("%s watcher timeout", self.kind)
            finally:
                w.stop()
                if self._stop_event.is_set():
                    self.log.info("%s watcher stopped", self.kind)
                    break
        self.log.warning("%s watcher finished", self.kind)

    def start(self):
        """
        Start the reflection process!

        We'll do a blocking read of all resources first, so that we don't
        race with any operations that are checking the state of the pod
        store - such as polls. This should be called only once at the
        start of program initialization (when the singleton is being created),
        and not afterwards!
        """
        if hasattr(self, 'watch_thread'):
            raise ValueError('Thread watching for resources is already running')

        self._list_and_update()
        self.watch_thread = threading.Thread(target=self._watch_and_update)
        # If the watch_thread is only thread left alive, exit app
        self.watch_thread.daemon = True
        self.watch_thread.start()

    def stop(self):
        self._stop_event.set()

    def stopped(self):
        return self._stop_event.is_set()
