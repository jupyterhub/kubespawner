"""
JupyterHub Spawner to spawn user notebooks on a Kubernetes cluster.

This module exports `KubeSpawner` class, which is the actual spawner
implementation that should be used by JupyterHub.
"""
import asyncio
import multiprocessing
import os
import signal
import string
import sys
import warnings
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from functools import partial
from urllib.parse import urlparse

import escapism
import kubernetes.config
from jinja2 import BaseLoader
from jinja2 import Environment
from jupyterhub.spawner import Spawner
from jupyterhub.traitlets import Command
from jupyterhub.utils import exponential_backoff
from kubernetes import client
from kubernetes.client.rest import ApiException
from slugify import slugify
from tornado import gen
from tornado.concurrent import run_on_executor
from tornado.ioloop import IOLoop
from traitlets import Bool
from traitlets import default
from traitlets import Dict
from traitlets import Integer
from traitlets import List
from traitlets import observe
from traitlets import Unicode
from traitlets import Union
from traitlets import validate

from .clients import shared_client
from .objects import make_namespace
from .objects import make_owner_reference
from .objects import make_pod
from .objects import make_pvc
from .objects import make_secret
from .objects import make_service
from .reflector import ResourceReflector
from .traitlets import Callable


class PodReflector(ResourceReflector):
    """
    PodReflector is merely a configured ResourceReflector. It exposes
    the pods property, which is simply mapping to self.resources where the
    ResourceReflector keeps an updated list of the resource defined by
    the `kind` field and the `list_method_name` field.
    """

    kind = "pods"

    # The default component label can be over-ridden by specifying the component_label property
    labels = {
        'component': 'singleuser-server',
    }

    @property
    def pods(self):
        """
        A dictionary of pods for the namespace as returned by the Kubernetes
        API. The dictionary keys are the pod ids and the values are
        dictionaries of the actual pod resource values.

        ref: https://kubernetes.io/docs/reference/generated/kubernetes-api/v1.20/#pod-v1-core
        """
        return self.resources


class EventReflector(ResourceReflector):
    """
    EventsReflector is merely a configured ResourceReflector. It
    exposes the events property, which is simply mapping to self.resources where
    the ResourceReflector keeps an updated list of the resource
    defined by the `kind` field and the `list_method_name` field.
    """

    kind = "events"

    @property
    def events(self):
        """
        Returns list of dictionaries representing the k8s
        events within the namespace, sorted by the latest event.

        ref: https://kubernetes.io/docs/reference/generated/kubernetes-api/v1.20/#event-v1-core
        """

        # NOTE:
        # - self.resources is a dictionary with keys mapping unique ids of
        #   Kubernetes Event resources, updated by ResourceReflector.
        #   self.resources will builds up with incoming k8s events, but can also
        #   suddenly refreshes itself entirely. We should not assume a call to
        #   this dictionary's values will result in a consistently ordered list,
        #   so we sort it to get it somewhat more structured.
        # - We either seem to get only event['lastTimestamp'] or
        #   event['eventTime'], both fields serve the same role but the former
        #   is a low resolution timestamp without and the other is a higher
        #   resolution timestamp.
        return sorted(
            self.resources.values(),
            key=lambda event: event["lastTimestamp"] or event["eventTime"],
        )


class MockObject(object):
    pass


class KubeSpawner(Spawner):
    """
    A JupyterHub spawner that spawn pods in a Kubernetes Cluster. Each server
    spawned by a user will have its own KubeSpawner instance.
    """

    # We want to have one single threadpool executor that is shared across all
    # KubeSpawner instances, so we apply a Singleton pattern. We initialize this
    # class variable from the first KubeSpawner instance that is created and
    # then reference it from all instances. The same goes for the PodReflector
    # and EventReflector.
    executor = None
    reflectors = {
        "pods": None,
        "events": None,
    }

    # Characters as defined by safe for DNS
    # Note: '-' is not in safe_chars, as it is being used as escape character
    safe_chars = set(string.ascii_lowercase + string.digits)

    @property
    def pod_reflector(self):
        """
        A convenience alias to the class variable reflectors['pods'].
        """
        return self.__class__.reflectors['pods']

    @property
    def event_reflector(self):
        """
        A convenience alias to the class variable reflectors['events'] if the
        spawner instance has events_enabled.
        """
        if self.events_enabled:
            return self.__class__.reflectors['events']

    def __init__(self, *args, **kwargs):
        _mock = kwargs.pop('_mock', False)
        super().__init__(*args, **kwargs)

        if _mock:
            # runs during test execution only
            if 'user' not in kwargs:
                user = MockObject()
                user.name = 'mock_name'
                user.id = 'mock_id'
                user.url = 'mock_url'
                self.user = user

            if 'hub' not in kwargs:
                hub = MockObject()
                hub.public_host = 'mock_public_host'
                hub.url = 'mock_url'
                hub.base_url = 'mock_base_url'
                hub.api_url = 'mock_api_url'
                self.hub = hub

        # We have to set the namespace (if user namespaces are enabled)
        #  before we start the reflectors, so this must run before
        #  watcher start in normal execution.  We still want to get the
        #  namespace right for test, though, so we need self.user to have
        #  been set in order to do that.

        # By now, all the traitlets have been set, so we can use them to
        # compute other attributes

        if self.enable_user_namespaces:
            self.namespace = self._expand_user_properties(self.user_namespace_template)
            self.log.info("Using user namespace: {}".format(self.namespace))

        if not _mock:
            # runs during normal execution only

            if self.__class__.executor is None:
                self.log.debug(
                    'Starting executor thread pool with %d workers',
                    self.k8s_api_threadpool_workers,
                )
                self.__class__.executor = ThreadPoolExecutor(
                    max_workers=self.k8s_api_threadpool_workers
                )

            # Set global kubernetes client configurations
            # before reflector.py code runs
            self._set_k8s_client_configuration()
            self.api = shared_client('CoreV1Api')

            # This will start watching in __init__, so it'll start the first
            # time any spawner object is created. Not ideal but works!
            self._start_watching_pods()
            if self.events_enabled:
                self._start_watching_events()

        # runs during both test and normal execution
        self.pod_name = self._expand_user_properties(self.pod_name_template)
        self.dns_name = self.dns_name_template.format(
            namespace=self.namespace, name=self.pod_name
        )
        self.secret_name = self._expand_user_properties(self.secret_name_template)

        self.pvc_name = self._expand_user_properties(self.pvc_name_template)
        if self.working_dir:
            self.working_dir = self._expand_user_properties(self.working_dir)
        if self.port == 0:
            # Our default port is 8888
            self.port = 8888
        # The attribute needs to exist, even though it is unset to start with
        self._start_future = None

    def _set_k8s_client_configuration(self):
        # The actual (singleton) Kubernetes client will be created
        # in clients.py shared_client but the configuration
        # for token / ca_cert / k8s api host is set globally
        # in kubernetes.py syntax.  It is being set here
        # and this method called prior to shared_client
        # for readability / coupling with traitlets values
        try:
            kubernetes.config.load_incluster_config()
        except kubernetes.config.ConfigException:
            kubernetes.config.load_kube_config()
        if self.k8s_api_ssl_ca_cert:
            global_conf = client.Configuration.get_default_copy()
            global_conf.ssl_ca_cert = self.k8s_api_ssl_ca_cert
            client.Configuration.set_default(global_conf)
        if self.k8s_api_host:
            global_conf = client.Configuration.get_default_copy()
            global_conf.host = self.k8s_api_host
            client.Configuration.set_default(global_conf)

    k8s_api_ssl_ca_cert = Unicode(
        "",
        config=True,
        help="""
        Location (absolute filepath) for CA certs of the k8s API server.

        Typically this is unnecessary, CA certs are picked up by
        config.load_incluster_config() or config.load_kube_config.

        In rare non-standard cases, such as using custom intermediate CA
        for your cluster, you may need to mount root CA's elsewhere in
        your Pod/Container and point this variable to that filepath
        """,
    )

    k8s_api_host = Unicode(
        "",
        config=True,
        help="""
        Full host name of the k8s API server ("https://hostname:port").

        Typically this is unnecessary, the hostname is picked up by
        config.load_incluster_config() or config.load_kube_config.
        """,
    )

    k8s_api_threadpool_workers = Integer(
        # Set this explicitly, since this is the default in Python 3.5+
        # but not in 3.4
        5 * multiprocessing.cpu_count(),
        config=True,
        help="""
        Number of threads in thread pool used to talk to the k8s API.

        Increase this if you are dealing with a very large number of users.

        Defaults to `5 * cpu_cores`, which is the default for `ThreadPoolExecutor`.
        """,
    )

    k8s_api_request_timeout = Integer(
        3,
        config=True,
        help="""
        API request timeout (in seconds) for all k8s API calls.

        This is the total amount of time a request might take before the connection
        is killed. This includes connection time and reading the response.

        NOTE: This is currently only implemented for creation and deletion of pods,
        and creation of PVCs.
        """,
    )

    k8s_api_request_retry_timeout = Integer(
        30,
        config=True,
        help="""
        Total timeout, including retry timeout, for kubernetes API calls

        When a k8s API request connection times out, we retry it while backing
        off exponentially. This lets you configure the total amount of time
        we will spend trying an API request - including retries - before
        giving up.
        """,
    )

    events_enabled = Bool(
        True,
        config=True,
        help="""
        Enable event-watching for progress-reports to the user spawn page.

        Disable if these events are not desirable
        or to save some performance cost.
        """,
    )

    enable_user_namespaces = Bool(
        False,
        config=True,
        help="""
        Cause each user to be spawned into an individual namespace.

        This comes with some caveats.  The Hub must run with significantly
        more privilege (must have ClusterRoles analogous to its usual Roles)
        and can therefore do heinous things to the entire cluster.

        It will also make the Reflectors aware of pods and events across
        all namespaces.  This will have performance implications, although
        using labels to restrict resource selection helps somewhat.

        If you use this, consider cleaning up the user namespace in your
        post_stop_hook.
        """,
    )

    user_namespace_template = Unicode(
        "{hubnamespace}-{username}",
        config=True,
        help="""
        Template to use to form the namespace of user's pods (only if
        enable_user_namespaces is True).

        `{username}`, `{userid}`, `{servername}`, `{hubnamespace}`,
        `{unescaped_username}`, and `{unescaped_servername}` will be expanded if
        found within strings of this configuration. The username and servername
        come escaped to follow the [DNS label
        standard](https://kubernetes.io/docs/concepts/overview/working-with-objects/names/#dns-label-names).
        """,
    )

    namespace = Unicode(
        config=True,
        help="""
        Kubernetes namespace to spawn user pods in.

        Assuming that you are not running with enable_user_namespaces
        turned on, if running inside a kubernetes cluster with service
        accounts enabled, defaults to the current namespace, and if not,
        defaults to `default`.

        If you are running with enable_user_namespaces, this parameter
        is ignored in favor of the `user_namespace_template` template
        resolved with the hub namespace and the user name, with the
        caveat that if the hub namespace is `default` the user
        namespace will have the prefix `user` rather than `default`.
        """,
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
        """,
    )

    cmd = Command(
        None,
        allow_none=True,
        minlen=0,
        config=True,
        help="""
        The command used to start the single-user server.

        Either
          - a string containing a single command or path to a startup script
          - a list of the command and arguments
          - `None` (default) to use the Docker image's `CMD`

        If `cmd` is set, it will be augmented with `spawner.get_args(). This will override the `CMD` specified in the Docker image.
        """,
    )

    # FIXME: Don't override 'default_value' ("") or 'allow_none' (False) (Breaking change)
    working_dir = Unicode(
        None,
        allow_none=True,
        config=True,
        help="""
        The working directory where the Notebook server will be started inside the container.
        Defaults to `None` so the working directory will be the one defined in the Dockerfile.

        `{username}`, `{userid}`, `{servername}`, `{hubnamespace}`,
        `{unescaped_username}`, and `{unescaped_servername}` will be expanded if
        found within strings of this configuration. The username and servername
        come escaped to follow the [DNS label
        standard](https://kubernetes.io/docs/concepts/overview/working-with-objects/names/#dns-label-names).
        """,
    )

    # FIXME: Don't override 'default_value' ("") or 'allow_none' (False) (Breaking change)
    service_account = Unicode(
        None,
        allow_none=True,
        config=True,
        help="""
        The service account to be mounted in the spawned user pod.

        The token of the service account is NOT mounted by default.
        This makes sure that we don't accidentally give access to the whole
        kubernetes API to the users in the spawned pods.
        Set automount_service_account_token True to mount it.

        This `serviceaccount` must already exist in the namespace the user pod is being spawned in.
        """,
    )

    automount_service_account_token = Bool(
        None,
        allow_none=True,
        config=True,
        help="""
        Whether to mount the service account token in the spawned user pod.

        The default value is None, which mounts the token if the service account is explicitly set,
        but doesn't mount it if not.

        WARNING: Be careful with this configuration! Make sure the service account being mounted
        has the minimal permissions needed, and nothing more. When misconfigured, this can easily
        give arbitrary users root over your entire cluster.
        """,
    )

    dns_name_template = Unicode(
        "{name}.{namespace}.svc.cluster.local",
        config=True,
        help="""
        Template to use to form the dns name for the pod.
        """,
    )

    pod_name_template = Unicode(
        'jupyter-{username}--{servername}',
        config=True,
        help="""
        Template to use to form the name of user's pods.

        `{username}`, `{userid}`, `{servername}`, `{hubnamespace}`,
        `{unescaped_username}`, and `{unescaped_servername}` will be expanded if
        found within strings of this configuration. The username and servername
        come escaped to follow the [DNS label
        standard](https://kubernetes.io/docs/concepts/overview/working-with-objects/names/#dns-label-names).

        Trailing `-` characters are stripped for safe handling of empty server names (user default servers).

        This must be unique within the namespace the pods are being spawned
        in, so if you are running multiple jupyterhubs spawning in the
        same namespace, consider setting this to be something more unique.

        .. versionchanged:: 0.12
            `--` delimiter added to the template,
            where it was implicitly added to the `servername` field before.
            Additionally, `username--servername` delimiter was `-` instead of `--`,
            allowing collisions in certain circumstances.
        """,
    )

    pod_connect_ip = Unicode(
        config=True,
        help="""
        The IP address (or hostname) of user's pods which KubeSpawner connects to.
        If you do not specify the value, KubeSpawner will use the pod IP.

        e.g. 'jupyter-{username}--{servername}.notebooks.jupyterhub.svc.cluster.local',

        `{username}`, `{userid}`, `{servername}`, `{hubnamespace}`,
        `{unescaped_username}`, and `{unescaped_servername}` will be expanded if
        found within strings of this configuration. The username and servername
        come escaped to follow the [DNS label
        standard](https://kubernetes.io/docs/concepts/overview/working-with-objects/names/#dns-label-names).

        Trailing `-` characters in each domain level are stripped for safe handling of empty server names (user default servers).

        This must be unique within the namespace the pods are being spawned
        in, so if you are running multiple jupyterhubs spawning in the
        same namespace, consider setting this to be something more unique.
        """,
    )

    storage_pvc_ensure = Bool(
        False,
        config=True,
        help="""
        Ensure that a PVC exists for each user before spawning.

        Set to true to create a PVC named with `pvc_name_template` if it does
        not exist for the user when their pod is spawning.
        """,
    )

    delete_pvc = Bool(
        True,
        config=True,
        help="""Delete PVCs when deleting Spawners.

        When a Spawner is deleted (not just stopped),
        delete its associated PVC.

        This occurs when a named server is deleted,
        or when the user itself is deleted for the default Spawner.

        Requires JupyterHub 1.4.1 for Spawner.delete_forever support.

        .. versionadded: 0.17
        """,
    )
    pvc_name_template = Unicode(
        'claim-{username}--{servername}',
        config=True,
        help="""
        Template to use to form the name of user's pvc.

        `{username}`, `{userid}`, `{servername}`, `{hubnamespace}`,
        `{unescaped_username}`, and `{unescaped_servername}` will be expanded if
        found within strings of this configuration. The username and servername
        come escaped to follow the [DNS label
        standard](https://kubernetes.io/docs/concepts/overview/working-with-objects/names/#dns-label-names).

        Trailing `-` characters are stripped for safe handling of empty server names (user default servers).

        This must be unique within the namespace the pvc are being spawned
        in, so if you are running multiple jupyterhubs spawning in the
        same namespace, consider setting this to be something more unique.

        .. versionchanged:: 0.12
            `--` delimiter added to the template,
            where it was implicitly added to the `servername` field before.
            Additionally, `username--servername` delimiter was `-` instead of `--`,
            allowing collisions in certain circumstances.
        """,
    )

    component_label = Unicode(
        'singleuser-server',
        config=True,
        help="""
        The component label used to tag the user pods. This can be used to override
        the spawner behavior when dealing with multiple hub instances in the same
        namespace. Usually helpful for CI workflows.
        """,
    )

    secret_name_template = Unicode(
        'jupyter-{username}{servername}',
        config=True,
        help="""
        Template to use to form the name of user's secret.

        `{username}`, `{userid}`, `{servername}`, `{hubnamespace}`,
        `{unescaped_username}`, and `{unescaped_servername}` will be expanded if
        found within strings of this configuration. The username and servername
        come escaped to follow the [DNS label
        standard](https://kubernetes.io/docs/concepts/overview/working-with-objects/names/#dns-label-names).

        This must be unique within the namespace the pvc are being spawned
        in, so if you are running multiple jupyterhubs spawning in the
        same namespace, consider setting this to be something more unique.
        """,
    )

    secret_mount_path = Unicode(
        "/etc/jupyterhub/ssl/",
        allow_none=False,
        config=True,
        help="""
        Location to mount the spawned pod's certificates needed for internal_ssl functionality.
        """,
    )

    # FIXME: Don't override 'default_value' ("") or 'allow_none' (False) (Breaking change)
    hub_connect_ip = Unicode(
        allow_none=True,
        config=True,
        help="""DEPRECATED. Use c.JupyterHub.hub_connect_ip""",
    )

    hub_connect_port = Integer(
        config=True, help="""DEPRECATED. Use c.JupyterHub.hub_connect_url"""
    )

    @observe('hub_connect_ip', 'hub_connect_port')
    def _deprecated_changed(self, change):
        warnings.warn(
            """
            KubeSpawner.{0} is deprecated with JupyterHub >= 0.8.
            Use JupyterHub.{0}
            """.format(
                change.name
            ),
            DeprecationWarning,
        )
        setattr(self.hub, change.name.split('_', 1)[1], change.new)

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
        """,
    )

    extra_labels = Dict(
        config=True,
        help="""
        Extra kubernetes labels to set on the spawned single-user pods, as well
        as on the pods' associated k8s Service and k8s Secret if internal_ssl is
        enabled.

        The keys and values specified here would be set as labels on the spawned single-user
        kubernetes pods. The keys and values must both be strings that match the kubernetes
        label key / value constraints.

        See `the Kubernetes documentation <https://kubernetes.io/docs/concepts/overview/working-with-objects/labels/>`__
        for more info on what labels are and why you might want to use them!

        `{username}`, `{userid}`, `{servername}`, `{hubnamespace}`,
        `{unescaped_username}`, and `{unescaped_servername}` will be expanded if
        found within strings of this configuration. The username and servername
        come escaped to follow the [DNS label
        standard](https://kubernetes.io/docs/concepts/overview/working-with-objects/names/#dns-label-names).
        """,
    )

    extra_annotations = Dict(
        config=True,
        help="""
        Extra Kubernetes annotations to set on the spawned single-user pods, as
        well as on the pods' associated k8s Service and k8s Secret if
        internal_ssl is enabled.

        The keys and values specified here are added as annotations on the spawned single-user
        kubernetes pods. The keys and values must both be strings.

        See `the Kubernetes documentation <https://kubernetes.io/docs/concepts/overview/working-with-objects/annotations/>`__
        for more info on what annotations are and why you might want to use them!

        `{username}`, `{userid}`, `{servername}`, `{hubnamespace}`,
        `{unescaped_username}`, and `{unescaped_servername}` will be expanded if
        found within strings of this configuration. The username and servername
        come escaped to follow the [DNS label
        standard](https://kubernetes.io/docs/concepts/overview/working-with-objects/names/#dns-label-names).
        """,
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

        """,
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
        """,
    )

    image_pull_secrets = Union(
        trait_types=[
            List(),
            Unicode(),
        ],
        config=True,
        help="""
        A list of references to Kubernetes Secret resources with credentials to
        pull images from image registries. This list can either have strings in
        it or objects with the string value nested under a name field.

        Passing a single string is still supported, but deprecated as of
        KubeSpawner 0.14.0.

        See `the Kubernetes documentation
        <https://kubernetes.io/docs/concepts/containers/images/#specifying-imagepullsecrets-on-a-pod>`__
        for more information on when and why this might need to be set, and what
        it should be set to.
        """,
    )

    @validate('image_pull_secrets')
    def _validate_image_pull_secrets(self, proposal):
        if type(proposal['value']) == str:
            warnings.warn(
                """Passing KubeSpawner.image_pull_secrets string values is
                deprecated since KubeSpawner 0.14.0. The recommended
                configuration is now a list of either strings or dictionary
                objects with the string referencing the Kubernetes Secret name
                in under the value of the dictionary's name key.""",
                DeprecationWarning,
            )
            return [{"name": proposal['value']}]

        return proposal['value']

    node_selector = Dict(
        config=True,
        help="""
        The dictionary Selector labels used to match the Nodes where Pods will be launched.

        Default is None and means it will be launched in any available Node.

        For example to match the Nodes that have a label of `disktype: ssd` use::

           c.KubeSpawner.node_selector = {'disktype': 'ssd'}
        """,
    )

    uid = Union(
        trait_types=[
            Integer(),
            Callable(),
        ],
        default_value=None,
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
        """,
    )

    gid = Union(
        trait_types=[
            Integer(),
            Callable(),
        ],
        default_value=None,
        allow_none=True,
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
        """,
    )

    fs_gid = Union(
        trait_types=[
            Integer(),
            Callable(),
        ],
        default_value=None,
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
        cloud providers. See `fsGroup <https://kubernetes.io/docs/reference/generated/kubernetes-api/v1.20/#podsecuritycontext-v1-core>`__
        for more details.
        """,
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
        """,
    )

    privileged = Bool(
        False,
        config=True,
        help="""
        Whether to run the pod with a privileged security context.
        """,
    )

    allow_privilege_escalation = Bool(
        False,
        allow_none=True,
        config=True,
        help="""
        Controls whether a process can gain more privileges than its parent process.

        When set to False (the default), the primary user visible effect is that
        setuid binaries (like sudo) will no longer work.

        When set to None, the defaults for the cluster are respected.

        This bool directly controls whether the no_new_privs flag gets set on the container

        AllowPrivilegeEscalation is true always when the container is:
        1) run as Privileged OR 2) has CAP_SYS_ADMIN.
        """,
    )

    container_security_context = Union(
        trait_types=[
            Dict(),
            Callable(),
        ],
        config=True,
        help="""
        A Kubernetes security context for the container. Note that all
        configuration options within here should be camelCased.

        What is configured here has the highest priority, so the alternative
        configuration `uid`, `gid`, `privileged`, and
        `allow_privilege_escalation` will be overridden by this.

        Rely on `the Kubernetes reference
        <https://kubernetes.io/docs/reference/generated/kubernetes-api/v1.20/#securitycontext-v1-core>`__
        for details on allowed configuration.
        """,
    )

    pod_security_context = Union(
        trait_types=[
            Dict(),
            Callable(),
        ],
        config=True,
        help="""
        A Kubernetes security context for the pod. Note that all configuration
        options within here should be camelCased.

        What is configured here has higher priority than `fs_gid` and
        `supplemental_gids`, but lower priority than what is set in the
        `container_security_context`.

        Note that anything configured on the Pod level will influence all
        containers, including init containers and sidecar containers.

        Rely on `the Kubernetes reference
        <https://kubernetes.io/docs/reference/generated/kubernetes-api/v1.20/#podsecuritycontext-v1-core>`__
        for details on allowed configuration.
        """,
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
        """,
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

        `{username}`, `{userid}`, `{servername}`, `{hubnamespace}`,
        `{unescaped_username}`, and `{unescaped_servername}` will be expanded if
        found within strings of this configuration. The username and servername
        come escaped to follow the [DNS label
        standard](https://kubernetes.io/docs/concepts/overview/working-with-objects/names/#dns-label-names).
        """,
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

        `{username}`, `{userid}`, `{servername}`, `{hubnamespace}`,
        `{unescaped_username}`, and `{unescaped_servername}` will be expanded if
        found within strings of this configuration. The username and servername
        come escaped to follow the [DNS label
        standard](https://kubernetes.io/docs/concepts/overview/working-with-objects/names/#dns-label-names).
        """,
    )

    # FIXME: Don't override 'default_value' ("") or 'allow_none' (False) (Breaking change)
    storage_capacity = Unicode(
        None,
        config=True,
        allow_none=True,
        help="""
        The amount of storage space to request from the volume that the pvc will
        mount to. This amount will be the amount of storage space the user has
        to work with on their notebook. If left blank, the kubespawner will not
        create a pvc for the pod.

        This will be added to the `resources: requests: storage:` in the k8s pod spec.

        See `the Kubernetes documentation <https://kubernetes.io/docs/concepts/storage/persistent-volumes/#persistentvolumeclaims>`__

        for more information on how storage works.

        Quantities can be represented externally as unadorned integers, or as fixed-point
        integers with one of these SI suffices (`E, P, T, G, M, K, m`) or their power-of-two
        equivalents (`Ei, Pi, Ti, Gi, Mi, Ki`). For example, the following represent roughly
        the same value: `128974848`, `129e6`, `129M`, `123Mi`.
        """,
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

        `{username}`, `{userid}`, `{servername}`, `{hubnamespace}`,
        `{unescaped_username}`, and `{unescaped_servername}` will be expanded if
        found within strings of this configuration. The username and servername
        come escaped to follow the [DNS label
        standard](https://kubernetes.io/docs/concepts/overview/working-with-objects/names/#dns-label-names).
        """,
    )

    # FIXME: Don't override 'default_value' ("") or 'allow_none' (False) (Breaking change)
    storage_class = Unicode(
        None,
        config=True,
        allow_none=True,
        help="""
        The storage class that the pvc will use.

        This will be added to the `annotations: volume.beta.kubernetes.io/storage-class:`
        in the pvc metadata.

        This will determine what type of volume the pvc will request to use. If one exists
        that matches the criteria of the StorageClass, the pvc will mount to that. Otherwise,
        b/c it has a storage class, k8s will dynamically spawn a pv for the pvc to bind to
        and a machine in the cluster for the pv to bind to.

        Note that an empty string is a valid value and is always interpreted to be
        requesting a pv with no class.

        See `the Kubernetes documentation <https://kubernetes.io/docs/concepts/storage/storage-classes/>`__
        for more information on how StorageClasses work.

        """,
    )

    storage_access_modes = List(
        ["ReadWriteOnce"],
        config=True,
        help="""
        List of access modes the user has for the pvc.

        The access modes are:

            - `ReadWriteOnce` : the volume can be mounted as read-write by a single node
            - `ReadOnlyMany` : the volume can be mounted read-only by many nodes
            - `ReadWriteMany` : the volume can be mounted as read-write by many nodes

        See `the Kubernetes documentation <https://kubernetes.io/docs/concepts/storage/persistent-volumes/#access-modes>`__
        for more information on how access modes work.
        """,
    )

    storage_selector = Dict(
        config=True,
        help="""
        The dictionary Selector labels used to match a PersistentVolumeClaim to
        a PersistentVolume.

        Default is None and means it will match based only on other storage criteria.

        For example to match the Nodes that have a label of `content: jupyter` use::

           c.KubeSpawner.storage_selector = {'matchLabels':{'content': 'jupyter'}}

        `{username}`, `{userid}`, `{servername}`, `{hubnamespace}`,
        `{unescaped_username}`, and `{unescaped_servername}` will be expanded if
        found within strings of this configuration. The username and servername
        come escaped to follow the [DNS label
        standard](https://kubernetes.io/docs/concepts/overview/working-with-objects/names/#dns-label-names).
        """,
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
        """,
    )

    init_containers = List(
        config=True,
        help="""
        List of initialization containers belonging to the pod.

        This list will be directly added under `initContainers` in the kubernetes pod spec,
        so you should use the same structure. Each item in the dict must a field
        of the `V1Container specification <https://kubernetes.io/docs/reference/generated/kubernetes-api/v1.20/#container-v1-core>`__

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
        """,
    )

    extra_container_config = Dict(
        config=True,
        help="""
        Extra configuration (e.g. ``envFrom``) for notebook container which is not covered by other attributes.

        This dict will be directly merge into `container` of notebook server,
        so you should use the same structure. Each item in the dict must a field
        of the `V1Container specification <https://kubernetes.io/docs/reference/generated/kubernetes-api/v1.20/#container-v1-core>`__.


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
        """,
    )

    extra_pod_config = Dict(
        config=True,
        help="""
        Extra configuration for the pod which is not covered by other attributes.

        This dict will be directly merge into pod,so you should use the same structure.
        Each item in the dict is field of pod configuration
        which follows spec at https://kubernetes.io/docs/reference/generated/kubernetes-api/v1.20/#podspec-v1-core


        One usage is set restartPolicy and dnsPolicy with configuration below::

            c.KubeSpawner.extra_pod_config = {
                "restartPolicy": "OnFailure",
                "dns_policy": "ClusterFirstWithHostNet"
            }

        The `key` could be either a camelCase word (used by Kubernetes yaml,
        e.g. `restartPolicy`) or a snake_case word (used by Kubernetes Python
        client, e.g. `dns_policy`).
        """,
    )

    extra_containers = List(
        config=True,
        help="""
        List of containers belonging to the pod which besides to the container generated for notebook server.

        This list will be directly appended under `containers` in the kubernetes pod spec,
        so you should use the same structure. Each item in the list is container configuration
        which follows spec at https://kubernetes.io/docs/reference/generated/kubernetes-api/v1.20/#container-v1-core


        One usage is setting crontab in a container to clean sensitive data with configuration below::

            c.KubeSpawner.extra_containers = [{
                "name": "crontab",
                "image": "supercronic",
                "command": ["/usr/local/bin/supercronic", "/etc/crontab"]
            }]

        `{username}`, `{userid}`, `{servername}`, `{hubnamespace}`,
        `{unescaped_username}`, and `{unescaped_servername}` will be expanded if
        found within strings of this configuration. The username and servername
        come escaped to follow the [DNS label
        standard](https://kubernetes.io/docs/concepts/overview/working-with-objects/names/#dns-label-names).
        """,
    )

    # FIXME: Don't override 'default_value' ("") or 'allow_none' (False) (Breaking change)
    scheduler_name = Unicode(
        None,
        allow_none=True,
        config=True,
        help="""
        Set the pod's scheduler explicitly by name. See `the Kubernetes documentation <https://kubernetes.io/docs/reference/generated/kubernetes-api/v1.20/#podspec-v1-core>`__
        for more information.
        """,
    )

    tolerations = List(
        config=True,
        help="""
        List of tolerations that are to be assigned to the pod in order to be able to schedule the pod
        on a node with the corresponding taints. See the official Kubernetes documentation for additional details
        https://kubernetes.io/docs/concepts/configuration/taint-and-toleration/

        Pass this field an array of `"Toleration" objects
        * https://kubernetes.io/docs/reference/generated/kubernetes-api/v1.20/#toleration-v1-core

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

        """,
    )

    node_affinity_preferred = List(
        config=True,
        help="""
        Affinities describe where pods prefer or require to be scheduled, they
        may prefer or require a node to have a certain label or be in proximity
        / remoteness to another pod. To learn more visit
        https://kubernetes.io/docs/concepts/configuration/assign-pod-node/

        Pass this field an array of "PreferredSchedulingTerm" objects.*
        * https://kubernetes.io/docs/reference/generated/kubernetes-api/v1.20/#preferredschedulingterm-v1-core

        """,
    )
    node_affinity_required = List(
        config=True,
        help="""
        Affinities describe where pods prefer or require to be scheduled, they
        may prefer or require a node to have a certain label or be in proximity
        / remoteness to another pod. To learn more visit
        https://kubernetes.io/docs/concepts/configuration/assign-pod-node/

        Pass this field an array of "NodeSelectorTerm" objects.*
        * https://kubernetes.io/docs/reference/generated/kubernetes-api/v1.20/#nodeselectorterm-v1-core

        """,
    )
    pod_affinity_preferred = List(
        config=True,
        help="""
        Affinities describe where pods prefer or require to be scheduled, they
        may prefer or require a node to have a certain label or be in proximity
        / remoteness to another pod. To learn more visit
        https://kubernetes.io/docs/concepts/configuration/assign-pod-node/

        Pass this field an array of "WeightedPodAffinityTerm" objects.*
        * https://kubernetes.io/docs/reference/generated/kubernetes-api/v1.20/#weightedpodaffinityterm-v1-core

        """,
    )
    pod_affinity_required = List(
        config=True,
        help="""
        Affinities describe where pods prefer or require to be scheduled, they
        may prefer or require a node to have a certain label or be in proximity
        / remoteness to another pod. To learn more visit
        https://kubernetes.io/docs/concepts/configuration/assign-pod-node/

        Pass this field an array of "PodAffinityTerm" objects.*
        * https://kubernetes.io/docs/reference/generated/kubernetes-api/v1.20/#podaffinityterm-v1-core

        """,
    )
    pod_anti_affinity_preferred = List(
        config=True,
        help="""
        Affinities describe where pods prefer or require to be scheduled, they
        may prefer or require a node to have a certain label or be in proximity
        / remoteness to another pod. To learn more visit
        https://kubernetes.io/docs/concepts/configuration/assign-pod-node/

        Pass this field an array of "WeightedPodAffinityTerm" objects.*
        * https://kubernetes.io/docs/reference/generated/kubernetes-api/v1.20/#weightedpodaffinityterm-v1-core
        """,
    )
    pod_anti_affinity_required = List(
        config=True,
        help="""
        Affinities describe where pods prefer or require to be scheduled, they
        may prefer or require a node to have a certain label or be in proximity
        / remoteness to another pod. To learn more visit
        https://kubernetes.io/docs/concepts/configuration/assign-pod-node/

        Pass this field an array of "PodAffinityTerm" objects.*
        * https://kubernetes.io/docs/reference/generated/kubernetes-api/v1.20/#podaffinityterm-v1-core
        """,
    )

    extra_resource_guarantees = Dict(
        config=True,
        help="""
        The dictionary used to request arbitrary resources.
        Default is None and means no additional resources are requested.
        For example, to request 1 Nvidia GPUs::

            c.KubeSpawner.extra_resource_guarantees = {"nvidia.com/gpu": "1"}
        """,
    )

    extra_resource_limits = Dict(
        config=True,
        help="""
        The dictionary used to limit arbitrary resources.
        Default is None and means no additional resources are limited.
        For example, to add a limit of 3 Nvidia GPUs::

            c.KubeSpawner.extra_resource_limits = {"nvidia.com/gpu": "3"}
        """,
    )

    delete_stopped_pods = Bool(
        True,
        config=True,
        help="""
        Whether to delete pods that have stopped themselves.
        Set to False to leave stopped pods in the completed state,
        allowing for easier debugging of why they may have stopped.
        """,
    )

    profile_form_template = Unicode(
        """
        <style>
        /* The profile description should not be bold, even though it is inside the <label> tag */
        #kubespawner-profiles-list label p {
            font-weight: normal;
        }
        </style>

        <div class='form-group' id='kubespawner-profiles-list'>
        {% for profile in profile_list %}
        <label for='profile-item-{{ profile.slug }}' class='form-control input-group'>
            <div class='col-md-1'>
                <input type='radio' name='profile' id='profile-item-{{ profile.slug }}' value='{{ profile.slug }}' {% if profile.default %}checked{% endif %} />
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
        """,
    )

    profile_list = Union(
        trait_types=[List(trait=Dict()), Callable()],
        config=True,
        help="""
        List of profiles to offer for selection by the user.

        Signature is: `List(Dict())`, where each item is a dictionary that has two keys:

        - `display_name`: the human readable display name (should be HTML safe)
        - `slug`: the machine readable slug to identify the profile
          (missing slugs are generated from display_name)
        - `description`: Optional description of this profile displayed to the user.
        - `kubespawner_override`: a dictionary with overrides to apply to the KubeSpawner
          settings. Each value can be either the final value to change or a callable that
          take the `KubeSpawner` instance as parameter and return the final value.
        - `default`: (optional Bool) True if this is the default selected option

        Example::

            c.KubeSpawner.profile_list = [
                {
                    'display_name': 'Training Env - Python',
                    'slug': 'training-python',
                    'default': True,
                    'kubespawner_override': {
                        'image': 'training/python:label',
                        'cpu_limit': 1,
                        'mem_limit': '512M',
                    }
                }, {
                    'display_name': 'Training Env - Datascience',
                    'slug': 'training-datascience',
                    'kubespawner_override': {
                        'image': 'training/datascience:label',
                        'cpu_limit': 4,
                        'mem_limit': '8G',
                    }
                }, {
                    'display_name': 'DataScience - Small instance',
                    'slug': 'datascience-small',
                    'kubespawner_override': {
                        'image': 'datascience/small:label',
                        'cpu_limit': 10,
                        'mem_limit': '16G',
                    }
                }, {
                    'display_name': 'DataScience - Medium instance',
                    'slug': 'datascience-medium',
                    'kubespawner_override': {
                        'image': 'datascience/medium:label',
                        'cpu_limit': 48,
                        'mem_limit': '96G',
                    }
                }, {
                    'display_name': 'DataScience - Medium instance (GPUx2)',
                    'slug': 'datascience-gpu2x',
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
        """,
    )

    priority_class_name = Unicode(
        config=True,
        help="""
        The priority class that the pods will use.

        See https://kubernetes.io/docs/concepts/configuration/pod-priority-preemption for
        more information on how pod priority works.
        """,
    )

    delete_grace_period = Integer(
        1,
        config=True,
        help="""
        Time in seconds for the pod to be in `terminating` state before is forcefully killed.

        Increase this if you need more time to execute a `preStop` lifecycle hook.

        See https://kubernetes.io/docs/concepts/workloads/pods/pod/#termination-of-pods for
        more information on how pod termination works.

        Defaults to `1`.
        """,
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
        "singleuser_allow_privilege_escalation" "singleuser_lifecycle_hooks",
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

        raw_servername = self.name or ''
        safe_servername = escapism.escape(
            raw_servername, safe=safe_chars, escape_char='-'
        ).lower()

        hub_namespace = self._namespace_default()
        if hub_namespace == "default":
            hub_namespace = "user"

        legacy_escaped_username = ''.join(
            [s if s in safe_chars else '-' for s in self.user.name.lower()]
        )
        safe_username = escapism.escape(
            self.user.name, safe=safe_chars, escape_char='-'
        ).lower()
        rendered = template.format(
            userid=self.user.id,
            username=safe_username,
            unescaped_username=self.user.name,
            legacy_escape_username=legacy_escaped_username,
            servername=safe_servername,
            unescaped_servername=raw_servername,
            hubnamespace=hub_namespace,
        )
        # strip trailing - delimiter in case of empty servername.
        # k8s object names cannot have trailing -
        return rendered.rstrip("-")

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
        # https://github.com/helm/helm-www/blob/HEAD/content/en/docs/chart_best_practices/labels.md
        labels = {
            'hub.jupyter.org/username': escapism.escape(
                self.user.name, safe=self.safe_chars, escape_char='-'
            ).lower()
        }
        labels.update(extra_labels)
        labels.update(self.common_labels)
        return labels

    def _build_pod_labels(self, extra_labels):
        labels = self._build_common_labels(extra_labels)
        labels.update(
            {
                'component': self.component_label,
                'hub.jupyter.org/servername': self.name,
            }
        )
        return labels

    def _build_common_annotations(self, extra_annotations):
        # Annotations don't need to be escaped
        annotations = {'hub.jupyter.org/username': self.user.name}
        if self.name:
            annotations['hub.jupyter.org/servername'] = self.name

        annotations.update(extra_annotations)
        return annotations

    # specify default ssl alt names
    @default("ssl_alt_names")
    def _default_ssl_alt_names(self):
        return [
            f"DNS:{self.dns_name}",
            f"DNS:{self.pod_name}",
            f"DNS:{self.pod_name}.{self.namespace}",
            f"DNS:{self.pod_name}.{self.namespace}.svc",
        ]

    @default("ssl_alt_names_include_local")
    def _default_ssl_alt_names_include_local(self):
        return False

    get_pod_url = Callable(
        default_value=None,
        allow_none=True,
        config=True,
        help="""Callable to retrieve pod url

        Called with (spawner, pod)

        Must not be async
        """,
    )

    def _get_pod_url(self, pod):
        """Return the pod url

        Default: use pod.status.pod_ip (dns_name if ssl is enabled)
        """
        if self.get_pod_url:
            # custom get_pod_url hook
            return self.get_pod_url(self, pod)

        if getattr(self, "internal_ssl", False):
            proto = "https"
            hostname = self.dns_name
        else:
            proto = "http"
            hostname = pod["status"]["podIP"]

        if self.pod_connect_ip:
            hostname = ".".join(
                [
                    s.rstrip("-")
                    for s in self._expand_user_properties(self.pod_connect_ip).split(
                        "."
                    )
                ]
            )

        return "{}://{}:{}".format(
            proto,
            hostname,
            self.port,
        )

    async def get_pod_manifest(self):
        """
        Make a pod manifest that will spawn current user's notebook pod.
        """
        if callable(self.uid):
            uid = await gen.maybe_future(self.uid(self))
        else:
            uid = self.uid

        if callable(self.gid):
            gid = await gen.maybe_future(self.gid(self))
        else:
            gid = self.gid

        if callable(self.fs_gid):
            fs_gid = await gen.maybe_future(self.fs_gid(self))
        else:
            fs_gid = self.fs_gid

        if callable(self.supplemental_gids):
            supplemental_gids = await gen.maybe_future(self.supplemental_gids(self))
        else:
            supplemental_gids = self.supplemental_gids

        if callable(self.container_security_context):
            csc = await gen.maybe_future(self.container_security_context(self))
        else:
            csc = self.container_security_context

        if callable(self.pod_security_context):
            psc = await gen.maybe_future(self.pod_security_context(self))
        else:
            psc = self.pod_security_context

        args = self.get_args()
        real_cmd = None
        if self.cmd:
            real_cmd = self.cmd + args
        elif args:
            self.log.warning(
                f"Ignoring arguments when using implicit command from image: {args}."
                " Set KubeSpawner.cmd explicitly to support passing cli arguments."
            )

        labels = self._build_pod_labels(self._expand_all(self.extra_labels))
        annotations = self._build_common_annotations(
            self._expand_all(self.extra_annotations)
        )

        return make_pod(
            name=self.pod_name,
            cmd=real_cmd,
            port=self.port,
            image=self.image,
            image_pull_policy=self.image_pull_policy,
            image_pull_secrets=self.image_pull_secrets,
            node_selector=self.node_selector,
            uid=uid,
            gid=gid,
            fs_gid=fs_gid,
            supplemental_gids=supplemental_gids,
            privileged=self.privileged,
            allow_privilege_escalation=self.allow_privilege_escalation,
            container_security_context=csc,
            pod_security_context=psc,
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
            service_account=self._expand_all(self.service_account),
            automount_service_account_token=self.automount_service_account_token,
            extra_container_config=self.extra_container_config,
            extra_pod_config=self._expand_all(self.extra_pod_config),
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
            ssl_secret_name=self.secret_name if self.internal_ssl else None,
            ssl_secret_mount_path=self.secret_mount_path,
            logger=self.log,
        )

    def get_secret_manifest(self, owner_reference):
        """
        Make a secret manifest that contains the ssl certificates.
        """

        labels = self._build_common_labels(self._expand_all(self.extra_labels))
        annotations = self._build_common_annotations(
            self._expand_all(self.extra_annotations)
        )

        return make_secret(
            name=self.secret_name,
            username=self.user.name,
            cert_paths=self.cert_paths,
            hub_ca=self.internal_trust_bundles['hub-ca'],
            owner_references=[owner_reference],
            labels=labels,
            annotations=annotations,
        )

    def get_service_manifest(self, owner_reference):
        """
        Make a service manifest for dns.
        """

        labels = self._build_common_labels(self._expand_all(self.extra_labels))
        annotations = self._build_common_annotations(
            self._expand_all(self.extra_annotations)
        )

        # TODO: validate that the service name
        return make_service(
            name=self.pod_name,
            port=self.port,
            servername=self.name,
            owner_references=[owner_reference],
            labels=labels,
            annotations=annotations,
        )

    def get_pvc_manifest(self):
        """
        Make a pvc manifest that will spawn current user's pvc.
        """
        labels = self._build_common_labels(self._expand_all(self.storage_extra_labels))
        labels.update({'component': 'singleuser-storage'})

        annotations = self._build_common_annotations({})

        storage_selector = self._expand_all(self.storage_selector)

        return make_pvc(
            name=self.pvc_name,
            storage_class=self.storage_class,
            access_modes=self.storage_access_modes,
            selector=storage_selector,
            storage=self.storage_capacity,
            labels=labels,
            annotations=annotations,
        )

    def is_pod_running(self, pod):
        """
        Check if the given pod is running

        pod must be a dictionary representing a Pod kubernetes API object.
        """
        # FIXME: Validate if this is really the best way
        is_running = (
            pod is not None
            and pod["status"]["phase"] == 'Running'
            and pod["status"]["podIP"] is not None
            and "deletionTimestamp" not in pod["metadata"]
            and all([cs["ready"] for cs in pod["status"]["containerStatuses"]])
        )
        return is_running

    def pod_has_uid(self, pod):
        """
        Check if the given pod exists and has a UID

        pod must be a dictionary representing a Pod kubernetes API object.
        """

        return bool(
            pod and pod.get("metadata") and pod["metadata"].get("uid") is not None
        )

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

    async def poll(self):
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
            await asyncio.wrap_future(self.pod_reflector.first_load_future)
        ref_key = "{}/{}".format(self.namespace, self.pod_name)
        pod = self.pod_reflector.pods.get(ref_key, None)
        if pod is not None:
            if pod["status"]["phase"] == 'Pending':
                return None
            ctr_stat = pod["status"].get("containerStatuses")
            if ctr_stat is None:  # No status, no container (we hope)
                # This seems to happen when a pod is idle-culled.
                return 1
            for c in ctr_stat:
                # return exit code if notebook container has terminated
                if c["name"] == 'notebook':
                    if "terminated" in c["state"]:
                        # call self.stop to delete the pod
                        if self.delete_stopped_pods:
                            await self.stop(now=True)
                        return c["state"]["terminated"]["exitCode"]
                    break

            # pod running. Check and update server url if it changed!
            # only do this if fully running, not just starting up
            # and there's a stored url in self.server to check against
            if self.is_pod_running(pod) and self.server:

                def _normalize_url(url):
                    """Normalize  url to be comparable

                    - parse with urlparse
                    - Ensures port is always defined
                    """
                    url = urlparse(url)
                    if url.port is None:
                        if url.scheme.lower() == "https":
                            url = url._replace(netloc=f"{url.hostname}:443")
                        elif url.scheme.lower() == "http":
                            url = url._replace(netloc=f"{url.hostname}:80")
                    return url

                pod_url = _normalize_url(self._get_pod_url(pod))
                server_url = _normalize_url(self.server.url)
                # netloc: only compare hostname:port, ignore path
                if server_url.netloc != pod_url.netloc:
                    self.log.warning(
                        f"Pod {ref_key} url changed! {server_url.netloc} -> {pod_url.netloc}"
                    )
                    self.server.ip = pod_url.hostname
                    self.server.port = pod_url.port
                    self.db.commit()

            # None means pod is running or starting up
            return None
        # pod doesn't exist or has been deleted
        return 1

    @run_on_executor
    def asynchronize(self, method, *args, **kwargs):
        return method(*args, **kwargs)

    @property
    def events(self):
        """Filter event-reflector to just this pods events

        Returns list of all events that match our pod_name
        since our ._last_event (if defined).
        ._last_event is set at the beginning of .start().
        """
        if not self.event_reflector:
            return []

        events = []
        for event in self.event_reflector.events:
            if event["involvedObject"]["name"] != self.pod_name:
                # only consider events for my pod name
                continue

            if self._last_event and event["metadata"]["uid"] == self._last_event:
                # saw last_event marker, ignore any previous events
                # and only consider future events
                # only include events *after* our _last_event marker
                events = []
            else:
                events.append(event)
        return events

    async def progress(self):
        """
        This function is reporting back the progress of spawning a pod until
        self._start_future has fired.

        This is working with events parsed by the python kubernetes client,
        and here is the specification of events that is relevant to understand:
        ref: https://kubernetes.io/docs/reference/generated/kubernetes-api/v1.20/#event-v1-core
        """
        if not self.events_enabled:
            return

        self.log.debug('progress generator: %s', self.pod_name)
        start_future = self._start_future
        progress = 0
        next_event = 0

        break_while_loop = False
        while True:
            # This logic avoids a race condition. self._start() will be invoked by
            # self.start() and almost directly set self._start_future. But,
            # progress() will be invoked via self.start(), so what happen first?
            # Due to this, the logic below is to avoid making an assumption that
            # self._start_future was set before this function was called.
            if start_future is None and self._start_future:
                start_future = self._start_future

            # Ensure we capture all events by inspecting events a final time
            # after the start_future signal has fired, we could have been in
            # .sleep() and missed something.
            if start_future and start_future.done():
                break_while_loop = True

            events = self.events
            len_events = len(events)
            if next_event < len_events:
                for i in range(next_event, len_events):
                    event = events[i]
                    # move the progress bar.
                    # Since we don't know how many events we will get,
                    # asymptotically approach 90% completion with each event.
                    # each event gets 33% closer to 90%:
                    # 30 50 63 72 78 82 84 86 87 88 88 89
                    progress += (90 - progress) / 3

                    yield {
                        'progress': int(progress),
                        'raw_event': event,
                        'message': "%s [%s] %s"
                        % (
                            event["lastTimestamp"] or event["eventTime"],
                            event["type"],
                            event["message"],
                        ),
                    }
                next_event = len_events

            if break_while_loop:
                break
            await asyncio.sleep(1)

    def _start_reflector(
        self,
        kind=None,
        reflector_class=ResourceReflector,
        replace=False,
        **kwargs,
    ):
        """Start a shared reflector on the KubeSpawner class


        kind: key for the reflector (e.g. 'pod' or 'events')
        reflector_class: Reflector class to be instantiated
        kwargs: extra keyword-args to be relayed to ReflectorClass

        If replace=False and the pod reflector is already running,
        do nothing.

        If replace=True, a running pod reflector will be stopped
        and a new one started (for recovering from possible errors).
        """
        main_loop = IOLoop.current()
        key = kind
        ReflectorClass = reflector_class

        def on_reflector_failure():
            self.log.critical(
                "%s reflector failed, halting Hub.",
                key.title(),
            )
            # This won't be called from the main thread, so sys.exit
            # will only kill current thread - not process.
            # https://stackoverflow.com/a/7099229
            os.kill(os.getpid(), signal.SIGINT)

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
            kind="events",
            reflector_class=EventReflector,
            fields={"involvedObject.kind": "Pod"},
            omit_namespace=self.enable_user_namespaces,
            replace=replace,
        )

    def _start_watching_pods(self, replace=False):
        """Start the pod reflector

        If replace=False and the pod reflector is already running,
        do nothing.

        If replace=True, a running pod reflector will be stopped
        and a new one started (for recovering from possible errors).
        """
        pod_reflector_class = PodReflector
        pod_reflector_class.labels.update({"component": self.component_label})
        return self._start_reflector(
            "pods",
            PodReflector,
            omit_namespace=self.enable_user_namespaces,
            replace=replace,
        )

    # record a future for the call to .start()
    # so we can use it to terminate .progress()
    def start(self):
        """Thin wrapper around self._start

        so we can hold onto a reference for the Future
        start returns, which we can use to terminate
        .progress()
        """
        self._start_future = asyncio.ensure_future(self._start())
        return self._start_future

    _last_event = None

    async def _make_create_pod_request(self, pod, request_timeout):
        """
        Make an HTTP request to create the given pod

        Designed to be used with exponential_backoff, so returns
        True / False on success / failure
        """
        try:
            self.log.info(
                f"Attempting to create pod {pod.metadata.name}, with timeout {request_timeout}"
            )
            # Use tornado's timeout, _request_timeout seems unreliable?
            await gen.with_timeout(
                timedelta(seconds=request_timeout),
                self.asynchronize(
                    self.api.create_namespaced_pod,
                    self.namespace,
                    pod,
                ),
            )
            return True
        except gen.TimeoutError:
            # Just try again
            return False
        except ApiException as e:
            pod_name = pod.metadata.name
            if e.status != 409:
                # We only want to handle 409 conflict errors
                self.log.exception("Failed for %s", pod.to_str())
                raise
            self.log.info(f'Found existing pod {pod_name}, attempting to kill')
            # TODO: this should show up in events
            await self.stop(True)

            self.log.info(
                f'Killed pod {pod_name}, will try starting singleuser pod again'
            )
            # We tell exponential_backoff to retry
            return False

    async def _make_create_pvc_request(self, pvc, request_timeout):
        # Try and create the pvc. If it succeeds we are good. If
        # returns a 409 indicating it already exists we are good. If
        # it returns a 403, indicating potential quota issue we need
        # to see if pvc already exists before we decide to raise the
        # error for quota being exceeded. This is because quota is
        # checked before determining if the PVC needed to be
        # created.
        pvc_name = pvc.metadata.name
        try:
            self.log.info(
                f"Attempting to create pvc {pvc.metadata.name}, with timeout {request_timeout}"
            )
            await gen.with_timeout(
                timedelta(seconds=request_timeout),
                self.asynchronize(
                    self.api.create_namespaced_persistent_volume_claim,
                    namespace=self.namespace,
                    body=pvc,
                ),
            )
            return True
        except gen.TimeoutError:
            # Just try again
            return False
        except ApiException as e:
            if e.status == 409:
                self.log.info(
                    "PVC " + pvc_name + " already exists, so did not create new pvc."
                )
                return True
            elif e.status == 403:
                t, v, tb = sys.exc_info()

                try:
                    await self.asynchronize(
                        self.api.read_namespaced_persistent_volume_claim,
                        name=pvc_name,
                        namespace=self.namespace,
                    )

                except ApiException as e:
                    raise v.with_traceback(tb)

                self.log.info(
                    "PVC "
                    + self.pvc_name
                    + " already exists, possibly have reached quota though."
                )
                return True
            else:
                raise

    async def _ensure_not_exists(self, kind, name):
        """Ensure a resource does not exist

        Request deletion and wait for it to be gone

        Designed to be used with exponential_backoff, so returns
        True when the resource no longer exists, False otherwise
        """
        delete = getattr(self.api, "delete_namespaced_{}".format(kind))
        read = getattr(self.api, "read_namespaced_{}".format(kind))

        # first, attempt to delete the resource
        try:
            self.log.info(f"Deleting {kind}/{name}")
            await gen.with_timeout(
                timedelta(seconds=self.k8s_api_request_timeout),
                self.asynchronize(delete, namespace=self.namespace, name=name),
            )
        except gen.TimeoutError:
            # Just try again
            return False
        except ApiException as e:
            if e.status == 404:
                self.log.info(f"{kind}/{name} is gone")
                # no such resource, delete successful
                return True
            self.log.exception("Error deleting {kind}/{name}: {e}")
            return False

        try:
            self.log.info(f"Checking for {kind}/{name}")
            await gen.with_timeout(
                timedelta(seconds=self.k8s_api_request_timeout),
                self.asynchronize(read, namespace=self.namespace, name=name),
            )
        except gen.TimeoutError:
            # Just try again
            return False
        except ApiException as e:
            if e.status == 404:
                self.log.info(f"{kind}/{name} is gone")
                return True
            self.log.exception("Error reading {kind}/{name}: {e}")
            return False
        # if we got here, resource still exists, try again
        return False

    async def _make_create_resource_request(self, kind, manifest):
        """Make an HTTP request to create the given resource

        Designed to be used with exponential_backoff, so returns
        True / False on success / failure
        """
        create = getattr(self.api, f"create_namespaced_{kind}")
        self.log.info(f"Attempting to create {kind} {manifest.metadata.name}")
        try:
            # Use tornado's timeout, _request_timeout seems unreliable?
            await gen.with_timeout(
                timedelta(seconds=self.k8s_api_request_timeout),
                self.asynchronize(
                    create,
                    self.namespace,
                    manifest,
                ),
            )
        except gen.TimeoutError:
            # Just try again
            return False
        except ApiException as e:
            name = manifest.metadata.name
            if e.status == 409:
                self.log.info(f'Found existing {kind} {name}')
                return True
            # We only want to handle 409 conflict errors
            self.log.exception("Failed to create %s", manifest.to_str())
            raise
        else:
            return True

    async def _start(self):
        """Start the user's pod"""

        # load user options (including profile)
        await self.load_user_options()

        # If we have user_namespaces enabled, create the namespace.
        #  It's fine if it already exists.
        if self.enable_user_namespaces:
            await self._ensure_namespace()

        # record latest event so we don't include old
        # events from previous pods in self.events
        # track by order and name instead of uid
        # so we get events like deletion of a previously stale
        # pod if it's part of this spawn process
        events = self.events
        if events:
            self._last_event = events[-1]["metadata"]["uid"]

        if self.storage_pvc_ensure:
            pvc = self.get_pvc_manifest()

            # If there's a timeout, just let it propagate
            await exponential_backoff(
                partial(
                    self._make_create_pvc_request, pvc, self.k8s_api_request_timeout
                ),
                f'Could not create PVC {self.pvc_name}',
                # Each req should be given k8s_api_request_timeout seconds.
                timeout=self.k8s_api_request_retry_timeout,
            )

        # If we run into a 409 Conflict error, it means a pod with the
        # same name already exists. We stop it, wait for it to stop, and
        # try again. We try 4 times, and if it still fails we give up.
        pod = await self.get_pod_manifest()
        if self.modify_pod_hook:
            pod = await gen.maybe_future(self.modify_pod_hook(self, pod))

        ref_key = "{}/{}".format(self.namespace, self.pod_name)
        # If there's a timeout, just let it propagate
        await exponential_backoff(
            partial(self._make_create_pod_request, pod, self.k8s_api_request_timeout),
            f'Could not create pod {ref_key}',
            timeout=self.k8s_api_request_retry_timeout,
        )

        if self.internal_ssl:
            try:
                # wait for pod to have uid,
                # required for creating owner reference
                await exponential_backoff(
                    lambda: self.pod_has_uid(
                        self.pod_reflector.pods.get(ref_key, None)
                    ),
                    f"pod/{ref_key} does not have a uid!",
                )

                pod = self.pod_reflector.pods[ref_key]
                owner_reference = make_owner_reference(
                    self.pod_name, pod["metadata"]["uid"]
                )

                # internal ssl, create secret object
                secret_manifest = self.get_secret_manifest(owner_reference)
                await exponential_backoff(
                    partial(
                        self._ensure_not_exists, "secret", secret_manifest.metadata.name
                    ),
                    f"Failed to delete secret {secret_manifest.metadata.name}",
                )
                await exponential_backoff(
                    partial(
                        self._make_create_resource_request, "secret", secret_manifest
                    ),
                    f"Failed to create secret {secret_manifest.metadata.name}",
                )

                service_manifest = self.get_service_manifest(owner_reference)
                await exponential_backoff(
                    partial(
                        self._ensure_not_exists,
                        "service",
                        service_manifest.metadata.name,
                    ),
                    f"Failed to delete service {service_manifest.metadata.name}",
                )
                await exponential_backoff(
                    partial(
                        self._make_create_resource_request, "service", service_manifest
                    ),
                    f"Failed to create service {service_manifest.metadata.name}",
                )
            except Exception:
                # cleanup on failure and re-raise
                await self.stop(True)
                raise

        # we need a timeout here even though start itself has a timeout
        # in order for this coroutine to finish at some point.
        # using the same start_timeout here
        # essentially ensures that this timeout should never propagate up
        # because the handler will have stopped waiting after
        # start_timeout, starting from a slightly earlier point.
        try:
            await exponential_backoff(
                lambda: self.is_pod_running(self.pod_reflector.pods.get(ref_key, None)),
                'pod %s did not start in %s seconds!' % (ref_key, self.start_timeout),
                timeout=self.start_timeout,
            )
        except TimeoutError:
            if ref_key not in self.pod_reflector.pods:
                # if pod never showed up at all,
                # restart the pod reflector which may have become disconnected.
                self.log.error(
                    "Pod %s never showed up in reflector, restarting pod reflector",
                    ref_key,
                )
                self.log.error("Pods: {}".format(self.pod_reflector.pods))
                self._start_watching_pods(replace=True)
            raise

        pod = self.pod_reflector.pods[ref_key]
        self.pod_id = pod["metadata"]["uid"]
        if self.event_reflector:
            self.log.debug(
                'pod %s events before launch: %s',
                ref_key,
                "\n".join(
                    [
                        "%s [%s] %s"
                        % (
                            event["lastTimestamp"] or event["eventTime"],
                            event["type"],
                            event["message"],
                        )
                        for event in self.events
                    ]
                ),
            )

        return self._get_pod_url(pod)

    async def _make_delete_pod_request(
        self, pod_name, delete_options, grace_seconds, request_timeout
    ):
        """
        Make an HTTP request to delete the given pod

        Designed to be used with exponential_backoff, so returns
        True / False on success / failure
        """
        ref_key = "{}/{}".format(self.namespace, pod_name)
        self.log.info("Deleting pod %s", ref_key)
        try:
            await gen.with_timeout(
                timedelta(seconds=request_timeout),
                self.asynchronize(
                    self.api.delete_namespaced_pod,
                    name=pod_name,
                    namespace=self.namespace,
                    body=delete_options,
                    grace_period_seconds=grace_seconds,
                ),
            )
            return True
        except gen.TimeoutError:
            return False
        except ApiException as e:
            if e.status == 404:
                self.log.warning(
                    "No pod %s to delete. Assuming already deleted.",
                    ref_key,
                )
                # If there isn't already a pod, that's ok too!
                return True
            else:
                raise

    async def _make_delete_pvc_request(self, pvc_name, request_timeout):
        """
        Make an HTTP request to delete the given PVC

        Designed to be used with exponential_backoff, so returns
        True / False on success / failure
        """
        self.log.info("Deleting pvc %s", pvc_name)
        try:
            await gen.with_timeout(
                timedelta(seconds=request_timeout),
                self.asynchronize(
                    self.api.delete_namespaced_persistent_volume_claim,
                    name=pvc_name,
                    namespace=self.namespace,
                ),
            )
            return True
        except gen.TimeoutError:
            return False
        except ApiException as e:
            if e.status == 404:
                self.log.warning(
                    "No pvc %s to delete. Assuming already deleted.",
                    pvc_name,
                )
                # If there isn't a PVC to delete, that's ok too!
                return True
            else:
                raise

    async def stop(self, now=False):
        delete_options = client.V1DeleteOptions()

        if now:
            grace_seconds = 0
        else:
            grace_seconds = self.delete_grace_period

        delete_options.grace_period_seconds = grace_seconds

        ref_key = "{}/{}".format(self.namespace, self.pod_name)
        await exponential_backoff(
            partial(
                self._make_delete_pod_request,
                self.pod_name,
                delete_options,
                grace_seconds,
                self.k8s_api_request_timeout,
            ),
            f'Could not delete pod {ref_key}',
            timeout=self.k8s_api_request_retry_timeout,
        )

        try:
            await exponential_backoff(
                lambda: self.pod_reflector.pods.get(ref_key, None) is None,
                'pod %s did not disappear in %s seconds!'
                % (ref_key, self.start_timeout),
                timeout=self.start_timeout,
            )
        except TimeoutError:
            self.log.error(
                "Pod %s did not disappear, restarting pod reflector", ref_key
            )
            self._start_watching_pods(replace=True)
            raise

    @default('env_keep')
    def _env_keep_default(self):
        return []

    _profile_list = None

    def _render_options_form(self, profile_list):
        self._profile_list = self._init_profile_list(profile_list)
        profile_form_template = Environment(loader=BaseLoader).from_string(
            self.profile_form_template
        )
        return profile_form_template.render(profile_list=self._profile_list)

    async def _render_options_form_dynamically(self, current_spawner):
        profile_list = await gen.maybe_future(self.profile_list(current_spawner))
        profile_list = self._init_profile_list(profile_list)
        return self._render_options_form(profile_list)

    @default('options_form')
    def _options_form_default(self):
        """
        Build the form template according to the `profile_list` setting.

        Returns:
            '' when no `profile_list` has been defined
            The rendered template (using jinja2) when `profile_list` is defined.
        """
        if not self.profile_list:
            return ''
        if callable(self.profile_list):
            return self._render_options_form_dynamically
        else:
            return self._render_options_form(self.profile_list)

    @default('options_from_form')
    def _options_from_form_default(self):
        return self._options_from_form

    def _options_from_form(self, formdata):
        """get the option selected by the user on the form

        This only constructs the user_options dict,
        it should not actually load any options.
        That is done later in `.load_user_options()`

        Args:
            formdata: user selection returned by the form

        To access to the value, you can use the `get` accessor and the name of the html element,
        for example::

            formdata.get('profile',[0])

        to get the value of the form named "profile", as defined in `form_template`::

            <select class="form-control" name="profile"...>
            </select>

        Returns:
            user_options (dict): the selected profile in the user_options form,
                e.g. ``{"profile": "cpus-8"}``
        """
        return {'profile': formdata.get('profile', [None])[0]}

    async def _load_profile(self, slug):
        """Load a profile by name

        Called by load_user_options
        """

        # find the profile
        default_profile = self._profile_list[0]
        for profile in self._profile_list:
            if profile.get('default', False):
                # explicit default, not the first
                default_profile = profile

            if profile['slug'] == slug:
                break
        else:
            if slug:
                # name specified, but not found
                raise ValueError(
                    "No such profile: %s. Options include: %s"
                    % (slug, ', '.join(p['slug'] for p in self._profile_list))
                )
            else:
                # no name specified, use the default
                profile = default_profile

        self.log.debug(
            "Applying KubeSpawner override for profile '%s'", profile['display_name']
        )
        kubespawner_override = profile.get('kubespawner_override', {})
        for k, v in kubespawner_override.items():
            if callable(v):
                v = v(self)
                self.log.debug(
                    ".. overriding KubeSpawner value %s=%s (callable result)", k, v
                )
            else:
                self.log.debug(".. overriding KubeSpawner value %s=%s", k, v)
            setattr(self, k, v)

    # set of recognised user option keys
    # used for warning about ignoring unrecognised options
    _user_option_keys = {
        'profile',
    }

    def _init_profile_list(self, profile_list):
        # generate missing slug fields from display_name
        for profile in profile_list:
            if 'slug' not in profile:
                profile['slug'] = slugify(profile['display_name'])

        return profile_list

    async def load_user_options(self):
        """Load user options from self.user_options dict

        This can be set via POST to the API or via options_from_form

        Only supported argument by default is 'profile'.
        Override in subclasses to support other options.
        """

        if self._profile_list is None:
            if callable(self.profile_list):
                profile_list = await gen.maybe_future(self.profile_list(self))
            else:
                profile_list = self.profile_list

            self._profile_list = self._init_profile_list(profile_list)

        selected_profile = self.user_options.get('profile', None)
        if self._profile_list:
            await self._load_profile(selected_profile)
        elif selected_profile:
            self.log.warning(
                "Profile %r requested, but profiles are not enabled", selected_profile
            )

        # help debugging by logging any option fields that are not recognized
        option_keys = set(self.user_options)
        unrecognized_keys = option_keys.difference(self._user_option_keys)
        if unrecognized_keys:
            self.log.warning(
                "Ignoring unrecognized KubeSpawner user_options: %s",
                ", ".join(map(str, sorted(unrecognized_keys))),
            )

    async def _ensure_namespace(self):
        ns = make_namespace(self.namespace)
        api = self.api
        try:
            await gen.with_timeout(
                timedelta(seconds=self.k8s_api_request_timeout),
                self.asynchronize(api.create_namespace, ns),
            )
        except ApiException as e:
            if e.status != 409:
                # It's fine if it already exists
                self.log.exception("Failed to create namespace %s", self.namespace)
                raise

    async def delete_forever(self):
        """Called when a user is deleted.

        This can do things like request removal of resources such as persistent storage.
        Only called on stopped spawners, and is likely the last action ever taken for the user.

        Called on each spawner after deletion,
        i.e. on named server deletion (not just stop),
        and on the default Spawner when the user is being deleted.

        Requires JupyterHub 1.4.1+

        .. versionadded: 0.17
        """
        log_name = self.user.name
        if self.name:
            log_name = f"{log_name}/{self.name}"

        if not self.delete_pvc:
            self.log.info(f"Not deleting pvc for {log_name}: {self.pvc_name}")
            return

        if self.name and '{servername}' not in self.pvc_name_template:
            # named server has the same PVC as the default server
            # don't delete the default server's PVC!
            self.log.info(
                f"Not deleting shared pvc for named server {log_name}: {self.pvc_name}"
            )
            return

        await exponential_backoff(
            partial(
                self._make_delete_pvc_request,
                self.pvc_name,
                self.k8s_api_request_timeout,
            ),
            f'Could not delete pvc {self.pvc_name}',
            timeout=self.k8s_api_request_retry_timeout,
        )
