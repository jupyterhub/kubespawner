"""Shared clients for kubernetes

avoids creating multiple kubernetes client objects,
each of which spawns an unused max-size thread pool
"""

from unittest.mock import Mock
import weakref

import kubernetes.client
from kubernetes.client import api_client

# FIXME: remove when instantiating a kubernetes client
# doesn't create N-CPUs threads unconditionally.
# monkeypatch threadpool in kubernetes api_client
# to avoid instantiating ThreadPools.
# This is known to work for kubernetes-4.0
# and may need updating with later kubernetes clients
_dummy_pool = Mock()
api_client.ThreadPool = lambda *args, **kwargs: _dummy_pool

_client_cache = {}


def shared_client(ClientType, *args, **kwargs):
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
        Client = getattr(kubernetes.client, ClientType)
        client = Client(*args, **kwargs)
        # cache weakref so that clients can be garbage collected
        _client_cache[cache_key] = weakref.ref(client)
    return client
