import asyncio
import json
import os
import string

import escapism
from jupyterhub.proxy import Proxy
from jupyterhub.utils import exponential_backoff
from kubernetes_asyncio import client
from traitlets import Unicode

from .clients import load_config
from .clients import shared_client
from .objects import make_ingress
from .reflector import ResourceReflector
from .utils import generate_hashed_slug


class IngressReflector(ResourceReflector):
    kind = 'ingresses'
    api_group_name = 'ExtensionsV1beta1Api'

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

        This class is not maintained thoroughly with tests and documentation, or
        actively used in any official distribution of JupyterHub.

        When it was originally developed and piloted by Yuvi (@yuvipanda), it is
        my (@consideRatio) unverified understanding that it was found to not be
        reliable, responsive, or performant enough compared to having a
        dedicated configurable proxy managed by JupyterHub that routed traffic
        to users and services - something that ships by default in the
        JupyterHub Helm chart.

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

    KubeIngressProxy is a implementation of a JupyterHub Proxy class that
    JupyterHub can be configured to rely on:

        c.JupyterHub.proxy_class = "kubespawner:KubeIngressProxy"

    The idea of KubeIngressProxy is that, like all JupyterHub Proxy
    implementations, will react to requests like `get_all_routes`, `add_route`,
    and `delete_route` in a way that ensures traffic gets routed to the user
    pods or JupyterHub registered external services. For reference, official
    documentation on writing a custom Proxy class like this is documented here:
    https://jupyterhub.readthedocs.io/en/stable/reference/proxy.html.

    KubeIngressProxy doesn't route traffic by itself, but instead relies on a
    k8s cluster's ability to route traffic according to Ingress resources. The
    only thing KubeIngressProxy does is to speak with a k8s api-server to
    create/delete such resources.

    Because KubeIngressProxy interacts with a k8s api-server and working with
    Ingress resources, it must have permissions to do so as well. These
    permissions should be granted to a k8s service account for where the
    JupyterHub is running, as that is also where the KubeIngressProxy class
    instance will run its code.

    FIXME: Verify what k8s RBAC permissions are required for KubeIngressProxy
           to function.

           Preliminary one can note that there is an IngressReflector,
           ServiceReflector, and EndpointsReflector. So at least permission to
           read/list/watch those resources would be needed.

           For Ingress resources, one would also need the ability to create,
           patch, and delete them, as concluded by inspection of `add_route` and
           `delete_route`.

           Without having verified these permissions are sufficient, it looks
           like these permissions are needed on a k8s Role resource bound to the
           k8s ServiceAccount (via a k8s RoleBinding) used on the k8s Pod where
           JupyterHub runs:

           ```yaml
           kind: Role
           apiVersion: rbac.authorization.k8s.io/v1
           metadata:
           name: kube-ingress-proxy
           rules:
             - apiGroups: [""]
               resources: ["endpoints", "services"]
               verbs: ["get", "watch", "list"]
             - apiGroups: ["networking.k8s.io"]
               resources: ["ingresses"]
               verbs: ["get", "watch", "list", "create", "update", "patch", "delete"]
           ```
    """

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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        load_config(host=self.k8s_api_host, ssl_ca_cert=self.k8s_api_ssl_ca_cert)
        self.core_api = shared_client('CoreV1Api')
        self.extension_api = shared_client('ExtensionsV1beta1Api')

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
            self, namespace=self.namespace, labels=labels
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
        labels = {
            'heritage': 'jupyterhub',
            'component': self.component_label,
            'hub.jupyter.org/proxy-route': 'true',
        }
        endpoint, service, ingress = make_ingress(
            safe_name, routespec, target, labels, data
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
                lambda: f'{self.namespace}/{safe_name}'
                in self.endpoint_reflector.endpoints.keys(),
                'Could not find endpoints/%s after creating it' % safe_name,
            )
        else:
            delete_endpoint = await self.core_api.delete_namespaced_endpoints(
                name=safe_name,
                namespace=self.namespace,
                body=client.V1DeleteOptions(grace_period_seconds=0),
            )
            await self._delete_if_exists('endpoint', safe_name, delete_endpoint)

        await ensure_object(
            self.core_api.create_namespaced_service,
            self.core_api.patch_namespaced_service,
            body=service,
            kind='service',
        )

        await exponential_backoff(
            lambda: f'{self.namespace}/{safe_name}'
            in self.service_reflector.services.keys(),
            'Could not find service/%s after creating it' % safe_name,
        )

        await ensure_object(
            self.extension_api.create_namespaced_ingress,
            self.extension_api.patch_namespaced_ingress,
            body=ingress,
            kind='ingress',
        )

        await exponential_backoff(
            lambda: f'{self.namespace}/{safe_name}'
            in self.ingress_reflector.ingresses.keys(),
            'Could not find ingress/%s after creating it' % safe_name,
        )

    async def delete_route(self, routespec):
        # We just ensure that these objects are deleted.
        # This means if some of them are already deleted, we just let it
        # be.

        safe_name = self._safe_name_for_routespec(routespec).lower()

        delete_options = client.V1DeleteOptions(grace_period_seconds=0)

        delete_endpoint = await self.core_api.delete_namespaced_endpoints(
            name=safe_name,
            namespace=self.namespace,
            body=delete_options,
        )

        delete_service = await self.core_api.delete_namespaced_service(
            name=safe_name,
            namespace=self.namespace,
            body=delete_options,
        )

        delete_ingress = await self.extension_api.delete_namespaced_ingress(
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
