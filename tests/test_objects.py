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
        env={},
        volumes=[],
        volume_mounts=[],
        cmd=['jupyterhub-singleuser'],
        working_dir=None,
        port=8888,
        cpu_limit=None,
        cpu_guarantee=None,
        mem_limit=None,
        mem_guarantee=None,
        node_selector=None,
        run_as_uid=None,
        fs_gid=None,
        run_privileged=False,
        image_pull_policy='IfNotPresent',
        image_pull_secret=None,
        labels={},
        lifecycle_hooks=None,
        init_containers=None,
        service_account=None
    )) == {
        "metadata": {
            "name": "test",
            "labels": {},
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
                    'volumeMounts': [{'name': 'no-api-access-please', 'mountPath': '/var/run/secrets/kubernetes.io/serviceaccount', 'readOnly': True}],
                    "resources": {
                        "limits": {},
                        "requests": {}
                    }
                }
            ],
            'volumes': [{'name': 'no-api-access-please', 'emptyDir': {}}],
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
        env={},
        volumes=[],
        volume_mounts=[],
        cmd=['jupyterhub-singleuser'],
        working_dir=None,
        port=8888,
        cpu_limit=None,
        cpu_guarantee=None,
        mem_limit=None,
        mem_guarantee=None,
        node_selector=None,
        run_as_uid=None,
        fs_gid=None,
        run_privileged=False,
        image_pull_policy='IfNotPresent',
        image_pull_secret=None,
        labels={"test": "true"},
        lifecycle_hooks=None,
        init_containers=None,
        service_account=None
    )) == {
        "metadata": {
            "name": "test",
            "labels": {"test": "true"},
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
                    'volumeMounts': [{'name': 'no-api-access-please', 'mountPath': '/var/run/secrets/kubernetes.io/serviceaccount', 'readOnly': True}],
                    "resources": {
                        "limits": {},
                        "requests": {}
                    }
                }
            ],
            'volumes': [{'name': 'no-api-access-please', 'emptyDir': {}}],
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
        env={},
        volumes=[],
        volume_mounts=[],
        cmd=['jupyterhub-singleuser'],
        working_dir=None,
        port=8888,
        cpu_limit=None,
        cpu_guarantee=None,
        mem_limit=None,
        mem_guarantee=None,
        node_selector=None,
        run_as_uid=None,
        fs_gid=None,
        run_privileged=False,
        image_pull_policy='IfNotPresent',
        image_pull_secret='super-sekrit',
        labels={},
        lifecycle_hooks=None,
        init_containers=None,
        service_account=None
    )) == {
        "metadata": {
            "name": "test",
            "labels": {},
        },
        "spec": {
            "securityContext": {},
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
                    'volumeMounts': [{'name': 'no-api-access-please', 'mountPath': '/var/run/secrets/kubernetes.io/serviceaccount', 'readOnly': True}],
                    "resources": {
                        "limits": {},
                        "requests": {}
                    }
                }
            ],
            'volumes': [{'name': 'no-api-access-please', 'emptyDir': {}}],
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
        env={},
        volumes=[],
        volume_mounts=[],
        cmd=['jupyterhub-singleuser'],
        working_dir=None,
        port=8888,
        cpu_limit=None,
        cpu_guarantee=None,
        mem_limit=None,
        mem_guarantee=None,
        node_selector=None,
        run_as_uid=1000,
        fs_gid=1000,
        run_privileged=False,
        image_pull_policy='IfNotPresent',
        image_pull_secret=None,
        labels={},
        lifecycle_hooks=None,
        init_containers=None,
        service_account=None
    )) == {
        "metadata": {
            "name": "test",
            "labels": {},
        },
        "spec": {
            "securityContext": {
                "runAsUser": 1000,
                "fsGroup": 1000
            },
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
                    'volumeMounts': [{'name': 'no-api-access-please', 'mountPath': '/var/run/secrets/kubernetes.io/serviceaccount', 'readOnly': True}],
                    "resources": {
                        "limits": {},
                        "requests": {}
                    }
                }
            ],
            'volumes': [{'name': 'no-api-access-please', 'emptyDir': {}}],
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
        env={},
        volumes=[],
        volume_mounts=[],
        cmd=['jupyterhub-singleuser'],
        working_dir=None,
        port=8888,
        cpu_limit=None,
        cpu_guarantee=None,
        mem_limit=None,
        mem_guarantee=None,
        node_selector=None,
        run_as_uid=None,
        fs_gid=None,
        run_privileged=True,
        image_pull_policy='IfNotPresent',
        image_pull_secret=None,
        labels={},
        lifecycle_hooks=None,
        init_containers=None,
        service_account=None
    )) == {
        "metadata": {
            "name": "test",
            "labels": {},
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
                    "resources": {
                        "limits": {},
                        "requests": {}
                    },
                    "securityContext": {
                        "privileged": True,
                    },
                    'volumeMounts': [{'name': 'no-api-access-please', 'mountPath': '/var/run/secrets/kubernetes.io/serviceaccount', 'readOnly': True}],
                }
            ],
            'volumes': [{'name': 'no-api-access-please', 'emptyDir': {}}],
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
        env={},
        volumes=[],
        volume_mounts=[],
        cpu_limit=2,
        cpu_guarantee=1,
        cmd=['jupyterhub-singleuser'],
        working_dir=None,
        port=8888,
        mem_limit='1Gi',
        mem_guarantee='512Mi',
        image_pull_policy='IfNotPresent',
        image_pull_secret="myregistrykey",
        node_selector={"disk": "ssd"},
        run_as_uid=None,
        fs_gid=None,
        run_privileged=False,
        labels={},
        lifecycle_hooks=None,
        init_containers=None,
        service_account=None
    )) == {
        "metadata": {
            "name": "test",
            "labels": {},
        },
        "spec": {
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
                    'volumeMounts': [{'name': 'no-api-access-please', 'mountPath': '/var/run/secrets/kubernetes.io/serviceaccount', 'readOnly': True}],
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
            'volumes': [{'name': 'no-api-access-please', 'emptyDir': {}}],
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
        volumes=[],
        volume_mounts=[],
        cmd=['jupyterhub-singleuser'],
        working_dir=None,
        port=8888,
        cpu_limit=None,
        cpu_guarantee=None,
        mem_limit=None,
        mem_guarantee=None,
        image_pull_policy='IfNotPresent',
        image_pull_secret=None,
        node_selector=None,
        run_as_uid=None,
        fs_gid=None,
        run_privileged=False,
        labels={},
        lifecycle_hooks=None,
        init_containers=None,
        service_account=None
    )) == {
        "metadata": {
            "name": "test",
            "labels": {},
        },
        "spec": {
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
                    'volumeMounts': [{'name': 'no-api-access-please', 'mountPath': '/var/run/secrets/kubernetes.io/serviceaccount', 'readOnly': True}],
                    "resources": {
                        "limits": {
                        },
                        "requests": {
                        }
                    }
                }
            ],
            'volumes': [{'name': 'no-api-access-please', 'emptyDir': {}}],
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
        env={},
        volumes=[],
        volume_mounts=[],
        cmd=['jupyterhub-singleuser'],
        working_dir=None,
        port=8888,
        cpu_limit=None,
        cpu_guarantee=None,
        mem_limit=None,
        mem_guarantee=None,
        image_pull_policy='IfNotPresent',
        image_pull_secret=None,
        run_as_uid=None,
        fs_gid=None,
        run_privileged=False,
        labels={},
        node_selector={},
        lifecycle_hooks={
            'preStop': {
                'exec': {
                    'command': ['/bin/sh', 'test']
                }
            }
        },
        init_containers=None,
        service_account=None
    )) == {
        "metadata": {
            "name": "test",
            "labels": {},
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
                    'volumeMounts': [{'name': 'no-api-access-please', 'mountPath': '/var/run/secrets/kubernetes.io/serviceaccount', 'readOnly': True}],
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
            'volumes': [{'name': 'no-api-access-please', 'emptyDir': {}}],
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
        env={},
        volumes=[],
        volume_mounts=[],
        cmd=['jupyterhub-singleuser'],
        working_dir=None,
        port=8888,
        cpu_limit=None,
        cpu_guarantee=None,
        mem_limit=None,
        mem_guarantee=None,
        image_pull_policy='IfNotPresent',
        image_pull_secret=None,
        run_as_uid=None,
        fs_gid=None,
        run_privileged=False,
        labels={},
        lifecycle_hooks=None,
        node_selector={},
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
        ],
        service_account=None
    )) == {
        "metadata": {
            "name": "test",
            "labels": {},
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
                    'volumeMounts': [{'name': 'no-api-access-please', 'mountPath': '/var/run/secrets/kubernetes.io/serviceaccount', 'readOnly': True}],
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
            'volumes': [{'name': 'no-api-access-please', 'emptyDir': {}}],
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
            'annotations': {
            },
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
            'accessModes': ['ReadWriteOnce'],
            'resources': {
                'requests': {
                    'storage': '10Gi'
                }
            }
        }
    }
