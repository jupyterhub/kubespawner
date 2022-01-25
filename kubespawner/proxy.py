import json
import os
import string
from concurrent.futures import ThreadPoolExecutor

import escapism
from jupyterhub.proxy import Proxy
from jupyterhub.utils import exponential_backoff
from kubernetes import client
from tornado import gen
from tornado.concurrent import run_on_executor
from traitlets import Unicode, default

from .objects import make_ingress
from .reflector import ResourceReflector
from .utils import generate_hashed_slug


class IngressReflector(ResourceReflector):
    kind = 'ingresses'

    @property
    def ingresses(self):
        return self.retrieve_resource_copy()


class ServiceReflector(ResourceReflector):
    kind = 'services'

    @property
    def services(self):
        return self.retrieve_resource_copy()


class EndpointsReflector(ResourceReflector):
    kind = 'endpoints'

    @property
    def endpoints(self):
        return self.retrieve_resource_copy()


class KubeIngressProxy(Proxy):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # The reflector instantiation will set the client configuration for us.

        labels = {
            'component': self.component_label,
            'hub.jupyter.org/proxy-route': 'true',
        }
        # Create our reflectors with the classmethod, to start their watch
        #  tasks and initialize their K8s configuration.
        self.ingress_reflector = IngressReflector.reflector(
            parent=self, namespace=self.namespace, labels=labels
        )
        self.service_reflector = ServiceReflector.reflector(
            parent=self, namespace=self.namespace, labels=labels
        )
        self.endpoint_reflector = EndpointsReflector.reflector(
            parent=self, namespace=self.namespace, labels=labels
        )

    ### Here through _namespace_default are traitlets shared with the spawner
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
        with service accounts enabled.

        If not in a k8s cluster with service accounts enabled, default to
        'default'
        """
        ns_path = '/var/run/secrets/kubernetes.io/serviceaccount/namespace'
        if os.path.exists(ns_path):
            with open(ns_path) as f:
                return f.read().strip()
        return 'default'

    #### End shared-with-spawner traitlets

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
            self.log.info(f"Deleted {kind}/{safe_name}")
        except client.rest.ApiException as e:
            if e.status != 404:
                raise
            self.log.warn(f"Could not delete nonexistent {kind}/{safe_name}")

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

        async def ensure_object(api_group_name="CoreV1Api",
                                body=None, kind=""):
            async with client.ApiClient() as api_client:
                grp=getattr(client, api_group_name)
                api=grp(api_client)
                create_func=getattr(api,f"create_namespaced_{kind}")
                patch_func=getattr(api,f"patch_namespaced_{kind}")
                try:
                    resp = await create_func(namespace=self.namespace,
                                             body=body)
                    self.log.info('Created %s/%s', kind, safe_name)
                except client.rest.ApiException as e:
                    if e.status == 409:
                        # This object already exists.
                        # We should patch it to make it be what we want
                        self.log.warn("Trying to patch extant " +
                                      f"{kind}/{safe_name}")
                        resp = await patch_func(
                            namespace=self.namespace,
                            body=body,
                            name=body.metadata.name,
                        )
                    else:
                        raise

            if endpoint is not None:
                await ensure_object(
                    body=endpoint,
                    kind='endpoints',
                )

                await exponential_backoff(
                    lambda: f"{self.namespace}/{safe_name}"
                    in self.endpoint_reflector.endpoints.keys(),
                    f"Could not find endpoints/{safe_name} after creating it"
                )
            else:
                delete_endpoint = api.delete_namespaced_endpoints(
                    name=safe_name,
                    namespace=self.namespace,
                    body=client.V1DeleteOptions(grace_period_seconds=0),
                )  # We want the future back, for the delete_if_exists call
                # That sounded way more philosophical than I meant it to.
                await self.delete_if_exists('endpoints', safe_name,
                                            delete_endpoint)

        await ensure_object(
            body=service,
            kind='service',
        )

        await exponential_backoff(
            lambda: f'{self.namespace}/{safe_name}'
            in self.service_reflector.services.keys(),
            'Could not find service/%s after creating it' % safe_name,
        )

        await ensure_object(
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
        async with client.ApiClient() as api_client:
            grp=getattr(client, "CoreV1Api")
            api=grp(api_client)
        
            delete_endpoint = api.delete_namespaced_endpoints(
                name=safe_name,
                namespace=self.namespace,
                body=delete_options,
            )

            delete_service = api.delete_namespaced_service(
                name=safe_name,
                namespace=self.namespace,
                body=delete_options,
            )

            delete_ingress = api.delete_namespaced_ingress(
                name=safe_name,
                namespace=self.namespace,
                body=delete_options,
                grace_period_seconds=0,
            )

            # This seems like cleanest way to parallelize all three of these
            # while also making sure we only ignore the exception when it's a
            # 404.
            # The order matters for endpoint & service - deleting the service
            # deletes the endpoint in the background. This can be racy.
            # however, so we do so explicitly ourselves as well. In the
            # future, we can probably try a foreground cascading deletion
            # (https://kubernetes.io/docs/concepts/workloads/controllers/garbage-collection/#foreground-cascading-deletion)
            # instead, but for now this works well enough.

            # Well, no it doesn't.  Creating tasks to delete those, and then
            # doing a gather, is probably cleaner than that.
            
            await self.delete_if_exists('endpoint', safe_name, delete_endpoint)
            await self.delete_if_exists('service', safe_name, delete_service)
            await self.delete_if_exists('ingress', safe_name, delete_ingress)

    async def get_all_routes(self):
        # copy everything, because iterating over this directly is not
        # threadsafe
        # FIXME: is this performance intensive? It could be! Measure?
        ingress_copy = self.ingress_reflector.retrieve_resources()
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
