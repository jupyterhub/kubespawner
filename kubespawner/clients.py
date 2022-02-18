"""Configures and instantiates REST API clients of various kinds to
communicate with a Kubernetes api-server, but only one instance per kind is
instantiated.

The instances of these REST API clients are also patched to avoid the creation
of unused threads.
"""
import weakref
from unittest.mock import Mock

import kubernetes_asyncio.client
from kubernetes_asyncio.client import api_client
from kubernetes_asyncio.client import Configuration

# FIXME: Remove this workaround when instantiating a k8s client doesn't
#        automatically create a ThreadPool with 1 thread that we won't use
#        anyhow. To know if that has happened, reading
#        https://github.com/jupyterhub/kubespawner/issues/567 may be helpful.
#
#        The workaround is to monkeypatch ThreadPool in the kubernetes
#        api_client to avoid ThreadPools. This is known to work with both
#        `kubernetes` and `kubernetes_asyncio`.
#
_dummy_pool = Mock()
api_client.ThreadPool = lambda *args, **kwargs: _dummy_pool

_client_cache = {}


def shared_client(ClientType, *args, **kwargs):
    """Return a shared kubernetes client instance
    based on the provided arguments.

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
        # Kubernetes client configuration is handled globally and should already
        # be configured from spawner.py or proxy.py via the load_config function
        # prior to a shared_client being instantiated.
        Client = getattr(kubernetes_asyncio.client, ClientType)
        client = Client(*args, **kwargs)
        # cache weakref so that clients can be garbage collected
        _client_cache[cache_key] = weakref.ref(client)

    return client


async def load_config(caller):
    """
    Loads global configuration for the Python client we use to communicate with
    a Kubernetes API server, and optionally tweaks that configuration based on
    specific settings on the passed caller object.

    This needs to be called before creating a kubernetes client, so practically
    before the shared_client function is called. The caller must have both the
    k8s_api_ssl_ca_cert and k8s_api_host attributes. KubeSpawner and
    KubeIngressProxy both have these attributes.
    """
    try:
        kubernetes_asyncio.config.load_incluster_config()
    except kubernetes_asyncio.config.ConfigException:
        await kubernetes_asyncio.config.load_kube_config()

    if caller.k8s_api_ssl_ca_cert:
        global_conf = Configuration.get_default_copy()
        global_conf.ssl_ca_cert = caller.k8s_api_ssl_ca_cert
        Configuration.set_default(global_conf)
    if caller.k8s_api_host:
        global_conf = Configuration.get_default_copy()
        global_conf.host = caller.k8s_api_host
        Configuration.set_default(global_conf)
