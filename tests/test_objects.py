"""
Test functions used to create k8s objects
"""
from kubespawner.objects import make_pod_spec, make_pvc_spec


def test_make_simplest_pod():
    """
    Test specification of the simplest possible pod specification
    """
    assert make_pod_spec(
        name='test',
        image_spec='jupyter/singleuser:latest',
        env={},
        volumes=[],
        volume_mounts=[],
        cpu_limit=None,
        cpu_guarantee=None,
        mem_limit=None,
        mem_guarantee=None
    ) == {
        "metadata": {
            "name": "test"
        },
        "spec": {
            "containers": [
                {
                    "env": [],
                    "name": "notebook",
                    "image": "jupyter/singleuser:latest",
                    "ports": [{
                        "containerPort": 8888
                    }],
                    "volumeMounts": [],
                    "resources": {
                        "limits": {
                            "cpu": None,
                            "memory": None
                        },
                        "requests": {
                            "cpu": None,
                            "memory": None
                        }
                    }
                }
            ],
            "volumes": []
        },
        "kind": "Pod",
        "apiVersion": "v1"
    }


def test_make_pod_resources_all():
    """
    Test specifying all possible resource limits & guarantees
    """
    assert make_pod_spec(
        name='test',
        image_spec='jupyter/singleuser:latest',
        env={},
        volumes=[],
        volume_mounts=[],
        cpu_limit=2,
        cpu_guarantee=1,
        mem_limit='1Gi',
        mem_guarantee='512Mi'
    ) == {
        "metadata": {
            "name": "test"
        },
        "spec": {
            "containers": [
                {
                    "env": [],
                    "name": "notebook",
                    "image": "jupyter/singleuser:latest",
                    "ports": [{
                        "containerPort": 8888
                    }],
                    "volumeMounts": [],
                    "resources": {
                        "limits": {
                            "cpu": 2,
                            "memory": '1Gi'
                        },
                        "requests": {
                            "cpu": 1,
                            "memory": '512Mi'
                        }
                    }
                }
            ],
            "volumes": []
        },
        "kind": "Pod",
        "apiVersion": "v1"
    }


def test_make_pod_with_env():
    """
    Test specification of a pod with custom environment variables
    """
    assert make_pod_spec(
        name='test',
        image_spec='jupyter/singleuser:latest',
        env={
            'TEST_KEY': 'TEST_VALUE'
        },
        volumes=[],
        volume_mounts=[],
        cpu_limit=None,
        cpu_guarantee=None,
        mem_limit=None,
        mem_guarantee=None
    ) == {
        "metadata": {
            "name": "test"
        },
        "spec": {
            "containers": [
                {
                    "env": [{'name': 'TEST_KEY', 'value': 'TEST_VALUE'}],
                    "name": "notebook",
                    "image": "jupyter/singleuser:latest",
                    "ports": [{
                        "containerPort": 8888
                    }],
                    "volumeMounts": [],
                    "resources": {
                        "limits": {
                            "cpu": None,
                            "memory": None
                        },
                        "requests": {
                            "cpu": None,
                            "memory": None
                        }
                    }
                }
            ],
            "volumes": []
        },
        "kind": "Pod",
        "apiVersion": "v1"
    }


def test_make_pvc_simple():
    """
    Test specification of the simplest possible pvc specification
    """
    assert make_pvc_spec(
        name='test',
        storage_class='',
        access_modes=[],
        storage=None
    ) == {
        'kind': 'PersistentVolumeClaim',
        'apiVersion': 'v1',
        'metadata': {
            'name': 'test',
            'annotations': {
                'volume.beta.kubernetes.io/storage-class': ''
            }
        },
        'spec': {
            'accessModes': [],
            'resources': {
                'requests': {
                    'storage': None
                }
            }
        }
    }


def test_make_resources_all():
    """
    Test specifying all possible resource limits & guarantees
    """
    assert make_pvc_spec(
        name='test',
        storage_class='gce-standard-storage',
        access_modes=['ReadWriteOnce'],
        storage='10Gi'
    ) == {
        'kind': 'PersistentVolumeClaim',
        'apiVersion': 'v1',
        'metadata': {
            'name': 'test',
            'annotations': {
                'volume.beta.kubernetes.io/storage-class': 'gce-standard-storage'
            }
        },
        'spec': {
            'accessModes': ['ReadWriteOnce'],
            'resources': {
                'requests': {
                    'storage': '10Gi'
                }
            }
        }
    }

