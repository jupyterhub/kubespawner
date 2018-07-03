from concurrent.futures import ThreadPoolExecutor
import os
import string
import escapism
import json
from kubernetes import client

from jupyterhub.proxy import Proxy
from jupyterhub.utils import exponential_backoff

from kubespawner.objects import make_ingress
from kubespawner.utils import generate_hashed_slug
from kubespawner.reflector import NamespacedResourceReflector
from .clients import shared_client
from traitlets import Unicode
from tornado import gen
from tornado.concurrent import run_on_executor


class IngressReflector(NamespacedResourceReflector):
    kind = 'ingresses'
    labels = {
        'component': 'singleuser-server',
        'hub.jupyter.org/proxy-route': 'true'
    }

    list_method_name = 'list_namespaced_ingress'
    api_group_name = 'ExtensionsV1beta1Api'

    @property
    def ingresses(self):
        return self.resources

class ServiceReflector(NamespacedResourceReflector):
    kind = 'services'
    labels = {
        'component': 'singleuser-server',
        'hub.jupyter.org/proxy-route': 'true'
    }

    list_method_name = 'list_namespaced_service'

    @property
    def services(self):
        return self.resources

class EndpointsReflector(NamespacedResourceReflector):
    kind = 'endpoints'
    labels = {
        'component': 'singleuser-server',
        'hub.jupyter.org/proxy-route': 'true'
    }

    list_method_name = 'list_namespaced_endpoints'

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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # We use the maximum number of concurrent user server starts (and thus proxy adds)
        # as our threadpool maximum. This ensures that contention here does not become
        # an accidental bottleneck. Since we serialize our create operations, we only
        # need 1x concurrent_spawn_limit, not 3x.
        self.executor = ThreadPoolExecutor(max_workers=self.app.concurrent_spawn_limit)

        self.ingress_reflector = IngressReflector(parent=self, namespace=self.namespace)
        self.service_reflector = ServiceReflector(parent=self, namespace=self.namespace)
        self.endpoint_reflector = EndpointsReflector(parent=self, namespace=self.namespace)

        self.core_api = shared_client('CoreV1Api')
        self.extension_api = shared_client('ExtensionsV1beta1Api')

    @run_on_executor
    def asynchronize(self, method, *args, **kwargs):
        return method(*args, **kwargs)

    def safe_name_for_routespec(self, routespec):
        safe_chars = set(string.ascii_lowercase + string.digits)
        safe_name = generate_hashed_slug(
            'jupyter-' + escapism.escape(routespec, safe=safe_chars, escape_char='-') + '-route'
        )
        return safe_name

    @gen.coroutine
    def delete_if_exists(self, kind, safe_name, future):
        try:
            yield future
            self.log.info('Deleted %s/%s', kind, safe_name)
        except client.rest.ApiException as e:
            if e.status != 404:
                raise
            self.log.warn("Could not delete %s/%s: does not exist", kind, safe_name)

    @gen.coroutine
    def add_route(self, routespec, target, data):
        # Create a route with the name being escaped routespec
        # Use full routespec in label
        # 'data' is JSON encoded and put in an annotation - we don't need to query for it
        safe_name = self.safe_name_for_routespec(routespec).lower()
        endpoint, service, ingress = make_ingress(
            safe_name,
            routespec,
            target,
            data
        )

        @gen.coroutine
        def ensure_object(create_func, patch_func, body, kind):
            try:
                resp = yield self.asynchronize(
                    create_func,
                    namespace=self.namespace,
                    body=body
                )
                self.log.info('Created %s/%s', kind, safe_name)
            except client.rest.ApiException as e:
                if e.status == 409:
                    # This object already exists, we should patch it to make it be what we want
                    self.log.warn("Trying to patch %s/%s, it already exists", kind, safe_name)
                    resp = yield self.asynchronize(
                        patch_func,
                        namespace=self.namespace,
                        body=body,
                        name=body.metadata.name
                    )
                else:
                    raise

        if endpoint is not None:
            yield ensure_object(
                self.core_api.create_namespaced_endpoints,
                self.core_api.patch_namespaced_endpoints,
                body=endpoint,
                kind='endpoints'
            )

            yield exponential_backoff(
                lambda: safe_name in self.endpoint_reflector.endpoints,
                'Could not find endpoints/%s after creating it' % safe_name
            )
        else:
            delete_endpoint = self.asynchronize(
                self.core_api.delete_namespaced_endpoints,
                name=safe_name,
                namespace=self.namespace,
                body=client.V1DeleteOptions(grace_period_seconds=0),
            )
            yield self.delete_if_exists('endpoint', safe_name, delete_endpoint)

        yield ensure_object(
            self.core_api.create_namespaced_service,
            self.core_api.patch_namespaced_service,
            body=service,
            kind='service'
        )

        yield exponential_backoff(
            lambda: safe_name in self.service_reflector.services,
            'Could not find service/%s after creating it' % safe_name
        )

        yield ensure_object(
            self.extension_api.create_namespaced_ingress,
            self.extension_api.patch_namespaced_ingress,
            body=ingress,
            kind='ingress'
        )

        yield exponential_backoff(
            lambda: safe_name in self.ingress_reflector.ingresses,
            'Could not find ingress/%s after creating it' % safe_name
        )

    @gen.coroutine
    def delete_route(self, routespec):
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
                grace_period_seconds=0
        )

        # This seems like cleanest way to parallelize all three of these while
        # also making sure we only ignore the exception when it's a 404.
        # The order matters for endpoint & service - deleting the service deletes
        # the endpoint in the background. This can be racy however, so we do so
        # explicitly ourselves as well. In the future, we can probably try a
        # foreground cascading deletion (https://kubernetes.io/docs/concepts/workloads/controllers/garbage-collection/#foreground-cascading-deletion)
        # instead, but for now this works well enough.
        yield self.delete_if_exists('endpoint', safe_name, delete_endpoint)
        yield self.delete_if_exists('service', safe_name, delete_service)
        yield self.delete_if_exists('ingress', safe_name, delete_ingress)


    @gen.coroutine
    def get_all_routes(self):
        # copy everything, because iterating over this directly is not threadsafe
        # FIXME: is this performance intensive? It could be! Measure?
        # FIXME: Validate that this shallow copy *is* thread safe
        ingress_copy = dict(self.ingress_reflector.ingresses)
        routes = {
            ingress.metadata.annotations['hub.jupyter.org/proxy-routespec']:
            {
                'routespec': ingress.metadata.annotations['hub.jupyter.org/proxy-routespec'],
                'target': ingress.metadata.annotations['hub.jupyter.org/proxy-target'],
                'data': json.loads(ingress.metadata.annotations['hub.jupyter.org/proxy-data'])
            }
            for ingress in ingress_copy.values()
        }

        return routes
