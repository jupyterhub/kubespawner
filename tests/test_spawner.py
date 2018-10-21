from unittest.mock import Mock

from jupyterhub.objects import Hub, Server
import pytest
from traitlets.config import Config
from asyncio import get_event_loop
from v3iokubespawner import KubeSpawner
from kubernetes.client.models import (
    V1SecurityContext, V1Container, V1Capabilities, V1Pod
)

def sync_wait(future):
    loop = get_event_loop()
    loop.run_until_complete(future)
    return future.result()


class MockUser(Mock):
    name = 'fake'
    server = Server()

    @property
    def url(self):
        return self.server.url


def test_deprecated_config():
    """Deprecated config is handled correctly"""
    c = Config()
    # both set, non-deprecated wins
    c.KubeSpawner.singleuser_fs_gid = 5
    c.KubeSpawner.fs_gid = 10
    # only deprecated set, should still work
    c.KubeSpawner.singleuser_extra_pod_config = extra_pod_config = {"key": "value"}
    spawner = KubeSpawner(config=c, _mock=True)
    assert spawner.fs_gid == 10
    assert spawner.extra_pod_config == extra_pod_config
    # deprecated access gets the right values, too
    assert spawner.singleuser_fs_gid == spawner.fs_gid
    assert spawner.singleuser_extra_pod_config == spawner.extra_pod_config


def test_deprecated_runtime_access():
    """Runtime access/modification of deprecated traits works"""
    spawner = KubeSpawner(_mock=True)
    spawner.singleuser_uid = 10
    assert spawner.uid == 10
    assert spawner.singleuser_uid == 10
    spawner.uid = 20
    assert spawner.uid == 20
    assert spawner.singleuser_uid == 20


@pytest.mark.asyncio
async def test_spawn(kube_ns, kube_client, config):
    spawner = KubeSpawner(hub=Hub(), user=MockUser(), config=config)
    # empty spawner isn't running
    status = await spawner.poll()
    assert isinstance(status, int)

    # start the spawner
    await spawner.start()
    # verify the pod exists
    pods = kube_client.list_namespaced_pod(kube_ns).items
    pod_names = [p.metadata.name for p in pods]
    assert "jupyter-%s" % spawner.user.name in pod_names
    # verify poll while running
    status = await spawner.poll()
    assert status is None
    # stop the pod
    await spawner.stop()

    # verify pod is gone
    pods = kube_client.list_namespaced_pod(kube_ns).items
    pod_names = [p.metadata.name for p in pods]
    assert "jupyter-%s" % spawner.user.name not in pod_names

    # verify exit status
    status = await spawner.poll()
    assert isinstance(status, int)


@pytest.mark.asyncio
async def test_spawn_progress(kube_ns, kube_client, config):
    spawner = KubeSpawner(hub=Hub(), user=MockUser(name="progress"), config=config)
    # empty spawner isn't running
    status = await spawner.poll()
    assert isinstance(status, int)

    # start the spawner
    start_future = spawner.start()
    # check progress events
    messages = []
    async for event in spawner.progress():
        assert 'progress' in event
        assert isinstance(event['progress'], int)
        assert 'message' in event
        assert isinstance(event['message'], str)
        messages.append(event['message'])
    assert 'Started container' in '\n'.join(messages)

    await start_future
    # stop the pod
    await spawner.stop()


def test_get_pod_manifest_tolerates_mixed_input():
    """
    Test that the get_pod_manifest function can handle a either a dictionary or
    an object both representing V1Container objects and that the function
    returns a V1Pod object containing V1Container objects.
    """
    c = Config()

    dict_model = {
        'name': 'mock_name_1',
        'image': 'mock_image_1',
        'command': ['mock_command_1']
    }
    object_model = V1Container(
        name="mock_name_2",
        image="mock_image_2",
        command=['mock_command_2'],
        security_context=V1SecurityContext(
            privileged=True,
            run_as_user=0,
            capabilities=V1Capabilities(add=['NET_ADMIN'])
        )
    )
    c.KubeSpawner.init_containers = [dict_model, object_model]

    spawner = KubeSpawner(config=c, _mock=True)

    # this test ensures the following line doesn't raise an error
    manifest = sync_wait(spawner.get_pod_manifest())

    # and tests the return value's types
    assert isinstance(manifest, V1Pod)
    assert isinstance(manifest.spec.init_containers[0], V1Container)
    assert isinstance(manifest.spec.init_containers[1], V1Container)
