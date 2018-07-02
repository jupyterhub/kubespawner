from traitlets.config import Config
from kubespawner import KubeSpawner


def test_deprecated_config():
    """Deprecated config is handled correctly"""
    cfg = Config()
    ks_cfg = cfg.KubeSpawner
    # both set, non-deprecated wins
    ks_cfg.singleuser_fs_gid = 5
    ks_cfg.fs_gid = 10
    # only deprecated set, should still work
    ks_cfg.singleuser_extra_pod_config = extra_pod_config = {"key": "value"}
    spawner = KubeSpawner(config=cfg, _mock=True)
    assert spawner.fs_gid == 10
    assert spawner.extra_pod_config == extra_pod_config
    # deprecated access gets the right values, too
    assert spawner.singleuser_fs_gid == spawner.fs_gid
    assert spawner.singleuser_extra_pod_config == spawner.singleuser_extra_pod_config


def test_deprecated_runtime_access():
    """Runtime access/modification of deprecated traits works"""
    spawner = KubeSpawner(_mock=True)
    spawner.singleuser_uid = 10
    assert spawner.uid == 10
    assert spawner.singleuser_uid == 10
    spawner.uid = 20
    assert spawner.uid == 20
    assert spawner.singleuser_uid == 20
