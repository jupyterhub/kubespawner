import time
import threading

from traitlets.config import LoggingConfigurable
from traitlets import Any, Dict, Unicode, Int
from kubernetes import client, config, watch
# This is kinda implementation specific, but we need to know it
from urllib3.exceptions import ReadTimeoutError


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
        0,
        config=True,
        help="""
        Network timeout for kubernetes watch.

        Trigger watch reconnect when no traffic has been received for this time.
        """
    )

    timeout_seconds = Int(
        0,
        config=True,
        help="""
        Timeout for kubernetes watch.

        Trigger watch reconnect when no watch event has been received.
        """
    )

    on_failure = Any(help="""Function to be called when the reflector gives up.""")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Load kubernetes config here, since this is a Singleton and
        # so this __init__ will be run way before anything else gets run.
        try:
            config.load_incluster_config()
        except config.ConfigException:
            config.load_kube_config()
        self.api = getattr(client, self.api_group_name)()

        # FIXME: Protect against malicious labels?
        self.label_selector = ','.join(['{}={}'.format(k, v) for k, v in self.labels.items()])

        self.start()

    def _list_and_update(self):
        """
        Update current list of resources by doing a full fetch.

        Overwrites all current resource info.
        """
        initial_resources = getattr(self.api, self.list_method_name)(
            self.namespace,
            label_selector=self.label_selector
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
        cur_delay = 0.1
        watch_args = {
            'namespace': self.namespace,
            'label_selector': self.label_selector,
        }
        if self.request_timeout:
            watch_args['_request_timeout'] = self.request_timeout
        if self.timeout_seconds:
            # This might not ever be triggered as with resource_version set,
            # we awmays get the last event sent again.
            watch_args['timeout_seconds'] = self.timeout_seconds
        while True:
            self.log.info("watching for %s with label selector %s in namespace %s", self.kind, self.label_selector, self.namespace)
            w = watch.Watch()
            try:
                # in case of timeout_seconds, the w.stream just exits (no exception thrown)
                # -> we stop the watcher and start a new one
                for ev in w.stream(
                        getattr(self.api, self.list_method_name),
                        **watch_args
                ):
                    cur_delay = 0.1
                    resource = ev['object']
                    if watch_args.get('resource_version') != resource.metadata.resource_version:
                        watch_args['resource_version'] = resource.metadata.resource_version
                        self.log.info('Watch Event: {} - {}'.format(ev['type'], resource.metadata.name))
                    if ev['type'] == 'DELETED':
                        # This is an atomic delete operation on the dictionary!
                        self.resources.pop(resource.metadata.name, None)
                    else:
                        # This is an atomic operation on the dictionary!
                        self.resources[resource.metadata.name] = resource
                self.log.debug('Watch Stream timeout')
            except ReadTimeoutError:
                # we expect this to happen, so that watch get's restarted and won't hang
                self.log.debug('Watch Stream network timeout')
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
            finally:
                w.stop()

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

        self.watch_thread = threading.Thread(target=self._watch_and_update)
        # If the watch_thread is only thread left alive, exit app
        self.watch_thread.daemon = True
        self.watch_thread.start()


