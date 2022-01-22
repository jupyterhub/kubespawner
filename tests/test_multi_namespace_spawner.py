import json
import os
from asyncio import get_event_loop
from unittest.mock import Mock

import pytest
from jupyterhub.objects import Hub
from jupyterhub.objects import Server
from jupyterhub.orm import Spawner
from kubernetes_asyncio import client
from kubernetes_asyncio.client import V1Namespace
from kubernetes_asyncio.client.models import V1Capabilities
from kubernetes_asyncio.client.models import V1Container
from kubernetes_asyncio.client.models import V1Pod
from kubernetes_asyncio.client.models import V1SecurityContext
from kubernetes_asyncio.client.rest import ApiException
from traitlets.config import Config

from kubespawner import KubeSpawner
from kubespawner.clients import set_k8s_client_configuration

class MockUser(Mock):
    name = 'multifake'
    server = Server()

    @property
    def escaped_name(self):
        return self.name

    @property
    def url(self):
        return self.server.url


def test_enable_user_namespaces():
    user = MockUser()
    spawner = KubeSpawner(user=user, _mock=True, enable_user_namespaces=True)
    assert spawner.namespace.endswith("-{}".format(user.escaped_name))


def test_multi_namespace_spawner_class():
    user = MockUser()
    spawner = KubeSpawner(user=user, _mock=True, enable_user_namespaces=True)
    assert spawner.namespace.endswith("-{}".format(user.escaped_name))


@pytest.mark.asyncio
async def test_multi_namespace_spawn():
    # We cannot use the fixtures, because they assume the standard
    #  namespace and client for that namespace.

    spawner = KubeSpawner(
        hub=Hub(),
        user=MockUser(),
        config=Config(),
        enable_user_namespaces=True,
    )

    # empty spawner isn't running
    status = await spawner.poll()
    assert isinstance(status, int)

    # get a client
    kube_ns = spawner.namespace
    await set_k8s_client_configuration()
    async with client.ApiClient() as api_client:
        api=client.CoreV1Api(api_client)

        # the spawner will create the namespace on its own.

        # Wrap in a try block so we clean up the namespace in finally.

        try:
            # start the spawner
            await spawner.start()
            print("after start()")
            # verify the pod exists
            p_list = await api.list_namespaced_pod(kube_ns) 
            pods = p_list.items
            pod_names = [p.metadata.name for p in pods]
            assert "jupyter-%s" % spawner.user.name in pod_names
            print("running")
            # verify poll while running
            status = await spawner.poll()
            assert status is None
            print("polled")
            # stop the pod
            await spawner.stop()
            print ("stopped")
            # verify pod is gone
            p_list = await api.list_namespaced_pod(kube_ns) 
            pods = p_list.items
            pod_names = [p.metadata.name for p in pods]
            assert "jupyter-%s" % spawner.user.name not in pod_names
            # verify exit status
            status = await spawner.poll()
            assert isinstance(status, int)
        # remove namespace
        finally:
            # Allow opting out of deletion.
            if not os.environ.get("KUBESPAWNER_DEBUG_NAMESPACE"):
                try:
                    await api.delete_namespace(kube_ns, body={})
                except ApiException as exc:
                    if exc.status == 404:
                        spawner.log.warning(f"Namespace {kube_ns} not found.")
                    else:
                        raise
