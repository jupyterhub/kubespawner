"""
Test functions used to create k8s objects
"""
from kubespawner.objects import make_pod, make_pvc
from kubernetes.client import ApiClient


api_client = ApiClient()

def test_make_simplest_pod():
    """
    Test specification of the simplest possible pod specification
    """
    assert api_client.sanitize_for_serialization(make_pod(
        name='test',
        image_spec='jupyter/singleuser:latest',
        cmd=['jupyterhub-singleuser'],
        port=8888,
        image_pull_policy='IfNotPresent'
    )) == {
        "metadata": {
            "name": "test",
            "labels": {},
            "annotations": {}
        },
        "spec": {
            "securityContext": {},
            'automountServiceAccountToken': False,
            "containers": [
                {
                    "env": [],
                    "name": "notebook",
                    "image": "jupyter/singleuser:latest",
                    "imagePullPolicy": "IfNotPresent",
                    "args": ["jupyterhub-singleuser"],
                    "ports": [{
                        "name": "notebook-port",
                        "containerPort": 8888
                    }],
                    'volumeMounts': [],
                    "resources": {
                        "limits": {},
                        "requests": {}
                    }
                }
            ],
            'volumes': [],
        },
        "kind": "Pod",
        "apiVersion": "v1"
    }

def test_make_labeled_pod():
    """
    Test specification of the simplest possible pod specification with labels
    """
    assert api_client.sanitize_for_serialization(make_pod(
        name='test',
        image_spec='jupyter/singleuser:latest',
        cmd=['jupyterhub-singleuser'],
        port=8888,
        image_pull_policy='IfNotPresent',
        labels={"test": "true"}
    )) == {
        "metadata": {
            "name": "test",
            "labels": {"test": "true"},
            "annotations": {}
        },
        "spec": {
            "securityContext": {},
            'automountServiceAccountToken': False,
            "containers": [
                {
                    "env": [],
                    "name": "notebook",
                    "image": "jupyter/singleuser:latest",
                    "imagePullPolicy": "IfNotPresent",
                    "args": ["jupyterhub-singleuser"],
                    "ports": [{
                        "name": "notebook-port",
                        "containerPort": 8888
                    }],
                    'volumeMounts': [],
                    "resources": {
                        "limits": {},
                        "requests": {}
                    }
                }
            ],
            'volumes': [],
        },
        "kind": "Pod",
        "apiVersion": "v1"
    }

def test_make_annotated_pod():
    """
    Test specification of the simplest possible pod specification with annotations
    """
    assert api_client.sanitize_for_serialization(make_pod(
        name='test',
        image_spec='jupyter/singleuser:latest',
        cmd=['jupyterhub-singleuser'],
        port=8888,
        image_pull_policy='IfNotPresent',
        annotations={"test": "true"}
    )) == {
        "metadata": {
            "name": "test",
            "annotations": {"test": "true"},
            "labels": {},
        },
        "spec": {
            "securityContext": {},
            'automountServiceAccountToken': False,
            "containers": [
                {
                    "env": [],
                    "name": "notebook",
                    "image": "jupyter/singleuser:latest",
                    "imagePullPolicy": "IfNotPresent",
                    "args": ["jupyterhub-singleuser"],
                    "ports": [{
                        "name": "notebook-port",
                        "containerPort": 8888
                    }],
                    'volumeMounts': [],
                    "resources": {
                        "limits": {},
                        "requests": {}
                    }
                }
            ],
            'volumes': [],
        },
        "kind": "Pod",
        "apiVersion": "v1"
    }

def test_make_pod_with_image_pull_secrets():
    """
    Test specification of the simplest possible pod specification
    """
    assert api_client.sanitize_for_serialization(make_pod(
        name='test',
        image_spec='jupyter/singleuser:latest',
        cmd=['jupyterhub-singleuser'],
        port=8888,
        image_pull_policy='IfNotPresent',
        image_pull_secret='super-sekrit'
    )) == {
        "metadata": {
            "name": "test",
            "annotations": {},
            "labels": {},
        },
        "spec": {
            "securityContext": {},
            'automountServiceAccountToken': False,
            "imagePullSecrets": [
                {'name': 'super-sekrit'}
            ],
            "containers": [
                {
                    "env": [],
                    "name": "notebook",
                    "image": "jupyter/singleuser:latest",
                    "imagePullPolicy": "IfNotPresent",
                    "args": ["jupyterhub-singleuser"],
                    "ports": [{
                        "name": "notebook-port",
                        "containerPort": 8888
                    }],
                    'volumeMounts': [],
                    "resources": {
                        "limits": {},
                        "requests": {}
                    }
                }
            ],
            'volumes': [],
        },
        "kind": "Pod",
        "apiVersion": "v1"
    }


def test_set_pod_uid_and_gid():
    """
    Test specification of the simplest possible pod specification
    """
    assert api_client.sanitize_for_serialization(make_pod(
        name='test',
        image_spec='jupyter/singleuser:latest',
        cmd=['jupyterhub-singleuser'],
        port=8888,
        run_as_uid=1000,
        run_as_gid=2000,
        image_pull_policy='IfNotPresent'
    )) == {
        "metadata": {
            "name": "test",
            "annotations": {},
            "labels": {},
        },
        "spec": {
            "securityContext": {
                "runAsUser": 1000,
                "runAsGroup": 2000
            },
            'automountServiceAccountToken': False,
            "containers": [
                {
                    "env": [],
                    "name": "notebook",
                    "image": "jupyter/singleuser:latest",
                    "imagePullPolicy": "IfNotPresent",
                    "args": ["jupyterhub-singleuser"],
                    "ports": [{
                        "name": "notebook-port",
                        "containerPort": 8888
                    }],
                    'volumeMounts': [],
                    "resources": {
                        "limits": {},
                        "requests": {}
                    }
                }
            ],
            'volumes': [],
        },
        "kind": "Pod",
        "apiVersion": "v1"
    }

def test_set_pod_uid_fs_gid():
    """
    Test specification of the simplest possible pod specification
    """
    assert api_client.sanitize_for_serialization(make_pod(
        name='test',
        image_spec='jupyter/singleuser:latest',
        cmd=['jupyterhub-singleuser'],
        port=8888,
        run_as_uid=1000,
        fs_gid=1000,
        image_pull_policy='IfNotPresent'
    )) == {
        "metadata": {
            "name": "test",
            "annotations": {},
            "labels": {},
        },
        "spec": {
            "securityContext": {
                "runAsUser": 1000,
                "fsGroup": 1000
            },
            'automountServiceAccountToken': False,
            "containers": [
                {
                    "env": [],
                    "name": "notebook",
                    "image": "jupyter/singleuser:latest",
                    "imagePullPolicy": "IfNotPresent",
                    "args": ["jupyterhub-singleuser"],
                    "ports": [{
                        "name": "notebook-port",
                        "containerPort": 8888
                    }],
                    'volumeMounts': [],
                    "resources": {
                        "limits": {},
                        "requests": {}
                    }
                }
            ],
            'volumes': [],
        },
        "kind": "Pod",
        "apiVersion": "v1"
    }

def test_set_pod_supplemental_gids():
    """
    Test specification of the simplest possible pod specification
    """
    assert api_client.sanitize_for_serialization(make_pod(
        name='test',
        image_spec='jupyter/singleuser:latest',
        cmd=['jupyterhub-singleuser'],
        port=8888,
        run_as_uid=1000,
        supplemental_gids=[100],
        image_pull_policy='IfNotPresent'
    )) == {
        "metadata": {
            "name": "test",
            "annotations": {},
            "labels": {},
        },
        "spec": {
            "securityContext": {
                "runAsUser": 1000,
                "supplementalGroups": [100]
            },
            'automountServiceAccountToken': False,
            "containers": [
                {
                    "env": [],
                    "name": "notebook",
                    "image": "jupyter/singleuser:latest",
                    "imagePullPolicy": "IfNotPresent",
                    "args": ["jupyterhub-singleuser"],
                    "ports": [{
                        "name": "notebook-port",
                        "containerPort": 8888
                    }],
                    'volumeMounts': [],
                    "resources": {
                        "limits": {},
                        "requests": {}
                    }
                }
            ],
            'volumes': [],
        },
        "kind": "Pod",
        "apiVersion": "v1"
    }

def test_run_privileged_container():
    """
    Test specification of the container to run as privileged
    """
    assert api_client.sanitize_for_serialization(make_pod(
        name='test',
        image_spec='jupyter/singleuser:latest',
        cmd=['jupyterhub-singleuser'],
        port=8888,
        run_privileged=True,
        image_pull_policy='IfNotPresent'
    )) == {
        "metadata": {
            "name": "test",
            "annotations": {},
            "labels": {},
        },
        "spec": {
            "securityContext": {},
            'automountServiceAccountToken': False,
            "containers": [
                {
                    "env": [],
                    "name": "notebook",
                    "image": "jupyter/singleuser:latest",
                    "imagePullPolicy": "IfNotPresent",
                    "args": ["jupyterhub-singleuser"],
                    "ports": [{
                        "name": "notebook-port",
                        "containerPort": 8888
                    }],                    
                    "resources": {
                        "limits": {},
                        "requests": {}
                    },
                    "securityContext": {
                        "privileged": True,
                    },
                    'volumeMounts': [],
                }
            ],
            'volumes': [],
        },
        "kind": "Pod",
        "apiVersion": "v1"
    }

def test_make_pod_resources_all():
    """
    Test specifying all possible resource limits & guarantees
    """
    assert api_client.sanitize_for_serialization(make_pod(
        name='test',
        image_spec='jupyter/singleuser:latest',
        cpu_limit=2,
        cpu_guarantee=1,
        cmd=['jupyterhub-singleuser'],
        port=8888,
        mem_limit='1Gi',
        mem_guarantee='512Mi',
        image_pull_policy='IfNotPresent',
        image_pull_secret="myregistrykey",
        node_selector={"disk": "ssd"}
    )) == {
        "metadata": {
            "name": "test",
            "annotations": {},
            "labels": {},
        },
        "spec": {
            "securityContext": {},
            'automountServiceAccountToken': False,
            "imagePullSecrets": [{"name": "myregistrykey"}],
            "nodeSelector": {"disk": "ssd"},
            "containers": [
                {
                    "env": [],
                    "name": "notebook",
                    "image": "jupyter/singleuser:latest",
                    "imagePullPolicy": "IfNotPresent",
                    "args": ["jupyterhub-singleuser"],
                    "ports": [{
                        "name": "notebook-port",
                        "containerPort": 8888
                    }],
                    'volumeMounts': [],
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
            'volumes': [],
        },
        "kind": "Pod",
        "apiVersion": "v1"
    }


def test_make_pod_with_env():
    """
    Test specification of a pod with custom environment variables
    """
    assert api_client.sanitize_for_serialization(make_pod(
        name='test',
        image_spec='jupyter/singleuser:latest',
        env={
            'TEST_KEY': 'TEST_VALUE'
        },
        cmd=['jupyterhub-singleuser'],
        port=8888,
        image_pull_policy='IfNotPresent'
    )) == {
        "metadata": {
            "name": "test",
            "annotations": {},
            "labels": {},
        },
        "spec": {
            'automountServiceAccountToken': False,
            "securityContext": {},
            "containers": [
                {
                    "env": [{'name': 'TEST_KEY', 'value': 'TEST_VALUE'}],
                    "name": "notebook",
                    "image": "jupyter/singleuser:latest",
                    "imagePullPolicy": "IfNotPresent",
                    "args": ["jupyterhub-singleuser"],
                    "ports": [{
                        "name": "notebook-port",
                        "containerPort": 8888
                    }],
                    'volumeMounts': [],
                    "resources": {
                        "limits": {
                        },
                        "requests": {
                        }
                    }
                }
            ],
            'volumes': [],
        },
        "kind": "Pod",
        "apiVersion": "v1"
    }

def test_make_pod_with_lifecycle():
    """
    Test specification of a pod with lifecycle
    """
    assert api_client.sanitize_for_serialization(make_pod(
        name='test',
        image_spec='jupyter/singleuser:latest',
        cmd=['jupyterhub-singleuser'],
        port=8888,
        image_pull_policy='IfNotPresent',
        lifecycle_hooks={
            'preStop': {
                'exec': {
                    'command': ['/bin/sh', 'test']
                }
            }
        }
    )) == {
        "metadata": {
            "name": "test",
            "annotations": {},
            "labels": {},
        },
        "spec": {
            "securityContext": {},
            'automountServiceAccountToken': False,
            "containers": [
                {
                    "env": [],
                    "name": "notebook",
                    "image": "jupyter/singleuser:latest",
                    "imagePullPolicy": "IfNotPresent",
                    "args": ["jupyterhub-singleuser"],
                    "ports": [{
                        "name": "notebook-port",
                        "containerPort": 8888
                    }],
                    'volumeMounts': [],
                    "resources": {
                        "limits": {
                        },
                        "requests": {
                        }
                    },
                    "lifecycle": {
                        "preStop": {
                            "exec": {
                                "command": ["/bin/sh", "test"]
                            }
                        }
                    }
                }
            ],
            'volumes': [],
        },
        "kind": "Pod",
        "apiVersion": "v1"
    }


def test_make_pod_with_init_containers():
    """
    Test specification of a pod with initContainers
    """
    assert api_client.sanitize_for_serialization(make_pod(
        name='test',
        image_spec='jupyter/singleuser:latest',
        cmd=['jupyterhub-singleuser'],
        port=8888,
        image_pull_policy='IfNotPresent',
        init_containers=[
            {
                'name': 'init-myservice',
                'image': 'busybox',
                'command': ['sh', '-c', 'until nslookup myservice; do echo waiting for myservice; sleep 2; done;']
            },
            {
                'name': 'init-mydb',
                'image': 'busybox',
                'command': ['sh', '-c', 'until nslookup mydb; do echo waiting for mydb; sleep 2; done;']
            }
        ]
    )) == {
        "metadata": {
            "name": "test",
            "annotations": {},
            "labels": {},
        },
        "spec": {
            'automountServiceAccountToken': False,
            "securityContext": {},
            "containers": [
                {
                    "env": [],
                    "name": "notebook",
                    "image": "jupyter/singleuser:latest",
                    "imagePullPolicy": "IfNotPresent",
                    "args": ["jupyterhub-singleuser"],
                    "ports": [{
                        "name": "notebook-port",
                        "containerPort": 8888
                    }],
                    'volumeMounts': [],
                    "resources": {
                        "limits": {
                        },
                        "requests": {
                        }
                    },
                }
            ],
            "initContainers": [
                {
                    "name": "init-myservice",
                    "image": "busybox",
                    "command": ["sh", "-c",
                                "until nslookup myservice; do echo waiting for myservice; sleep 2; done;"]
                },
                {
                    "name": "init-mydb",
                    "image": "busybox",
                    "command": ["sh", "-c", "until nslookup mydb; do echo waiting for mydb; sleep 2; done;"]
                }
            ],
            'volumes': [],
        },
        "kind": "Pod",
        "apiVersion": "v1"
    }


def test_make_pod_with_extra_container_config():
    """
    Test specification of a pod with initContainers
    """
    assert api_client.sanitize_for_serialization(make_pod(
        name='test',
        image_spec='jupyter/singleuser:latest',
        cmd=['jupyterhub-singleuser'],
        port=8888,
        image_pull_policy='IfNotPresent',
        extra_container_config={
            'envFrom': [
                {
                    'configMapRef': {
                        'name': 'special-config'
                    }
                }
            ]
        }
    )) == {
        "metadata": {
            "name": "test",
            "annotations": {},
            "labels": {},
        },
        "spec": {
            'automountServiceAccountToken': False,
            "securityContext": {},
            "containers": [
                {
                    "env": [],
                    "name": "notebook",
                    "image": "jupyter/singleuser:latest",
                    "imagePullPolicy": "IfNotPresent",
                    "args": ["jupyterhub-singleuser"],
                    "ports": [{
                        "name": "notebook-port",
                        "containerPort": 8888
                    }],
                    'volumeMounts': [],
                    "resources": {
                        "limits": {
                        },
                        "requests": {
                        }
                    },
                    'envFrom': [
                        {
                            'configMapRef': {
                                'name': 'special-config'
                            }
                        }
                    ]
                }
            ],
            'volumes': [],
        },
        "kind": "Pod",
        "apiVersion": "v1"
    }


def test_make_pod_with_extra_pod_config():
    """
    Test specification of a pod with initContainers
    """
    assert api_client.sanitize_for_serialization(make_pod(
        name='test',
        image_spec='jupyter/singleuser:latest',
        cmd=['jupyterhub-singleuser'],
        port=8888,
        image_pull_policy='IfNotPresent',
        extra_pod_config={
            'tolerations': [
                {
                    'key': 'dedicated',
                    'operator': 'Equal',
                    'value': 'notebook'
                }
            ]
        }
    )) == {
        "metadata": {
            "name": "test",
            "annotations": {},
            "labels": {},
        },
        "spec": {
            'automountServiceAccountToken': False,
            "securityContext": {},
            "containers": [
                {
                    "env": [],
                    "name": "notebook",
                    "image": "jupyter/singleuser:latest",
                    "imagePullPolicy": "IfNotPresent",
                    "args": ["jupyterhub-singleuser"],
                    "ports": [{
                        "name": "notebook-port",
                        "containerPort": 8888
                    }],
                    'volumeMounts': [],
                    "resources": {
                        "limits": {
                        },
                        "requests": {
                        }
                    }
                }
            ],
            'volumes': [],
            'tolerations': [
                {
                    'key': 'dedicated',
                    'operator': 'Equal',
                    'value': 'notebook'
                }
            ]
        },
        "kind": "Pod",
        "apiVersion": "v1"
    }


def test_make_pod_with_extra_containers():
    """
    Test specification of a pod with initContainers
    """
    assert api_client.sanitize_for_serialization(make_pod(
        name='test',
        image_spec='jupyter/singleuser:latest',
        cmd=['jupyterhub-singleuser'],
        port=8888,
        image_pull_policy='IfNotPresent',
        extra_containers=[
            {
                'name': 'crontab',
                'image': 'supercronic',
                'command': ['/usr/local/bin/supercronic', '/etc/crontab']
            }
        ]
    )) == {
        "metadata": {
            "name": "test",
            "annotations": {},
            "labels": {},
        },
        "spec": {
            'automountServiceAccountToken': False,
            "securityContext": {},
            "containers": [
                {
                    "env": [],
                    "name": "notebook",
                    "image": "jupyter/singleuser:latest",
                    "imagePullPolicy": "IfNotPresent",
                    "args": ["jupyterhub-singleuser"],
                    "ports": [{
                        "name": "notebook-port",
                        "containerPort": 8888
                    }],
                    'volumeMounts': [],
                    "resources": {
                        "limits": {
                        },
                        "requests": {
                        }
                    },
                },
                {
                    'name': 'crontab',
                    'image': 'supercronic',
                    'command': ['/usr/local/bin/supercronic', '/etc/crontab']
                }
            ],
            'volumes': [],
        },
        "kind": "Pod",
        "apiVersion": "v1"
    }

def test_make_pod_with_extra_resources():
    """
    Test specification of extra resources (like GPUs)
    """
    assert api_client.sanitize_for_serialization(make_pod(
        name='test',
        image_spec='jupyter/singleuser:latest',
        cpu_limit=2,
        cpu_guarantee=1,
        extra_resource_limits={"nvidia.com/gpu": "5", "k8s.io/new-resource": "1"},
        extra_resource_guarantees={"nvidia.com/gpu": "3"},
        cmd=['jupyterhub-singleuser'],
        port=8888,
        mem_limit='1Gi',
        mem_guarantee='512Mi',
        image_pull_policy='IfNotPresent',
        image_pull_secret="myregistrykey",
        node_selector={"disk": "ssd"}
    )) == {
        "metadata": {
            "name": "test",
            "annotations": {},
            "labels": {},
        },
        "spec": {
            'automountServiceAccountToken': False,
            "securityContext": {},
            "imagePullSecrets": [{"name": "myregistrykey"}],
            "nodeSelector": {"disk": "ssd"},
            "containers": [
                {
                    "env": [],
                    "name": "notebook",
                    "image": "jupyter/singleuser:latest",
                    "imagePullPolicy": "IfNotPresent",
                    "args": ["jupyterhub-singleuser"],
                    "ports": [{
                        "name": "notebook-port",
                        "containerPort": 8888
                    }],
                    'volumeMounts': [],
                    "resources": {
                        "limits": {
                            "cpu": 2,
                            "memory": '1Gi',
                            "nvidia.com/gpu": "5",
                            "k8s.io/new-resource": "1"
                        },
                        "requests": {
                            "cpu": 1,
                            "memory": '512Mi',
                            "nvidia.com/gpu": "3"
                        }
                    }
                }
            ],
            'volumes': [],
        },
        "kind": "Pod",
        "apiVersion": "v1"
    }

def test_make_pvc_simple():
    """
    Test specification of the simplest possible pvc specification
    """
    assert api_client.sanitize_for_serialization(make_pvc(
        name='test',
        storage_class='',
        access_modes=[],
        storage=None,
        labels={}
    )) == {
        'kind': 'PersistentVolumeClaim',
        'apiVersion': 'v1',
        'metadata': {
            'name': 'test',
            'annotations': {},
            'labels': {}
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
    assert api_client.sanitize_for_serialization(make_pvc(
        name='test',
        storage_class='gce-standard-storage',
        access_modes=['ReadWriteOnce'],
        storage='10Gi',
        labels={'key': 'value'}
    )) == {
        'kind': 'PersistentVolumeClaim',
        'apiVersion': 'v1',
        'metadata': {
            'name': 'test',
            'annotations': {
                'volume.beta.kubernetes.io/storage-class': 'gce-standard-storage'
            },
            'labels': {
                'key': 'value'
            }
        },
        'spec': {
            'storageClassName': 'gce-standard-storage',
            'accessModes': ['ReadWriteOnce'],
            'resources': {
                'requests': {
                    'storage': '10Gi'
                }
            }
        }
    }

    
def test_make_pod_with_service_account():
    """
    Test specification of the simplest possible pod specification with non-default service account
    """
    assert api_client.sanitize_for_serialization(make_pod(
        name='test',
        image_spec='jupyter/singleuser:latest',
        cmd=['jupyterhub-singleuser'],
        port=8888,
        image_pull_policy='IfNotPresent',
        service_account='test'
    )) == {
        "metadata": {
            "name": "test",
            "labels": {},
            "annotations": {}
        },
        "spec": {
            "securityContext": {},
            "containers": [
                {
                    "env": [],
                    "name": "notebook",
                    "image": "jupyter/singleuser:latest",
                    "imagePullPolicy": "IfNotPresent",
                    "args": ["jupyterhub-singleuser"],
                    "ports": [{
                        "name": "notebook-port",
                        "containerPort": 8888
                    }],
                    'volumeMounts': [],
                    "resources": {
                        "limits": {},
                        "requests": {}
                    }
                }
            ],
            'volumes': [],
            'serviceAccountName': 'test'
        },
        "kind": "Pod",
        "apiVersion": "v1"
    }
