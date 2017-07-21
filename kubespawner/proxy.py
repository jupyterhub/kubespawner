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
        self.executor = ThreadPoolExecutor(max_workers=8)

        self.ingress_reflector = IngressReflector(parent=self, namespace=self.namespace)

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

        yield self.asynchronize(
            self.core_api.create_namespaced_endpoints,
            namespace=self.namespace,
            body=endpoint
        )

        yield self.asynchronize(
            self.core_api.create_namespaced_service,
            namespace=self.namespace,
            body=service
        )

        yield self.asynchronize(
            self.extension_api.create_namespaced_ingress,
            namespace=self.namespace,
            body=ingress
        )


    @gen.coroutine
    def delete_route(self, routespec):
        # We just ensure that these objects are deleted.
        # This means if some of them are already deleted, we just let it
        # be.
        safe_chars = set(string.ascii_lowercase + string.digits)
        safe_name = 'jupyter-' + escapism.escape(routespec, safe=safe_chars, escape_char='-').lower() + '-route'

        delete_options = client.V1DeleteOptions()

        try:
            yield self.asynchronize(
                self.core_api.delete_namespaced_endpoints,
                name=safe_name,
                namespace=self.namespace,
                body=delete_options
            )
        except client.rest.ApiException as e:
            if e.status != 404:
                raise
            self.log.warn("Could not delete endpoints %s: does not exist", safe_name)

        try:
            yield self.asynchronize(
                self.core_api.delete_namespaced_service,
                name=safe_name,
                namespace=self.namespace,
            )
        except client.rest.ApiException as e:
            if e.status != 404:
                raise
            self.log.warn("Could not delete service %s: does not exist", safe_name)

        try:
            yield self.asynchronize(
                self.extension_api.delete_namespaced_ingress,
                name=safe_name,
                namespace=self.namespace,
                body=delete_options
            )
        except client.rest.ApiException as e:
            if e.status != 404:
                raise
            self.log.warn("Could not delete ingress %s: does not exist", safe_name)

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
