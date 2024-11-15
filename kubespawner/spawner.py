"""
JupyterHub Spawner to spawn user notebooks on a Kubernetes cluster.

This module exports `KubeSpawner` class, which is the actual spawner
implementation that should be used by JupyterHub.
"""

import asyncio
import copy
import ipaddress
import os
import re
import string
import sys
import warnings
from functools import partial
from typing import Optional, Tuple, Type
from urllib.parse import urlparse

import jupyterhub
from jinja2 import ChoiceLoader, Environment, FileSystemLoader, PackageLoader
from jupyterhub.spawner import Spawner
from jupyterhub.traitlets import Callable, Command
from jupyterhub.utils import exponential_backoff, maybe_future
from kubernetes_asyncio import client
from kubernetes_asyncio.client.rest import ApiException
from slugify import slugify
from traitlets import (
    Bool,
    Dict,
    Enum,
    Integer,
    List,
    Unicode,
    Union,
    default,
    observe,
    validate,
)

from . import __version__
from .clients import load_config, shared_client
from .objects import (
    make_namespace,
    make_owner_reference,
    make_pod,
    make_pvc,
    make_secret,
    make_service,
)
from .reflector import ResourceReflector
from .slugs import escape_slug, is_valid_label, multi_slug, safe_slug
from .utils import recursive_format, recursive_update


class PodReflector(ResourceReflector):
    """
    PodReflector is merely a configured ResourceReflector. It exposes
    the pods property, which is simply mapping to self.resources where the
    ResourceReflector keeps an updated list of the resource defined by
    the `kind` field and the `list_method_name` field.
    """

    kind = "pods"

    @property
    def pods(self):
        """
        A dictionary of pods for the namespace as returned by the Kubernetes
        API. The dictionary keys are the pod ids and the values are
        dictionaries of the actual pod resource values.

        ref: https://kubernetes.io/docs/reference/generated/kubernetes-api/v1.28/#pod-v1-core
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

        ref: https://kubernetes.io/docs/reference/generated/kubernetes-api/v1.28/#event-v1-core
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


class MockObject:
    pass


class KubeSpawner(Spawner):
    """
    A JupyterHub spawner that spawn pods in a Kubernetes Cluster. Each server
    spawned by a user will have its own KubeSpawner instance.
    """

    # Reflectors keeping track of the k8s api-server's state for various k8s
    # resources are singletons as that state can be tracked and shared by all
    # KubeSpawner objects.
    reflectors = {}

    # Characters as defined by safe for DNS
    # Note: '-' is not in safe_chars, as it is being used as escape character
    safe_chars = set(string.ascii_lowercase + string.digits)

    def _get_reflector_key(self, kind: str) -> Tuple[str, str, Optional[str]]:
        if self.enable_user_namespaces:
            # one reflector fo all namespaces
            return (kind, None)

        return (kind, self.namespace)

    @property
    def pod_reflector(self):
        """
        Returns instance of ResourceReflector for pods.
        """
        key = self._get_reflector_key('pods')
        return self.__class__.reflectors.get(key, None)

    @property
    def event_reflector(self):
        """
        Returns instance of ResourceReflector for events, if the
        spawner instance has events_enabled.
        """
        if self.events_enabled:
            key = self._get_reflector_key('events')
            return self.__class__.reflectors.get(key, None)
        return None

    def __init__(self, *args, **kwargs):
        _mock = kwargs.pop('_mock', False)
        super().__init__(*args, **kwargs)

        if _mock:
            # runs during test execution only
            if 'user' not in kwargs:
                user = MockObject()
                user.name = 'mock@name'
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
        # before we start the reflectors, so this must run before
        # watcher start in normal execution.  We still want to get the
        # namespace right for test, though, so we need self.user to have
        # been set in order to do that.

        # By now, all the traitlets have been set, so we can use them to
        # compute other attributes

        # namespace, pod_name, etc. are persisted in state
        # so values set here are only _default_ values.
        # If this Spawner has ever launched before,
        # these values will be be overridden in `get_state()`
        #
        # these same assignments should match clear_state
        # for transitive values (pod_name, dns_name)
        # but not persistent values (namespace, pvc_name)
        if self.enable_user_namespaces:
            self.namespace = self._expand_user_properties(self.user_namespace_template)
            self.log.info(f"Using user namespace: {self.namespace}")

        self.pod_name = self._expand_user_properties(self.pod_name_template)
        self.dns_name = self.dns_name_template.format(
            namespace=self.namespace, name=self.pod_name
        )

        self.secret_name = self._expand_user_properties(self.secret_name_template)

        self.pvc_name = self._expand_user_properties(self.pvc_name_template)
        # _pvc_exists indicates whether we've checked at least once that our pvc name is right
        # only persist pvc name in state if pvc exists
        self._pvc_exists = False  # initialized from load_state or start
        if self.working_dir:
            self.working_dir = self._expand_user_properties(self.working_dir)
        if self.port == 0:
            # Our default port is 8888
            self.port = 8888
        # The attribute needs to exist, even though it is unset to start with
        self._start_future = None

        load_config(
            host=self.k8s_api_host,
            ssl_ca_cert=self.k8s_api_ssl_ca_cert,
            verify_ssl=self.k8s_api_verify_ssl,
        )
        self.api = shared_client("CoreV1Api")

    k8s_api_verify_ssl = Bool(
        None,
        allow_none=True,
        config=True,
        help="""
        Verify TLS certificates when connecting to the k8s master.
        
        Set this to false to skip verifying SSL certificate when calling API
        from https server.
        """,
    )

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
        config=True,
        help="""
        DEPRECATED in KubeSpawner 3.0.0.

        No longer has any effect, as there is no threadpool anymore.
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

    slug_scheme = Enum(
        default_value="safe",
        values=["safe", "escape"],
        config=True,
        help="""Select the scheme for producing slugs such as pod names, etc.

        Can be 'safe' or 'escape'.

        'escape' is the legacy scheme, used in kubespawner < 7.
        Pick this to minimize changes when upgrading from kubespawner 6.
        
        The way templates are computed is different between the two schemes:
        
        'escape' scheme:
        
        - does not guarantee correct names, e.g. does not handle capital letters or length
        
        'safe' scheme:
        
        - should guarantee correct names
        - escapes only if needed
        - enforces length requirements
        - uses hash to avoid collisions when escaping is required

        'safe' is the default and preferred as it produces both:

        - better values, where possible (no `-2d` inserted to escape hyphens)
        - always valid names, avoiding issues where escaping produced invalid names,
          stripping characters and appending hashes where needed for names
          that are not already valid.

        .. versionadded:: 7
        """,
    )

    user_namespace_labels = Dict(
        config=True,
        help="""
        Kubernetes labels that user namespaces will get (only if
        enable_user_namespaces is True).

        Note that these are only set when the namespaces are created, not
        later when this setting is updated.

        .. seealso::

          :ref:`templates` for information on fields available in template strings.

        """,
    )

    user_namespace_annotations = Dict(
        config=True,
        help="""
        Kubernetes annotations that user namespaces will get (only if
        enable_user_namespaces is True).

        Note that these are only set when the namespaces are created, not
        later when this setting is updated.

        .. seealso::

          :ref:`templates` for information on fields available in template strings.

        """,
    )

    user_namespace_template = Unicode(
        "{hubnamespace}-{username}",
        config=True,
        help="""
        Template to use to form the namespace of user's pods (only if
        enable_user_namespaces is True).

        .. seealso::

          :ref:`templates` for information on fields available in template strings.

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

    services_enabled = Bool(
        False,
        config=True,
        help="""
        Enable fronting the user pods with a kubernetes service.

        This is useful in cases when network rules don't allow direct traffic
        routing to pods in a cluster. Should be enabled when using jupyterhub
        with a service mesh like istio with mTLS enabled.
        """,
    )

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

        If `cmd` is set, it will be augmented with `spawner.get_args()`. This will override the `CMD` specified in the Docker image.
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

        .. seealso::

          :ref:`templates` for information on fields available in template strings.

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
        'jupyter-{user_server}',
        config=True,
        help="""
        Template to use to form the name of user's pods.

        This must be unique within the namespace the pods are being spawned
        in, so if you are running multiple jupyterhubs spawning in the
        same namespace, consider setting this to be something more unique.

        .. seealso::

          :ref:`templates` for information on fields available in template strings.

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

        e.g. `{pod_name}.notebooks.jupyterhub.svc.cluster.local`,

        .. seealso::

          :ref:`templates` for information on fields available in template strings.

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
        'claim-{user_server}',
        config=True,
        help="""
        Template to use to form the name of user's pvc.


        Trailing `-` characters are stripped for safe handling of empty server names (user default servers).

        This must be unique within the namespace the pvc are being spawned
        in, so if you are running multiple jupyterhubs spawning in the
        same namespace, consider setting this to be something more unique.

        .. seealso::

          :ref:`templates` for information on fields available in template strings.

        .. versionchanged:: 0.12
            `--` delimiter added to the template,
            where it was implicitly added to the `servername` field before.
            Additionally, `username--servername` delimiter was `-` instead of `--`,
            allowing collisions in certain circumstances.
        """,
    )

    remember_pvc_name = Bool(
        True,
        config=True,
        help="""
        Remember the PVC name across restarts and configuration changes.

        If True, once the PVC has been created, its name will be remembered and reused
        and changing pvc_name_template will have no effect on servers that have previously mounted PVCs.
        If False, changing pvc_name_template or slug_scheme may detatch servers from their PVCs.

        `False` is the behavior of kubespawner prior to version 7.
        """,
    )

    component_label = Unicode(
        'singleuser-server',
        config=True,
        help="""
        The value of the labels app.kubernetes.io/component and component, used
        to identify user pods kubespawner is to manage.

        This can be used to override the spawner behavior when dealing with
        multiple hub instances in the same namespace. Usually helpful for CI
        workflows.
        """,
    )

    secret_name_template = Unicode(
        '{pod_name}',
        config=True,
        help="""
        Template to use to form the name of user's secret.

        Default: same as `pod_name`. It is unlikely that this should be changed.
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
            'app.kubernetes.io/name': 'jupyterhub',
            'app.kubernetes.io/managed-by': 'kubespawner',
            # app and heritage are older variants of the modern
            # app.kubernetes.io labels
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

        .. seealso::

          :ref:`templates` for information on fields available in template strings.
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

        .. seealso::

          :ref:`templates` for information on fields available in template strings.

        """,
    )

    image = Unicode(
        'quay.io/jupyterhub/singleuser:latest',
        config=True,
        help="""
        Docker image to use for spawning user's containers.

        Defaults to `quay.io/jupyterhub/singleuser:latest`

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
        None,
        allow_none=True,
        config=True,
        help="""
        The image pull policy of the docker container specified in
        `image`.

        Defaults to `None`, which means it is omitted. This leads to it behaving
        like 'Always' when a tag is absent or 'latest', and 'IfNotPresent' when
        the tag is specified to be something else, per https://kubernetes.io/docs/concepts/containers/images/#imagepullpolicy-defaulting.
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
        if isinstance(proposal['value'], str):
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
        cloud providers. See `fsGroup <https://kubernetes.io/docs/reference/generated/kubernetes-api/v1.28/#podsecuritycontext-v1-core>`__
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
        <https://kubernetes.io/docs/reference/generated/kubernetes-api/v1.28/#securitycontext-v1-core>`__
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
        <https://kubernetes.io/docs/reference/generated/kubernetes-api/v1.28/#podsecuritycontext-v1-core>`__
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

    after_pod_created_hook = Callable(
        None,
        allow_none=True,
        config=True,
        help="""
        Callable to augment the Pod object after launching.

        Expects a callable that takes two parameters:

           1. The spawner object that is doing the spawning
           2. The Pod object that was launched

        This can be a coroutine if necessary. When set to none, no augmenting is done.

        This is very useful if you want to add some services or ingress to the pod after it is launched.
        Note that the spawner object can change between versions of KubeSpawner and JupyterHub,
        so be careful relying on this!
        """,
    )

    volumes = Union(
        trait_types=[
            List(),
            Dict(),
        ],
        config=True,
        help="""
        List of Kubernetes Volume specifications that will be mounted in the user pod,
        or a dictionary where the values specify the volume specifications.

        If provided as a list, this list will be directly added under `volumes` in
        the kubernetes pod spec

        If provided as a dictionary, the items will be sorted lexicographically by the dictionary keys
        and then the sorted values will be added to the `volumes` key. The keys of the
        dictionary can be any descriptive name for the volume specification.

        Each item (whether in the list or dictionary values) must be a dictionary with
        the following two keys:

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

        .. seealso::

          :ref:`templates` for information on fields available in template strings.

        """,
    )

    volume_mounts = Union(
        trait_types=[
            List(),
            Dict(),
        ],
        config=True,
        help="""
        List of paths on which to mount volumes in the user notebook's pod, or a dictionary
        where the values specify the paths to mount the volumes.

        If provided as a list, this list will be added directly to the values of the
        `volumeMounts` key under the user's container in the kubernetes pod spec.

        If provided as a dictionary, the items will be sorted lexicographically by the dictionary keys and
        then the sorted values will be added to the `volumeMounts` key. The keys of the
        dictionary can be any descriptive name for the volume mount.

        Each item (whether in the list or dictionary values) should be a dictionary with
        at least these two keys:

           - `mountPath` The path on the container in which we want to mount the volume.
           - `name` The name of the volume we want to mount, as specified in the `volumes` config.

        See `the Kubernetes documentation <https://kubernetes.io/docs/concepts/storage/volumes>`__
        for more information on how the `volumeMount` item works.

        .. seealso::

          :ref:`templates` for information on fields available in template strings.

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

    storage_extra_annotations = Dict(
        config=True,
        help="""
        Extra kubernetes annotations to set on the user PVCs.

        The keys and values specified here would be set as annotations on the PVCs
        created by kubespawner for the user. Note that these are only set
        when the PVC is created, not later when this setting is updated.

        See `the Kubernetes documentation <https://kubernetes.io/docs/concepts/overview/working-with-objects/annotations/>`__
        for more info on what annotations are and why you might want to use them!

        .. seealso::

          :ref:`templates` for information on fields available in template strings.

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

        .. seealso::

          :ref:`templates` for information on fields available in template strings.

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

        .. seealso::

          :ref:`templates` for information on fields available in template strings.

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

    init_containers = Union(
        trait_types=[
            List(),
            Dict(),
        ],
        config=True,
        help="""
        List or dictionary of initialization containers belonging to the pod.

        If provided as a list, this list will be directly added under `initContainers` in the kubernetes pod spec.
        If provided as a dictionary, the items will be sorted lexicographically by the dictionary keys and
        then the sorted values will be added to the `initContainers` key.

        Each item (whether in the list or dictionary values) must be a dictionary which follows the spec at
        `V1Container specification <https://kubernetes.io/docs/reference/generated/kubernetes-api/v1.28/#container-v1-core>`__

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

        Or as a dictionary::

            c.KubeSpawner.init_containers = {
                "01-iptables": {
                    "name": "init-iptables",
                    "image": "<image with iptables installed>",
                    "command": ["iptables", "-A", "OUTPUT", "-p", "tcp", "--dport", "80", "-d", "169.254.169.254", "-j", "DROP"],
                    "securityContext": {
                        "capabilities": {
                            "add": ["NET_ADMIN"]
                        }
                    }
                }
            }

        See `the Kubernetes documentation <https://kubernetes.io/docs/concepts/workloads/pods/init-containers/>`__
        for more info on what init containers are and why you might want to use them!

        To use this feature, Kubernetes version must be greater than 1.6.
        """,
    )

    extra_container_config = Dict(
        config=True,
        help="""
        Extra configuration (e.g. ``envFrom``) for notebook container which is not covered by other attributes.

        This dict will be directly merge into `container` of notebook server,
        so you should use the same structure. Each item in the dict must a field
        of the `V1Container specification <https://kubernetes.io/docs/reference/generated/kubernetes-api/v1.28/#container-v1-core>`__.


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
        which follows spec at https://kubernetes.io/docs/reference/generated/kubernetes-api/v1.28/#podspec-v1-core


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

    extra_containers = Union(
        trait_types=[
            List(),
            Dict(),
        ],
        config=True,
        help="""
        List or dictionary of containers belonging to the pod in addition to
        the container generated for the notebook server.

        If provided as a list, this list will be directly appended under `containers` in the kubernetes pod spec.
        If provided as a dictionary, the items will be sorted lexicographically by the dictionary keys and
        then the sorted values will be appended to the `containers` key.

        Each item (whether in the list or dictionary values) is container configuration
        which follows the spec at https://kubernetes.io/docs/reference/generated/kubernetes-api/v1.28/#container-v1-core

        One usage is setting crontab in a container to clean sensitive data with configuration below::

            c.KubeSpawner.extra_containers = [{
                "name": "crontab",
                "image": "supercronic",
                "command": ["/usr/local/bin/supercronic", "/etc/crontab"]
            }]

        or as a dictionary::

            c.KubeSpawner.extra_containers = {
                "01-crontab": {
                    "name": "crontab",
                    "image": "supercronic",
                    "command": ["/usr/local/bin/supercronic", "/etc/crontab"]
                }
            }

        .. seealso::

          :ref:`templates` for information on fields available in template strings.

        """,
    )

    handle_legacy_names = Bool(
        True,
        config=True,
        help="""handle legacy names and labels
        
        kubespawner 7 changed the scheme for computing names and labels to be more reliably valid.
        In order to preserve backward compatibility, the old names must be handled in some places.

        Currently, this only affects `pvc_name`
        and has no effect when `remember_pvc_name` is False.

        You can safely disable this if no PVCs were created or running servers were started
        before upgrading to kubespawner 7.
        """,
    )

    # FIXME: Don't override 'default_value' ("") or 'allow_none' (False) (Breaking change)
    scheduler_name = Unicode(
        None,
        allow_none=True,
        config=True,
        help="""
        Set the pod's scheduler explicitly by name. See `the Kubernetes documentation <https://kubernetes.io/docs/reference/generated/kubernetes-api/v1.28/#podspec-v1-core>`__
        for more information.
        """,
    )

    tolerations = Union(
        trait_types=[
            List(),
            Dict(),
        ],
        config=True,
        help="""
        List or dictionary of tolerations that are to be assigned to the pod in order to be able to schedule the pod
        on a node with the corresponding taints. See the official Kubernetes documentation for additional details
        https://kubernetes.io/docs/concepts/configuration/taint-and-toleration/

        If provided as a list, each item should be a "Toleration" object.
        If provided as a dictionary, the keys can be any descriptive name and the values should be "Toleration" objects.
        The items will be sorted lexicographically by the dictionary keys and the sorted values will be added to the pod spec.

        Each "Toleration" object should follow the specification at:
        https://kubernetes.io/docs/reference/generated/kubernetes-api/v1.28/#toleration-v1-core

        Example as a list::

            c.KubeSpawner.tolerations = [
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

        Example as a dictionary::

            c.KubeSpawner.tolerations = {
                "01-gpu-toleration": {
                    'key': 'gpu',
                    'operator': 'Equal',
                    'value': 'true',
                    'effect': 'NoSchedule'
                },
                "02-general-toleration": {
                    'key': 'key',
                    'operator': 'Exists',
                    'effect': 'NoSchedule'
                }
            }

        """,
    )

    node_affinity_preferred = Union(
        trait_types=[
            List(),
            Dict(),
        ],
        config=True,
        help="""
        List or dictionary of preferred node affinities.

        Affinities describe where pods prefer or require to be scheduled, they
        may prefer or require a node to have a certain label or be in proximity
        / remoteness to another pod. To learn more visit
        https://kubernetes.io/docs/concepts/configuration/assign-pod-node/

        If provided as a list, each item should be a "PreferredSchedulingTerm" object.
        If provided as a dictionary, the keys can be any descriptive name and the values should be "PreferredSchedulingTerm" objects.
        The items will be sorted lexicographically by the dictionary keys and the sorted values will be added to the pod spec.

        Each item should follow the `"PreferredSchedulingTerm" specification
        <https://kubernetes.io/docs/reference/generated/kubernetes-api/v1.28/#preferredschedulingterm-v1-core>`__.
        """,
    )

    node_affinity_required = Union(
        trait_types=[
            List(),
            Dict(),
        ],
        config=True,
        help="""
        List or dictionary of required node affinities.

        Affinities describe where pods prefer or require to be scheduled, they
        may prefer or require a node to have a certain label or be in proximity
        / remoteness to another pod. To learn more visit
        https://kubernetes.io/docs/concepts/configuration/assign-pod-node/

        If provided as a list, each item should be a "NodeSelectorTerm" object.
        If provided as a dictionary, the keys can be any descriptive name and the values should be "NodeSelectorTerm" objects.
        The items will be sorted lexicographically by the dictionary keys and the sorted values will be added to the pod spec.

        Each item should follow the `"NodeSelectorTerm" specification
        <https://kubernetes.io/docs/reference/generated/kubernetes-api/v1.28/#nodeselectorterm-v1-core>`__.
        """,
    )

    pod_affinity_preferred = Union(
        trait_types=[
            List(),
            Dict(),
        ],
        config=True,
        help="""
        List or dictionary of preferred pod affinities.

        Affinities describe where pods prefer or require to be scheduled, they
        may prefer or require a node to have a certain label or be in proximity
        / remoteness to another pod. To learn more visit
        https://kubernetes.io/docs/concepts/configuration/assign-pod-node/

        If provided as a list, each item should be a "WeightedPodAffinityTerm" object.
        If provided as a dictionary, the keys can be any descriptive name and the values should be "WeightedPodAffinityTerm" objects.
        The items will be sorted lexicographically by the dictionary keys and the sorted values will be added to the pod spec.

        Each item should follow the `"WeightedPodAffinityTerm" specification
        <https://kubernetes.io/docs/reference/generated/kubernetes-api/v1.28/#weightedpodaffinityterm-v1-core>`__.
        """,
    )

    pod_affinity_required = Union(
        trait_types=[
            List(),
            Dict(),
        ],
        config=True,
        help="""
        List or dictionary of required pod affinities.

        Affinities describe where pods prefer or require to be scheduled, they
        may prefer or require a node to have a certain label or be in proximity
        / remoteness to another pod. To learn more visit
        https://kubernetes.io/docs/concepts/configuration/assign-pod-node/

        If provided as a list, each item should be a "PodAffinityTerm" object.
        If provided as a dictionary, the keys can be any descriptive name and the values should be "PodAffinityTerm" objects.
        The items will be sorted lexicographically by the dictionary keys and the sorted values will be added to the pod spec.

        Each item should follow the `"PodAffinityTerm" specification
        <https://kubernetes.io/docs/reference/generated/kubernetes-api/v1.28/#podaffinityterm-v1-core>`__.
        """,
    )

    pod_anti_affinity_preferred = Union(
        trait_types=[
            List(),
            Dict(),
        ],
        config=True,
        help="""
        List or dictionary of preferred pod anti-affinities.

        Affinities describe where pods prefer or require to be scheduled, they
        may prefer or require a node to have a certain label or be in proximity
        / remoteness to another pod. To learn more visit
        https://kubernetes.io/docs/concepts/configuration/assign-pod-node/

        If provided as a list, each item should be a "WeightedPodAffinityTerm" object.
        If provided as a dictionary, the keys can be any descriptive name and the values should be "WeightedPodAffinityTerm" objects.
        The items will be sorted lexicographically by the dictionary keys and the sorted values will be added to the pod spec.

        Each item should follow the `"WeightedPodAffinityTerm" specification
        <https://kubernetes.io/docs/reference/generated/kubernetes-api/v1.28/#weightedpodaffinityterm-v1-core>`__.
        """,
    )

    pod_anti_affinity_required = Union(
        trait_types=[
            List(),
            Dict(),
        ],
        config=True,
        help="""
        List or dictionary of required pod anti-affinities.

        Affinities describe where pods prefer or require to be scheduled, they
        may prefer or require a node to have a certain label or be in proximity
        / remoteness to another pod. To learn more visit
        https://kubernetes.io/docs/concepts/configuration/assign-pod-node/

        If provided as a list, each item should be a "PodAffinityTerm" object.
        If provided as a dictionary, the keys can be any descriptive name and the values should be "PodAffinityTerm" objects.
        The items will be sorted lexicographically by the dictionary keys and the sorted values will be added to the pod spec.

        Each item should follow the `"PodAffinityTerm" specification
        <https://kubernetes.io/docs/reference/generated/kubernetes-api/v1.28/#podaffinityterm-v1-core>`__.
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

    additional_profile_form_template_paths = List(
        help="""
        Additional paths to search for jinja2 templates when rendering profile_form.

        These directories will be searched before the default `templates/` directory
        shipped with kubespawner with the default template.

        Any file named `form.html` in these directories will be used to render the
        profile options form.
        """,
        config=True,
    )

    profile_form_template = Unicode(
        "",
        config=True,
        help="""
        Literal Jinja2 template for constructing profile list shown to user.

        Used when `profile_list` is set.

        The contents of `profile_list` are passed in to the template.
        This should be used to construct the contents of a HTML form. When
        posted, this form is expected to have an item with name `profile` and
        the value the index of the profile in `profile_list`.

        When this traitlet is not set, the default template `form.html` from the
        directory `kubespawner/templates` is used. Admins can override this by
        setting the `additional_profile_form_template_paths` config to a directory
        with jinja2 templates, and any file named `form.html` in there will be used
        instead of the default.

        Using additional_profile_form_template_paths is recommended instead of
        this.
        """,
    )

    profile_list = Union(
        trait_types=[List(trait=Dict()), Callable()],
        config=True,
        help="""
        List of profiles to offer for selection by the user.

        Signature is: `List(Dict())`, where each item is a dictionary that has two keys:

        - `display_name`: the human readable display name (should be HTML safe)
        - `default`: (Optional Bool) True if this is the default selected option
        - `description`: Optional description of this profile displayed to the user.
        - `slug`: (Optional) the machine readable string to identify the
          profile (missing slugs are generated from display_name)
        - `kubespawner_override`: a dictionary with overrides to apply to the KubeSpawner
          settings. Each value can be either the final value to change or a callable that
          take the `KubeSpawner` instance as parameter and return the final value. This can
          be further overridden by 'profile_options'
          If the traitlet being overriden is a *dictionary*, the dictionary
          will be *recursively updated*, rather than overriden. If you want to
          remove a key, set its value to `None`
        - `profile_options`: A dictionary of sub-options that allow users to further customize the
          selected profile. By default, these are rendered as a dropdown with the label
          provided by `display_name`. Items should have a unique key representing the customization,
          and the value is a dictionary with the following keys:

          - `display_name`: Name used to identify this particular option
          - `unlisted_choice`: Object to specify if there should be a free-form field if the user
            selected "Other" as a choice:

            - `enabled`: Boolean, whether the free form input should be enabled
            - `display_name`: String, label for input field
            - `display_name_in_choices`: Optional, display name for the choice
              to specify an unlisted choice in the dropdown list of pre-defined
              choices. Defaults to "Other...".
            - `validation_regex`: Optional, regex that the free form input
              should match, eg. `^pangeo/.*$`.
            - `validation_message`: Optional, validation message for the regex.
              Should describe the required input format in a human-readable way.
            - `kubespawner_override`: a dictionary with overrides to apply to
              the KubeSpawner settings, where the string `{value}` will be
              substituted with what was filled in by the user if its found in
              string values anywhere in the dictionary. As an example, if the
              choice made is about an image tag for an image only to be used
              with JupyterLab, it could look like this:

              .. code-block:: python

                 {
                     "image_spec": "jupyter/datascience-notebook:{value}",
                     "default_url": "/lab",
                     "extra_labels: {
                        "user-specified-image-tag": "{value}",
                     },
                 }
          - `choices`: A dictionary containing list of choices for the user to choose from
            to set the value for this particular option. The key is an identifier for this
            choice, and the value is a dictionary with the following possible keys:

            - `display_name`: Human readable display name for this choice.
            - `default`: (optional Bool) True if this is the default selected choice
            - `kubespawner_override`: A dictionary with overrides to apply to the KubeSpawner
              settings, on top of whatever was applied with the `kubespawner_override` key
              for the profile itself. The key should be the name of the kubespawner setting,
              and value can be either the final value or a callable that returns the final
              value when called with the spawner instance as the only parameter. The callable
              may be async.
              If the traitlet being overriden is a *dictionary*, the dictionary
              will be *recursively updated*, rather than overriden. If you want to
              remove a key, set its value to `None`

        kubespawner setting overrides work in the following manner, with items further in the
        list *replacing* (not merging with) items earlier in the list:

        1. Settings directly set on KubeSpawner, via c.KubeSpawner.<traitlet_name>
        2. `kubespawner_override` in the profile the user has chosen
        3. `kubespawner_override` in the specific choices the user has made within the
           profile, applied linearly based on the ordering of the option in the profile
           definition configuration

        Example::

            c.KubeSpawner.profile_list = [
                {
                    'display_name': 'Demo - profile_list entry 1',
                    'description': 'Demo description for profile_list entry 1, and it should look good even though it is a bit lengthy.',
                    'slug': 'demo-1',
                    'default': True,
                    'profile_options': {
                        'image': {
                            'display_name': 'Image',
                            'choices': {
                                'base': {
                                    'display_name': 'jupyter/base-notebook:latest',
                                    'kubespawner_override': {
                                        'image': 'jupyter/base-notebook:latest'
                                    },
                                },
                                'minimal': {
                                    'display_name': 'jupyter/minimal-notebook:latest',
                                    'default': True,
                                    'kubespawner_override': {
                                        'image': 'jupyter/minimal-notebook:latest'
                                    },
                                },
                            },
                            'unlisted_choice': {
                                'enabled': True,
                                'display_name': 'Other image',
                                'display_name_in_choices': 'Enter image manually',
                                'validation_regex': '^jupyter/.+:.+$',
                                'validation_message': 'Must be an image matching ^jupyter/<name>:<tag>$',
                                'kubespawner_override': {'image': '{value}'},
                            },
                        },
                    },
                    'kubespawner_override': {
                        'default_url': '/lab',
                    },
                },
                {
                    'display_name': 'Demo - profile_list entry 2',
                    'slug': 'demo-2',
                    'kubespawner_override': {
                        'extra_resource_guarantees': {"nvidia.com/gpu": "1"},
                    },
                },
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

    def _expand_user_properties(self, template, slug_scheme=None):
        if slug_scheme is None:
            slug_scheme = self.slug_scheme

        raw_servername = self.name or ''
        escaped_servername = escape_slug(raw_servername)

        # TODO: measure string template?
        # for object names, max is 255, so very unlikely to exceed
        # but labels are only 64, so adding a few fields together could easily exceed length limit
        # if the per-field limit is more than half the whole budget
        # for now, recommend {user_server} anywhere both username and servername are desired
        _slug_max_length = 48

        if raw_servername:
            safe_servername = safe_slug(raw_servername, max_length=_slug_max_length)
        else:
            safe_servername = ""

        username = raw_username = self.user.name
        safe_username = safe_slug(raw_username, max_length=_slug_max_length)

        # compute safe_user_server = {username}--{servername}
        if (
            # double-escape if safe names are too long after join
            len(safe_username) + len(safe_servername) + 2
            > _slug_max_length
        ):
            # need double-escape if there's a chance of collision
            safe_user_server = multi_slug(
                [username, raw_servername], max_length=_slug_max_length
            )
        else:
            if raw_servername:
                # choices:
                # - {safe_username}--{safe_servername}  # could get 2 hashes
                # - always {multi_slug}  # always a hash for named servers
                # - safe_slug({username}--{servername})  # lots of possible collisions to handle specially
                safe_user_server = f"{safe_username}--{safe_servername}"
            else:
                safe_user_server = safe_username

        hub_namespace = self._namespace_default()
        if hub_namespace == "default":
            hub_namespace = "user"

        escaped_username = escape_slug(self.user.name)

        if slug_scheme == "safe":
            username = safe_username
            servername = safe_servername
            user_server = safe_user_server
        elif slug_scheme == "escape":
            # backward-compatible 'escape' scheme is not safe
            username = escaped_username
            servername = escaped_servername
            if servername:
                user_server = f"{escaped_username}--{escaped_servername}"
            else:
                user_server = escaped_username
        else:
            raise ValueError(
                f"slug scheme must be 'safe' or 'escape', not '{slug_scheme}'"
            )

        ns = dict(
            # raw values, always consistent
            userid=self.user.id,
            unescaped_username=self.user.name,
            unescaped_servername=raw_servername,
            hubnamespace=hub_namespace,
            # scheme-dependent
            username=username,
            servername=servername,
            user_server=user_server,
            # safe values (new 'safe' scheme)
            safe_username=safe_username,
            safe_servername=safe_servername,
            safe_user_server=safe_user_server,
            # legacy values (old 'escape' scheme)
            escaped_username=escaped_username,
            escaped_servername=escaped_servername,
            escaped_user_server=f"{escaped_username}--{escaped_servername}",
        )
        # add some resolved values so they can be referred to.
        # these may not be defined yet (i.e. when computing the values themselves).
        for attr_name in ("pod_name", "pvc_name", "namespace"):
            ns[attr_name] = getattr(self, attr_name, f"{attr_name}_unavailable!")

        rendered = template.format(**ns)
        # strip trailing - delimiter in case of empty servername and old {username}--{servername} template
        # but only if trailing '-' is added by the template rendering,
        # and not in the template itself
        if not template.endswith("-"):
            rendered = rendered.rstrip("-")
        return rendered

    def _expand_env(self, env):
        # environment expansion requires special handling because the parent class
        # may have also modified it, e.g. by evaluating a callable
        expanded_env = {}
        for k, v in env.items():
            if isinstance(v, (list, dict, str)):
                expanded_env[k] = self._expand_all(v)
            # else do nothing- this will be merged with the parent env
            # by the caller so by omitting the key we keep the parent value
        return expanded_env

    def _expand_all(self, src):
        if isinstance(src, list):
            return [self._expand_all(i) for i in src]
        elif isinstance(src, dict):
            return {k: self._expand_all(v) for k, v in src.items()}
        elif isinstance(src, str):
            return self._expand_user_properties(src)
        else:
            return src

    def _sorted_dict_values(self, src):
        """
        Return a list of dict values sorted by keys if src is a dict, otherwise return src as-is.
        """
        if isinstance(src, dict):
            return [src[key] for key in sorted(src.keys())]
        else:
            return src

    def _build_common_labels(self, extra_labels):
        # Default set of labels, picked up from
        # https://github.com/helm/helm-www/blob/HEAD/content/en/docs/chart_best_practices/labels.md
        labels = {
            'hub.jupyter.org/username': safe_slug(
                self.user.name, is_valid=is_valid_label
            ),
        }
        labels.update(extra_labels)
        labels.update(self.common_labels)
        return labels

    def _build_pod_labels(self, extra_labels):
        labels = self._build_common_labels(extra_labels)
        labels.update(
            {
                'app.kubernetes.io/component': self.component_label,
                'component': self.component_label,
                'hub.jupyter.org/servername': safe_slug(
                    self.name, is_valid=is_valid_label
                ),
            }
        )
        return labels

    def _build_common_annotations(self, extra_annotations):
        # Annotations don't need to be escaped
        annotations = {'hub.jupyter.org/username': self.user.name}
        if self.name:
            annotations['hub.jupyter.org/servername'] = self.name
        annotations["hub.jupyter.org/kubespawner-version"] = __version__
        annotations["hub.jupyter.org/jupyterhub-version"] = jupyterhub.__version__

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

        Default: use pod.status.pod_ip (dns_name if ssl or services_enabled is enabled)
        """
        if self.get_pod_url:
            # custom get_pod_url hook
            return self.get_pod_url(self, pod)

        if getattr(self, "internal_ssl", False):
            proto = "https"
            hostname = self.dns_name
        elif getattr(self, "services_enabled", False):
            proto = "http"
            hostname = self.dns_name
        else:
            proto = "http"
            hostname = pod["status"]["podIP"]
            if isinstance(ipaddress.ip_address(hostname), ipaddress.IPv6Address):
                hostname = f"[{hostname}]"

        if self.pod_connect_ip:
            # pod_connect_ip is not a slug
            hostname = ".".join(
                [
                    self._expand_user_properties(s) if '{' in s else s
                    for s in self.pod_connect_ip.split(".")
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
            uid = await maybe_future(self.uid(self))
        else:
            uid = self.uid

        if callable(self.gid):
            gid = await maybe_future(self.gid(self))
        else:
            gid = self.gid

        if callable(self.fs_gid):
            fs_gid = await maybe_future(self.fs_gid(self))
        else:
            fs_gid = self.fs_gid

        if callable(self.supplemental_gids):
            supplemental_gids = await maybe_future(self.supplemental_gids(self))
        else:
            supplemental_gids = self.supplemental_gids

        if callable(self.container_security_context):
            csc = await maybe_future(self.container_security_context(self))
        else:
            csc = self.container_security_context

        if callable(self.pod_security_context):
            psc = await maybe_future(self.pod_security_context(self))
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
            env=self.get_env(),  # Expansion is handled by get_env
            volumes=self._expand_all(self._sorted_dict_values(self.volumes)),
            volume_mounts=self._expand_all(
                self._sorted_dict_values(self.volume_mounts)
            ),
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
            init_containers=self._expand_all(
                self._sorted_dict_values(self.init_containers)
            ),
            service_account=self._expand_all(self.service_account),
            automount_service_account_token=self.automount_service_account_token,
            extra_container_config=self.extra_container_config,
            extra_pod_config=self._expand_all(self.extra_pod_config),
            extra_containers=self._expand_all(
                self._sorted_dict_values(self.extra_containers)
            ),
            scheduler_name=self.scheduler_name,
            tolerations=self._sorted_dict_values(self.tolerations),
            node_affinity_preferred=self._sorted_dict_values(
                self.node_affinity_preferred
            ),
            node_affinity_required=self._sorted_dict_values(
                self.node_affinity_required
            ),
            pod_affinity_preferred=self._sorted_dict_values(
                self.pod_affinity_preferred
            ),
            pod_affinity_required=self._sorted_dict_values(self.pod_affinity_required),
            pod_anti_affinity_preferred=self._sorted_dict_values(
                self.pod_anti_affinity_preferred
            ),
            pod_anti_affinity_required=self._sorted_dict_values(
                self.pod_anti_affinity_required
            ),
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
        selector = self._build_pod_labels(self._expand_all(self.extra_labels))

        # TODO: validate that the service name
        return make_service(
            name=self.pod_name,
            port=self.port,
            selector=selector,
            owner_references=[owner_reference],
            labels=labels,
            annotations=annotations,
        )

    def get_pvc_manifest(self):
        """
        Make a pvc manifest that will spawn current user's pvc.
        """
        labels = self._build_common_labels(self._expand_all(self.storage_extra_labels))
        labels.update(
            {
                # The component label has been set to singleuser-storage, but should
                # probably have been set to singleuser-server (self.component_label)
                # as that ties it to the user pods kubespawner creates. Due to that,
                # the newly introduced label app.kubernetes.io/component gets
                # singleuser-server (self.component_label) as a value instead.
                'app.kubernetes.io/component': self.component_label,
                'component': 'singleuser-storage',
            }
        )

        annotations = self._build_common_annotations(
            self._expand_all(self.storage_extra_annotations)
        )

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

        `pod_name` is saved as `pod_template` can change between hub restarts,
        and we do not want to lose track of the old pods when that happens.

        We also save the namespace and DNS name for use cases where the namespace is
        calculated dynamically, or it changes between restarts.

        `pvc_name` is also saved, to prevent data loss if template changes across restarts.
        """
        state = super().get_state()
        state["kubespawner_version"] = __version__
        # pod_name, dns_name should only be persisted if our pod is running
        # but we don't have a sync check for that
        # is that true for namespace as well? (namespace affects pvc)
        state['pod_name'] = self.pod_name
        state['namespace'] = self.namespace
        state['dns_name'] = self.dns_name

        # persist pvc name only if it's established that it exists
        # ignore 'remember_pvc_name' config here so the info is available
        # so future calls to load_state can decide whether to use it or not
        if self._pvc_exists:
            state['pvc_name'] = self.pvc_name
        return state

    def get_env(self):
        """Return the environment dict to use for the Spawner.

        See also: jupyterhub.Spawner.get_env
        """

        env = super().get_env()
        # deprecate image
        env['JUPYTER_IMAGE_SPEC'] = self.image
        env['JUPYTER_IMAGE'] = self.image

        # Explicitly expand *and* set all the admin specified variables only.
        # This allows JSON-like strings set by JupyterHub itself to not be
        # expanded. https://github.com/jupyterhub/kubespawner/issues/743
        env.update(self._expand_env(self.environment))

        return env

    # remember version of kubespawner that state was loaded from
    _state_kubespawner_version = None

    def load_state(self, state):
        """
        Load state from storage required to reinstate this user's pod

        Since this runs after `__init__`, this will override the generated `pod_name`
        if there's one we have saved in state. These are the same in most cases,
        but if the `pod_template` has changed in between restarts, it will no longer
        be the case. This allows us to continue serving from the old pods with
        the old names.

        For a similar reason, we also save the namespace, dns name, pvc name.
        Anything where changing a template may break something after Hub restart
        should be persisted here.
        """
        if 'pod_name' in state:
            self.pod_name = state['pod_name']

        if 'namespace' in state:
            self.namespace = state['namespace']

        if 'dns_name' in state:
            self.dns_name = state['dns_name']

        if 'pvc_name' in state and self.remember_pvc_name:
            self.pvc_name = state['pvc_name']
            # indicate that we've already checked that self.pvc_name is correct
            # and we don't need to check for legacy names anymore
            self._pvc_exists = True

        if 'kubespawner_version' in state:
            self._state_kubespawner_version = state["kubespawner_version"]
        elif state:
            self.log.warning(
                f"Loading state for {self.user.name}/{self.name} from unknown prior version of kubespawner (likely 6.x), will attempt to upgrade."
            )
            # if there was any state to load, we assume 'unknown' version
            # (most likely 6.x, prior to 'safe' slug scheme)
            self._state_kubespawner_version = "unknown"
        else:
            # None means no state loaded (i.e. fresh launch)
            self._state_kubespawner_version = None

    def clear_state(self):
        """Reset state for a stopped server

        This should reset all state values to new values,
        except those that should persist across Spawner restarts (e.g. pvc_name)
        """
        super().clear_state()
        # this should be the same initialization as __init__ / trait defaults
        # this allows changing config to take effect after a server restart
        self.pod_name = self._expand_user_properties(self.pod_name_template)
        self.dns_name = self.dns_name_template.format(
            namespace=self.namespace, name=self.pod_name
        )
        # reset namespace as well?

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
        await self._start_watching_pods()

        ref_key = f"{self.namespace}/{self.pod_name}"
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
        ref: https://kubernetes.io/docs/reference/generated/kubernetes-api/v1.28/#event-v1-core
        """

        if not self.events_enabled:
            return

        await self._start_watching_events()

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

    async def _start_reflector(
        self,
        kind: str,
        reflector_class: Type[ResourceReflector],
        replace: bool = False,
        **kwargs,
    ):
        """Start a shared reflector on the KubeSpawner class

        kind: used to generate key to store reflector shared instance (e.g. 'pod' or 'events')
        reflector_class: Reflector class to be instantiated
        kwargs: extra keyword-args to be relayed to ReflectorClass

        If replace=False and the pod reflector is already running,
        do nothing.

        If replace=True, a running pod reflector will be stopped
        and a new one started (for recovering from possible errors).
        """

        key = self._get_reflector_key(kind)
        previous_reflector = self.__class__.reflectors.get(key, None)

        if previous_reflector and not replace:
            # fast path
            if not previous_reflector.first_load_future.done():
                # make sure it's loaded, so subsequent calls to start_reflector
                # don't finish before the first
                await previous_reflector.first_load_future
            return previous_reflector

        if self.enable_user_namespaces:
            # Create one reflector for all namespaces.
            # This requires binding ServiceAccount to ClusterRole.

            def on_reflector_failure():
                # If reflector cannot be started, halt the JH application.
                self.log.critical(
                    "Reflector with key %r failed, halting Hub.",
                    key,
                )
                sys.exit(1)

            async def catch_reflector_start(func):
                try:
                    await func
                except Exception:
                    self.log.exception(f"Reflector with key {key} failed to start.")
                    sys.exit(1)

        else:
            # Create a dedicated reflector for each namespace.
            # This allows JH to run pods in multiple namespaces without binding ServiceAccount to ClusterRole.

            on_reflector_failure = None

            async def catch_reflector_start(func):
                # If reflector cannot be started (e.g. insufficient access rights, namespace cannot be found),
                # just raise an exception instead halting the entire JH application.
                try:
                    await func
                except Exception:
                    self.log.exception(f"Reflector with key {key} failed to start.")
                    raise

        self.__class__.reflectors[key] = current_reflector = reflector_class(
            parent=self,
            namespace=self.namespace,
            on_failure=on_reflector_failure,
            **kwargs,
        )
        await catch_reflector_start(current_reflector.start())

        if previous_reflector:
            # we replaced the reflector, stop the old one
            await asyncio.ensure_future(previous_reflector.stop())

        # wait for first load
        await current_reflector.first_load_future

        # return the current reflector
        return current_reflector

    async def _start_watching_events(self, replace=False):
        """Start the events reflector

        If replace=False and the event reflector is already running,
        do nothing.

        If replace=True, a running pod reflector will be stopped
        and a new one started (for recovering from possible errors).
        """
        return await self._start_reflector(
            kind="events",
            reflector_class=EventReflector,
            fields={"involvedObject.kind": "Pod"},
            omit_namespace=self.enable_user_namespaces,
            replace=replace,
        )

    async def _start_watching_pods(self, replace=False):
        """Start the pods reflector

        If replace=False and the pod reflector is already running,
        do nothing.

        If replace=True, a running pod reflector will be stopped
        and a new one started (for recovering from possible errors).
        """
        return await self._start_reflector(
            kind="pods",
            reflector_class=PodReflector,
            # NOTE: We monitor resources with the old component label instead of
            #       the modern app.kubernetes.io/component label. A change here
            #       is only non-breaking if we can assume the running resources
            #       monitored can be detected by either old or new labels.
            #
            #       The modern labels were added to resources created by
            #       KubeSpawner 7 first adopted in z2jh 4.0.
            #
            #       Related to https://github.com/jupyterhub/kubespawner/issues/834
            #
            labels={"component": self.component_label},
            omit_namespace=self.enable_user_namespaces,
            replace=replace,
        )

    @classmethod
    async def _stop_all_reflectors(cls):
        """Stop reflectors for all instances, a function used when running tests."""
        tasks = []
        for key in list(cls.reflectors.keys()):
            reflector = cls.reflectors.pop(key)
            tasks.append(reflector.stop())

        # make sure all tasks are Futures so we can cancel them later
        # in case of error
        futures = [asyncio.ensure_future(task) for task in tasks]
        try:
            await asyncio.gather(*futures)
        except Exception:
            # cancel any unfinished tasks before re-raising
            # because gather doesn't cancel unfinished tasks.
            # TaskGroup would do this cancel for us, but requires Python 3.11
            for future in futures:
                if not future.done():
                    future.cancel()
            raise

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
            await asyncio.wait_for(
                self.api.create_namespaced_pod(
                    self.namespace,
                    pod,
                ),
                request_timeout,
            )
            return True
        except asyncio.TimeoutError:
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
            await asyncio.wait_for(
                self.api.create_namespaced_persistent_volume_claim(
                    namespace=self.namespace,
                    body=pvc,
                ),
                request_timeout,
            )
            return True
        except asyncio.TimeoutError:
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
                    await self.api.read_namespaced_persistent_volume_claim(
                        name=pvc_name,
                        namespace=self.namespace,
                    )
                except ApiException:
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
        delete = getattr(self.api, f"delete_namespaced_{kind}")
        read = getattr(self.api, f"read_namespaced_{kind}")

        # first, attempt to delete the resource
        try:
            self.log.info(f"Deleting {kind}/{name}")
            await asyncio.wait_for(
                delete(namespace=self.namespace, name=name),
                self.k8s_api_request_timeout,
            )
        except asyncio.TimeoutError:
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
            await asyncio.wait_for(
                read(namespace=self.namespace, name=name), self.k8s_api_request_timeout
            )
        except asyncio.TimeoutError:
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
            await asyncio.wait_for(
                create(self.namespace, manifest), self.k8s_api_request_timeout
            )
        except asyncio.TimeoutError:
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

    async def _check_pvc_exists(self, pvc_name, namespace):
        """Return True/False if a pvc exists"""
        try:
            await exponential_backoff(
                partial(
                    self.api.read_namespaced_persistent_volume_claim,
                    name=pvc_name,
                    namespace=self.namespace,
                ),
                f"Could not check if PVC {pvc_name} exists",
                timeout=self.k8s_api_request_retry_timeout,
            )
        except ApiException as e:
            if e.status == 404:
                return False
            else:
                raise
        return True

    async def _start(self):
        """Start the user's pod"""

        # load user options (including profile)
        await self.load_user_options()

        # If we have user_namespaces enabled, create the namespace.
        #  It's fine if it already exists.
        if self.enable_user_namespaces:
            await self._ensure_namespace()

        # namespace can be changed via kubespawner_override, start watching pods only after
        # load_user_options() is called
        start_tasks = [self._start_watching_pods()]
        if self.events_enabled:
            start_tasks.append(self._start_watching_events())
        # create Futures for coroutines so we can cancel them
        # in case of an error
        start_futures = [asyncio.ensure_future(task) for task in start_tasks]
        try:
            await asyncio.gather(*start_futures)
        except Exception:
            # cancel any unfinished tasks before re-raising
            # because gather doesn't cancel unfinished tasks.
            # TaskGroup would do this cancel for us, but requires Python 3.11
            for future in start_futures:
                if not future.done():
                    future.cancel()
            raise

        # record latest event so we don't include old
        # events from previous pods in self.events
        # track by order and name instead of uid
        # so we get events like deletion of a previously stale
        # pod if it's part of this spawn process
        events = self.events
        if events:
            self._last_event = events[-1]["metadata"]["uid"]

        if self.storage_pvc_ensure:
            if (
                self.handle_legacy_names
                and self.remember_pvc_name
                and not self._pvc_exists
                and self._state_kubespawner_version == "unknown"
            ):
                # pvc name wasn't reliably persisted before kubespawner 7,
                # so if the name changed check if a pvc with the legacy name exists and use it.
                # This will be persisted in state on next launch in the future,
                # so the comparison below will be False for launches after the first.
                # this check will only work if pvc_name_template itself has not changed across the upgrade.
                legacy_pvc_name = self._expand_user_properties(
                    self.pvc_name_template, slug_scheme="escape"
                )
                if legacy_pvc_name != self.pvc_name:
                    self.log.debug(
                        f"Checking for legacy-named pvc {legacy_pvc_name} for {self.user.name}"
                    )
                    if await self._check_pvc_exists(self.pvc_name, self.namespace):
                        # if current name exists: use it
                        self._pvc_exists = True
                    else:
                        # current name doesn't exist, check if legacy name exists
                        if await self._check_pvc_exists(
                            legacy_pvc_name, self.namespace
                        ):
                            # legacy name exists, use it to avoid data loss
                            self.log.warning(
                                f"Using legacy pvc {legacy_pvc_name} for {self.user.name}"
                            )
                            self.pvc_name = legacy_pvc_name
                            self._pvc_exists = True

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
            # indicate that pvc name is known and should be persisted
            self._pvc_exists = True

        # If we run into a 409 Conflict error, it means a pod with the
        # same name already exists. We stop it, wait for it to stop, and
        # try again. We try 4 times, and if it still fails we give up.
        pod = await self.get_pod_manifest()
        if self.modify_pod_hook:
            self.log.info('Pod is being modified via modify_pod_hook')
            pod = await maybe_future(self.modify_pod_hook(self, pod))

        ref_key = f"{self.namespace}/{self.pod_name}"
        # If there's a timeout, just let it propagate
        await exponential_backoff(
            partial(self._make_create_pod_request, pod, self.k8s_api_request_timeout),
            f'Could not create pod {ref_key}',
            timeout=self.k8s_api_request_retry_timeout,
        )

        if self.internal_ssl or self.services_enabled or self.after_pod_created_hook:
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

                if self.internal_ssl:
                    # internal ssl, create secret object
                    secret_manifest = self.get_secret_manifest(owner_reference)
                    await exponential_backoff(
                        partial(
                            self._ensure_not_exists,
                            "secret",
                            secret_manifest.metadata.name,
                        ),
                        f"Failed to delete secret {secret_manifest.metadata.name}",
                    )
                    await exponential_backoff(
                        partial(
                            self._make_create_resource_request,
                            "secret",
                            secret_manifest,
                        ),
                        f"Failed to create secret {secret_manifest.metadata.name}",
                    )

                if self.internal_ssl or self.services_enabled:
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
                            self._make_create_resource_request,
                            "service",
                            service_manifest,
                        ),
                        f"Failed to create service {service_manifest.metadata.name}",
                    )

                if self.after_pod_created_hook:
                    self.log.info('Executing after_pod_created_hook')
                    await maybe_future(self.after_pod_created_hook(self, pod))
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
                f'pod {ref_key} did not start in {self.start_timeout} seconds!',
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
                self.log.error("Pods: %s", sorted(self.pod_reflector.pods.keys()))
                await asyncio.ensure_future(self._start_watching_pods(replace=True))
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
        ref_key = f"{self.namespace}/{pod_name}"
        self.log.info("Deleting pod %s", ref_key)
        try:
            await asyncio.wait_for(
                self.api.delete_namespaced_pod(
                    name=pod_name,
                    namespace=self.namespace,
                    body=delete_options,
                    grace_period_seconds=grace_seconds,
                ),
                request_timeout,
            )
            return True
        except asyncio.TimeoutError:
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
            await asyncio.wait_for(
                self.api.delete_namespaced_persistent_volume_claim(
                    name=pvc_name,
                    namespace=self.namespace,
                ),
                request_timeout,
            )
            return True
        except asyncio.TimeoutError:
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
        await self._start_watching_pods()

        delete_options = client.V1DeleteOptions()

        if now:
            grace_seconds = 0
        else:
            grace_seconds = self.delete_grace_period

        delete_options.grace_period_seconds = grace_seconds

        ref_key = f"{self.namespace}/{self.pod_name}"
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
            await asyncio.ensure_future(self._start_watching_pods(replace=True))
            raise

    @default('env_keep')
    def _env_keep_default(self):
        return []

    def _render_options_form(self, profile_list):
        """
        Renders a KubeSpawner specific jinja2 template, passing `profile_list` as a variable.

        The template rendered is either:
        - `profile_form_template` if configured
        - a "form.html" file if found in `additional_profile_form_template_paths`
        - a "form.html" file bundled with kubespawner

        Note that the return value can either be plain HTML or a jinja2 template
        that JupyterHub in turn will render with variables like `spawner`,
        `for_user`, `user`, `auth_state`, `error_message`.

        Reference
            https://github.com/jupyterhub/jupyterhub/blob/4.0.2/jupyterhub/handlers/pages.py#L94-L106
            https://github.com/jupyterhub/jupyterhub/blob/4.0.2/jupyterhub/handlers/base.py#L1272-L1308
        """
        profile_list = self._get_initialized_profile_list(profile_list)

        loader = ChoiceLoader(
            [
                FileSystemLoader(self.additional_profile_form_template_paths),
                PackageLoader("kubespawner", "templates"),
            ]
        )

        env = Environment(loader=loader)

        # jinja2's tojson sorts keys in dicts by default. This was useful
        # in the time when python's dicts were not ordered. However, now that
        # dicts are ordered in python, this screws it up. Since profiles are
        # dicts, ordering *does* matter - they should be displayed to the user
        # in the order that the admin sets them. This allows template writers
        # to use `|tojson` on the profile_list (to be read by JS)
        # without worrying about ordering getting mangled. Template writers
        # can still sort keys by explicitly using `|dictsort` in their
        # template
        env.policies['json.dumps_kwargs'] = {'sort_keys': False}

        if self.profile_form_template != "":
            profile_form_template = env.from_string(self.profile_form_template)
        else:
            profile_form_template = env.get_template("form.html")
        return profile_form_template.render(profile_list=profile_list)

    async def _render_options_form_dynamically(self, current_spawner):
        """
        A function configured to be used by JupyterHub via
        `_options_form_default` when `profile_list` is a callable, to render the
        server options for a user after evaluating the `profile_list` function.
        """
        profile_list = await maybe_future(self.profile_list(current_spawner))
        return self._render_options_form(profile_list)

    @default('options_form')
    def _options_form_default(self):
        """
        Returns a form template for JupyterHub to render, by rendering a
        KubeSpawner specific template that is passed through the `profile_list` config.

        JupyterHub renders the returned form template when a user is to start a
        server based on template variables like `spawner`, `for_user`, `user`,
        `auth_state`, `error_message`.

        JupyterHub parses submitted forms' data with `options_from_form`, saves
        it to `user_options`, and then individual KubeSpawner instances
        representing individual servers adjusts to it via `load_user_options` in
        `start`.

        Reference:
            https://jupyterhub.readthedocs.io/en/stable/reference/spawners.html#spawner-options-form
        """
        if not self.profile_list:
            return ''
        if callable(self.profile_list):
            # Let jupyterhub evaluate the callable profile_list (and render a
            # form template based on it) just in time by returning a function
            # doing that
            return self._render_options_form_dynamically
        else:
            # Return the rendered string, as it does not change
            return self._render_options_form(self.profile_list)

    @default('options_from_form')
    def _options_from_form_default(self):
        return self._options_from_form

    def _options_from_form(self, formdata):
        """
        Called by jupyterhub when processing a request to spawn a server, where
        the user either have submitted a POST request via a form or submitted a
        GET request with query parameters.

        This only constructs the user_options dict,
        it should not actually load any options.
        That is done later in `.load_user_options()`

        Args:
            formdata: user selection returned by the form

        As an example formdata could be set to::

            {'profile': ['demo-1'], 'profile-option-demo-1--image': ['minimal']}

        To access to the value, you can use the `get` accessor and the name of the html element,
        for example::

            formdata.get('profile', [None])[0]

        to get the value of the form named "profile", as defined in `form_template`::

            <select class="form-control" name="profile"...>
            </select>

        Returns:
            user_options (dict): the selected profile in the user_options form,
                e.g. ``{"profile": "cpus-8"}``
        """
        profile_slug = formdata.get('profile', [None])[0]

        # initialize a dictionary to return
        user_options = {}

        # if a profile is declared, add a dictionary key for the profile, and
        # dictionary keys for the formdata related to the profile's
        # profile_options, as recognized by being named like:
        #
        #     profile-option-{profile_slug}--{profile_option_slug}
        #
        if profile_slug:
            user_options["profile"] = profile_slug
            prefix = f'profile-option-{profile_slug}--'
            for k, v in formdata.items():
                if k.startswith(prefix):
                    profile_option_slug = k[len(prefix) :]
                    user_options[profile_option_slug] = v[0]

        # warn about any unrecognized form data, which is anything besides
        # "profile" and "profile-option-" prefixed keys
        unrecognized_keys = set(formdata)
        unrecognized_keys = unrecognized_keys.difference({"profile"})
        unrecognized_keys = [
            k for k in unrecognized_keys if not k.startswith("profile-option-")
        ]
        if unrecognized_keys:
            self.log.warning(
                "Ignoring unrecognized form data in spawn request: %s",
                ", ".join(map(str, sorted(unrecognized_keys))),
            )

        return user_options

    def _validate_user_options(self, profile_list):
        """
        Validate `user_options` using an initialized `profile_list` by raising
        an error if there are issues that can't be resolved.

        `user_options` is set via `_user_options_from_form` unless when the
        JupyterHub REST API has been used to start a server, then `user_options`
        are set directly via JSON data in the REST API request.

        Some examples of `user_options` to validate are::

            {"profile": "demo-1", "image": "minimal"}
            {"profile": "demo-1", "image--unlisted-choice": "jupyter/datascience-notebook:latest"}
            {}
            {"garbage-arrived-via-rest-api": "anything"}
            {"profile": "demo-1", "garbage-arrived-via-rest-api": "anything"}

        The current implementation doesn't emit warnings about irrelevant
        user_options that could have been passed when spawning via the REST API.
        """
        # `user_options` is allowed to be falsy as it could be via a JupyterHub
        # REST API request to spawn a server - then `user_options` can be
        # anything.
        if not self.user_options:
            return

        # If "profile" isn't declared or falsy, no further validation is done.
        profile_slug = self.user_options.get("profile")
        if not profile_slug:
            return

        # Ensure "profile" is defined in profile_list by calling _get_profile
        # with a truthy profile_slug.
        profile = self._get_profile(profile_slug, profile_list)

        # Ensure user_options related to the profile's profile_options are valid
        for option_name, option in profile.get('profile_options', {}).items():
            unlisted_choice_key = f"{option_name}--unlisted-choice"
            unlisted_choice = self.user_options.get(unlisted_choice_key)
            choice = self.user_options.get(option_name)
            if not (unlisted_choice or choice):
                # no user_options was passed for this profile option, the
                # profile option's default value can be used
                continue
            if unlisted_choice:
                # we have been passed a value for the profile option's
                # unlisted_choice, it must be enabled and the provided value
                # must validate against the validation_regex if configured
                if not option.get("unlisted_choice", {}).get("enabled"):
                    raise ValueError(
                        f"Received unlisted_choice for {option_name} without being enabled."
                    )

                validation_regex = option["unlisted_choice"].get("validation_regex")
                if validation_regex and not re.match(validation_regex, unlisted_choice):
                    raise ValueError(
                        f"Received unlisted_choice for {option_name} that failed validation regex."
                    )

    def _get_profile(self, slug: Optional[str], profile_list: list):
        """
        Returns the profile from profile_list matching given slug, or the
        (first) default profile if slug is falsy.

        profile_list is required to have a default profile.

        Raises an error if no profile exists for the given slug.
        """
        if not slug:
            # return the default profile
            return next(p for p in profile_list if p.get('default'))

        for profile in profile_list:
            if profile['slug'] == slug:
                # return matching profile
                return profile

        raise ValueError(
            "No such profile: %s. Options include: %s"
            % (slug, ', '.join(p['slug'] for p in profile_list))
        )

    def _apply_overrides(self, spawner_override: dict):
        """
        Apply set of overrides onto the current spawner instance

        spawner_override is a dict with key being the name of the traitlet
        to override, and value is either a callable or the value for the
        traitlet. If the value is a dictionary, it is *merged* with the
        existing value (rather than replaced). Callables are called with
        one parameter - the current spawner instance.
        """
        for k, v in spawner_override.items():
            if callable(v):
                v = v(self)
                self.log.debug(
                    ".. overriding KubeSpawner value %s=%s (callable result)", k, v
                )
            else:
                self.log.debug(".. overriding KubeSpawner value %s=%s", k, v)

            # If v is a dict, *merge* it with existing values, rather than completely
            # resetting it. This allows *adding* things like environment variables rather
            # than completely replacing them. If value is set to None, the key
            # will be removed
            if isinstance(v, dict) and isinstance(getattr(self, k), dict):
                recursive_update(getattr(self, k), v)
            else:
                setattr(self, k, v)

    def _load_profile(self, slug, profile_list):
        """
        Applies configured overrides for a selected or default profile,
        including the selected or default overrides for the profile's
        profile_options.

        Called by `load_user_options` after validation of user_options has been
        done with the initialized profile_list.
        """
        profile = self._get_profile(slug, profile_list)

        self.log.debug(
            "Applying KubeSpawner override for profile '%s'", profile['display_name']
        )

        # Apply overrides for the profile
        self._apply_overrides(profile.get("kubespawner_override", {}))

        # Apply overrides for the profile_options's choices or defaults
        profile_options = profile.get("profile_options", {})
        for option_name, option in profile_options.items():
            unlisted_choice_key = f"{option_name}--unlisted-choice"
            unlisted_choice = self.user_options.get(unlisted_choice_key)
            choice = self.user_options.get(option_name)

            if unlisted_choice:
                # An unlisted_choice value was passed, its kubespawner_override
                # needs to be rendered using the value
                option_overrides = option["unlisted_choice"].get(
                    "kubespawner_override", {}
                )
                for k, v in option_overrides.items():
                    option_overrides[k] = recursive_format(v, value=unlisted_choice)
            elif choice:
                # A pre-defined choice was selected
                option_overrides = option["choices"][choice].get(
                    "kubespawner_override", {}
                )
            else:
                # A default choice for the option needs to be determined
                if not option.get("choices"):
                    # if the option only defined unlisted_choice, we can't
                    # determine a default choice or associated overrides
                    raise ValueError(
                        f"Unable to determine a default choice for {option_name}."
                    )

                default_choice = next(
                    c for c in option["choices"].values() if c.get("default")
                )
                option_overrides = default_choice.get("kubespawner_override", {})

            self._apply_overrides(option_overrides)

    def _get_initialized_profile_list(self, profile_list: list):
        """
        Returns a fully initialized copy of profile_list.

        - If 'slug' is not set for a profile, its generated from display_name.
        - If profile_options are present with choices, but no choice is set
          as the default, the first choice is set to be the default.
        - If no default profile is set, the first profile is set to be the
          default
        """
        profile_list = copy.deepcopy(profile_list)

        if not profile_list:
            # empty profile lists are just returned
            return profile_list

        for profile in profile_list:
            # generate missing slug fields from display_name
            if 'slug' not in profile:
                profile['slug'] = slugify(profile['display_name'])

            # ensure each option in profile_options has a default choice if
            # pre-defined choices are available, and initialize an
            # unlisted_choice dictionary
            for option_config in profile.get('profile_options', {}).values():
                if option_config.get('choices') and not any(
                    c.get('default') for c in option_config['choices'].values()
                ):
                    # pre-defined choices were provided without a default choice
                    default_choice = list(option_config['choices'].keys())[0]
                    option_config['choices'][default_choice]["default"] = True
                unlisted_choice = option_config.setdefault("unlisted_choice", {})
                unlisted_choice.setdefault("enabled", False)
                if unlisted_choice["enabled"]:
                    unlisted_choice.setdefault("display_name_in_choices", "Other...")
        # ensure there is one default profile
        if not any(p.get("default") for p in profile_list):
            profile_list[0]["default"] = True

        return profile_list

    async def load_user_options(self):
        """
        Applies profile_list defined overrides to the spawner instance based on
        self.user_options that represents the choices made by a user.

        self.user_options is set by jupyterhub when a server is to be spawned to
        a POST request's body / a GET request's query parameters, the most
        recently passed options for this user server, or an empty dictionary as
        a final fallback.

        KubeSpawner recognizes the option named 'profile' and options named like
        'profile-option-{profile_slug}--{option_slug}'. These user_options will
        be validated against the spawner's profile_list.

        Override in subclasses to support other options.
        """
        # get an initialized profile list
        profile_list = self.profile_list
        if callable(profile_list):
            profile_list = await maybe_future(profile_list(self))
        profile_list = self._get_initialized_profile_list(profile_list)

        # validate user_options against initialized profile_list
        self._validate_user_options(profile_list)

        selected_profile = self.user_options.get("profile")
        if profile_list:
            self._load_profile(selected_profile, profile_list)
        elif selected_profile:
            self.log.warning(
                "Profile %r requested, but no profile_lists are configured",
                selected_profile,
            )

    async def _ensure_namespace(self):
        ns = make_namespace(
            self.namespace,
            labels=self._expand_all(self.user_namespace_labels),
            annotations=self._expand_all(self.user_namespace_annotations),
        )
        api = self.api
        try:
            await asyncio.wait_for(
                api.create_namespace(ns),
                self.k8s_api_request_timeout,
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

        if self.name and '{user_server}' not in self.pvc_name_template:
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
