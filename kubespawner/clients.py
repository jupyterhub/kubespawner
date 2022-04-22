"""Configures and instantiates REST API clients of various kinds to
communicate with a Kubernetes api-server, but only one instance per kind is
instantiated.

The instances of these REST API clients are also patched to avoid the creation
of unused threads.
"""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from unittest.mock import Mock

import kubernetes_asyncio.client
from kubernetes_asyncio.client import Configuration, api_client

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

    Cache is one client per running loop per combination of input args.

    Client will be closed when the loop closes.
    """
    kwarg_key = tuple((key, kwargs[key]) for key in sorted(kwargs))
    cache_key = (asyncio.get_running_loop(), ClientType, args, kwarg_key)
    client = _client_cache.get(cache_key, None)

    if client is None:
        # Kubernetes client configuration is handled globally and should already
        # be configured from spawner.py or proxy.py via the load_config function
        # prior to a shared_client being instantiated.
        Client = getattr(kubernetes_asyncio.client, ClientType)
        client = Client(*args, **kwargs)

        _client_cache[cache_key] = client

        # create a task that will close the client when it is cancelled
        # relies on JupyterHub's task cleanup at shutdown
        async def close_client_task():
            try:
                async with client.api_client:
                    while True:
                        await asyncio.sleep(300)
            except asyncio.CancelledError:
                pass
            finally:
                _client_cache.pop(cache_key, None)

        asyncio.create_task(close_client_task())

    return client


@lru_cache()
def load_config(host=None, ssl_ca_cert=None):
    """
    Loads global configuration for the Python client we use to communicate with
    a Kubernetes API server, and optionally tweaks that configuration based on
    specific settings on the passed caller object.

    This needs to be called before creating a kubernetes client, so practically
    before the shared_client function is called.
    """
    try:
        kubernetes_asyncio.config.load_incluster_config()
    except kubernetes_asyncio.config.ConfigException:
        # avoid making this async just for load-config
        # run async load_kube_config in a background thread,
        # blocking this thread until it's done
        with ThreadPoolExecutor(1) as pool:
            load_sync = lambda: asyncio.run(
                kubernetes_asyncio.config.load_kube_config()
            )
            future = pool.submit(load_sync)
            # blocking wait for load to complete
            future.result()

    if ssl_ca_cert:
        global_conf = Configuration.get_default_copy()
        global_conf.ssl_ca_cert = ssl_ca_cert
        Configuration.set_default(global_conf)
    if host:
        global_conf = Configuration.get_default_copy()
        global_conf.host = host
        Configuration.set_default(global_conf)
