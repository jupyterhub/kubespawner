from traitlets.config import Config
from asyncio import get_event_loop
from kubespawner import KubeSpawner
from kubernetes.client.models import (
    V1SecurityContext, V1Container, V1Capabilities, V1Pod
)

def sync_wait(future):
    loop = get_event_loop()
    loop.run_until_complete(future)
    return future.result()


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
