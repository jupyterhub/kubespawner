"""
JupyterHub Spawner to spawn user notebooks on a Kubernetes cluster.

This module exports `KubeSpawner` class, which is the actual spawner
implementation that should be used by JupyterHub.
"""

from functools import partial  # noqa
import os
import sys
import string
import multiprocessing
from concurrent.futures import ThreadPoolExecutor
import warnings

from tornado import gen
from tornado.ioloop import IOLoop
from tornado.concurrent import run_on_executor
from traitlets import (
    Bool,
    Dict,
    Integer,
    List,
    Unicode,
    Union,
    default,
    observe,
    validate,
)
from jupyterhub.spawner import Spawner
from jupyterhub.utils import exponential_backoff
from jupyterhub.traitlets import Command
from kubernetes.client.rest import ApiException
from kubernetes import client
import escapism
from jinja2 import Environment, BaseLoader

from .clients import shared_client
from kubespawner.traitlets import Callable
from kubespawner.objects import make_pod, make_pvc
from kubespawner.reflector import NamespacedResourceReflector
from asyncio import sleep
from async_generator import async_generator, yield_


class PodReflector(NamespacedResourceReflector):
    kind = 'pods'
    # FUTURE: These labels are the selection labels for the PodReflector. We
    # might want to support multiple deployments in the same namespace, so we
    # would need to select based on additional labels such as `app` and
    # `release`.
    labels = {
        'component': 'singleuser-server',
    }

    list_method_name = 'list_namespaced_pod'

    @property
    def pods(self):
        return self.resources


class EventReflector(NamespacedResourceReflector):
    kind = 'events'

    list_method_name = 'list_namespaced_event'

    @property
    def events(self):
        return sorted(
            self.resources.values(),
            key=lambda x: x.last_timestamp,
        )


class MockObject(object):
    pass

class KubeSpawner(Spawner):
    """
    Implement a JupyterHub spawner to spawn pods in a Kubernetes Cluster.
    """

    # We want to have one threadpool executor that is shared across all spawner objects
    # This is initialized by the first spawner that is created
    executor = None

    # We also want only one reflector per type per application
    reflectors = {}

    @property
    def pod_reflector(self):
        """alias to reflectors['pods']"""
        return self.reflectors['pods']

    @property
    def event_reflector(self):
        """alias to reflectors['events']"""
        if self.events_enabled:
            return self.reflectors['events']

    def __init__(self, *args, **kwargs):
        _mock = kwargs.pop('_mock', False)
        super().__init__(*args, **kwargs)

        if _mock:
            # runs during test execution only
            user = MockObject()
            user.name = 'mock_name'
            user.id = 'mock_id'
            user.url = 'mock_url'
            self.user = user

            hub = MockObject()
            hub.public_host = 'mock_public_host'
            hub.url = 'mock_url'
            hub.base_url = 'mock_base_url'
            hub.api_url = 'mock_api_url'
            self.hub = hub
        else:
            # runs during normal execution only

            # By now, all the traitlets have been set, so we can use them to compute
            # other attributes
            if self.__class__.executor is None:
                self.__class__.executor = ThreadPoolExecutor(
                    max_workers=self.k8s_api_threadpool_workers
                )

            # This will start watching in __init__, so it'll start the first
            # time any spawner object is created. Not ideal but works!
            self._start_watching_pods()
            if self.events_enabled:
                self._start_watching_events()

            self.api = shared_client('CoreV1Api')

        # runs during both test and normal execution
        self.pod_name = self._expand_user_properties(self.pod_name_template)
        self.pvc_name = self._expand_user_properties(self.pvc_name_template)
        if self.working_dir:
            self.working_dir = self._expand_user_properties(self.working_dir)
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

        Defaults to `5 * cpu_cores`, which is the default for `ThreadPoolExecutor`.
        """
    )

    events_enabled = Bool(
        True,
        config=True,
        help="""
        Enable event-watching for progress-reports to the user spawn page.

        Disable if these events are not desirable
        or to save some performance cost.
        """
    )

    namespace = Unicode(
        config=True,
        help="""
        Kubernetes namespace to spawn user pods in.

        If running inside a kubernetes cluster with service accounts enabled,
        defaults to the current namespace. If not, defaults to `default`
        """
    )

    @default('namespace')
    def _namespace_default(self):
        """
        Set namespace default to current namespace if running in a k8s cluster

        If not in a k8s cluster with service accounts enabled, default to
        `default`
        """
        ns_path = '/var/run/secrets/kubernetes.io/serviceaccount/namespace'
        if os.path.exists(ns_path):
            with open(ns_path) as f:
                return f.read().strip()
        return 'default'

    ip = Unicode(
        '0.0.0.0',
        config=True,
        help="""
        The IP address (or hostname) the single-user server should listen on.

        We override this from the parent so we can set a more sane default for
        the Kubernetes setup.
        """
    )

    cmd = Command(
        None,
        allow_none=True,
        minlen=0,
        config=True,
        help="""
        The command used for starting the single-user server.

        Provide either a string or a list containing the path to the startup script command. Extra arguments,
        other than this path, should be provided via `args`.

        This is usually set if you want to start the single-user server in a different python
        environment (with virtualenv/conda) than JupyterHub itself.

        Some spawners allow shell-style expansion here, allowing you to use environment variables.
        Most, including the default, do not. Consult the documentation for your spawner to verify!

        If set to `None`, Kubernetes will start the `CMD` that is specified in the Docker image being started.
        """
    )

    # FIXME: Don't override 'default_value' ("") or 'allow_none' (False) (Breaking change)
    working_dir = Unicode(
        None,
        allow_none=True,
        config=True,
        help="""
        The working directory where the Notebook server will be started inside the container.
        Defaults to `None` so the working directory will be the one defined in the Dockerfile.

        `{username}` is expanded to the escaped, dns-label safe username.
        """
    )

    # FIXME: Don't override 'default_value' ("") or 'allow_none' (False) (Breaking change)
    service_account = Unicode(
        None,
        allow_none=True,
        config=True,
        help="""
        The service account to be mounted in the spawned user pod.

        When set to `None` (the default), no service account is mounted, and the default service account
        is explicitly disabled.

        This `serviceaccount` must already exist in the namespace the user pod is being spawned in.

        WARNING: Be careful with this configuration! Make sure the service account being mounted
        has the minimal permissions needed, and nothing more. When misconfigured, this can easily
        give arbitrary users root over your entire cluster.
        """
    )

    pod_name_template = Unicode(
        'jupyter-{username}{servername}',
        config=True,
        help="""
        Template to use to form the name of user's pods.

        `{username}` is expanded to the escaped, dns-label safe username.

        This must be unique within the namespace the pods are being spawned
        in, so if you are running multiple jupyterhubs spawning in the
        same namespace, consider setting this to be something more unique.
        """
    )

    storage_pvc_ensure = Bool(
        False,
        config=True,
        help="""
        Ensure that a PVC exists for each user before spawning.

        Set to true to create a PVC named with `pvc_name_template` if it does
        not exist for the user when their pod is spawning.
        """
    )

    pvc_name_template = Unicode(
        'claim-{username}{servername}',
        config=True,
        help="""
        Template to use to form the name of user's pvc.

        `{username}` is expanded to the escaped, dns-label safe username.

        This must be unique within the namespace the pvc are being spawned
        in, so if you are running multiple jupyterhubs spawning in the
        same namespace, consider setting this to be something more unique.
        """
    )

    # FIXME: Don't override 'default_value' ("") or 'allow_none' (False) (Breaking change)
    hub_connect_ip = Unicode(
        allow_none=True,
        config=True,
        help="""DEPRECATED. Use c.JupyterHub.hub_connect_ip"""
    )

    hub_connect_port = Integer(
        config=True,
        help="""DEPRECATED. Use c.JupyterHub.hub_connect_url"""
    )

    @observe('hub_connect_ip', 'hub_connect_port')
    def _deprecated_changed(self, change):
        warnings.warn("""
            KubeSpawner.{0} is deprecated with JupyterHub >= 0.8.
            Use JupyterHub.{0}
            """.format(change.name),
            DeprecationWarning)
        setattr(self.hub, change.name, change.value)

    common_labels = Dict(
        {
            'app': 'jupyterhub',
            'heritage': 'jupyterhub',
        },
        config=True,
        help="""
        Kubernetes labels that both spawned singleuser server pods and created
        user PVCs will get.

        Note that these are only set when the Pods and PVCs are created, not
        later when this setting is updated.
        """
    )

    extra_labels = Dict(
        config=True,
        help="""
        Extra kubernetes labels to set on the spawned single-user pods.

        The keys and values specified here would be set as labels on the spawned single-user
        kubernetes pods. The keys and values must both be strings that match the kubernetes
        label key / value constraints.

        See `the Kubernetes documentation <https://kubernetes.io/docs/concepts/overview/working-with-objects/labels/>`__
        for more info on what labels are and why you might want to use them!

        `{username}` is expanded to the escaped, dns-label safe username.
        """
    )

    extra_annotations = Dict(
        config=True,
        help="""
        Extra Kubernetes annotations to set on the spawned single-user pods.

        The keys and values specified here are added as annotations on the spawned single-user
        kubernetes pods. The keys and values must both be strings.

        See `the Kubernetes documentation <https://kubernetes.io/docs/concepts/overview/working-with-objects/annotations/>`__
        for more info on what annotations are and why you might want to use them!

        `{username}` is expanded to the escaped, dns-label safe username.
        """
    )

    image = Unicode(
        'jupyterhub/singleuser:latest',
        config=True,
        help="""
        Docker image to use for spawning user's containers.

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
        for the image.

        If your image is very large, you might need to increase the timeout
        for starting the single user container from the default. You can
        set this with::

           c.KubeSpawner.start_timeout = 60 * 5  # Up to 5 minutes

        """
    )

    image_pull_policy = Unicode(
        'IfNotPresent',
        config=True,
        help="""
        The image pull policy of the docker container specified in
        `image`.

        Defaults to `IfNotPresent` which causes the Kubelet to NOT pull the image
        specified in KubeSpawner.image if it already exists, except if the tag
        is `:latest`. For more information on image pull policy,
        refer to `the Kubernetes documentation <https://kubernetes.io/docs/concepts/containers/images/>`__.


        This configuration is primarily used in development if you are
        actively changing the `image_spec` and would like to pull the image
        whenever a user container is spawned.
        """
    )

    # FIXME: Don't override 'default_value' ("") or 'allow_none' (False) (Breaking change)
    image_pull_secrets = Unicode(
        None,
        allow_none=True,
        config=True,
        help="""
        The kubernetes secret to use for pulling images from private repository.

        Set this to the name of a Kubernetes secret containing the docker configuration
        required to pull the image.

        See `the Kubernetes documentation <https://kubernetes.io/docs/concepts/containers/images/#specifying-imagepullsecrets-on-a-pod>`__
        for more information on when and why this might need to be set, and what
        it should be set to.
        """
    )

    node_selector = Dict(
        config=True,
        help="""
        The dictionary Selector labels used to match the Nodes where Pods will be launched.

        Default is None and means it will be launched in any available Node.

        For example to match the Nodes that have a label of `disktype: ssd` use::

           c.KubeSpawner.node_selector = {'disktype': 'ssd'}
        """
    )

    uid = Union(
        trait_types=[
            Integer(),
            Callable(),
        ],
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

    gid = Union(
        trait_types=[
            Integer(),
            Callable(),
        ],
        config=True,
        help="""
        The GID to run the single-user server containers as.

        This GID should ideally map to a group that already exists in the container
        image being used. Running as root is discouraged.

        Instead of an integer, this could also be a callable that takes as one
        parameter the current spawner instance and returns an integer. The callable
        will be called asynchronously if it returns a future. Note that
        the interface of the spawner class is not deemed stable across versions,
        so using this functionality might cause your JupyterHub or kubespawner
        upgrades to break.

        If set to `None`, the group of the user specified with the `USER` directive
        in the container metadata is used.
        """
    )

    fs_gid = Union(
        trait_types=[
            Integer(),
            Callable(),
        ],
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
        cloud providers. See `fsGroup <https://kubernetes.io/docs/reference/generated/kubernetes-api/v1.11/#podsecuritycontext-v1-core>`_
        for more details.
        """
    )

    supplemental_gids = Union(
        trait_types=[
            List(),
            Callable(),
        ],
        config=True,
        help="""
        A list of GIDs that should be set as additional supplemental groups to the
        user that the container runs as.

        Instead of a list of integers, this could also be a callable that takes as one
        parameter the current spawner instance and returns a list of integers. The
        callable will be called asynchronously if it returns a future, rather than
        a list. Note that the interface of the spawner class is not deemed stable
        across versions, so using this functionality might cause your JupyterHub
        or kubespawner upgrades to break.

        You may have to set this if you are deploying to an environment with RBAC/SCC
        enforced and pods run with a 'restricted' SCC which results in the image being
        run as an assigned user ID. The supplemental group IDs would need to include
        the corresponding group ID of the user ID the image normally would run as. The
        image must setup all directories/files any application needs access to, as group
        writable.
        """
    )

    privileged = Bool(
        False,
        config=True,
        help="""
        Whether to run the pod with a privileged security context.
        """
    )

    modify_pod_hook = Callable(
        None,
        allow_none=True,
        config=True,
        help="""
        Callable to augment the Pod object before launching.

        Expects a callable that takes two parameters:

           1. The spawner object that is doing the spawning
           2. The Pod object that is to be launched

        You should modify the Pod object and return it.

        This can be a coroutine if necessary. When set to none, no augmenting is done.

        This is very useful if you want to modify the pod being launched dynamically.
        Note that the spawner object can change between versions of KubeSpawner and JupyterHub,
        so be careful relying on this!
        """
    )

    volumes = List(
        config=True,
        help="""
        List of Kubernetes Volume specifications that will be mounted in the user pod.

        This list will be directly added under `volumes` in the kubernetes pod spec,
        so you should use the same structure. Each item in the list must have the
        following two keys:

          - `name`
            Name that'll be later used in the `volume_mounts` config to mount this
            volume at a specific path.
          - `<name-of-a-supported-volume-type>` (such as `hostPath`, `persistentVolumeClaim`,
            etc)
            The key name determines the type of volume to mount, and the value should
            be an object specifying the various options available for that kind of
            volume.

        See `the Kubernetes documentation <https://kubernetes.io/docs/concepts/storage/volumes>`__
        for more information on the various kinds of volumes available and their options.
        Your kubernetes cluster must already be configured to support the volume types you want to use.

        `{username}` is expanded to the escaped, dns-label safe username.
        """
    )

    volume_mounts = List(
        config=True,
        help="""
        List of paths on which to mount volumes in the user notebook's pod.

        This list will be added to the values of the `volumeMounts` key under the user's
        container in the kubernetes pod spec, so you should use the same structure as that.
        Each item in the list should be a dictionary with at least these two keys:

           - `mountPath` The path on the container in which we want to mount the volume.
           - `name` The name of the volume we want to mount, as specified in the `volumes` config.

        See `the Kubernetes documentation <https://kubernetes.io/docs/concepts/storage/volumes>`__
        for more information on how the `volumeMount` item works.

        `{username}` is expanded to the escaped, dns-label safe username.
        """
    )

    # FIXME: Don't override 'default_value' ("") or 'allow_none' (False) (Breaking change)
    storage_capacity = Unicode(
        None,
        config=True,
        allow_none=True,
        help="""
        The ammount of storage space to request from the volume that the pvc will
        mount to. This ammount will be the ammount of storage space the user has
        to work with on their notebook. If left blank, the kubespawner will not
        create a pvc for the pod.

        This will be added to the `resources: requests: storage:` in the k8s pod spec.

        See `the Kubernetes documentation <https://kubernetes.io/docs/concepts/storage/persistent-volumes/#persistentvolumeclaims>`__
        for more information on how storage works.

        Quantities can be represented externally as unadorned integers, or as fixed-point
        integers with one of these SI suffices (`E, P, T, G, M, K, m`) or their power-of-two
        equivalents (`Ei, Pi, Ti, Gi, Mi, Ki`). For example, the following represent roughly
        the same value: `128974848`, `129e6`, `129M`, `123Mi`.
        """
    )

    storage_extra_labels = Dict(
        config=True,
        help="""
        Extra kubernetes labels to set on the user PVCs.

        The keys and values specified here would be set as labels on the PVCs
        created by kubespawner for the user. Note that these are only set
        when the PVC is created, not later when this setting is updated.

        See `the Kubernetes documentation <https://kubernetes.io/docs/concepts/overview/working-with-objects/labels/>`__
        for more info on what labels are and why you might want to use them!

        `{username}` is expanded to the escaped, dns-label safe username.
        """
    )

    # FIXME: Don't override 'default_value' ("") or 'allow_none' (False) (Breaking change)
    storage_class = Unicode(
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
        b/c it has a storage class, k8s will dynamically spawn a pv for the pvc to bind to
        and a machine in the cluster for the pv to bind to.

        See `the Kubernetes documentation <https://kubernetes.io/docs/concepts/storage/storage-classes/>`__
        for more information on how StorageClasses work.

        """
    )

    storage_access_modes = List(
        ["ReadWriteOnce"],
        config=True,
        help="""
        List of access modes the user has for the pvc.

        The access modes are:

            - `ReadWriteOnce` – the volume can be mounted as read-write by a single node
            - `ReadOnlyMany` – the volume can be mounted read-only by many nodes
            - `ReadWriteMany` – the volume can be mounted as read-write by many nodes

        See `the Kubernetes documentation <https://kubernetes.io/docs/concepts/storage/persistent-volumes/#access-modes>`__
        for more information on how access modes work.
        """
    )

    lifecycle_hooks = Dict(
        config=True,
        help="""
        Kubernetes lifecycle hooks to set on the spawned single-user pods.

        The keys is name of hooks and there are only two hooks, postStart and preStop.
        The values are handler of hook which executes by Kubernetes management system when hook is called.

        Below is an sample copied from
        `the Kubernetes documentation <https://kubernetes.io/docs/tasks/configure-pod-container/attach-handler-lifecycle-event/>`__::


            c.KubeSpawner.lifecycle_hooks = {
                "postStart": {
                    "exec": {
                        "command": ["/bin/sh", "-c", "echo Hello from the postStart handler > /usr/share/message"]
                    }
                },
                "preStop": {
                    "exec": {
                        "command": ["/usr/sbin/nginx", "-s", "quit"]
                    }
                }
            }

        See `the Kubernetes documentation <https://kubernetes.io/docs/concepts/containers/container-lifecycle-hooks/>`__
        for more info on what lifecycle hooks are and why you might want to use them!
        """
    )

    init_containers = List(
        config=True,
        help="""
        List of initialization containers belonging to the pod.

        This list will be directly added under `initContainers` in the kubernetes pod spec,
        so you should use the same structure. Each item in the dict must a field
        of the `V1Container specification <https://kubernetes.io/docs/reference/generated/kubernetes-api/v1.11/#container-v1-core>`_.

        One usage is disabling access to metadata service from single-user
        notebook server with configuration below::

            c.KubeSpawner.init_containers = [{
                "name": "init-iptables",
                "image": "<image with iptables installed>",
                "command": ["iptables", "-A", "OUTPUT", "-p", "tcp", "--dport", "80", "-d", "169.254.169.254", "-j", "DROP"],
                "securityContext": {
                    "capabilities": {
                        "add": ["NET_ADMIN"]
                    }
                }
            }]


        See `the Kubernetes documentation <https://kubernetes.io/docs/concepts/workloads/pods/init-containers/>`__
        for more info on what init containers are and why you might want to use them!

        To user this feature, Kubernetes version must greater than 1.6.
        """
    )

    extra_container_config = Dict(
        config=True,
        help="""
        Extra configuration (e.g. ``envFrom``) for notebook container which is not covered by other attributes.

        This dict will be directly merge into `container` of notebook server,
        so you should use the same structure. Each item in the dict must a field
        of the `V1Container specification <https://kubernetes.io/docs/reference/generated/kubernetes-api/v1.11/#container-v1-core>`_.

        One usage is set ``envFrom`` on notebook container with configuration below::

            c.KubeSpawner.extra_container_config = {
                "envFrom": [{
                    "configMapRef": {
                        "name": "special-config"
                    }
                }]
            }

        The key could be either a camelCase word (used by Kubernetes yaml, e.g.
        ``envFrom``) or a snake_case word (used by Kubernetes Python client,
        e.g. ``env_from``).
        """
    )

    extra_pod_config = Dict(
        config=True,
        help="""
        Extra configuration for the pod which is not covered by other attributes.

        This dict will be directly merge into pod,so you should use the same structure.
        Each item in the dict is field of pod configuration
        which follows spec at https://kubernetes.io/docs/reference/generated/kubernetes-api/v1.11/#podspec-v1-core.

        One usage is set restartPolicy and dnsPolicy with configuration below::

            c.KubeSpawner.extra_pod_config = {
                "restartPolicy": "OnFailure",
                "dns_policy": "ClusterFirstWithHostNet"
            }

        The `key` could be either a camelCase word (used by Kubernetes yaml,
        e.g. `restartPolicy`) or a snake_case word (used by Kubernetes Python
        client, e.g. `dns_policy`).
        """
    )

    extra_containers = List(
        config=True,
        help="""
        List of containers belonging to the pod which besides to the container generated for notebook server.

        This list will be directly appended under `containers` in the kubernetes pod spec,
        so you should use the same structure. Each item in the list is container configuration
        which follows spec at https://kubernetes.io/docs/reference/generated/kubernetes-api/v1.11/#container-v1-core.

        One usage is setting crontab in a container to clean sensitive data with configuration below::

            c.KubeSpawner.extra_containers = [{
                "name": "crontab",
                "image": "supercronic",
                "command": ["/usr/local/bin/supercronic", "/etc/crontab"]
            }]

        `{username}` is expanded to the escaped, dns-label safe username.
        """
    )

    # FIXME: Don't override 'default_value' ("") or 'allow_none' (False) (Breaking change)
    scheduler_name = Unicode(
        None,
        allow_none=True,
        config=True,
        help="""
        Set the pod's scheduler explicitly by name. See `the Kubernetes documentation <https://kubernetes.io/docs/reference/generated/kubernetes-api/v1.11/#podspec-v1-core>`__
        for more information.
        """
    )

    tolerations = List(
        config=True,
        help="""
        List of tolerations that are to be assigned to the pod in order to be able to schedule the pod
        on a node with the corresponding taints. See the official Kubernetes documentation for additional details
        https://kubernetes.io/docs/concepts/configuration/taint-and-toleration/

        Pass this field an array of `"Toleration" objects
        <https://kubernetes.io/docs/reference/generated/kubernetes-api/v1.11/#nodeselectorterm-v1-core>`__

        Example::

            [
                {
                    'key': 'key',
                    'operator': 'Equal',
                    'value': 'value',
                    'effect': 'NoSchedule'
                },
                {
                    'key': 'key',
                    'operator': 'Exists',
                    'effect': 'NoSchedule'
                }
            ]

        """
    )

    node_affinity_preferred = List(
        config=True,
        help="""
        Affinities describe where pods prefer or require to be scheduled, they
        may prefer or require a node to have a certain label or be in proximity
        / remoteness to another pod. To learn more visit
        https://kubernetes.io/docs/concepts/configuration/assign-pod-node/

        Pass this field an array of "PreferredSchedulingTerm" objects.*
        * https://kubernetes.io/docs/reference/generated/kubernetes-api/v1.11/#preferredschedulingterm-v1-core
        """
    )
    node_affinity_required = List(
        config=True,
        help="""
        Affinities describe where pods prefer or require to be scheduled, they
        may prefer or require a node to have a certain label or be in proximity
        / remoteness to another pod. To learn more visit
        https://kubernetes.io/docs/concepts/configuration/assign-pod-node/

        Pass this field an array of "NodeSelectorTerm" objects.*
        * https://kubernetes.io/docs/reference/generated/kubernetes-api/v1.11/#nodeselectorterm-v1-core
        """
    )
    pod_affinity_preferred = List(
        config=True,
        help="""
        Affinities describe where pods prefer or require to be scheduled, they
        may prefer or require a node to have a certain label or be in proximity
        / remoteness to another pod. To learn more visit
        https://kubernetes.io/docs/concepts/configuration/assign-pod-node/

        Pass this field an array of "WeightedPodAffinityTerm" objects.*
        * https://kubernetes.io/docs/reference/generated/kubernetes-api/v1.11/#weightedpodaffinityterm-v1-core
        """
    )
    pod_affinity_required = List(
        config=True,
        help="""
        Affinities describe where pods prefer or require to be scheduled, they
        may prefer or require a node to have a certain label or be in proximity
        / remoteness to another pod. To learn more visit
        https://kubernetes.io/docs/concepts/configuration/assign-pod-node/

        Pass this field an array of "PodAffinityTerm" objects.*
        * https://kubernetes.io/docs/reference/generated/kubernetes-api/v1.11/#podaffinityterm-v1-core
        """
    )
    pod_anti_affinity_preferred = List(
        config=True,
        help="""
        Affinities describe where pods prefer or require to be scheduled, they
        may prefer or require a node to have a certain label or be in proximity
        / remoteness to another pod. To learn more visit
        https://kubernetes.io/docs/concepts/configuration/assign-pod-node/

        Pass this field an array of "WeightedPodAffinityTerm" objects.*
        * https://kubernetes.io/docs/reference/generated/kubernetes-api/v1.11/#weightedpodaffinityterm-v1-core
        """
    )
    pod_anti_affinity_required = List(
        config=True,
        help="""
        Affinities describe where pods prefer or require to be scheduled, they
        may prefer or require a node to have a certain label or be in proximity
        / remoteness to another pod. To learn more visit
        https://kubernetes.io/docs/concepts/configuration/assign-pod-node/

        Pass this field an array of "PodAffinityTerm" objects.*
        * https://kubernetes.io/docs/reference/generated/kubernetes-api/v1.11/#podaffinityterm-v1-core
        """
    )

    extra_resource_guarantees = Dict(
        config=True,
        help="""
        The dictionary used to request arbitrary resources.
        Default is None and means no additional resources are requested.
        For example, to request 1 Nvidia GPUs::

            c.KubeSpawner.extra_resource_guarantees = {"nvidia.com/gpu": "1"}
        """
    )

    extra_resource_limits = Dict(
        config=True,
        help="""
        The dictionary used to limit arbitrary resources.
        Default is None and means no additional resources are limited.
        For example, to add a limit of 3 Nvidia GPUs::

            c.KubeSpawner.extra_resource_limits = {"nvidia.com/gpu": "3"}
        """
    )

    delete_stopped_pods = Bool(
        True,
        config=True,
        help="""
        Whether to delete pods that have stopped themselves.
        Set to False to leave stopped pods in the completed state,
        allowing for easier debugging of why they may have stopped.
        """
    )

    profile_form_template = Unicode(
        """
        <script>
        // JupyterHub 0.8 applied form-control indisciminately to all form elements.
        // Can be removed once we stop supporting JupyterHub 0.8
        $(document).ready(function() {
            $('#kubespawner-profiles-list input[type="radio"]').removeClass('form-control');
        });
        </script>
        <style>
        /* The profile description should not be bold, even though it is inside the <label> tag */
        #kubespawner-profiles-list label p {
            font-weight: normal;
        }
        </style>

        <div class='form-group' id='kubespawner-profiles-list'>
        {% for profile in profile_list %}
        <label for='profile-item-{{ loop.index0 }}' class='form-control input-group'>
            <div class='col-md-1'>
                <input type='radio' name='profile' id='profile-item-{{ loop.index0 }}' value='{{ loop.index0 }}' {% if profile.default %}checked{% endif %} />
            </div>
            <div class='col-md-11'>
                <strong>{{ profile.display_name }}</strong>
                {% if profile.description %}
                <p>{{ profile.description }}</p>
                {% endif %}
            </div>
        </label>
        {% endfor %}
        </div>
        """,
        config=True,
        help="""
        Jinja2 template for constructing profile list shown to user.

        Used when `profile_list` is set.

        The contents of `profile_list` are passed in to the template.
        This should be used to construct the contents of a HTML form. When
        posted, this form is expected to have an item with name `profile` and
        the value the index of the profile in `profile_list`.
        """
    )

    profile_list = Union(
        trait_types=[
            List(trait=Dict()),
            Callable()
        ],
        config=True,
        help="""
        List of profiles to offer for selection by the user.

        Signature is: `List(Dict())`, where each item is a dictionary that has two keys:

        - `display_name`: the human readable display name (should be HTML safe)
        - `description`: Optional description of this profile displayed to the user.
        - `kubespawner_override`: a dictionary with overrides to apply to the KubeSpawner
          settings. Each value can be either the final value to change or a callable that
          take the `KubeSpawner` instance as parameter and return the final value.
        - `default`: (optional Bool) True if this is the default selected option

        Example::

            c.KubeSpawner.profile_list = [
                {
                    'display_name': 'Training Env - Python',
                    'default': True,
                    'kubespawner_override': {
                        'image': 'training/python:label',
                        'cpu_limit': 1,
                        'mem_limit': '512M',
                    }
                }, {
                    'display_name': 'Training Env - Datascience',
                    'kubespawner_override': {
                        'image': 'training/datascience:label',
                        'cpu_limit': 4,
                        'mem_limit': '8G',
                    }
                }, {
                    'display_name': 'DataScience - Small instance',
                    'kubespawner_override': {
                        'image': 'datascience/small:label',
                        'cpu_limit': 10,
                        'mem_limit': '16G',
                    }
                }, {
                    'display_name': 'DataScience - Medium instance',
                    'kubespawner_override': {
                        'image': 'datascience/medium:label',
                        'cpu_limit': 48,
                        'mem_limit': '96G',
                    }
                }, {
                    'display_name': 'DataScience - Medium instance (GPUx2)',
                    'kubespawner_override': {
                        'image': 'datascience/medium:label',
                        'cpu_limit': 48,
                        'mem_limit': '96G',
                        'extra_resource_guarantees': {"nvidia.com/gpu": "2"},
                    }
                }
            ]

        Instead of a list of dictionaries, this could also be a callable that takes as one
        parameter the current spawner instance and returns a list of dictionaries. The
        callable will be called asynchronously if it returns a future, rather than
        a list. Note that the interface of the spawner class is not deemed stable
        across versions, so using this functionality might cause your JupyterHub
        or kubespawner upgrades to break.
        """
    )

    priority_class_name = Unicode(
        config=True,
        help="""
        The priority class that the pods will use.

        See https://kubernetes.io/docs/concepts/configuration/pod-priority-preemption for
        more information on how pod priority works.
        """
    )

    # deprecate redundant and inconsistent singleuser_ and user_ prefixes:
    _deprecated_traits_09 = [
        "singleuser_working_dir",
        "singleuser_service_account",
        "singleuser_extra_labels",
        "singleuser_extra_annotations",
        "singleuser_image_spec",
        "singleuser_image_pull_policy",
        "singleuser_image_pull_secrets",
        "singleuser_node_selector",
        "singleuser_uid",
        "singleuser_fs_gid",
        "singleuser_supplemental_gids",
        "singleuser_privileged",
        "singleuser_lifecycle_hooks",
        "singleuser_extra_pod_config",
        "singleuser_init_containers",
        "singleuser_extra_container_config",
        "singleuser_extra_containers",
        "user_storage_class",
        "user_storage_pvc_ensure",
        "user_storage_capacity",
        "user_storage_extra_labels",
        "user_storage_access_modes",
    ]
    # other general deprecations:
    _deprecated_traits = {
        'image_spec': ('image', '0.10'),
    }
    # add the bulk deprecations from 0.9
    for _deprecated_name in _deprecated_traits_09:
        _new_name = _deprecated_name.split('_', 1)[1]
        _deprecated_traits[_deprecated_name] = (_new_name, '0.9')

    @validate('config')
    def _handle_deprecated_config(self, proposal):
        config = proposal.value
        if 'KubeSpawner' not in config:
            # nothing to check
            return config
        for _deprecated_name, (_new_name, version) in self._deprecated_traits.items():
            # for any `singleuser_name` deprecate in favor of `name`
            if _deprecated_name not in config.KubeSpawner:
                # nothing to do
                continue

            # remove deprecated value from config
            _deprecated_value = config.KubeSpawner.pop(_deprecated_name)
            self.log.warning(
                "KubeSpawner.%s is deprecated in %s. Use KubeSpawner.%s instead",
                _deprecated_name,
                version,
                _new_name,
            )
            if _new_name in config.KubeSpawner:
                # *both* config values found,
                # ignore deprecated config and warn about the collision
                _new_value = config.KubeSpawner[_new_name]
                # ignore deprecated config in favor of non-deprecated config
                self.log.warning(
                    "Ignoring deprecated config KubeSpawner.%s = %r "
                    " in favor of KubeSpawner.%s = %r",
                    _deprecated_name,
                    _deprecated_value,
                    _new_name,
                    _new_value,
                )
            else:
                # move deprecated config to its new home
                config.KubeSpawner[_new_name] = _deprecated_value

        return config

    # define properties for deprecated names
    # so we can propagate their values to the new traits.
    # most deprecations should be handled via config above,
    # but in case these are set at runtime, e.g. by subclasses
    # or hooks, hook this up.
    # The signature-order of these is funny
    # because the property methods are created with
    # functools.partial(f, name) so name is passed as the first arg
    # before self.

    def _get_deprecated(name, new_name, version, self):
        # warn about the deprecated name
        self.log.warning(
            "KubeSpawner.%s is deprecated in %s. Use KubeSpawner.%s",
            name,
            version,
            new_name,
        )
        return getattr(self, new_name)

    def _set_deprecated(name, new_name, version, self, value):
        # warn about the deprecated name
        self.log.warning(
            "KubeSpawner.%s is deprecated in %s. Use KubeSpawner.%s",
            name,
            version,
            new_name,
        )
        return setattr(self, new_name, value)

    for _deprecated_name, (_new_name, _version) in _deprecated_traits.items():
        exec(
            """{0} = property(
                partial(_get_deprecated, '{0}', '{1}', '{2}'),
                partial(_set_deprecated, '{0}', '{1}', '{2}'),
            )
            """.format(
                _deprecated_name,
                _new_name,
                _version,
            )
        )
    del _deprecated_name

    def _expand_user_properties(self, template):
        # Make sure username and servername match the restrictions for DNS labels
        # Note: '-' is not in safe_chars, as it is being used as escape character
        safe_chars = set(string.ascii_lowercase + string.digits)

        # Set servername based on whether named-server initialised
        if self.name:
            servername = '-{}'.format(self.name)
            safe_servername = escapism.escape(servername, safe=safe_chars, escape_char='-').lower()
        else:
            servername = ''
            safe_servername = ''

        legacy_escaped_username = ''.join([s if s in safe_chars else '-' for s in self.user.name.lower()])
        safe_username = escapism.escape(self.user.name, safe=safe_chars, escape_char='-').lower()
        return template.format(
            userid=self.user.id,
            username=safe_username,
            unescaped_username=self.user.name,
            legacy_escape_username=legacy_escaped_username,
            servername=safe_servername,
            unescaped_servername=servername
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

    def _build_common_labels(self, extra_labels):
        # Default set of labels, picked up from
        # https://github.com/kubernetes/helm/blob/master/docs/chart_best_practices/labels.md
        labels = {}
        labels.update(extra_labels)
        labels.update(self.common_labels)
        return labels

    def _build_pod_labels(self, extra_labels):
        labels = self._build_common_labels(extra_labels)
        labels.update({
            'component': 'singleuser-server'
        })
        return labels

    def _build_common_annotations(self, extra_annotations):
        # Annotations don't need to be escaped
        annotations = {
            'hub.jupyter.org/username': self.user.name
        }
        if self.name:
            annotations['hub.jupyter.org/servername'] = self.name

        annotations.update(extra_annotations)
        return annotations

    @gen.coroutine
    def get_pod_manifest(self):
        """
        Make a pod manifest that will spawn current user's notebook pod.
        """
        if callable(self.uid):
            uid = yield gen.maybe_future(self.uid(self))
        else:
            uid = self.uid

        if callable(self.gid):
            gid = yield gen.maybe_future(self.gid(self))
        else:
            gid = self.gid

        if callable(self.fs_gid):
            fs_gid = yield gen.maybe_future(self.fs_gid(self))
        else:
            fs_gid = self.fs_gid

        if callable(self.supplemental_gids):
            supplemental_gids = yield gen.maybe_future(self.supplemental_gids(self))
        else:
            supplemental_gids = self.supplemental_gids

        if self.cmd:
            real_cmd = self.cmd + self.get_args()
        else:
            real_cmd = None

        labels = self._build_pod_labels(self._expand_all(self.extra_labels))
        annotations = self._build_common_annotations(self._expand_all(self.extra_annotations))

        return make_pod(
            name=self.pod_name,
            cmd=real_cmd,
            port=self.port,
            image=self.image,
            image_pull_policy=self.image_pull_policy,
            image_pull_secret=self.image_pull_secrets,
            node_selector=self.node_selector,
            run_as_uid=uid,
            run_as_gid=gid,
            fs_gid=fs_gid,
            supplemental_gids=supplemental_gids,
            run_privileged=self.privileged,
            env=self.get_env(),
            volumes=self._expand_all(self.volumes),
            volume_mounts=self._expand_all(self.volume_mounts),
            working_dir=self.working_dir,
            labels=labels,
            annotations=annotations,
            cpu_limit=self.cpu_limit,
            cpu_guarantee=self.cpu_guarantee,
            mem_limit=self.mem_limit,
            mem_guarantee=self.mem_guarantee,
            extra_resource_limits=self.extra_resource_limits,
            extra_resource_guarantees=self.extra_resource_guarantees,
            lifecycle_hooks=self.lifecycle_hooks,
            init_containers=self._expand_all(self.init_containers),
            service_account=self.service_account,
            extra_container_config=self.extra_container_config,
            extra_pod_config=self.extra_pod_config,
            extra_containers=self._expand_all(self.extra_containers),
            scheduler_name=self.scheduler_name,
            tolerations=self.tolerations,
            node_affinity_preferred=self.node_affinity_preferred,
            node_affinity_required=self.node_affinity_required,
            pod_affinity_preferred=self.pod_affinity_preferred,
            pod_affinity_required=self.pod_affinity_required,
            pod_anti_affinity_preferred=self.pod_anti_affinity_preferred,
            pod_anti_affinity_required=self.pod_anti_affinity_required,
            priority_class_name=self.priority_class_name,
            logger=self.log,
        )

    def get_pvc_manifest(self):
        """
        Make a pvc manifest that will spawn current user's pvc.
        """
        labels = self._build_common_labels(self._expand_all(self.storage_extra_labels))
        labels.update({
            'component': 'singleuser-storage'
        })

        annotations = self._build_common_annotations({})

        return make_pvc(
            name=self.pvc_name,
            storage_class=self.storage_class,
            access_modes=self.storage_access_modes,
            storage=self.storage_capacity,
            labels=labels,
            annotations=annotations
        )

    def is_pod_running(self, pod):
        """
        Check if the given pod is running

        pod must be a dictionary representing a Pod kubernetes API object.
        """
        # FIXME: Validate if this is really the best way
        is_running = (
            pod is not None and
            pod.status.phase == 'Running' and
            pod.status.pod_ip is not None and
            pod.metadata.deletion_timestamp is None and
            all([cs.ready for cs in pod.status.container_statuses])
        )
        return is_running

    def get_state(self):
        """
        Save state required to reinstate this user's pod from scratch

        We save the `pod_name`, even though we could easily compute it,
        because JupyterHub requires you save *some* state! Otherwise
        it assumes your server is dead. This works around that.

        It's also useful for cases when the `pod_template` changes between
        restarts - this keeps the old pods around.
        """
        state = super().get_state()
        state['pod_name'] = self.pod_name
        return state

    def get_env(self):
        """Return the environment dict to use for the Spawner.

        See also: jupyterhub.Spawner.get_env
        """

        env = super(KubeSpawner, self).get_env()
        # deprecate image
        env['JUPYTER_IMAGE_SPEC'] = self.image
        env['JUPYTER_IMAGE'] = self.image

        return env

    def load_state(self, state):
        """
        Load state from storage required to reinstate this user's pod

        Since this runs after `__init__`, this will override the generated `pod_name`
        if there's one we have saved in state. These are the same in most cases,
        but if the `pod_template` has changed in between restarts, it will no longer
        be the case. This allows us to continue serving from the old pods with
        the old names.
        """
        if 'pod_name' in state:
            self.pod_name = state['pod_name']

    @gen.coroutine
    def poll(self):
        """
        Check if the pod is still running.

        Uses the same interface as subprocess.Popen.poll(): if the pod is
        still running, returns None.  If the pod has exited, return the
        exit code if we can determine it, or 1 if it has exited but we
        don't know how.  These are the return values JupyterHub expects.

        Note that a clean exit will have an exit code of zero, so it is
        necessary to check that the returned value is None, rather than
        just Falsy, to determine that the pod is still running.
        """
        # have to wait for first load of data before we have a valid answer
        if not self.pod_reflector.first_load_future.done():
            yield self.pod_reflector.first_load_future
        data = self.pod_reflector.pods.get(self.pod_name, None)
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

    @run_on_executor
    def asynchronize(self, method, *args, **kwargs):
        return method(*args, **kwargs)

    @property
    def events(self):
        """Filter event-reflector to just our events

        Returns list of all events that match our pod_name
        since our ._last_event (if defined).
        ._last_event is set at the beginning of .start().
        """
        if not self.event_reflector:
            return []

        events = []
        for event in self.event_reflector.events:
            if event.involved_object.name != self.pod_name:
                # only consider events for my pod name
                continue

            if self._last_event and event.metadata.uid == self._last_event:
                # saw last_event marker, ignore any previous events
                # and only consider future events
                # only include events *after* our _last_event marker
                events = []
            else:
                events.append(event)
        return events

    @async_generator
    async def progress(self):
        if not self.events_enabled:
            return
        next_event = 0
        self.log.debug('progress generator: %s', self.pod_name)

        pod_id = None
        first_run = True
        start_future = self._start_future
        progress = 0
        while first_run or not start_future.done():
            # run at least once, so we get events that are already waiting,
            # even if we've stopped waiting for new events
            first_run = False
            events = self.events
            len_events = len(events)
            if next_event < len_events:
                # only show messages for the 'current' pod
                # pod_id may change if a previous pod is being stopped
                # before starting a new one
                # use the uid of the latest event to identify 'current'
                pod_id = events[-1].involved_object.uid
                for i in range(next_event, len_events):
                    event = events[i]
                    # move the progress bar.
                    # Since we don't know how many events we will get,
                    # asymptotically approach 90% completion with each event.
                    # each event gets 33% closer to 90%:
                    # 30 50 63 72 78 82 84 86 87 88 88 89
                    progress += (90 - progress) / 3
                    await yield_({
                        'progress': int(progress),
                        'message':  "%s [%s] %s" % (
                            event.last_timestamp,
                            event.type,
                            event.message,
                        )
                    })
                next_event = len_events
            await sleep(1)

    def _start_reflector(self, key, ReflectorClass, replace=False, **kwargs):
        """Start a shared reflector on the KubeSpawner class


        key: key for the reflector (e.g. 'pod' or 'events')
        Reflector: Reflector class to be instantiated
        kwargs: extra keyword-args to be relayed to ReflectorClass

        If replace=False and the pod reflector is already running,
        do nothing.

        If replace=True, a running pod reflector will be stopped
        and a new one started (for recovering from possible errors).
        """
        main_loop = IOLoop.current()
        def on_reflector_failure():
            self.log.critical(
                "%s reflector failed, halting Hub.",
                key.title(),
            )
            sys.exit(1)

        previous_reflector = self.__class__.reflectors.get(key)

        if replace or not previous_reflector:
            self.__class__.reflectors[key] = ReflectorClass(
                parent=self,
                namespace=self.namespace,
                on_failure=on_reflector_failure,
                **kwargs,
            )

        if replace and previous_reflector:
            # we replaced the reflector, stop the old one
            previous_reflector.stop()

        # return the current reflector
        return self.__class__.reflectors[key]


    def _start_watching_events(self, replace=False):
        """Start the events reflector

        If replace=False and the event reflector is already running,
        do nothing.

        If replace=True, a running pod reflector will be stopped
        and a new one started (for recovering from possible errors).
        """
        return self._start_reflector(
            "events",
            EventReflector,
            fields={"involvedObject.kind": "Pod"},
            replace=replace,
        )

    def _start_watching_pods(self, replace=False):
        """Start the pod reflector

        If replace=False and the pod reflector is already running,
        do nothing.

        If replace=True, a running pod reflector will be stopped
        and a new one started (for recovering from possible errors).
        """
        return self._start_reflector("pods", PodReflector, replace=replace)

    # record a future for the call to .start()
    # so we can use it to terminate .progress()
    def start(self):
        """Thin wrapper around self._start

        so we can hold onto a reference for the Future
        start returns, which we can use to terminate
        .progress()
        """
        self._start_future = self._start()
        return self._start_future

    _last_event = None

    @gen.coroutine
    def _start(self):
        """Start the user's pod"""
        # record latest event so we don't include old
        # events from previous pods in self.events
        # track by order and name instead of uid
        # so we get events like deletion of a previously stale
        # pod if it's part of this spawn process
        events = self.events
        if events:
            self._last_event = events[-1].metadata.uid

        if self.storage_pvc_ensure:
            # Try and create the pvc. If it succeeds we are good. If
            # returns a 409 indicating it already exists we are good. If
            # it returns a 403, indicating potential quota issue we need
            # to see if pvc already exists before we decide to raise the
            # error for quota being exceeded. This is because quota is
            # checked before determining if the PVC needed to be
            # created.

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

                elif e.status == 403:
                    t, v, tb = sys.exc_info()

                    try:
                        yield self.asynchronize(
                            self.api.read_namespaced_persistent_volume_claim,
                            name=self.pvc_name,
                            namespace=self.namespace)

                    except ApiException as e:
                        raise v.with_traceback(tb)

                    self.log.info("PVC " + self.pvc_name + " already exists, possibly have reached quota though.")

                else:
                    raise

        # If we run into a 409 Conflict error, it means a pod with the
        # same name already exists. We stop it, wait for it to stop, and
        # try again. We try 4 times, and if it still fails we give up.
        # FIXME: Have better / cleaner retry logic!
        retry_times = 4
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
                self.log.info('Found existing pod %s, attempting to kill', self.pod_name)
                # TODO: this should show up in events
                yield self.stop(True)

                self.log.info('Killed pod %s, will try starting singleuser pod again', self.pod_name)
        else:
            raise Exception(
                'Can not create user pod %s already exists & could not be deleted' % self.pod_name)

        # we need a timeout here even though start itself has a timeout
        # in order for this coroutine to finish at some point.
        # using the same start_timeout here
        # essentially ensures that this timeout should never propagate up
        # because the handler will have stopped waiting after
        # start_timeout, starting from a slightly earlier point.
        try:
            yield exponential_backoff(
                lambda: self.is_pod_running(self.pod_reflector.pods.get(self.pod_name, None)),
                'pod/%s did not start in %s seconds!' % (self.pod_name, self.start_timeout),
                timeout=self.start_timeout,
            )
        except TimeoutError:
            if self.pod_name not in self.pod_reflector.pods:
                # if pod never showed up at all,
                # restart the pod reflector which may have become disconnected.
                self.log.error(
                    "Pod %s never showed up in reflector, restarting pod reflector",
                    self.pod_name,
                )
                self._start_watching_pods(replace=True)
            raise

        pod = self.pod_reflector.pods[self.pod_name]
        self.pod_id = pod.metadata.uid
        if self.event_reflector:
            self.log.debug(
                'pod %s events before launch: %s',
                self.pod_name,
                "\n".join(
                    [
                        "%s [%s] %s" % (event.last_timestamp, event.type, event.message)
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
                lambda: self.pod_reflector.pods.get(self.pod_name, None) is None,
                'pod/%s did not disappear in %s seconds!' % (self.pod_name, self.start_timeout),
                timeout=self.start_timeout,
            )
        except TimeoutError:
            self.log.error("Pod %s did not disappear, restarting pod reflector", self.pod_name)
            self._start_watching_pods(replace=True)
            raise

    @default('env_keep')
    def _env_keep_default(self):
        return []

    def _render_options_form(self, profile_list):
        self._profile_list = profile_list
        profile_form_template = Environment(loader=BaseLoader).from_string(self.profile_form_template)
        return profile_form_template.render(profile_list=profile_list)

    @gen.coroutine
    def _render_options_form_dynamically(self, current_spawner):
        profile_list = yield gen.maybe_future(self.profile_list(current_spawner))
        return self._render_options_form(profile_list)

    @default('options_form')
    def _options_form_default(self):
        '''
        Build the form template according to the `profile_list` setting.

        Returns:
            '' when no `profile_list` has been defined
            The rendered template (using jinja2) when `profile_list` is defined.
        '''
        if not self.profile_list:
            return ''
        if callable(self.profile_list):
            return self._render_options_form_dynamically
        else:
            return self._render_options_form(self.profile_list)

    def options_from_form(self, formdata):
        """get the option selected by the user on the form

        It actually reset the settings of kubespawner to each item found in the selected profile
        (`kubespawner_override`).

        Args:
            formdata: user selection returned by the form

        To access to the value, you can use the `get` accessor and the name of the html element,
        for example::

            formdata.get('profile',[0])

        to get the value of the form named "profile", as defined in `form_template`::

            <select class="form-control" name="profile"...>
            </select>

        Returns:
            the selected user option
        """
        if not self.profile_list or not hasattr(self, '_profile_list'):
            return formdata
        # Default to first profile if somehow none is provided
        selected_profile = int(formdata.get('profile', [0])[0])
        options = self._profile_list[selected_profile]
        self.log.debug("Applying KubeSpawner override for profile '%s'", options['display_name'])
        kubespawner_override = options.get('kubespawner_override', {})
        for k, v in kubespawner_override.items():
            if callable(v):
                v = v(self)
                self.log.debug(".. overriding KubeSpawner value %s=%s (callable result)", k, v)
            else:
                self.log.debug(".. overriding KubeSpawner value %s=%s", k, v)
            setattr(self, k, v)
        return options
