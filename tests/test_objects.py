"""
Test functions used to create k8s objects
"""
from v3iokubespawner.objects import make_pod, make_pvc
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
        tolerations=[{
            'key': 'wrong_toleration',
            'operator': 'Equal',
            'value': 'wrong_value'
        }],
        extra_pod_config={
            'dns_policy': 'ClusterFirstWithHostNet',
            'restartPolicy': 'OnFailure',
            'tolerations': [{
                'key': 'correct_toleration',
                'operator': 'Equal',
                'value': 'correct_value'
            }],
        },
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
            'dnsPolicy': 'ClusterFirstWithHostNet',
            'restartPolicy': 'OnFailure',
            'tolerations': [
                {
                    'key': 'correct_toleration',
                    'operator': 'Equal',
                    'value': 'correct_value'
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


def test_make_pod_with_scheduler_name():
    """
    Test specification of the simplest possible pod specification with non-default scheduler name
    """
    assert api_client.sanitize_for_serialization(make_pod(
        name='test',
        image_spec='jupyter/singleuser:latest',
        cmd=['jupyterhub-singleuser'],
        port=8888,
        image_pull_policy='IfNotPresent',
        scheduler_name='my-custom-scheduler'
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
                        "limits": {},
                        "requests": {}
                    }
                }
            ],
            'volumes': [],
            'schedulerName': 'my-custom-scheduler',
        },
        "kind": "Pod",
        "apiVersion": "v1"
    }


def test_make_pod_with_tolerations():
    """
    Test specification of the simplest possible pod specification with non-empty tolerations
    """
    tolerations = [
        {
            'key': 'hub.jupyter.org/dedicated',
            'operator': 'Equal',
            'value': 'user',
            'effect': 'NoSchedule'
        },
        {
            'key': 'key',
            'operator': 'Exists',
            'effect': 'NoSchedule'
        }
    ]
    assert api_client.sanitize_for_serialization(make_pod(
        name='test',
        image_spec='jupyter/singleuser:latest',
        cmd=['jupyterhub-singleuser'],
        port=8888,
        image_pull_policy='IfNotPresent',
        tolerations=tolerations
    )) == {
        "metadata": {
            "name": "test",
            "labels": {},
            "annotations": {}
        },
        "spec": {
            "automountServiceAccountToken": False,
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
            'tolerations': tolerations
        },
        "kind": "Pod",
        "apiVersion": "v1"
    }


def test_make_pod_with_node_affinity_preferred():
    """
    Test specification of the simplest possible pod specification with non-empty node_affinity_preferred
    """
    node_affinity_preferred = [{
        "weight": 1,
        "preference": {
            "matchExpressions": [{
                "key": "hub.jupyter.org/node-purpose",
                "operator": "In",
                "values": ["user"],
            }],
        }
    }]
    assert api_client.sanitize_for_serialization(make_pod(
        name='test',
        image_spec='jupyter/singleuser:latest',
        cmd=['jupyterhub-singleuser'],
        port=8888,
        image_pull_policy='IfNotPresent',
        node_affinity_preferred=node_affinity_preferred
    )) == {
        "metadata": {
            "name": "test",
            "labels": {},
            "annotations": {}
        },
        "spec": {
            "automountServiceAccountToken": False,
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
            "volumes": [],
            "affinity": {
                "nodeAffinity": {
                    "preferredDuringSchedulingIgnoredDuringExecution": node_affinity_preferred
                }
            }
        },
        "kind": "Pod",
        "apiVersion": "v1"
    }


def test_make_pod_with_node_affinity_required():
    """
    Test specification of the simplest possible pod specification with non-empty node_affinity_required
    """
    node_affinity_required = [{
        "matchExpressions": [{
            "key": "hub.jupyter.org/node-purpose",
            "operator": "In",
            "values": ["user"],
        }]
    }]
    assert api_client.sanitize_for_serialization(make_pod(
        name='test',
        image_spec='jupyter/singleuser:latest',
        cmd=['jupyterhub-singleuser'],
        port=8888,
        image_pull_policy='IfNotPresent',
        node_affinity_required=node_affinity_required
    )) == {
        "metadata": {
            "name": "test",
            "labels": {},
            "annotations": {}
        },
        "spec": {
            "automountServiceAccountToken": False,
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
            "volumes": [],
            "affinity": {
                "nodeAffinity": {
                    "requiredDuringSchedulingIgnoredDuringExecution": {
                        "nodeSelectorTerms": node_affinity_required
                    }
                }
            }
        },
        "kind": "Pod",
        "apiVersion": "v1"
    }


def test_make_pod_with_pod_affinity_preferred():
    """
    Test specification of the simplest possible pod specification with non-empty pod_affinity_preferred
    """
    pod_affinity_preferred = [{
        "weight": 100,
        "podAffinityTerm": {
            "labelSelector": {
                "matchExpressions": [{
                    "key": "hub.jupyter.org/pod-kind",
                    "operator": "In",
                    "values": ["user"],
                }]
            },
            "topologyKey": "kubernetes.io/hostname"
        }
    }]
    assert api_client.sanitize_for_serialization(make_pod(
        name='test',
        image_spec='jupyter/singleuser:latest',
        cmd=['jupyterhub-singleuser'],
        port=8888,
        image_pull_policy='IfNotPresent',
        pod_affinity_preferred=pod_affinity_preferred
    )) == {
        "metadata": {
            "name": "test",
            "labels": {},
            "annotations": {}
        },
        "spec": {
            "automountServiceAccountToken": False,
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
            "volumes": [],
            "affinity": {
                "podAffinity": {
                    "preferredDuringSchedulingIgnoredDuringExecution": pod_affinity_preferred
                }
            }
        },
        "kind": "Pod",
        "apiVersion": "v1"
    }


def test_make_pod_with_pod_affinity_required():
    """
    Test specification of the simplest possible pod specification with non-empty pod_affinity_required
    """
    pod_affinity_required = [{
        "labelSelector": {
            "matchExpressions": [{
                "key": "security",
                "operator": "In",
                "values": ["S1"],
            }]
        },
        "topologyKey": "failure-domain.beta.kubernetes.io/zone"
    }]
    assert api_client.sanitize_for_serialization(make_pod(
        name='test',
        image_spec='jupyter/singleuser:latest',
        cmd=['jupyterhub-singleuser'],
        port=8888,
        image_pull_policy='IfNotPresent',
        pod_affinity_required=pod_affinity_required
    )) == {
        "metadata": {
            "name": "test",
            "labels": {},
            "annotations": {}
        },
        "spec": {
            "automountServiceAccountToken": False,
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
            "volumes": [],
            "affinity": {
                "podAffinity": {
                    "requiredDuringSchedulingIgnoredDuringExecution": pod_affinity_required
                }
            }
        },
        "kind": "Pod",
        "apiVersion": "v1"
    }


def test_make_pod_with_pod_anti_affinity_preferred():
    """
    Test specification of the simplest possible pod specification with non-empty pod_anti_affinity_preferred
    """
    pod_anti_affinity_preferred = [{
        "weight": 100,
        "podAffinityTerm": {
            "labelSelector": {
                "matchExpressions": [{
                    "key": "hub.jupyter.org/pod-kind",
                    "operator": "In",
                    "values": ["user"],
                }]
            },
            "topologyKey": "kubernetes.io/hostname"
        }
    }]
    assert api_client.sanitize_for_serialization(make_pod(
        name='test',
        image_spec='jupyter/singleuser:latest',
        cmd=['jupyterhub-singleuser'],
        port=8888,
        image_pull_policy='IfNotPresent',
        pod_anti_affinity_preferred=pod_anti_affinity_preferred
    )) == {
        "metadata": {
            "name": "test",
            "labels": {},
            "annotations": {}
        },
        "spec": {
            "automountServiceAccountToken": False,
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
            "volumes": [],
            "affinity": {
                "podAntiAffinity": {
                    "preferredDuringSchedulingIgnoredDuringExecution": pod_anti_affinity_preferred
                }
            }
        },
        "kind": "Pod",
        "apiVersion": "v1"
    }


def test_make_pod_with_pod_anti_affinity_required():
    """
    Test specification of the simplest possible pod specification with non-empty pod_anti_affinity_required
    """
    pod_anti_affinity_required = [{
        "labelSelector": {
            "matchExpressions": [{
                "key": "security",
                "operator": "In",
                "values": ["S1"],
            }]
        },
        "topologyKey": "failure-domain.beta.kubernetes.io/zone"
    }]
    assert api_client.sanitize_for_serialization(make_pod(
        name='test',
        image_spec='jupyter/singleuser:latest',
        cmd=['jupyterhub-singleuser'],
        port=8888,
        image_pull_policy='IfNotPresent',
        pod_anti_affinity_required=pod_anti_affinity_required
    )) == {
        "metadata": {
            "name": "test",
            "labels": {},
            "annotations": {}
        },
        "spec": {
            "automountServiceAccountToken": False,
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
            "volumes": [],
            "affinity": {
                "podAntiAffinity": {
                    "requiredDuringSchedulingIgnoredDuringExecution": pod_anti_affinity_required
                }
            }
        },
        "kind": "Pod",
        "apiVersion": "v1"
    }


def test_make_pod_with_priority_class_name():
    """
    Test specification of the simplest possible pod specification with non-default priorityClassName set
    """
    assert api_client.sanitize_for_serialization(make_pod(
        name='test',
        image_spec='jupyter/singleuser:latest',
        cmd=['jupyterhub-singleuser'],
        port=8888,
        image_pull_policy='IfNotPresent',
        priority_class_name='my-custom-priority-class'
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
                        "limits": {},
                        "requests": {}
                    }
                }
            ],
            'volumes': [],
            'priorityClassName': 'my-custom-priority-class',
        },
        "kind": "Pod",
        "apiVersion": "v1"
    }
