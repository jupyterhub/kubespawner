import json
import os
import time
from unittest.mock import Mock

import pytest
from jupyterhub.objects import Hub
from jupyterhub.objects import Server
from jupyterhub.orm import Spawner
from traitlets.config import Config
from kubernetes_asyncio import client
from kubernetes_asyncio.client.rest import ApiException

from kubespawner import KubeSpawner
from kubespawner.clients import set_k8s_client_configuration

class MockUser(Mock):
    name = 'fake'
    server = Server()

    def __init__(self, **kwargs):
        super().__init__()
        for key, value in kwargs.items():
            setattr(self, key, value)

    @property
    def escaped_name(self):
        return self.name

    @property
    def url(self):
        return self.server.url

@pytest.mark.asyncio
async def test_spawn_progress():
    spawner = KubeSpawner(
        hub=Hub(),
        enable_user_namespaces=True,
        user=MockUser(name="progress"),
        config=Config()
    )

    # empty spawner isn't running
    status = await spawner.poll()
    assert isinstance(status, int)

    kube_ns = spawner.namespace

    try:
        # start the spawner
        start_future = spawner.start()
        # check progress events
        messages = []
        async for progress in spawner.progress():
            assert 'progress' in progress
            assert isinstance(progress['progress'], int)
            assert 'message' in progress
            assert isinstance(progress['message'], str)
            messages.append(progress['message'])

            # ensure we can serialize whatever we return
            with open(os.devnull, "w") as devnull:
                json.dump(progress, devnull)

        assert 'started' in ('\n'.join(messages)).lower()

        await start_future
        # stop the pod
        await spawner.stop()

    finally:
        # Allow opting out of deletion.
        if not os.environ.get("KUBESPAWNER_DEBUG_NAMESPACE"):
            try:
                await set_k8s_client_configuration()
                async with client.ApiClient() as api_client:
                    api=client.CoreV1Api(api_client)
                    await api.delete_namespace(kube_ns, body={})
            except ApiException as exc:
                if exc.status == 404:
                    spawner.log.warning(f"Namespace {kube_ns} not found.")
                else:
                    raise
        
