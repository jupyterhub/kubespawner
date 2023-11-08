import asyncio
import json
import os
import string

import escapism
from jupyterhub.proxy import Proxy
from jupyterhub.utils import exponential_backoff
from kubernetes_asyncio import client
from traitlets import Bool, Dict, List, Unicode

from .clients import load_config, shared_client
from .objects import make_ingress
from .reflector import ResourceReflector
from .utils import generate_hashed_slug


class IngressReflector(ResourceReflector):
    kind = 'ingresses'
    api_group_name = 'NetworkingV1Api'

    @property
    def ingresses(self):
        return self.resources


class ServiceReflector(ResourceReflector):
    kind = 'services'

    @property
    def services(self):
        return self.resources


class EndpointsReflector(ResourceReflector):
    kind = 'endpoints'

    @property
    def endpoints(self):
        return self.resources


class KubeIngressProxy(Proxy):
    """
    DISCLAIMER:

        This JupyterHub Proxy class is not maintained thoroughly with tests and
        documentation, or actively used in any official distribution of
        JupyterHub.

        KubeIngressProxy was originally developed by @yuvipanda in preparation
        to support a JupyterHub that could end up with ~20k simultaneous users.
        The single ConfigurableHTTPProxy server that is controlled by the
        default JupyterHub Proxy class could bottleneck for such heavy load,
        even though it has been found to be good enough for ~2k simultaneous
        users. By instead using this JupyterHub Proxy class that would create
        k8s resources (Ingress, Service, Endpoint) that in turn controlled how a
        flexible set of proxy servers would proxy traffic, the bottleneck could
        be removed.

        KubeIngressProxy's efficiency relates greatly to the performance of the
        k8s api-server and the k8s controller that routes traffic based on
        changes to Ingress resources registered by the k8s api-server. This
        means users of KubeIngressProxy may have greatly varying experiences of
        using it depending on the performance of their k8s cluster setup.

        Use of KubeIngressProxy as a JupyterHub Proxy class, is entirely
        independent of use of KubeSpawner as a JupyterHub Spawner class. For
        reasons related to sharing code with KubeSpawner in reflectors.py, it
        has been made and remained part of the jupyterhub/kubespawner project.

        Related issues:
        - Need for tests: https://github.com/jupyterhub/kubespawner/issues/496
        - Need for docs:  https://github.com/jupyterhub/kubespawner/issues/163

    ---

    KubeIngressProxy is an implementation of the JupyterHub Proxy class that
    JupyterHub can be configured to rely on:

        c.JupyterHub.proxy_class = "kubespawner.proxy:KubeIngressProxy"

    Like all JupyterHub Proxy implementations, KubeIngressProxy will know
    how to respond to hub requests like `get_all_routes`, `add_route`, and
    `delete_route` in a way that will ensure traffic will get routed to the user
    pods or JupyterHub registered external services. For reference, the official
    documentation on writing a custom Proxy class like this is documented here:
    https://jupyterhub.readthedocs.io/en/stable/reference/proxy.html.

    KubeIngressProxy communicates with the k8s api-server in order to
    create/delete Ingress resources according to the hub's `add_route`/`delete_route`
    requests. It doesn't route traffic by itself, but instead relies on the k8s cluster's
    ability to route traffic according to these Ingress resources.

    Because KubeIngressProxy interacts with a k8s api-server that manages
    Ingress resources, it must have permissions to do so as well. These
    permissions should be granted to a k8s service account for where the
    JupyterHub is running, as that is also where the KubeIngressProxy class
    instance will run its code.

    FIXME: Verify what k8s RBAC permissions are required for KubeIngressProxy
           to function.

           - The IngressReflector, ServiceReflector, and EndpointsReflector
             require permission to read/list/watch those resources.
           - `add_route` and `delete_route` requires permission to
             create/update/patch/delete Ingress, Service, and Endpoints
             resources.

           These permissions are needed on a k8s Role resource bound to the k8s
           ServiceAccount (via a k8s RoleBinding) used on the k8s Pod where
           JupyterHub runs:

           ```yaml
           kind: Role
           apiVersion: rbac.authorization.k8s.io/v1
           metadata:
           name: kube-ingress-proxy
           rules:
             - apiGroups: [""]
               resources: ["endpoints", "services"]
               verbs: ["get", "watch", "list", "create", "update", "patch", "delete"]
             - apiGroups: ["networking.k8s.io"]
               resources: ["ingresses"]
               verbs: ["get", "watch", "list", "create", "update", "patch", "delete"]
           ```
    """

    # JupyterHub should not try to start or stop this proxy
    should_start = False

    namespace = Unicode(
        config=True,
        help="""
        Kubernetes namespace to spawn ingresses for single-user servers in.

        If running inside a kubernetes cluster with service accounts enabled,
        defaults to the current namespace. If not, defaults to 'default'
        """,
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

    component_label = Unicode(
        'singleuser-server',
        config=True,
        help="""
        The component label used to tag the user pods. This can be used to override
        the spawner behavior when dealing with multiple hub instances in the same
        namespace. Usually helpful for CI workflows.
        """,
    )

    common_labels = Dict(
        {
            'app': 'jupyterhub',
            'heritage': 'jupyterhub',
        },
        config=True,
        help="""
        Extra kubernetes labels to set on all created objects.

        The keys and values must both be strings that match the kubernetes
        label key / value constraints.

        See `the Kubernetes documentation <https://kubernetes.io/docs/concepts/overview/working-with-objects/labels/>`__
        for more info on what labels are and why you might want to use them!

        `{username}`, `{servername}`, `{servicename}`, `{routespec}`, `{hubnamespace}`,
        `{unescaped_username}`, `{unescaped_servername}`, `{unescaped_servicename}` and `{unescaped_routespec}` will be expanded if
        found within strings of this configuration.

        Names have to be are escaped to follow the `DNS label standard
        <https://kubernetes.io/docs/concepts/overview/working-with-objects/names/#dns-label-names>`__.
        """,
    )

    ingress_extra_labels = Dict(
        config=True,
        help="""
        Extra kubernetes labels to set to Ingress objects.

        The keys and values must both be strings that match the kubernetes
        label key / value constraints.

        See `the Kubernetes documentation <https://kubernetes.io/docs/concepts/overview/working-with-objects/labels/>`__
        for more info on what labels are and why you might want to use them!

        `{username}`, `{servername}`, `{servicename}`, `{routespec}`, `{hubnamespace}`,
        `{unescaped_username}`, `{unescaped_servername}`, `{unescaped_servicename}` and `{unescaped_routespec}` will be expanded if
        found within strings of this configuration.

        Names have to be are escaped to follow the `DNS label standard
        <https://kubernetes.io/docs/concepts/overview/working-with-objects/names/#dns-label-names>`__.
        """,
    )

    ingress_extra_annotations = Dict(
        config=True,
        help="""
        Extra kubernetes annotations to set on the Ingress object.

        The keys and values must both be strings.

        See `the Kubernetes documentation <https://kubernetes.io/docs/concepts/overview/working-with-objects/labels/>`__
        for more info on what labels are and why you might want to use them!

        `{username}`, `{servername}`, `{servicename}`, `{routespec}`, `{hubnamespace}`,
        `{unescaped_username}`, `{unescaped_servername}`, `{unescaped_servicename}` and `{unescaped_routespec}` will be expanded if
        found within strings of this configuration.

        Names have to be are escaped to follow the `DNS label standard
        <https://kubernetes.io/docs/concepts/overview/working-with-objects/names/#dns-label-names>`__.
        """,
    )

    ingress_class_name = Unicode(
        config=True,
        help="""
        Default value for 'ingressClassName' field in Ingress specification
        """,
    )

    ingress_specifications = List(
        trait=Dict,
        config=True,
        help="""
        Specifications for ingress routes. List of dicts of the following format:

        [{'host': 'host.example.domain'}]
        [{'host': 'host.example.domain', 'tlsSecret': 'tlsSecretName'}]
        [{'host': 'jh.{hubnamespace}.domain', 'tlsSecret': 'tlsSecretName'}]

        Wildcard might not work, refer to your ingress controller documentation.

        `{routespec}`, `{hubnamespace}`, and `{unescaped_routespec}` will be expanded if
        found within strings of this configuration.

        Names have to be are escaped to follow the `DNS label standard
        <https://kubernetes.io/docs/concepts/overview/working-with-objects/names/#dns-label-names>`__.
        """,
    )

    reuse_existing_services = Bool(
        False,
        config=True,
        help="""
        If `True`, proxy will try to reuse existing services created by `KubeSpawner.services_enabled=True`
        or `KubeSpawner.internal_ssl=True`.
        If `False` (default), KubeSpawner creates service with type `ExternalName`, pointing to the pod's service.

        Sometimes `ExternalName` could lead to issues with accessing pod, like `500 Redirect loop detected`,
        so setting this option to `True` could solve this issue.

        By default, KubeSpawner does not create service for a pod at all (`service_enabled=False`, `internal_ssl=False`).
        In such a case KubeSpawner creates service with type `ClusterIP`, pointing to the pod IP and port.

        If KubeSpawner creates pod in a different namespace, this option is ignored,
        because Ingress(namespace=hub) cannot point to Service(namespace=user).
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        load_config(
            host=self.k8s_api_host,
            ssl_ca_cert=self.k8s_api_ssl_ca_cert,
            verify_ssl=self.k8s_api_verify_ssl,
        )
        self.core_api = shared_client('CoreV1Api')
        self.networking_api = shared_client('NetworkingV1Api')

        labels = {
            'component': self.component_label,
            'hub.jupyter.org/proxy-route': 'true',
        }
        self.ingress_reflector = IngressReflector(
            parent=self, namespace=self.namespace, labels=labels
        )
        self.service_reflector = ServiceReflector(
            parent=self, namespace=self.namespace, labels=labels
        )
        self.endpoint_reflector = EndpointsReflector(
            parent=self, namespace=self.namespace, labels=labels
        )

        # schedule our reflectors to start in the event loop,
        # reflectors first load can be awaited with:
        #
        #   await some_reflector._first_load_future
        #
        asyncio.ensure_future(self.ingress_reflector.start())
        asyncio.ensure_future(self.service_reflector.start())
        asyncio.ensure_future(self.endpoint_reflector.start())

    def _safe_name_for_routespec(self, routespec):
        safe_chars = set(string.ascii_lowercase + string.digits)
        safe_name = generate_hashed_slug(
            'jupyter-'
            + escapism.escape(routespec, safe=safe_chars, escape_char='-')
            + '-route'
        )
        return safe_name

    def _expand_user_properties(self, template, routespec, data):
        # Make sure username and servername match the restrictions for DNS labels
        # Note: '-' is not in safe_chars, as it is being used as escape character
        safe_chars = set(string.ascii_lowercase + string.digits)

        raw_servername = data.get('server_name') or ''
        safe_servername = escapism.escape(
            raw_servername, safe=safe_chars, escape_char='-'
        ).lower()

        hub_namespace = self._namespace_default()
        if hub_namespace == "default":
            hub_namespace = "user"

        raw_username = data.get('user') or ''
        safe_username = escapism.escape(
            raw_username, safe=safe_chars, escape_char='-'
        ).lower()

        raw_servicename = data.get('services') or ''
        safe_servicename = escapism.escape(
            raw_servicename, safe=safe_chars, escape_char='-'
        ).lower()

        raw_routespec = routespec
        safe_routespec = self._safe_name_for_routespec(routespec)

        rendered = template.format(
            username=safe_username,
            unescaped_username=raw_username,
            servername=safe_servername,
            unescaped_servername=raw_servername,
            servicename=safe_servicename,
            unescaped_servicename=raw_servicename,
            routespec=safe_routespec,
            unescaped_routespec=raw_routespec,
            hubnamespace=hub_namespace,
        )
        # strip trailing - delimiter in case of empty servername.
        # k8s object names cannot have trailing -
        return rendered.rstrip("-")

    def _expand_all(self, src, routespec, data):
        if isinstance(src, list):
            return [self._expand_all(i, routespec, data) for i in src]
        elif isinstance(src, dict):
            return {k: self._expand_all(v, routespec, data) for k, v in src.items()}
        elif isinstance(src, str):
            return self._expand_user_properties(src, routespec, data)
        else:
            return src

    async def _delete_if_exists(self, kind, safe_name, future):
        try:
            await future
            self.log.info('Deleted %s/%s', kind, safe_name)
        except client.rest.ApiException as e:
            if e.status != 404:
                raise
            self.log.warn("Could not delete %s/%s: does not exist", kind, safe_name)

    async def add_route(self, routespec, target, data):
        # Create a route with the name being escaped routespec
        # Use full routespec in label
        # 'data' is JSON encoded and put in an annotation - we don't need to query for it

        safe_name = self._safe_name_for_routespec(routespec).lower()
        full_name = f'{self.namespace}/{safe_name}'

        common_labels = self._expand_all(self.common_labels, routespec, data)
        common_labels.update({'component': self.component_label})

        ingress_extra_labels = self._expand_all(
            self.ingress_extra_labels, routespec, data
        )
        ingress_extra_annotations = self._expand_all(
            self.ingress_extra_annotations, routespec, data
        )

        ingress_specifications = self._expand_all(
            self.ingress_specifications,
            routespec,
            data,
        )

        endpoint, service, ingress = make_ingress(
            name=safe_name,
            routespec=routespec,
            target=target,
            data=data,
            namespace=self.namespace,
            common_labels=common_labels,
            ingress_extra_labels=ingress_extra_labels,
            ingress_extra_annotations=ingress_extra_annotations,
            ingress_class_name=self.ingress_class_name,
            ingress_specifications=ingress_specifications,
            reuse_existing_services=self.reuse_existing_services,
        )

        async def ensure_object(create_func, patch_func, body, kind):
            try:
                await create_func(namespace=self.namespace, body=body)
                self.log.info('Created %s/%s', kind, safe_name)
            except client.rest.ApiException as e:
                if e.status == 409:
                    # This object already exists, we should patch it to make it be what we want
                    self.log.warn(
                        "Trying to patch %s/%s, it already exists", kind, safe_name
                    )
                    await patch_func(
                        namespace=self.namespace,
                        body=body,
                        name=body.metadata.name,
                    )
                else:
                    raise

        if endpoint is not None:
            await ensure_object(
                self.core_api.create_namespaced_endpoints,
                self.core_api.patch_namespaced_endpoints,
                body=endpoint,
                kind='endpoints',
            )

            await exponential_backoff(
                lambda: full_name in self.endpoint_reflector.endpoints,
                'Could not find endpoints/%s after creating it' % safe_name,
            )
        else:
            delete_endpoint = self.core_api.delete_namespaced_endpoints(
                name=safe_name,
                namespace=self.namespace,
                body=client.V1DeleteOptions(grace_period_seconds=0),
            )
            await self._delete_if_exists('endpoint', safe_name, delete_endpoint)

        if service is not None:
            await ensure_object(
                self.core_api.create_namespaced_service,
                self.core_api.patch_namespaced_service,
                body=service,
                kind='service',
            )
            await exponential_backoff(
                lambda: full_name in self.service_reflector.services,
                'Could not find services/%s after creating it' % safe_name,
            )
        else:
            delete_service = self.core_api.delete_namespaced_service(
                name=safe_name,
                namespace=self.namespace,
                body=client.V1DeleteOptions(grace_period_seconds=0),
            )
            await self._delete_if_exists('service', safe_name, delete_service)

        await ensure_object(
            self.networking_api.create_namespaced_ingress,
            self.networking_api.patch_namespaced_ingress,
            body=ingress,
            kind='ingress',
        )

        await exponential_backoff(
            lambda: full_name in self.ingress_reflector.ingresses,
            'Could not find ingress/%s after creating it' % safe_name,
        )

    async def delete_route(self, routespec):
        # We just ensure that these objects are deleted.
        # This means if some of them are already deleted, we just let it
        # be.

        safe_name = self._safe_name_for_routespec(routespec).lower()

        delete_options = client.V1DeleteOptions(grace_period_seconds=0)

        delete_endpoint = self.core_api.delete_namespaced_endpoints(
            name=safe_name,
            namespace=self.namespace,
            body=delete_options,
        )

        delete_service = self.core_api.delete_namespaced_service(
            name=safe_name,
            namespace=self.namespace,
            body=delete_options,
        )

        delete_ingress = self.networking_api.delete_namespaced_ingress(
            name=safe_name,
            namespace=self.namespace,
            body=delete_options,
            grace_period_seconds=0,
        )

        # This seems like cleanest way to parallelize all three of these while
        # also making sure we only ignore the exception when it's a 404.
        # The order matters for endpoint & service - deleting the service deletes
        # the endpoint in the background. This can be racy however, so we do so
        # explicitly ourselves as well. In the future, we can probably try a
        # foreground cascading deletion (https://kubernetes.io/docs/concepts/workloads/controllers/garbage-collection/#foreground-cascading-deletion)
        # instead, but for now this works well enough.
        await asyncio.gather(
            self._delete_if_exists('endpoint', safe_name, delete_endpoint),
            self._delete_if_exists('service', safe_name, delete_service),
            self._delete_if_exists('ingress', safe_name, delete_ingress),
        )

    async def get_all_routes(self):
        if not self.ingress_reflector.first_load_future.done():
            await self.ingress_reflector.first_load_future

        routes = {
            ingress["metadata"]["annotations"]['hub.jupyter.org/proxy-routespec']: {
                'routespec': ingress["metadata"]["annotations"][
                    'hub.jupyter.org/proxy-routespec'
                ],
                'target': ingress["metadata"]["annotations"][
                    'hub.jupyter.org/proxy-target'
                ],
                'data': json.loads(
                    ingress["metadata"]["annotations"]['hub.jupyter.org/proxy-data']
                ),
            }
            for ingress in self.ingress_reflector.ingresses.values()
        }

        return routes
