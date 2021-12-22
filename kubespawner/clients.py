"""Shared clients for kubernetes

avoids creating multiple kubernetes client objects,
each of which spawns an unused max-size thread pool
"""
import asyncio
import os
import weakref
from unittest.mock import Mock
from traitlets import default
from traitlets import Unicode

import kubernetes_asyncio.client
from kubernetes_asyncio.client import api_client

_client_cache = {}


async def shared_client(ClientType, *args, **kwargs):
    """Return a single shared kubernetes client instance

    A weak reference to the instance is cached,
    so that concurrent calls to shared_client
    will all return the same instance until
    all references to the client are cleared.
    """
    kwarg_key = tuple((key, kwargs[key]) for key in sorted(kwargs))
    cache_key = (ClientType, args, kwarg_key)
    client = None
    if cache_key in _client_cache:
        # resolve cached weakref
        # client can still be None after this!
        client = _client_cache[cache_key]()

    if client is None:
        Client = getattr(kubernetes_asyncio.client, ClientType)
        client = Client(*args, **kwargs)
        # cache weakref so that clients can be garbage collected
        _client_cache[cache_key] = weakref.ref(client)
    return client

async def set_k8s_client_configuration(client=None):
    # The actual (singleton) Kubernetes client will be created
    # in shared_client but the configuration for token / ca_cert /
    # k8s api host is set globally.  Call this prior to using
    # shared_client() for readability / coupling with traitlets values.
    try:
        kubernetes_asyncio.config.load_incluster_config()
    except kubernetes_asyncio.config.ConfigException:
        await kubernetes_asyncio.config.load_kube_config()
    if not client:
        return
    if client.k8s_api_ssl_ca_cert:
        global_conf = kubernetes_asyncio.client.Configuration.get_default_copy()
        global_conf.ssl_ca_cert = client.k8s_api_ssl_ca_cert
        kubernetes_asyncio.client.Configuration.set_default(global_conf)
    if client.k8s_api_host:
        global_conf = kubernetes_asyncio.client.Configuration.get_default_copy()
        global_conf.host = client.k8s_api_host
        kubernetes_asyncio.client.Configuration.set_default(global_conf)


class K8sAsyncClientMixin(object):
    """
    This class is designed to be mixed into either the KubeIngressProxy
    or KubeSpawner class.

    It handles instantiating the appropriate K8s clients for each of those
    classes (or derived classes)
    """

    async def _ensure_core_api(self):
        await self._set_k8s_client_configuration()
        if self.core_api is None:
            self.core_api = await shared_client('CoreV1Api')

    async def _ensure_extension_api(self):
        await self._set_k8s_client_configuration()        
        if self.extension_api is None:
            self.extension_api = await shared_client('ExtensionsV1beta1Api')

    async def _set_k8s_client_configuration(self):
        if not hasattr(self, "_k8s_client_configured"):
            self._k8s_client_configured = False
        if self._k8s_client_configured:
            return
        await set_k8s_client_configuration(self)
        self._k8s_client_configured = True
