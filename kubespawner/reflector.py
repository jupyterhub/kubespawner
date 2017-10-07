import time
import threading

from traitlets.config import SingletonConfigurable
from traitlets import Any, Dict, Unicode
from kubernetes import client, config, watch
from tornado.ioloop import IOLoop

class PodReflector(SingletonConfigurable):
    """
    Local up-to-date copy of a set of kubernetes pods
    """
    labels = Dict(
        {
            'heritage': 'jupyterhub',
            'component': 'singleuser-server',
        },
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

    pods = Dict(
        {},
        help="""
        Dictionary of pod names to Pod objects.

        This can be directly accessed from multiple threads.
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
        self.api = client.CoreV1Api()

        # FIXME: Protect against malicious labels?
        self.label_selector = ','.join(['{}={}'.format(k, v) for k, v in self.labels.items()])

        self.start()

    def _list_and_update(self):
        """
        Update current list of pods by doing a full fetch of pod information.

        Overwrites all current pod info.
        """
        initial_pods = self.api.list_namespaced_pod(
            self.namespace,
            label_selector=self.label_selector
        )
        # This is an atomic operation on the dictionary!
        self.pods = {p.metadata.name: p for p in initial_pods.items}
        # return the resource version so we can hook up a watch
        return initial_pods.metadata.resource_version

    def _watch_and_update(self):
        """
        Keeps the current list of pods up-to-date

        This method is to be run not on the main thread!

        We first fetch the list of current pods, and store that. Then we
        register to be notified of changes to those pods, and keep our
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
        while True:
            self.log.info("watching for pods with label selector %s in namespace %s", self.label_selector, self.namespace)
            w = watch.Watch()
            try:
                resource_version = self._list_and_update()
                for ev in w.stream(
                        self.api.list_namespaced_pod,
                        self.namespace,
                        label_selector=self.label_selector,
                        resource_version=resource_version,
                ):
                    cur_delay = 0.1
                    pod = ev['object']
                    if ev['type'] == 'DELETED':
                        # This is an atomic delete operation on the dictionary!
                        self.pods.pop(pod.metadata.name, None)
                    else:
                        # This is an atomic operation on the dictionary!
                        self.pods[pod.metadata.name] = pod
            except Exception:
                cur_delay = cur_delay * 2
                if cur_delay > 30:
                    self.log.exception("Watching pods never recovered, giving up")
                    if self.on_failure:
                        self.on_failure()
                    return
                self.log.exception("Error when watching pods, retrying in %ss", cur_delay)
                time.sleep(cur_delay)
                continue
            finally:
                w.stop()

    def start(self):
        """
        Start the reflection process!

        We'll do a blocking read of all pods first, so that we don't
        race with any operations that are checking the state of the pod
        store - such as polls. This should be called only once at the
        start of program initialization (when the singleton is being created),
        and not afterwards!
        """
        if hasattr(self, 'watch_thread'):
            raise ValueError('Thread watching for pods is already running')

        self._list_and_update()
        self.watch_thread = threading.Thread(target=self._watch_and_update)
        # If the watch_thread is only thread left alive, exit app
        self.watch_thread.daemon = True
        self.watch_thread.start()
