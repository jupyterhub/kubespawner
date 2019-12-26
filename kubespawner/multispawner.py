'''
JupyterHub Spawner to spawn user notebooks on a Kubernetes cluster in per-
user namespaces.

This module exports `MultiNamespacedKubeSpawner` class, which is the spawner
implementation that should be used by JupyterHub.
'''

from jupyterhub.utils import exponential_backoff
from kubernetes import client
from kubernetes.client.rest import ApiException
from tornado import gen
from tornado.ioloop import IOLoop
from traitlets import Bool
from . import KubeSpawner
from .clients import shared_client
from .multireflector import MultiNamespacePodReflector, EventReflector


class MultiNamespacedKubeSpawner(KubeSpawner):
    '''Implement a JupyterHub spawner to spawn pods in a Kubernetes Cluster
    with per-user namespaces.
    '''

    rbac_api = None  # We need an RBAC client

    delete_namespace_on_stop = Bool(
        False,
        config=True,
        help='''
        If True, the entire namespace will be deleted when the lab pod stops.
        '''
    ).tag(config=True)

    allow_ancillary_spawning = Bool(
        True,
        config=True,
        help='''
        If True, a ServiceAccount, Role, and Rolebinding will be created
        so that the user pod can itself spawn more pods (e.g. for dask or
        workflow).

        This requires additional RBAC permissions.
        '''
    ).tag(config=True)

    enable_namespace_quotas = Bool(
        False,
        config=True,
        help='''
        If True, a quota will be created along with the namespace to restrict
        the amount of resources the user namespace can consume.
        '''
        # FIXME: add some clean way to specify those quotas; maybe more
        #  configurables but it gets unwieldy.
    ).tag(config=True)

    def __init__(self, *args, **kwargs):
        _mock = kwargs.get('_mock', False)  # Don't pop!  Parent wants it.
        super().__init__(*args, **kwargs)

        self.rbac_api = shared_client('RbacAuthorizationV1Api')

        selected_pod_reflector_classref = MultiNamespacePodReflector
        selected_event_reflector_classref = EventReflector
        self.namespace = self.get_user_namespace()

        main_loop = IOLoop.current()

        def on_pod_reflector_failure():
            self.log.critical("Pod reflector failed, halting Hub.")
            main_loop.stop()

        if _mock:
            # Don't actually try to create the reflectors if we are mocking.
            return

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

        _ = yield self.ensure_namespace_resources()

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

        if self.delete_namespace_on_stop:
            _ = yield self._maybe_delete_namespace()

    @gen.coroutine
    def _ensure_namespace_resources(self):
        '''Here we make sure that the namespace exists, creating it if
        it does not.  That requires a ClusterRole that can list and create
        namespaces.

        If we create the namespace, we also create (if needed) a ServiceAccount
        and its Role and Rolebinding within the namespace to allow the user 
        pod to spawn other pods (e.g. dask or workflow).

        '''
        namespace = self.namespace
        if not namespace or namespace == "default":
            raise ValueError("Will not use default namespace!")
        api = self.api
        ns = client.V1Namespace(
            metadata=client.V1ObjectMeta(name=namespace))
        try:
            self.log.info("Attempting to create namespace '%s'" % namespace)
            api.create_namespace(ns)
        except ApiException as e:
            if e.status != 409:
                estr = "Create namespace '%s' failed: %s" % (ns, str(e))
                self.log.exception(estr)
                raise
            else:
                self.log.info("Namespace '%s' already exists." % namespace)
        # Wait for the namespace to actually appear before creating objects
        #  in it.
        _ = yield self._wait_for_namespace()
        if self.allow_ancillary_spawning:
            self.log.debug("Ensuring namespaced service account.")
            _ = yield self._ensure_namespaced_service_account()
        if self.enable_namespace_quotas:
            quotaspec = yield self._determine_quota()
            _ = yield self._ensure_namespaced_resource_quota(quotaspec)
        self.log.debug("Namespace resources ensured.")

    @gen.coroutine
    def _ensure_namespaced_service_account(self):
        # Create a service account with role and rolebinding to allow it
        #  to manipulate pods in the namespace.
        self.log.info("Ensuring namespaced service account.")
        namespace = self.namespace
        api = self.api
        rbac_api = self.rbac_api
        svcacct, role, rolebinding = yield \
            self._define_namespaced_account_objects()
        account = self.service_account
        try:
            self.log.info("Attempting to create service account.")
            api.create_namespaced_service_account(
                namespace=namespace,
                body=svcacct)
        except ApiException as e:
            if e.status != 409:
                self.log.exception("Create service account '%s' " % account +
                                   "in namespace '%s' " % namespace +
                                   "failed: %s" % str(e))
                raise
            else:
                self.log.info("Service account '%s' " % account +
                              "in namespace '%s' already exists." % namespace)
        try:
            self.log.info("Attempting to create role in namespace.")
            rbac_api.create_namespaced_role(
                namespace,
                role)
        except ApiException as e:
            if e.status != 409:
                self.log.exception("Create role '%s' " % account +
                                   "in namespace '%s' " % namespace +
                                   "failed: %s" % str(e))
                raise
            else:
                self.log.info("Role '%s' " % account +
                              "already exists in namespace '%s'." % namespace)
        try:
            self.log.info("Attempting to create rolebinding in namespace.")
            rbac_api.create_namespaced_role_binding(
                namespace,
                rolebinding)
        except ApiException as e:
            if e.status != 409:
                self.log.exception("Create rolebinding '%s'" % account +
                                   "in namespace '%s' " % namespace +
                                   "failed: %s", str(e))
                raise
            else:
                self.log.info("Rolebinding '%s' " % account +
                              "already exists in '%s'." % namespace)

    @gen.coroutine
    def _wait_for_namespace(self, timeout=30):
        '''Wait for namespace to be created.'''
        namespace = self.namespace
        for dl in range(timeout):
            self.log.debug("Checking for namespace " +
                           "{} [{}/{}]".format(namespace, dl, timeout))
            nl = self.parent.api.list_namespace(timeout_seconds=1)
            for ns in nl.items:
                nsname = ns.metadata.name
                if nsname == namespace:
                    self.log.debug("Namespace {} found.".format(namespace))
                    return
                self.log.debug(
                    "Namespace {} not present yet.".format(namespace))
            time.sleep(1)
        raise RuntimeError(
            "Namespace '{}' was not created in {} seconds!".format(namespace,
                                                                   timeout))

    @gen.coroutine
    def _define_namespaced_account_objects(self):
        namespace = self.namespace
        username = self.user.escaped_name
        # FIXME: probably something a little more sophisticated is called for.
        account = "{}-{}".format(username, "svcacct")
        self.service_account = account
        md = client.V1ObjectMeta(name=account)
        svcacct = client.V1ServiceAccount(metadata=md)
        # These rules are suitable for spawning Dask pods.  You will need to
        #  modify them for spawning other things, such as Argo Workflows.
        rules = [
            client.V1PolicyRule(
                api_groups=[""],
                resources=["pods", "services"],
                verbs=["get", "list", "watch", "create", "delete"]
            ),
            client.V1PolicyRule(
                api_groups=[""],
                resources=["pods/log", "serviceaccounts"],
                verbs=["get", "list"]
            ),
        ]
        role = client.V1Role(
            rules=rules,
            metadata=md)
        rolebinding = client.V1RoleBinding(
            metadata=md,
            role_ref=client.V1RoleRef(api_group="rbac.authorization.k8s.io",
                                      kind="Role",
                                      name=account),
            subjects=[client.V1Subject(
                kind="ServiceAccount",
                name=account,
                namespace=namespace)]
        )

        return svcacct, role, rolebinding

    @gen.coroutine
    def _determine_quota(self):
        '''This is something you will probably want to override in a subclass.

        You could do different quotas by user group membership, or size
        based on things you determine from the environment.  This
        implementation is just a stub that returns defaults appropriate for
        smallish environments.
        '''
        cpu = '100'
        memory = '300Gi'
        qs = client.V1ResourceQuotaSpec(
            hard={"limits.cpu": cpu,
                  "limits.memory": memory})

    @gen.coroutine
    def _ensure_namespaced_resource_quota(self, quotaspec):
        '''Create K8s quota object if necessary.
        '''
        self.log.debug("Entering ensure_namespaced_resource_quota()")
        namespace = self.namespace
        api = self.api
        if namespace == "default":
            self.log.error("Will not create quota for default namespace!")
            return
        quota = client.V1ResourceQuota(
            metadata=client.V1ObjectMeta(
                name="quota",
            ),
            spec=quotaspec
        )
        self.log.info("Creating quota: %r" % quota)
        try:
            api.create_namespaced_resource_quota(namespace, quota)
        except ApiException as e:
            if e.status != 409:
                self.log.exception("Create resourcequota '%s'" % quota +
                                   "in namespace '%s' " % namespace +
                                   "failed: %s", str(e))
                raise
            else:
                self.log.debug("Resourcequota '%r' " % quota +
                               "already exists in '%s'." % namespace)

    @gen.coroutine
    def _maybe_delete_namespace(self):
        '''Here we try to delete the namespace.  We perform a check to see
        whether anything is still running in the namespace such that it
        should not be deleted, and assuming that comes back clean, 
        we then try to delete the namespace.

        This requires a cluster role that can delete namespaces.'''
        self.log.debug("Attempting to delete namespace.")
        api = self.api
        namespace = self.namespace
        if not namespace or namespace == "default":
            raise RuntimeError("Cannot delete default namespace!")
            return
        podlist = api.list_namespaced_pod(namespace)
        clear_to_delete = True
        if podlist and podlist.items:
            clear_to_delete = yield self._check_pods(podlist.items)
        if not clear_to_delete:
            self.log.info("Not deleting namespace '%s'" % namespace)
            return False
        self.log.info("Deleting namespace '%s'" % namespace)
        api.delete_namespace(namespace)
        return True

    @gen.coroutine
    def _check_pods(self, items):
        '''Returns True if there's nothing in the namespace that should
        prevent namespace deletion.  Default is pods in "Running", "Pending",
        or "Unknown" phases.
        '''
        # You might want to, for instance, allow deletion of namespaces even
        #  if there are running dask pods, on the grounds that without a
        #  head node to report back to, they're pretty useless.
        namespace = self.namespace
        for i in items:
            if i and i.status:
                phase = i.status.phase
                if (phase == "Running" or phase == "Unknown"
                        or phase == "Pending"):
                    self.log.warning(("Pod in phase '{}'; cannot delete " +
                                      "namespace '{}'.").format(phase,
                                                                namespace))
                    return False
        return True
