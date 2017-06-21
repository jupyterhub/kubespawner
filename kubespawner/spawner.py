"""
JupyterHub Spawner to spawn user notebooks on a Kubernetes cluster.

This module exports `KubeSpawner` class, which is the actual spawner
implementation that should be used by JupyterHub.
"""
import os
import json
import string
from urllib.parse import urlparse, urlunparse
from concurrent.futures import ThreadPoolExecutor
import multiprocessing


from tornado import gen
from tornado.concurrent import run_on_executor
from traitlets import Type, Unicode, List, Integer, Union, Dict, Bool
from jupyterhub.spawner import Spawner
from jupyterhub.traitlets import Command
from kubernetes.client.models.v1_volume import V1Volume
from kubernetes.client.models.v1_volume_mount import V1VolumeMount
from kubernetes.client.rest import ApiException
from kubernetes import client, config, watch
import escapism

from kubespawner.traitlets import Callable
from kubespawner.utils import request_maker, k8s_url
from kubespawner.objects import make_pod, make_pvc


class KubeSpawner(Spawner):
    """
    Implement a JupyterHub spawner to spawn pods in a Kubernetes Cluster.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # By now, all the traitlets have been set, so we can use them to compute
        # other attributes
        self.executor = ThreadPoolExecutor(max_workers=self.k8s_api_threadpool_workers)

        try:
            config.load_incluster_config()
        except config.ConfigException:
            config.load_kube_config()
        self.api = client.CoreV1Api()

        self.pod_name = self._expand_user_properties(self.pod_name_template)
        self.pvc_name = self._expand_user_properties(self.pvc_name_template)
        if self.hub_connect_ip:
            scheme, netloc, path, params, query, fragment = urlparse(self.hub.api_url)
            netloc = '{ip}:{port}'.format(
                ip=self.hub_connect_ip,
                port=self.hub_connect_port,
            )
            self.accessible_hub_api_url = urlunparse((scheme, netloc, path, params, query, fragment))
        else:
            self.accessible_hub_api_url = self.hub.api_url

        if self.port == 0:
            # Our default port is 8888
            self.port = 8888

    k8s_api_threadpool_workers = Integer(
        # Set this explicitly, since this is the default in Python 3.5+
        # but not in 3.4
        5 * multiprocessing.cpu_count(),
        config=True,
        help="""
        Number of threads in thread pool used to talk to the k8s API.

        Increase this if you are dealing with a very large number of users.

        Defaults to '5 * cpu_cores', which is the default for ThreadPoolExecutor.
        """
    )

    namespace = Unicode(
        config=True,
        help="""
        Kubernetes namespace to spawn user pods in.

        If running inside a kubernetes cluster with service accounts enabled,
        defaults to the current namespace. If not, defaults to 'default'
        """
    )

    def _namespace_default(self):
        """
        Set namespace default to current namespace if running in a k8s cluster

        If not in a k8s cluster with service accounts enabled, default to
        'default'
        """
        ns_path = '/var/run/secrets/kubernetes.io/serviceaccount/namespace'
        if os.path.exists(ns_path):
            with open(ns_path) as f:
                return f.read().strip()
        return 'default'

    ip = Unicode('0.0.0.0',
        help="""
        The IP address (or hostname) the single-user server should listen on.

        We override this from the parent so we can set a more sane default for
        the Kubernetes setup.
        """
    ).tag(config=True)

    cmd = Command(
        None,
        allow_none=True,
        minlen=0,
        help="""
        The command used for starting the single-user server.

        Provide either a string or a list containing the path to the startup script command. Extra arguments,
        other than this path, should be provided via `args`.

        This is usually set if you want to start the single-user server in a different python
        environment (with virtualenv/conda) than JupyterHub itself.

        Some spawners allow shell-style expansion here, allowing you to use environment variables.
        Most, including the default, do not. Consult the documentation for your spawner to verify!

        If set to None, Kubernetes will start the CMD that is specified in the Docker image being started.
        """
    ).tag(config=True)

    singleuser_working_dir = Unicode(
        None,
        allow_none=True,
        help="""
        The working directory were the Notebook server will be started inside the container.
        Defaults to `None` so the working directory will be the one defined in the Dockerfile.
        """
    ).tag(config=True)

    pod_name_template = Unicode(
        'jupyter-{username}',
        config=True,
        help="""
        Template to use to form the name of user's pods.

        {username} and {userid} are expanded to the escaped, dns-label safe
        username & integer user id respectively.

        This must be unique within the namespace the pods are being spawned
        in, so if you are running multiple jupyterhubs spawning in the
        same namespace, consider setting this to be something more unique.
        """
    )

    user_storage_pvc_ensure = Bool(
        False,
        config=True,
        help="""
        Ensure that a PVC exists for each user before spawning.

        Set to true to create a PVC named with `pvc_name_template` if it does
        not exist for the user when their pod is spawning.
        """
    )

    pvc_name_template = Unicode(
        'claim-{username}',
        config=True,
        help="""
        Template to use to form the name of user's pvc.

        {username} and {userid} are expanded to the escaped, dns-label safe
        username & integer user id respectively.

        This must be unique within the namespace the pvc are being spawned
        in, so if you are running multiple jupyterhubs spawning in the
        same namespace, consider setting this to be something more unique.
        """
    )

    hub_connect_ip = Unicode(
        None,
        config=True,
        allow_none=True,
        help="""
        IP/DNS hostname to be used by pods to reach out to the hub API.

        Defaults to `None`, in which case the `hub_ip` config is used.

        In kubernetes contexts, this is often not the same as `hub_ip`,
        since the hub runs in a pod which is fronted by a service. This IP
        should be something that pods can access to reach the hub process.
        This can also be through the proxy - API access is authenticated
        with a token that is passed only to the hub, so security is fine.

        Usually set to the service IP / DNS name of the service that fronts
        the hub pod (deployment/replicationcontroller/replicaset)

        Used together with `hub_connect_port` configuration.
        """
    )

    hub_connect_port = Integer(
        config=True,
        help="""
        Port to use by pods to reach out to the hub API.

        Defaults to be the same as `hub_port`.

        In kubernetes contexts, this is often not the same as `hub_port`,
        since the hub runs in a pod which is fronted by a service. This
        allows easy port mapping, and some systems take advantage of it.

        This should be set to the `port` attribute of a service that is
        fronting the hub pod.
        """
    )

    def _hub_connect_port_default(self):
        """
        Set default port on which pods connect to hub to be the hub port

        The hub needs to be accessible to the pods at this port. We default
        to the port the hub is listening on. This would be overriden in case
        some amount of port mapping is happening.
        """
        return self.hub.server.port

    singleuser_extra_labels = Dict(
        {},
        config=True,
        help="""
        Extra kubernetes labels to set on the spawned single-user pods.

        The keys and values specified here would be set as labels on the spawned single-user
        kubernetes pods. The keys and values must both be strings that match the kubernetes
        label key / value constraints.

        See https://kubernetes.io/docs/concepts/overview/working-with-objects/labels/ for more
        info on what labels are and why you might want to use them!

        {username} and {userid} are expanded to the escaped, dns-label safe
        username & integer user id respectively, wherever they are used.
        """
    )

    singleuser_image_spec = Unicode(
        'jupyterhub/singleuser:latest',
        config=True,
        help="""
        Docker image spec to use for spawning user's containers.

        Defaults to `jupyterhub/singleuser:latest`

        Name of the container + a tag, same as would be used with
        a `docker pull` command. If tag is set to `latest`, kubernetes will
        check the registry each time a new user is spawned to see if there
        is a newer image available. If available, new image will be pulled.
        Note that this could cause long delays when spawning, especially
        if the image is large. If you do not specify a tag, whatever version
        of the image is first pulled on the node will be used, thus possibly
        leading to inconsistent images on different nodes. For all these
        reasons, it is recommended to specify a specific immutable tag
        for the imagespec.

        If your image is very large, you might need to increase the timeout
        for starting the single user container from the default. You can
        set this with:

        ```
        c.KubeSpawner.start_timeout = 60 * 5  # Upto 5 minutes
        ```
        """
    )

    singleuser_image_pull_policy = Unicode(
        'IfNotPresent',
        config=True,
        help="""
        The image pull policy of the docker container specified in
        singleuser_image_spec.

        Defaults to `IfNotPresent` which causes the Kubelet to NOT pull the image
        specified in singleuser_image_spec if it already exists, except if the tag
        is :latest. For more information on image pull policy, refer to
        http://kubernetes.io/docs/user-guide/images/

        This configuration is primarily used in development if you are
        actively changing the singleuser_image_spec and would like to pull the image
        whenever a user container is spawned.
        """
    )

    singleuser_image_pull_secrets = Unicode(
        None,
        allow_none=True,
        config=True,
        help="""
        The kubernetes secret to use for pulling images from private repository.

        Set this to the name of a Kubernetes secret containing the docker configuration
        required to pull the image specified in singleuser_image_spec.

        https://kubernetes.io/docs/user-guide/images/#specifying-imagepullsecrets-on-a-pod
        has more information on when and why this might need to be set, and what it
        should be set to.
        """
    )

    singleuser_node_selector = Dict(
        {},
        config=True,
        help="""
        The dictionary Selector labels used to match the Nodes where Pods will be launched.

        Default is None and means it will be launched in any available Node.

        For example to match the Nodes that have a label of `disktype: ssd` use:
            `{"disktype": "ssd"}`
        """
    )

    singleuser_uid = Union([
            Integer(),
            Callable()
        ],
        allow_none=True,
        config=True,
        help="""
        The UID to run the single-user server containers as.

        This UID should ideally map to a user that already exists in the container
        image being used. Running as root is discouraged.

        Instead of an integer, this could also be a callable that takes as one
        parameter the current spawner instance and returns an integer. The callable
        will be called asynchronously if it returns a future. Note that
        the interface of the spawner class is not deemed stable across versions,
        so using this functionality might cause your JupyterHub or kubespawner
        upgrades to break.

        If set to `None`, the user specified with the `USER` directive in the
        container metadata is used.
        """
    )

    singleuser_fs_gid = Union([
            Integer(),
            Callable()
        ],
        allow_none=True,
        config=True,
        help="""
        The GID of the group that should own any volumes that are created & mounted.

        A special supplemental group that applies primarily to the volumes mounted
        in the single-user server. In volumes from supported providers, the following
        things happen:

          1. The owning GID will be the this GID
          2. The setgid bit is set (new files created in the volume will be owned by
             this GID)
          3. The permission bits are OR’d with rw-rw

        The single-user server will also be run with this gid as part of its supplemental
        groups.

        Instead of an integer, this could also be a callable that takes as one
        parameter the current spawner instance and returns an integer. The callable will
        be called asynchronously if it returns a future, rather than an int. Note that
        the interface of the spawner class is not deemed stable across versions,
        so using this functionality might cause your JupyterHub or kubespawner
        upgrades to break.

        You'll *have* to set this if you are using auto-provisioned volumes with most
        cloud providers. See [fsGroup](http://kubernetes.io/docs/api-reference/v1/definitions/#_v1_podsecuritycontext)
        for more details.
        """
    )

    volumes = List(
        [],
        config=True,
        help="""
        List of Kubernetes Volume specifications that will be mounted in the user pod.

        This list will be directly added under `volumes` in the kubernetes pod spec,
        so you should use the same structure. Each item in the list must have the
        following two keys:
          - name
            Name that'll be later used in the `volume_mounts` config to mount this
            volume at a specific path.
          - <name-of-a-supported-volume-type> (such as `hostPath`, `persistentVolumeClaim`,
            etc)
            The key name determines the type of volume to mount, and the value should
            be an object specifying the various options available for that kind of
            volume.

        See http://kubernetes.io/docs/user-guide/volumes/ for more information on the
        various kinds of volumes available and their options. Your kubernetes cluster
        must already be configured to support the volume types you want to use.

        {username} and {userid} are expanded to the escaped, dns-label safe
        username & integer user id respectively, wherever they are used.
        """
    )

    volume_mounts = List(
        [],
        config=True,
        help="""
        List of paths on which to mount volumes in the user notebook's pod.

        This list will be added to the values of the `volumeMounts` key under the user's
        container in the kubernetes pod spec, so you should use the same structure as that.
        Each item in the list should be a dictionary with at least these two keys:
          - mountPath
            The path on the container in which we want to mount the volume.
          - name
            The name of the volume we want to mount, as specified in the `volumes`
            config.

        See http://kubernetes.io/docs/user-guide/volumes/ for more information on how
        the volumeMount item works.

        {username} and {userid} are expanded to the escaped, dns-label safe
        username & integer user id respectively, wherever they are used.
        """
    )

    user_storage_capacity = Unicode(
        None,
        config=True,
        allow_none=True,
        help="""
        The ammount of storage space to request from the volume that the pvc will
        mount to. This ammount will be the ammount of storage space the user has
        to work with on their notebook. If left blank, the kubespawner will not
        create a pvc for the pod.

        This will be added to the `resources: requests: storage:` in the k8s pod spec.

        See http://kubernetes.io/docs/user-guide/persistent-volumes/#persistentvolumeclaims
        for more information on how storage works.

        Quantities can be represented externally as unadorned integers, or as fixed-point
        integers with one of these SI suffices (E, P, T, G, M, K, m) or their power-of-two
        equivalents (Ei, Pi, Ti, Gi, Mi, Ki). For example, the following represent roughly
        'the same value: 128974848, "129e6", "129M" , "123Mi".
        (https://github.com/kubernetes/kubernetes/blob/master/docs/design/resources.md)
        """
    )

    user_storage_extra_labels = Dict(
        {},
        config=True,
        help="""
        Extra kubernetes labels to set on the user PVCs.

        The keys and values specified here would be set as labels on the PVCs
        created by kubespawner for the user. Note that these are only set
        when the PVC is created, not later when they are updated.

        See https://kubernetes.io/docs/concepts/overview/working-with-objects/labels/ for more
        info on what labels are and why you might want to use them!

        {username} and {userid} are expanded to the escaped, dns-label safe
        username & integer user id respectively, wherever they are used.
        """
    )

    user_storage_class = Unicode(
        None,
        config=True,
        allow_none=True,
        help="""
        The storage class that the pvc will use. If left blank, the kubespawner will not
        create a pvc for the pod.

        This will be added to the `annotations: volume.beta.kubernetes.io/storage-class:`
        in the pvc metadata.

        This will determine what type of volume the pvc will request to use. If one exists
        that matches the criteria of the StorageClass, the pvc will mount to that. Otherwise,
        b/c it has a storage class, k8s will dynamicallly spawn a pv for the pvc to bind to
        and a machine in the cluster for the pv to bind to.

        See http://kubernetes.io/docs/user-guide/persistent-volumes/#storageclasses for
        more information on how StorageClasses work.
        """
    )

    user_storage_access_modes = List(
        ["ReadWriteOnce"],
        config=True,
        help="""
        List of access modes the user has for the pvc.

        The access modes are:
            The access modes are:
                ReadWriteOnce – the volume can be mounted as read-write by a single node
                ReadOnlyMany – the volume can be mounted read-only by many nodes
                ReadWriteMany – the volume can be mounted as read-write by many nodes

        See http://kubernetes.io/docs/user-guide/persistent-volumes/#access-modes for
        more information on how access modes work.
        """
    )

    singleuser_lifecycle_hooks = Dict(
        {},
        config=True,
        help="""
        Kubernetes lifecycle hooks to set on the spawned single-user pods.

        The keys is name of hooks and there are only two hooks, postStart and preStop.
        The values are handler of hook which executes by Kubernetes management system when hook is called.

        Below are a sample copied from Kubernetes doc 
        https://kubernetes.io/docs/tasks/configure-pod-container/attach-handler-lifecycle-event/

        lifecycle:
          postStart:
            exec:
              command: ["/bin/sh", "-c", "echo Hello from the postStart handler > /usr/share/message"]
          preStop:
            exec:
              command: ["/usr/sbin/nginx","-s","quit"]

        See https://kubernetes.io/docs/concepts/containers/container-lifecycle-hooks/ for more
        info on what lifecycle hooks are and why you might want to use them!
        """
    )

    singleuser_init_containers = List(
        None,
        config=True,
        help="""
        List of initialization containers belonging to the pod.

        This list will be directly added under `initContainers` in the kubernetes pod spec,
        so you should use the same structure. Each item in the list is container configuration
        which follows spec at https://kubernetes.io/docs/api-reference/v1.6/#container-v1-core.
         
        One usage is disabling access to metadata service from single-user notebook server with configuration below:
        initContainers:
        - name: init-iptables
          image: <image with iptables installed>
          command: ["iptables", "-A", "OUTPUT", "-p", "tcp", "--dport", "80", "-d", "169.254.169.254", "-j", "DROP"]
          securityContext:
            capabilities:
              add:
              - NET_ADMIN         

        See https://kubernetes.io/docs/concepts/workloads/pods/init-containers/ for more
        info on what init containers are and why you might want to use them!
        
        To user this feature, Kubernetes version must greater than 1.6.
        """
    )

    def _expand_user_properties(self, template):
        # Make sure username matches the restrictions for DNS labels
        safe_chars = set(string.ascii_lowercase + string.digits)
        legacy_escaped_username = ''.join([s if s in safe_chars else '-' for s in self.user.name.lower()])
        safe_username = escapism.escape(self.user.name, safe=safe_chars, escape_char='-').lower()
        return template.format(
            userid=self.user.id,
            username=safe_username,
            legacy_escape_username=legacy_escaped_username
        )

    def _expand_all(self, src):
        if isinstance(src, list):
            return [self._expand_all(i) for i in src]
        elif isinstance(src, dict):
            return {k: self._expand_all(v) for k, v in src.items()}
        elif isinstance(src, str):
            return self._expand_user_properties(src)
        else:
            return src

    @gen.coroutine
    def get_pod_manifest(self):
        """
        Make a pod manifest that will spawn current user's notebook pod.
        """
        if callable(self.singleuser_uid):
            singleuser_uid = yield gen.maybe_future(self.singleuser_uid(self))
        else:
            singleuser_uid = self.singleuser_uid

        if callable(self.singleuser_fs_gid):
            singleuser_fs_gid = yield gen.maybe_future(self.singleuser_fs_gid(self))
        else:
            singleuser_fs_gid = self.singleuser_fs_gid

        if self.cmd:
            real_cmd = self.cmd + self.get_args()
        else:
            real_cmd = None

        # Add a hack to ensure that no service accounts are mounted in spawned pods
        # This makes sure that we don"t accidentally give access to the whole
        # kubernetes API to the users in the spawned pods.
        # See https://github.com/kubernetes/kubernetes/issues/16779#issuecomment-157460294
        hack_volume = V1Volume()
        hack_volume.name =  "no-api-access-please"
        hack_volume.empty_dir = {}

        hack_volume_mount = V1VolumeMount()
        hack_volume_mount.name = "no-api-access-please"
        hack_volume_mount.mount_path = "/var/run/secrets/kubernetes.io/serviceaccount"
        hack_volume_mount.read_only = True

        # Default set of labels, picked up from
        # https://github.com/kubernetes/helm/blob/master/docs/chart_best_practices/labels.md
        labels = {
            'heritage': 'jupyterhub',
            'component': 'singleuser-server',
            'app': 'jupyterhub',
            'hub.jupyter.org/username': escapism.escape(self.user.name)
        }

        labels.update(self._expand_all(self.singleuser_extra_labels))

        return make_pod(
            name=self.pod_name,
            image_spec=self.singleuser_image_spec,
            image_pull_policy=self.singleuser_image_pull_policy,
            image_pull_secret=self.singleuser_image_pull_secrets,
            port=self.port,
            cmd=real_cmd,
            node_selector=self.singleuser_node_selector,
            run_as_uid=singleuser_uid,
            fs_gid=singleuser_fs_gid,
            env=self.get_env(),
            volumes=self._expand_all(self.volumes) + [hack_volume],
            volume_mounts=self._expand_all(self.volume_mounts) + [hack_volume_mount],
            working_dir=self.singleuser_working_dir,
            labels=labels,
            cpu_limit=self.cpu_limit,
            cpu_guarantee=self.cpu_guarantee,
            mem_limit=self.mem_limit,
            mem_guarantee=self.mem_guarantee,
            lifecycle_hooks=self.singleuser_lifecycle_hooks,
            init_containers=self.singleuser_init_containers,
        )

    def get_pvc_manifest(self):
        """
        Make a pvc manifest that will spawn current user's pvc.
        """
        # Default set of labels, picked up from
        # https://github.com/kubernetes/helm/blob/master/docs/chart_best_practices/labels.md
        labels = {
            'heritage': 'jupyterhub',
            'app': 'jupyterhub',
            'hub.jupyter.org/username': escapism.escape(self.user.name)
        }

        labels.update(self._expand_all(self.user_storage_extra_labels))
        return make_pvc(
            name=self.pvc_name,
            storage_class=self.user_storage_class,
            access_modes=self.user_storage_access_modes,
            storage=self.user_storage_capacity,
            labels=labels
        )

    @gen.coroutine
    def get_pod_info(self, pod_name):
        """
        Fetch info about a specific pod with the given pod name in current namespace

        Return `None` if pod with given name does not exist in current namespace
        """
        try:
            pod = yield self.asynchronize(
                self.api.read_namespaced_pod,
                name=self.pod_name,
                namespace=self.namespace,
            )
        except ApiException as e:
            if e.status == 404:
                return None
            raise
        return pod

    def is_pod_running(self, pod):
        """
        Check if the given pod is running

        pod must be a dictionary representing a Pod kubernetes API object.
        """
        # FIXME: Validate if this is really the best way
        is_running = pod.status.phase == 'Running' and (pod.status.pod_ip is not None)
        return is_running

    def get_state(self):
        """
        Save state required to reinstate this user's pod from scratch

        We save the pod_name, even though we could easily compute it,
        because JupyterHub requires you save *some* state! Otherwise
        it assumes your server is dead. This works around that.

        It's also useful for cases when the pod_template changes between
        restarts - this keeps the old pods around.
        """
        state = super().get_state()
        state['pod_name'] = self.pod_name
        return state

    def load_state(self, state):
        """
        Load state from storage required to reinstate this user's pod

        Since this runs after __init__, this will override the generated pod_name
        if there's one we have saved in state. These are the same in most cases,
        but if the pod_template has changed in between restarts, it will no longer
        be the case. This allows us to continue serving from the old pods with
        the old names.
        """
        if 'pod_name' in state:
            self.pod_name = state['pod_name']

    @gen.coroutine
    def poll(self):
        """
        Check if the pod is still running.

        Returns None if it is, and 1 if it isn't. These are the return values
        JupyterHub expects.
        """
        data = yield self.get_pod_info(self.pod_name)
        if data is not None and self.is_pod_running(data):
            return None
        return 1

    @run_on_executor
    def asynchronize(self, method, *args, **kwargs):
        return method(*args, **kwargs)

    @gen.coroutine
    def start(self):
        if self.user_storage_pvc_ensure:
            pvc = self.get_pvc_manifest()
            try:
                yield self.asynchronize(
                    self.api.create_namespaced_persistent_volume_claim,
                    namespace=self.namespace,
                    body=pvc
                )
            except ApiException as e:
                if e.status == 409:
                    self.log.info("PVC " + self.pvc_name + " already exists, so did not create new pvc.")
                else:
                    raise

        # If we run into a 409 Conflict error, it means a pod with the
        # same name already exists. We stop it, wait for it to stop, and
        # try again. We try 4 times, and if it still fails we give up.
        # FIXME: Have better / cleaner retry logic!
        retry_times = 4
        pod = yield self.get_pod_manifest()
        for i in range(retry_times):
            try:
                yield self.asynchronize(
                    self.api.create_namespaced_pod,
                    self.namespace,
                    pod
                )
                break
            except ApiException as e:
                if e.status != 409:
                    # We only want to handle 409 conflict errors
                    self.log.exception("Failed for %s", json.dumps(pod_manifest))
                    raise
                self.log.info('Found existing pod %s, attempting to kill', self.pod_name)
                yield self.stop(True)

                self.log.info('Killed pod %s, will try starting singleuser pod again', self.pod_name)
        else:
            raise Exception(
                'Can not create user pod %s already exists & could not be deleted' % self.pod_name)

        while True:
            pod = yield self.get_pod_info(self.pod_name)
            if pod is not None and self.is_pod_running(pod):
                break
            yield gen.sleep(1)
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
        yield self.asynchronize(
            self.api.delete_namespaced_pod,
            name=self.pod_name,
            namespace=self.namespace,
            body=delete_options,
            grace_period_seconds=grace_seconds
        )
        while True:
            data = yield self.get_pod_info(self.pod_name)
            if data is None:
                break
            yield gen.sleep(1)

    def _env_keep_default(self):
        return []

    def get_args(self):
        args = super(KubeSpawner, self).get_args()

        # HACK: we wanna replace --hub-api-url=self.hub.api_url with
        # self.accessible_hub_api_url. This is required in situations where
        # the IP the hub is listening on (such as 0.0.0.0) is not the IP where
        # it can be reached by the pods (such as the service IP used for the hub!)
        # FIXME: Make this better?
        to_replace = '--hub-api-url="%s"' % (self.hub.api_url)
        for i in range(len(args)):
            if args[i] == to_replace:
                args[i] = '--hub-api-url="%s"' % (self.accessible_hub_api_url)
                break
        return args

    def get_env(self):
        # HACK: This is deprecated, and should be removed soon.
        # We set these to be compatible with DockerSpawner and earlie KubeSpawner
        env = super(KubeSpawner, self).get_env()
        env.update({
            'JPY_USER': self.user.name,
            'JPY_COOKIE_NAME': self.user.server.cookie_name,
            'JPY_BASE_URL': self.user.server.base_url,
            'JPY_HUB_PREFIX': self.hub.server.base_url,
            'JPY_HUB_API_URL': self.accessible_hub_api_url
        })
        return env
