import json
import os
from asyncio import get_event_loop
from unittest.mock import Mock

import pytest
from jupyterhub.objects import Hub
from jupyterhub.objects import Server
from jupyterhub.orm import Spawner
from kubernetes.client import V1Namespace
from kubernetes.client.models import V1Capabilities
from kubernetes.client.models import V1Container
from kubernetes.client.models import V1Pod
from kubernetes.client.models import V1SecurityContext
from kubernetes.config import load_kube_config
from traitlets.config import Config

from kubespawner import KubeSpawner
from kubespawner.clients import shared_client


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
    load_kube_config()
    client = shared_client('CoreV1Api')

    # the spawner will create the namespace on its own.

    # Wrap in a try block so we clean up the namespace.

    saved_exception = None
    try:
        # start the spawner
        await spawner.start()

        # verify the pod exists
        pods = client.list_namespaced_pod(kube_ns).items
        pod_names = [p.metadata.name for p in pods]
        assert "jupyter-%s" % spawner.user.name in pod_names
        # verify poll while running
        status = await spawner.poll()
        assert status is None
        # stop the pod
        await spawner.stop()
        # verify pod is gone
        pods = client.list_namespaced_pod(kube_ns).items
        pod_names = [p.metadata.name for p in pods]
        assert "jupyter-%s" % spawner.user.name not in pod_names
        # verify exit status
        status = await spawner.poll()
        assert isinstance(status, int)
    except Exception as saved_exception:
        pass  # We will raise after namespace removal
    # remove namespace
    client.delete_namespace(kube_ns, body={})
    if saved_exception is not None:
        raise saved_exception
