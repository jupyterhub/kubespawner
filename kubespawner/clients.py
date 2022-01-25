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

async def set_k8s_client_configuration(client=None):
    # Call this prior to using a client for readability /
    # coupling with traitlets values.
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
