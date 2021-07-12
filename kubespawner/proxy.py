import json
import os
import string
from concurrent.futures import ThreadPoolExecutor

import escapism
import kubernetes.config
from jupyterhub.proxy import Proxy
from jupyterhub.utils import exponential_backoff
from kubernetes import client
from tornado import gen
from tornado.concurrent import run_on_executor
from traitlets import Unicode

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

        # We use the maximum number of concurrent user server starts (and thus proxy adds)
        # as our threadpool maximum. This ensures that contention here does not become
        # an accidental bottleneck. Since we serialize our create operations, we only
        # need 1x concurrent_spawn_limit, not 3x.
        self.executor = ThreadPoolExecutor(max_workers=self.app.concurrent_spawn_limit)

        # Global configuration before reflector.py code runs
        self._set_k8s_client_configuration()
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
            parent=self, namespace=self.namespace, labels=labels
        )

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

    @run_on_executor
    def asynchronize(self, method, *args, **kwargs):
        return method(*args, **kwargs)

    def safe_name_for_routespec(self, routespec):
        safe_chars = set(string.ascii_lowercase + string.digits)
        safe_name = generate_hashed_slug(
            'jupyter-'
            + escapism.escape(routespec, safe=safe_chars, escape_char='-')
            + '-route'
        )
        return safe_name

    async def delete_if_exists(self, kind, safe_name, future):
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
        safe_name = self.safe_name_for_routespec(routespec).lower()
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
                resp = await self.asynchronize(
                    create_func, namespace=self.namespace, body=body
                )
                self.log.info('Created %s/%s', kind, safe_name)
            except client.rest.ApiException as e:
                if e.status == 409:
                    # This object already exists, we should patch it to make it be what we want
                    self.log.warn(
                        "Trying to patch %s/%s, it already exists", kind, safe_name
                    )
                    resp = await self.asynchronize(
                        patch_func,
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
            delete_endpoint = self.asynchronize(
                self.core_api.delete_namespaced_endpoints,
                name=safe_name,
                namespace=self.namespace,
                body=client.V1DeleteOptions(grace_period_seconds=0),
            )
            await self.delete_if_exists('endpoint', safe_name, delete_endpoint)

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
        safe_name = self.safe_name_for_routespec(routespec).lower()

        delete_options = client.V1DeleteOptions(grace_period_seconds=0)

        delete_endpoint = self.asynchronize(
            self.core_api.delete_namespaced_endpoints,
            name=safe_name,
            namespace=self.namespace,
            body=delete_options,
        )

        delete_service = self.asynchronize(
            self.core_api.delete_namespaced_service,
            name=safe_name,
            namespace=self.namespace,
            body=delete_options,
        )

        delete_ingress = self.asynchronize(
            self.extension_api.delete_namespaced_ingress,
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
        await self.delete_if_exists('endpoint', safe_name, delete_endpoint)
        await self.delete_if_exists('service', safe_name, delete_service)
        await self.delete_if_exists('ingress', safe_name, delete_ingress)

    async def get_all_routes(self):
        # copy everything, because iterating over this directly is not threadsafe
        # FIXME: is this performance intensive? It could be! Measure?
        # FIXME: Validate that this shallow copy *is* thread safe
        ingress_copy = dict(self.ingress_reflector.ingresses)
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
            for ingress in ingress_copy.values()
        }

        return routes
