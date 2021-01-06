"""
Test functions used to create k8s objects
"""
from kubernetes.client import ApiClient
from kubespawner.objects import make_ingress, make_pod, make_pvc, make_secret

api_client = ApiClient()

def test_make_simplest_pod():
    """
    Test specification of the simplest possible pod specification
    """
    assert api_client.sanitize_for_serialization(make_pod(
        name='test',
        image='jupyter/singleuser:latest',
        env=[],
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
            'automountServiceAccountToken': False,
            "containers": [
                {
                    "env": [],
                    "envFrom": [{'secretRef': {}}],
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
            'restartPolicy': 'OnFailure',
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
        image='jupyter/singleuser:latest',
        env=[],
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
            'automountServiceAccountToken': False,
            "containers": [
                {
                    "env": [],
                    "envFrom": [{'secretRef': {}}],
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
            'restartPolicy': 'OnFailure',
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
        image='jupyter/singleuser:latest',
        env=[],
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
            'automountServiceAccountToken': False,
            "containers": [
                {
                    "env": [],
                    "envFrom": [{'secretRef': {}}],
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
            'restartPolicy': 'OnFailure',
            'volumes': [],
        },
        "kind": "Pod",
        "apiVersion": "v1"
    }

def test_make_pod_with_image_pull_secrets_simplified_format():
    """
    Test specification of the simplest possible pod specification
    """
    assert api_client.sanitize_for_serialization(make_pod(
        name='test',
        image='jupyter/singleuser:latest',
        env=[],
        cmd=['jupyterhub-singleuser'],
        port=8888,
        image_pull_policy='IfNotPresent',
        image_pull_secrets=["k8s-secret-a", "k8s-secret-b"],
    )) == {
        "metadata": {
            "name": "test",
            "annotations": {},
            "labels": {},
        },
        "spec": {
            'automountServiceAccountToken': False,
            "imagePullSecrets": [
                {"name": "k8s-secret-a"},
                {"name": "k8s-secret-b"}
            ],
            "containers": [
                {
                    "env": [],
                    "envFrom": [{'secretRef': {}}],
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
            'restartPolicy': 'OnFailure',
            'volumes': [],
        },
        "kind": "Pod",
        "apiVersion": "v1"
    }


def test_make_pod_with_image_pull_secrets_k8s_native_format():
    """
    Test specification of the simplest possible pod specification
    """
    assert api_client.sanitize_for_serialization(make_pod(
        name='test',
        image='jupyter/singleuser:latest',
        env=[],
        cmd=['jupyterhub-singleuser'],
        port=8888,
        image_pull_policy='IfNotPresent',
        image_pull_secrets=[{"name": "k8s-secret-a"}, {"name": "k8s-secret-b"}],
    )) == {
        "metadata": {
            "name": "test",
            "annotations": {},
            "labels": {},
        },
        "spec": {
            'automountServiceAccountToken': False,
            "imagePullSecrets": [
                {"name": "k8s-secret-a"},
                {"name": "k8s-secret-b"}
            ],
            "containers": [
                {
                    "env": [],
                    "envFrom": [{'secretRef': {}}],
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
            'restartPolicy': 'OnFailure',
            'volumes': [],
        },
        "kind": "Pod",
        "apiVersion": "v1"
    }


def test_set_container_uid_and_gid():
    """
    Test specification of the simplest possible pod specification
    """
    assert api_client.sanitize_for_serialization(make_pod(
        name='test',
        image='jupyter/singleuser:latest',
        env=[],
        cmd=['jupyterhub-singleuser'],
        port=8888,
        run_as_uid=0,
        run_as_gid=0,
        image_pull_policy='IfNotPresent'
    )) == {
        "metadata": {
            "name": "test",
            "annotations": {},
            "labels": {},
        },
        "spec": {
            'automountServiceAccountToken': False,
            "containers": [
                {
                    "securityContext": {
                        "runAsUser": 0,
                        "runAsGroup": 0
                    },
                    "env": [],
                    "envFrom": [{'secretRef': {}}],
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
            'restartPolicy': 'OnFailure',
            'volumes': [],
        },
        "kind": "Pod",
        "apiVersion": "v1"
    }

def test_set_container_uid_and_pod_fs_gid():
    """
    Test specification of the simplest possible pod specification
    """
    assert api_client.sanitize_for_serialization(make_pod(
        name='test',
        image='jupyter/singleuser:latest',
        env=[],
        cmd=['jupyterhub-singleuser'],
        port=8888,
        run_as_uid=1000,
        fs_gid=0,
        image_pull_policy='IfNotPresent'
    )) == {
        "metadata": {
            "name": "test",
            "annotations": {},
            "labels": {},
        },
        "spec": {
            'automountServiceAccountToken': False,
            "containers": [
                {
                    "securityContext": {
                        "runAsUser": 1000,
                    },
                    "env": [],
                    "envFrom": [{'secretRef': {}}],
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
            'restartPolicy': 'OnFailure',
            'securityContext': {
                'fsGroup': 0,
            },
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
        image='jupyter/singleuser:latest',
        env=[],
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
            'automountServiceAccountToken': False,
            "containers": [
                {
                    "securityContext": {
                        "runAsUser": 1000,
                    },
                    "env": [],
                    "envFrom": [{'secretRef': {}}],
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
            'restartPolicy': 'OnFailure',
            'securityContext': {
                'supplementalGroups': [100],
            },
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
        image='jupyter/singleuser:latest',
        env=[],
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
            'automountServiceAccountToken': False,
            "containers": [
                {
                    "env": [],
                    "envFrom": [{'secretRef': {}}],
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
            'restartPolicy': 'OnFailure',
            'volumes': [],
        },
        "kind": "Pod",
        "apiVersion": "v1"
    }

def test_allow_privilege_escalation_container():
    """
    Test specification of the container to run without privilege escalation (AllowPrivilegeEscalation=False).
    """
    assert api_client.sanitize_for_serialization(make_pod(
        name='test',
        image='jupyter/singleuser:latest',
        env=[],
        cmd=['jupyterhub-singleuser'],
        port=8888,
        allow_privilege_escalation=False,
        image_pull_policy='IfNotPresent'
    )) == {
        "metadata": {
            "name": "test",
            "annotations": {},
            "labels": {},
        },
        "spec": {
            'automountServiceAccountToken': False,
            "containers": [
                {
                    "env": [],
                    "envFrom": [{'secretRef': {}}],
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
                        "allowPrivilegeEscalation": False
                    },
                    'volumeMounts': [],
                }
            ],
            'restartPolicy': 'OnFailure',
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
        image='jupyter/singleuser:latest',
        cpu_limit=2,
        cpu_guarantee=1,
        cmd=['jupyterhub-singleuser'],
        env=[],
        port=8888,
        mem_limit='1Gi',
        mem_guarantee='512Mi',
        image_pull_policy='IfNotPresent',
        node_selector={"disk": "ssd"}
    )) == {
        "metadata": {
            "name": "test",
            "annotations": {},
            "labels": {},
        },
        "spec": {
            'automountServiceAccountToken': False,
            "nodeSelector": {"disk": "ssd"},
            "containers": [
                {
                    "env": [],
                    "envFrom": [{'secretRef': {}}],
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
            'restartPolicy': 'OnFailure',
            'volumes': [],
        },
        "kind": "Pod",
        "apiVersion": "v1"
    }


def test_make_pod_with_env_from():
    """
    Test specification of a pod with custom environment variables.
    """
    assert api_client.sanitize_for_serialization(make_pod(
        name='test',
        image='jupyter/singleuser:latest',
        env=[
                {
                    'name': 'TEST_KEY_1',
                    'valueFrom': {
                        'secretKeyRef': {
                            'name': 'my-test-secret',
                            'key': 'password',
                        },
                    },
                },
                {
                    'name': 'TEST_KEY_2',
                    'valueFrom': {
                        'secretKeyRef': {
                            'name': 'my-test-secret',
                            'key': 'password',
                        },
                    },
                },
            ],
        env_from='my-k8s-secret',
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
            "containers": [
                {
                    "env": [
                        {
                            'name': 'TEST_KEY_1',
                            'valueFrom': {
                                'secretKeyRef': {
                                    'name': 'my-test-secret',
                                    'key': 'password',
                                },
                            },
                        },
                        {
                            'name': 'TEST_KEY_2',
                            'valueFrom': {
                                'secretKeyRef': {
                                    'name': 'my-test-secret',
                                    'key': 'password',
                                },
                            },
                        },
                    ],
                    "envFrom": [
                        {
                            'secretRef': {
                                'name': 'my-k8s-secret'
                            }
                        }
                    ],
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
            'restartPolicy': 'OnFailure',
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
        image='jupyter/singleuser:latest',
        env=[],
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
            'automountServiceAccountToken': False,
            "containers": [
                {
                    "env": [],
                    "envFrom": [{'secretRef': {}}],
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
            'restartPolicy': 'OnFailure',
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
        image='jupyter/singleuser:latest',
        env=[],
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
            "containers": [
                {
                    "env": [],
                    "envFrom": [{'secretRef': {}}],
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
            'restartPolicy': 'OnFailure',
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
        image='jupyter/singleuser:latest',
        env=[],
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
            "containers": [
                {
                    "env": [],
                    "envFrom": [{'secretRef': {}}],
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
            'restartPolicy': 'OnFailure',
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
        image='jupyter/singleuser:latest',
        env=[],
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
            'restartPolicy': 'Always',
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
            "containers": [
                {
                    "env": [],
                    "envFrom": [{'secretRef': {}}],
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
            'restartPolicy': 'Always',
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
        image='jupyter/singleuser:latest',
        env=[],
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
            "containers": [
                {
                    "env": [],
                    "envFrom": [{'secretRef': {}}],
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
            'restartPolicy': 'OnFailure',
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
        image='jupyter/singleuser:latest',
        cpu_limit=2,
        cpu_guarantee=1,
        extra_resource_limits={"nvidia.com/gpu": "5", "k8s.io/new-resource": "1"},
        extra_resource_guarantees={"nvidia.com/gpu": "3"},
        env=[],
        cmd=['jupyterhub-singleuser'],
        port=8888,
        mem_limit='1Gi',
        mem_guarantee='512Mi',
        image_pull_policy='IfNotPresent',
        node_selector={"disk": "ssd"}
    )) == {
        "metadata": {
            "name": "test",
            "annotations": {},
            "labels": {},
        },
        "spec": {
            'automountServiceAccountToken': False,
            "nodeSelector": {"disk": "ssd"},
            "containers": [
                {
                    "env": [],
                    "envFrom": [{'secretRef': {}}],
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
            'restartPolicy': 'OnFailure',
            'volumes': [],
        },
        "kind": "Pod",
        "apiVersion": "v1"
    }

def test_make_secret_simple():
    """
    Test specification of the simplest possible secret specification
    """
    assert api_client.sanitize_for_serialization(make_secret(
        name='my-k8s-secret',
        str_data={},
        username='test',
        owner_references=[],
        labels={}    
    )) == {
        'kind': 'Secret',
        'apiVersion': 'v1',
        'metadata': {
            'name': 'my-k8s-secret',
            'annotations': {},
            'labels': {},
            'ownerReferences': []
        },
        'stringData': {}
    }

def test_make_secret_with_data():
    """
    Test specification of the simplest possible secret specification
    """
    assert api_client.sanitize_for_serialization(make_secret(
        name='my-k8s-secret',
        str_data={"TEST1": "VALUE1"},
        username='test',
        owner_references=[],
        labels={}    
    )) == {
        'kind': 'Secret',
        'apiVersion': 'v1',
        'metadata': {
            'name': 'my-k8s-secret',
            'ownerReferences': [],
            'annotations': {},
            'labels': {}
        },
        'stringData': {"TEST1": "VALUE1"}
    }


def test_make_pvc_simple():
    """
    Test specification of the simplest possible pvc specification
    """
    assert api_client.sanitize_for_serialization(make_pvc(
        name='test',
        storage_class=None,
        access_modes=[],
        selector=None,
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


def test_make_pvc_empty_storage_class():
    """
    Test specification of pvc with empty storage class
    """
    assert api_client.sanitize_for_serialization(make_pvc(
        name='test',
        storage_class='',
        access_modes=[],
        selector=None,
        storage=None,
        labels={}
    )) == {
        'kind': 'PersistentVolumeClaim',
        'apiVersion': 'v1',
        'metadata': {
            'name': 'test',
            'annotations': {
                'volume.beta.kubernetes.io/storage-class': ''
            },
            'labels': {}
        },
        'spec': {
            'accessModes': [],
            'resources': {
                'requests': {
                    'storage': None
                }
            },
            'storageClassName': ''
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
        selector={'matchLabels':{'content': 'jupyter'}},
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
            'selector': {
                'matchLabels': {
                    'content': 'jupyter'
                }
            },
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
        image='jupyter/singleuser:latest',
        env=[],
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
            "containers": [
                {
                    "env": [],
                    "envFrom": [{'secretRef': {}}],
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
            'restartPolicy': 'OnFailure',
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
        image='jupyter/singleuser:latest',
        env=[],
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
            'automountServiceAccountToken': False,
            "containers": [
                {
                    "env": [],
                    "envFrom": [{'secretRef': {}}],
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
            'restartPolicy': 'OnFailure',
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
        image='jupyter/singleuser:latest',
        env=[],
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
            "containers": [
                {
                    "env": [],
                    "envFrom": [{'secretRef': {}}],
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
            'restartPolicy': 'OnFailure',
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
        image='jupyter/singleuser:latest',
        env=[],
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
            "containers": [
                {
                    "env": [],
                    "envFrom": [{'secretRef': {}}],
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
            'restartPolicy': 'OnFailure',
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
        image='jupyter/singleuser:latest',
        env=[],
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
            "containers": [
                {
                    "env": [],
                    "envFrom": [{'secretRef': {}}],
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
            'restartPolicy': 'OnFailure',
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
        image='jupyter/singleuser:latest',
        env=[],
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
            "containers": [
                {
                    "env": [],
                    "envFrom": [{'secretRef': {}}],
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
            'restartPolicy': 'OnFailure',
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
        image='jupyter/singleuser:latest',
        env=[],
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
            "containers": [
                {
                    "env": [],
                    "envFrom": [{'secretRef': {}}],
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
            'restartPolicy': 'OnFailure',
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
        image='jupyter/singleuser:latest',
        env=[],
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
            "containers": [
                {
                    "env": [],
                    "envFrom": [{'secretRef': {}}],
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
            'restartPolicy': 'OnFailure',
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
        image='jupyter/singleuser:latest',
        cmd=['jupyterhub-singleuser'],
        env=[],
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
            "containers": [
                {
                    "env": [],
                    "envFrom": [{'secretRef': {}}],
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
            'restartPolicy': 'OnFailure',
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
        image='jupyter/singleuser:latest',
        cmd=['jupyterhub-singleuser'],
        env=[],
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
            'automountServiceAccountToken': False,
            "containers": [
                {
                    "env": [],
                    "envFrom": [{'secretRef': {}}],
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
            'restartPolicy': 'OnFailure',
            'volumes': [],
            'priorityClassName': 'my-custom-priority-class',
        },
        "kind": "Pod",
        "apiVersion": "v1"
    }

def test_make_ingress():
    """
    Test specification of the ingress objects
    """
    labels={
        'heritage': 'jupyterhub',
        'component': 'singleuser-server',
        'hub.jupyter.org/proxy-route': 'true'
    }
    endpoint, service, ingress = api_client.sanitize_for_serialization(make_ingress(
        name='jupyter-test',
        routespec='/my-path',
        target='http://192.168.1.10:9000',
        labels=labels,
        data={"mykey": "myvalue"}
    ))

    assert endpoint == {
        'kind': 'Endpoints',
        'metadata': {
            'annotations': {
                'hub.jupyter.org/proxy-data': '{"mykey": "myvalue"}',
                'hub.jupyter.org/proxy-routespec': '/my-path',
                'hub.jupyter.org/proxy-target': 'http://192.168.1.10:9000'},
            'labels': {
                'component': 'singleuser-server',
                'heritage': 'jupyterhub',
                'hub.jupyter.org/proxy-route': 'true'},
            'name': 'jupyter-test'
        },
        'subsets': [
            {'addresses': [{'ip': '192.168.1.10'}
        ],
        'ports': [{'port': 9000}]}]
    }

    assert service == {
        'kind': 'Service',
        'metadata': {
            'annotations': {
                'hub.jupyter.org/proxy-data': '{"mykey": "myvalue"}',
                'hub.jupyter.org/proxy-routespec': '/my-path',
                'hub.jupyter.org/proxy-target': 'http://192.168.1.10:9000'},
            'labels': {
                'component': 'singleuser-server',
                'heritage': 'jupyterhub',
                'hub.jupyter.org/proxy-route': 'true'},
            'name': 'jupyter-test'
        },
        'spec': {
            'externalName': '',
            'ports': [{'port': 9000, 'targetPort': 9000}],
            'type': 'ClusterIP'
        }
    }
    assert ingress ==  {
        'kind': 'Ingress',
        'metadata': {
            'annotations': {
                'hub.jupyter.org/proxy-data': '{"mykey": "myvalue"}',
                'hub.jupyter.org/proxy-routespec': '/my-path',
                'hub.jupyter.org/proxy-target': 'http://192.168.1.10:9000'},
            'labels': {
                'component': 'singleuser-server',
                'heritage': 'jupyterhub',
                'hub.jupyter.org/proxy-route': 'true'},
            'name': 'jupyter-test'},
        'spec': {
            'rules': [
                {'http': {
                    'paths': [
                        {
                            'backend': {
                                'serviceName': 'jupyter-test',
                                'servicePort': 9000},
                            'path': '/my-path'
                        }
                    ]}
                }]
            }
        }

def test_make_pod_with_ssl():
    """
    Test specification of a pod with ssl enabled
    """
    assert api_client.sanitize_for_serialization(
        make_pod(
            name='ssl',
            image='jupyter/singleuser:latest',
            env=[],
            env_from='ssl',
            working_dir='/',
            cmd=['jupyterhub-singleuser'],
            port=8888,
            image_pull_policy='IfNotPresent',
            ssl_secret_name='ssl',
            ssl_secret_mount_path="/etc/jupyterhub/ssl/",
        )
    ) == {
        "metadata": {
            "name": "ssl",
            "annotations": {},
            "labels": {},
        },
        "spec": {
            'automountServiceAccountToken': False,
            "containers": [
                {
                    "env": [],
                    "envFrom": [
                        {
                            'secretRef': {
                                'name': 'ssl'
                            }
                        },
                    ],
                    "name": "notebook",
                    "image": "jupyter/singleuser:latest",
                    "imagePullPolicy": "IfNotPresent",
                    "args": ["jupyterhub-singleuser"],
                    "ports": [{"name": "notebook-port", "containerPort": 8888}],
                    'volumeMounts': [
                        {
                            'mountPath': '/etc/jupyterhub/ssl/',
                            'name': 'jupyterhub-internal-certs',
                        }
                    ],
                    'workingDir': '/',
                    "resources": {"limits": {}, "requests": {}},
                }
            ],
            'restartPolicy': 'OnFailure',
            'volumes': [
                {
                    'name': 'jupyterhub-internal-certs',
                    'secret': {'defaultMode': 511, 'secretName': 'ssl'},
                }
            ],
        },
        "kind": "Pod",
        "apiVersion": "v1",
    }
