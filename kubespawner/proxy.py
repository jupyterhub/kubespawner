import os
import string
import escapism
import json
from kubernetes import client

from jupyterhub.proxy import Proxy

from kubespawner.objects import make_ingress
from kubespawner.reflector import NamespacedResourceReflector
from concurrent.futures import ThreadPoolExecutor
from traitlets import Unicode
from tornado import gen
from tornado.concurrent import run_on_executor


class IngressReflector(NamespacedResourceReflector):
    labels = {
        'heritage': 'jupyterhub',
        'component': 'singleuser-server',
        'hub.jupyter.org/proxy-route': 'true'
    }

    list_method_name = 'list_namespaced_ingress'
    api_group_name = 'ExtensionsV1beta1Api'

    @property
    def ingresses(self):
        return self.resources

class ServiceReflector(NamespacedResourceReflector):
    labels = {
        'heritage': 'jupyterhub',
        'component': 'singleuser-server',
        'hub.jupyter.org/proxy-route': 'true'
    }

    list_method_name = 'list_namespaced_service'

    @property
    def services(self):
        return self.resources

class EndpointsReflector(NamespacedResourceReflector):
    labels = {
        'heritage': 'jupyterhub',
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

        # other attributes
        self.executor = ThreadPoolExecutor(max_workers=24)

        self.ingress_reflector = IngressReflector(parent=self, namespace=self.namespace)
        self.service_reflector = ServiceReflector(parent=self, namespace=self.namespace)
        self.endpoint_reflector = EndpointsReflector(parent=self, namespace=self.namespace)

        self.core_api = client.CoreV1Api()
        self.extension_api = client.ExtensionsV1beta1Api()

    @run_on_executor
    def asynchronize(self, method, *args, **kwargs):
        return method(*args, **kwargs)

    @gen.coroutine
    def add_route(self, routespec, target, data):
        # Create a route with the name being escaped routespec
        # Use full routespec in label
        # 'data' is JSON encoded and put in an annotation - we don't need to query for it
        safe_chars = set(string.ascii_lowercase + string.digits)
        safe_name = 'jupyter-' + escapism.escape(routespec, safe=safe_chars, escape_char='-').lower() + '-route'
        endpoint, service, ingress = make_ingress(
            safe_name,
            routespec,
            target,
            data
        )

        @gen.coroutine
        def create_if_required(create_func, delete_func, body, kind, pass_body_to_delete=True, attempt=0):
            try:
                resp = yield self.asynchronize(
                    create_func,
                    namespace=self.namespace,
                    body=body
                )
                self.log.info('Created %s/%s', kind, safe_name)
            except client.rest.ApiException as e:
                if e.status == 409 and attempt == 0:
                    # This object already exists, we should delete it and try again
                    self.log.warn("Trying to create %s/%s, it already exists. Deleting & recreating", kind, safe_name)
                    delete_options = client.V1DeleteOptions(grace_period_seconds=0)
                    try:
                        kwargs = {
                            'name': safe_name,
                            'namespace': self.namespace
                        }
                        if pass_body_to_delete:
                            kwargs['body'] = delete_options
                        yield self.asynchronize(
                            delete_func,
                            **kwargs
                        )
                        create_if_required(create_func, delete_func, body, kind, attempt+1)
                    except client.rest.ApiException as e:
                        if e.status == 404:
                            self.log.warn("Could not delete %s/%s, it has already been deleted?", kind, safe_name)
                        else:
                            raise
                else:
                    raise

        yield create_if_required(
            self.core_api.create_namespaced_endpoints,
            self.core_api.delete_namespaced_endpoints,
            body=endpoint,
            kind='endpoints'
        )

        while safe_name not in self.endpoint_reflector.endpoints:
            self.log.info('waiting for endpoints %s to show up!', safe_name)
            yield gen.sleep(1)

        yield create_if_required(
            self.core_api.create_namespaced_service,
            self.core_api.delete_namespaced_service,
            body=service,
            pass_body_to_delete=False,
            kind='service'
        )

        while safe_name not in self.service_reflector.services:
            self.log.info('waiting for services %s to show up!', safe_name)
            yield gen.sleep(1)


        yield create_if_required(
            self.extension_api.create_namespaced_ingress,
            self.extension_api.delete_namespaced_ingress,
            body=ingress,
            kind='ingress'
        )
        while safe_name not in self.ingress_reflector.ingresses:
            self.log.info('waiting for ingress %s to show up!', safe_name)
            yield gen.sleep(1)

        self.log.info("Created ingress %s", safe_name)


    @gen.coroutine
    def delete_route(self, routespec):
        # We just ensure that these objects are deleted.
        # This means if some of them are already deleted, we just let it
        # be.
        safe_chars = set(string.ascii_lowercase + string.digits)
        safe_name = 'jupyter-' + escapism.escape(routespec, safe=safe_chars, escape_char='-').lower() + '-route'

        delete_options = client.V1DeleteOptions(grace_period_seconds=0)

        delete_endpoint = self.asynchronize(
            self.core_api.delete_namespaced_endpoints,
            name=safe_name,
            namespace=self.namespace,
        )

        delete_service = self.asynchronize(
            self.core_api.delete_namespaced_service,
            name=safe_name,
            namespace=self.namespace,
        )

        delete_ingress = self.asynchronize(
                self.extension_api.delete_namespaced_ingress,
                name=safe_name,
                namespace=self.namespace,
                body=delete_options,
                grace_period_seconds=0
        )

        # This seems like cleanest way to parallelize all three of these while
        # also making sure we only ignore the exception when it's a 404
        def delete_if_exists(kind, future):
            try:
                yield future
            except client.rest.ApiException as e:
                if e.status != 404:
                    raise
                self.log.warn("Could not delete %s %s: does not exist", kind, safe_name)


        delete_if_exists('endpoint', delete_endpoint)
        delete_if_exists('service', delete_service)
        delete_if_exists('ingress', delete_ingress)


    @gen.coroutine
    def get_all_routes(self):
        # FIXME: Is this threadsafe?
        routes = {
            i.metadata.annotations['hub.jupyter.org/proxy-routespec']:
            {
                'routespec': i.metadata.annotations['hub.jupyter.org/proxy-routespec'],
                'target': i.metadata.annotations['hub.jupyter.org/proxy-target'],
                'data': json.loads(i.metadata.annotations['hub.jupyter.org/proxy-data'])
            }
            for i in self.ingress_reflector.ingresses.values()
        }

        return routes
