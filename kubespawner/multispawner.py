'''
JupyterHub Spawner to spawn user notebooks on a Kubernetes cluster in per-
user namespaces.

This module exports `MultiNamespacedKubeSpawner` class, which is the spawner
implementation that should be used by JupyterHub.
'''

from jupyterhub.utils import exponential_backoff
from kubernetes import client
from kubernetes.client.rest import ApiException
from . import KubeSpawner
from .clients import shared_client
from tornado import gen
from tornado.ioloop import IOLoop
from .multireflector import MultiNamespacePodReflector, EventReflector


class MultiNamespacedKubeSpawner(KubeSpawner):
    '''Implement a JupyterHub spawner to spawn pods in a Kubernetes Cluster
    with per-user namespaces.
    '''

    rbac_api = None  # We need an RBAC client

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.rbac_api = shared_client('RbacAuthorizationV1Api')

        selected_pod_reflector_classref = MultiNamespacePodReflector
        selected_event_reflector_classref = EventReflector
        self.namespace = self.get_user_namespace()

        main_loop = IOLoop.current()

        def on_pod_reflector_failure():
            self.log.critical("Pod reflector failed, halting Hub.")
            main_loop.stop()

        # Replace pod_reflector
        self.__class__.pod_reflector = selected_pod_reflector_classref(
            parent=self, namespace=self.namespace,
            on_failure=on_pod_reflector_failure
        )
        self.log.debug("Created new pod reflector: " +
                       "%r" % self.__class__.pod_reflector)
        # And event_reflector
        self.__class__.event_reflector = selected_event_reflector_classref(
            parent=self, namespace=self.namespace)

    def get_user_namespace(self):
        '''Return namespace for user pods (and ancillary objects).
        '''
        defname = self._namespace_default()
        # We concatenate the default namespace and the name so that we
        #  can continue having multiple Jupyter instances in the same
        #  k8s cluster in different namespaces.  The user namespaces must
        #  themselves be namespaced, as it were.
        if defname == "default":
            if self.user.name != "mock_name":
                raise ValueError("Won't spawn into default namespace!")
            else:
                self.log.critical("Default namespace, but mocking is on.")
        return "{}-{}".format(defname, self.user.escaped_name)

    @gen.coroutine
    def poll(self):
        '''
        Check if the pod is still running.

        Uses the same interface as subprocess.Popen.poll(): if the pod is
        still running, returns None.  If the pod has exited, return the
        exit code if we can determine it, or 1 if it has exited but we
        don't know how.  These are the return values JupyterHub expects.

        Note that a clean exit will have an exit code of zero, so it is
        necessary to check that the returned value is None, rather than
        just Falsy, to determine that the pod is still running.
        '''
        # have to wait for first load of data before we have a valid answer
        if not self.pod_reflector.first_load_future.done():
            yield self.pod_reflector.first_load_future
        data = self.pod_reflector.pods.get((self.namespace, self.pod_name),
                                           None)
        if data is not None:
            if data.status.phase == 'Pending':
                return None
            ctr_stat = data.status.container_statuses
            if ctr_stat is None:  # No status, no container (we hope)
                # This seems to happen when a pod is idle-culled.
                return 1
            for c in ctr_stat:
                # return exit code if notebook container has terminated
                if c.name == 'notebook':
                    if c.state.terminated:
                        # call self.stop to delete the pod
                        if self.delete_stopped_pods:
                            yield self.stop(now=True)
                        return c.state.terminated.exit_code
                    break
            # None means pod is running or starting up
            return None
        # pod doesn't exist or has been deleted
        return 1

    @gen.coroutine
    def _start(self):
        '''Start the user's pod.
        '''
        retry_times = 4  # Ad-hoc
        pod = yield self.get_pod_manifest()
        if self.modify_pod_hook:
            pod = yield gen.maybe_future(self.modify_pod_hook(self, pod))
        for i in range(retry_times):
            try:
                yield self.asynchronize(
                    self.api.create_namespaced_pod,
                    self.namespace,
                    pod,
                )
                break
            except ApiException as e:
                if e.status != 409:
                    # We only want to handle 409 conflict errors
                    self.log.exception("Failed for %s", pod.to_str())
                    raise
                self.log.info(
                    'Found existing pod %s, attempting to kill', self.pod_name)
                # TODO: this should show up in events
                yield self.stop(True)

                self.log.info(
                    'Killed pod %s, will try starting ' % self.pod_name +
                    'singleuser pod again')
        else:
            raise Exception(
                'Can not create user pod %s :' % self.pod_name +
                'already exists and could not be deleted')

        # we need a timeout here even though start itself has a timeout
        # in order for this coroutine to finish at some point.
        # using the same start_timeout here
        # essentially ensures that this timeout should never propagate up
        # because the handler will have stopped waiting after
        # start_timeout, starting from a slightly earlier point.
        try:
            yield exponential_backoff(
                lambda: self.is_pod_running(self.pod_reflector.pods.get(
                    (self.namespace, self.pod_name), None)),
                'pod/%s did not start in %s seconds!' % (
                    self.pod_name, self.start_timeout),
                timeout=self.start_timeout,
            )
        except TimeoutError:
            if self.pod_name not in self.pod_reflector.pods:
                # if pod never showed up at all,
                # restart the pod reflector which may have become disconnected.
                self.log.error(
                    "Pod %s never showed up in reflector;" % self.pod_name +
                    " restarting pod reflector."
                )
                self._start_watching_pods(replace=True)
            raise

        pod = self.pod_reflector.pods[(self.namespace, self.pod_name)]
        self.pod_id = pod.metadata.uid
        if self.event_reflector:
            self.log.debug(
                'pod %s events before launch: %s',
                self.pod_name,
                "\n".join(
                    [
                        "%s [%s] %s" % (event.last_timestamp,
                                        event.type, event.message)
                        for event in self.events
                    ]
                ),
            )
        return (pod.status.pod_ip, self.port)

    @gen.coroutine
    def stop(self, now=False):
        delete_options = client.V1DeleteOptions()

        if now:
            grace_seconds = 0
        else:
            # Give it some time, but not the default (which is 30s!)
            # FIXME: Move this into pod creation maybe?
            grace_seconds = 1

        delete_options.grace_period_seconds = grace_seconds
        self.log.info("Deleting pod %s", self.pod_name)
        try:
            yield self.asynchronize(
                self.api.delete_namespaced_pod,
                name=self.pod_name,
                namespace=self.namespace,
                body=delete_options,
                grace_period_seconds=grace_seconds,
            )
        except ApiException as e:
            if e.status == 404:
                self.log.warning(
                    "No pod %s to delete. Assuming already deleted.",
                    self.pod_name,
                )
            else:
                raise
        try:
            yield exponential_backoff(
                lambda: self.pod_reflector.pods.get((self.namespace,
                                                     self.pod_name), None) is
                None,
                'pod/%s did not disappear in %s seconds!' % (
                    self.pod_name, self.start_timeout),
                timeout=self.start_timeout,
            )
        except TimeoutError:
            self.log.error(
                "Pod %s did not disappear, " % self.pod_name +
                "restarting pod reflector")
            self._start_watching_pods(replace=True)
            raise
