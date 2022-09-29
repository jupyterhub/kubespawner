"""
Test functions used to create k8s objects
"""
import pytest
from kubernetes_asyncio.client import ApiClient

from kubespawner.objects import (
    make_ingress,
    make_namespace,
    make_pod,
    make_pvc,
    make_service,
)

api_client = ApiClient()


def test_make_simplest_pod():
    """
    Test specification of the simplest possible pod specification
    """
    assert api_client.sanitize_for_serialization(
        make_pod(
            name='test',
            image='jupyter/singleuser:latest',
            cmd=['jupyterhub-singleuser'],
            port=8888,
            image_pull_policy='IfNotPresent',
        )
    ) == {
        "metadata": {"name": "test", "labels": {}, "annotations": {}},
        "spec": {
            'automountServiceAccountToken': False,
            "containers": [
                {
                    "env": [],
                    "name": "notebook",
                    "image": "jupyter/singleuser:latest",
                    "imagePullPolicy": "IfNotPresent",
                    "args": ["jupyterhub-singleuser"],
                    "ports": [{"name": "notebook-port", "containerPort": 8888}],
                    'volumeMounts': [],
                    "resources": {"limits": {}, "requests": {}},
                    "securityContext": {"allowPrivilegeEscalation": False},
                }
            ],
            'restartPolicy': 'OnFailure',
            'volumes': [],
        },
        "kind": "Pod",
        "apiVersion": "v1",
    }


def test_make_labeled_pod():
    """
    Test specification of the simplest possible pod specification with labels
    """
    assert api_client.sanitize_for_serialization(
        make_pod(
            name='test',
            image='jupyter/singleuser:latest',
            cmd=['jupyterhub-singleuser'],
            port=8888,
            image_pull_policy='IfNotPresent',
            labels={"test": "true"},
        )
    ) == {
        "metadata": {"name": "test", "labels": {"test": "true"}, "annotations": {}},
        "spec": {
            'automountServiceAccountToken': False,
            "containers": [
                {
                    "env": [],
                    "name": "notebook",
                    "image": "jupyter/singleuser:latest",
                    "imagePullPolicy": "IfNotPresent",
                    "args": ["jupyterhub-singleuser"],
                    "ports": [{"name": "notebook-port", "containerPort": 8888}],
                    'volumeMounts': [],
                    "resources": {"limits": {}, "requests": {}},
                    "securityContext": {"allowPrivilegeEscalation": False},
                }
            ],
            'restartPolicy': 'OnFailure',
            'volumes': [],
        },
        "kind": "Pod",
        "apiVersion": "v1",
    }


def test_make_annotated_pod():
    """
    Test specification of the simplest possible pod specification with annotations
    """
    assert api_client.sanitize_for_serialization(
        make_pod(
            name='test',
            image='jupyter/singleuser:latest',
            cmd=['jupyterhub-singleuser'],
            port=8888,
            image_pull_policy='IfNotPresent',
            annotations={"test": "true"},
        )
    ) == {
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
                    "name": "notebook",
                    "image": "jupyter/singleuser:latest",
                    "imagePullPolicy": "IfNotPresent",
                    "args": ["jupyterhub-singleuser"],
                    "ports": [{"name": "notebook-port", "containerPort": 8888}],
                    'volumeMounts': [],
                    "resources": {"limits": {}, "requests": {}},
                    "securityContext": {"allowPrivilegeEscalation": False},
                }
            ],
            'restartPolicy': 'OnFailure',
            'volumes': [],
        },
        "kind": "Pod",
        "apiVersion": "v1",
    }


def test_make_pod_with_image_pull_secrets_simplified_format():
    """
    Test specification of the simplest possible pod specification
    """
    assert api_client.sanitize_for_serialization(
        make_pod(
            name='test',
            image='jupyter/singleuser:latest',
            cmd=['jupyterhub-singleuser'],
            port=8888,
            image_pull_policy='IfNotPresent',
            image_pull_secrets=["k8s-secret-a", "k8s-secret-b"],
        )
    ) == {
        "metadata": {
            "name": "test",
            "annotations": {},
            "labels": {},
        },
        "spec": {
            'automountServiceAccountToken': False,
            "imagePullSecrets": [{"name": "k8s-secret-a"}, {"name": "k8s-secret-b"}],
            "containers": [
                {
                    "env": [],
                    "name": "notebook",
                    "image": "jupyter/singleuser:latest",
                    "imagePullPolicy": "IfNotPresent",
                    "args": ["jupyterhub-singleuser"],
                    "ports": [{"name": "notebook-port", "containerPort": 8888}],
                    'volumeMounts': [],
                    "resources": {"limits": {}, "requests": {}},
                    "securityContext": {"allowPrivilegeEscalation": False},
                }
            ],
            'restartPolicy': 'OnFailure',
            'volumes': [],
        },
        "kind": "Pod",
        "apiVersion": "v1",
    }


def test_make_pod_with_image_pull_secrets_k8s_native_format():
    """
    Test specification of the simplest possible pod specification
    """
    assert api_client.sanitize_for_serialization(
        make_pod(
            name='test',
            image='jupyter/singleuser:latest',
            cmd=['jupyterhub-singleuser'],
            port=8888,
            image_pull_policy='IfNotPresent',
            image_pull_secrets=[{"name": "k8s-secret-a"}, {"name": "k8s-secret-b"}],
        )
    ) == {
        "metadata": {
            "name": "test",
            "annotations": {},
            "labels": {},
        },
        "spec": {
            'automountServiceAccountToken': False,
            "imagePullSecrets": [{"name": "k8s-secret-a"}, {"name": "k8s-secret-b"}],
            "containers": [
                {
                    "env": [],
                    "name": "notebook",
                    "image": "jupyter/singleuser:latest",
                    "imagePullPolicy": "IfNotPresent",
                    "args": ["jupyterhub-singleuser"],
                    "ports": [{"name": "notebook-port", "containerPort": 8888}],
                    'volumeMounts': [],
                    "resources": {"limits": {}, "requests": {}},
                    "securityContext": {"allowPrivilegeEscalation": False},
                }
            ],
            'restartPolicy': 'OnFailure',
            'volumes': [],
        },
        "kind": "Pod",
        "apiVersion": "v1",
    }


def test_set_container_uid_and_gid():
    """
    Test specification of the simplest possible pod specification
    """
    assert api_client.sanitize_for_serialization(
        make_pod(
            name='test',
            image='jupyter/singleuser:latest',
            cmd=['jupyterhub-singleuser'],
            port=8888,
            uid=0,
            gid=0,
            image_pull_policy='IfNotPresent',
        )
    ) == {
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
                        "runAsGroup": 0,
                        "allowPrivilegeEscalation": False,
                    },
                    "env": [],
                    "name": "notebook",
                    "image": "jupyter/singleuser:latest",
                    "imagePullPolicy": "IfNotPresent",
                    "args": ["jupyterhub-singleuser"],
                    "ports": [{"name": "notebook-port", "containerPort": 8888}],
                    'volumeMounts': [],
                    "resources": {"limits": {}, "requests": {}},
                }
            ],
            'restartPolicy': 'OnFailure',
            'volumes': [],
        },
        "kind": "Pod",
        "apiVersion": "v1",
    }


def test_set_container_uid_and_pod_fs_gid():
    """
    Test specification of the simplest possible pod specification
    """
    assert api_client.sanitize_for_serialization(
        make_pod(
            name='test',
            image='jupyter/singleuser:latest',
            cmd=['jupyterhub-singleuser'],
            port=8888,
            uid=1000,
            fs_gid=0,
            image_pull_policy='IfNotPresent',
        )
    ) == {
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
                        "allowPrivilegeEscalation": False,
                    },
                    "env": [],
                    "name": "notebook",
                    "image": "jupyter/singleuser:latest",
                    "imagePullPolicy": "IfNotPresent",
                    "args": ["jupyterhub-singleuser"],
                    "ports": [{"name": "notebook-port", "containerPort": 8888}],
                    'volumeMounts': [],
                    "resources": {"limits": {}, "requests": {}},
                }
            ],
            'restartPolicy': 'OnFailure',
            'securityContext': {
                'fsGroup': 0,
            },
            'volumes': [],
        },
        "kind": "Pod",
        "apiVersion": "v1",
    }


def test_set_pod_supplemental_gids():
    """
    Test specification of the simplest possible pod specification
    """
    assert api_client.sanitize_for_serialization(
        make_pod(
            name='test',
            image='jupyter/singleuser:latest',
            cmd=['jupyterhub-singleuser'],
            port=8888,
            uid=1000,
            supplemental_gids=[100],
            image_pull_policy='IfNotPresent',
        )
    ) == {
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
                        "allowPrivilegeEscalation": False,
                    },
                    "env": [],
                    "name": "notebook",
                    "image": "jupyter/singleuser:latest",
                    "imagePullPolicy": "IfNotPresent",
                    "args": ["jupyterhub-singleuser"],
                    "ports": [{"name": "notebook-port", "containerPort": 8888}],
                    'volumeMounts': [],
                    "resources": {"limits": {}, "requests": {}},
                }
            ],
            'restartPolicy': 'OnFailure',
            'securityContext': {
                'supplementalGroups': [100],
            },
            'volumes': [],
        },
        "kind": "Pod",
        "apiVersion": "v1",
    }


def test_privileged_container():
    """
    Test specification of the container to run as privileged
    """
    assert api_client.sanitize_for_serialization(
        make_pod(
            name='test',
            image='jupyter/singleuser:latest',
            cmd=['jupyterhub-singleuser'],
            port=8888,
            privileged=True,
            image_pull_policy='IfNotPresent',
        )
    ) == {
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
                    "name": "notebook",
                    "image": "jupyter/singleuser:latest",
                    "imagePullPolicy": "IfNotPresent",
                    "args": ["jupyterhub-singleuser"],
                    "ports": [{"name": "notebook-port", "containerPort": 8888}],
                    "resources": {"limits": {}, "requests": {}},
                    "securityContext": {
                        "privileged": True,
                        "allowPrivilegeEscalation": False,
                    },
                    'volumeMounts': [],
                }
            ],
            'restartPolicy': 'OnFailure',
            'volumes': [],
        },
        "kind": "Pod",
        "apiVersion": "v1",
    }


def test_allow_privilege_escalation_container():
    """
    Test specification of the container to run without privilege escalation (AllowPrivilegeEscalation=False).
    """
    assert api_client.sanitize_for_serialization(
        make_pod(
            name='test',
            image='jupyter/singleuser:latest',
            cmd=['jupyterhub-singleuser'],
            port=8888,
            allow_privilege_escalation=False,
            image_pull_policy='IfNotPresent',
        )
    ) == {
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
                    "name": "notebook",
                    "image": "jupyter/singleuser:latest",
                    "imagePullPolicy": "IfNotPresent",
                    "args": ["jupyterhub-singleuser"],
                    "ports": [{"name": "notebook-port", "containerPort": 8888}],
                    "resources": {"limits": {}, "requests": {}},
                    "securityContext": {"allowPrivilegeEscalation": False},
                    'volumeMounts': [],
                }
            ],
            'restartPolicy': 'OnFailure',
            'volumes': [],
        },
        "kind": "Pod",
        "apiVersion": "v1",
    }


def test_pod_security_context_container():
    """
    Test specification of the container to run with a security context.

    ref: https://kubernetes.io/docs/reference/generated/kubernetes-api/v1.20/#podsecuritycontext-v1-core
    """
    assert api_client.sanitize_for_serialization(
        make_pod(
            name='test',
            image='jupyter/singleuser:latest',
            image_pull_policy='IfNotPresent',
            cmd=['jupyterhub-singleuser'],
            port=8888,
            supplemental_gids=[100],
            fs_gid=100,
            pod_security_context={
                'supplementalGroups': [200],
                'fsGroup': 200,
                'fsGroupChangePolicy': "OnRootMismatch",
                'sysctls': [{"name": "kernel.msgmax", "value": "65536"}],
                "runAsUser": 2000,
                "runAsGroup": 200,
                "runAsNonRoot": False,
                "seLinuxOptions": {"level": "s0:c123,c456"},
                "seccompProfile": {"type": "RuntimeDefault"},
                "windowsOptions": {"gmsaCredentialSpecName": "gmsa-webapp1"},
            },
        )
    ) == {
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
                    "name": "notebook",
                    "image": "jupyter/singleuser:latest",
                    "imagePullPolicy": "IfNotPresent",
                    "args": ["jupyterhub-singleuser"],
                    "ports": [{"name": "notebook-port", "containerPort": 8888}],
                    'volumeMounts': [],
                    "resources": {"limits": {}, "requests": {}},
                    "securityContext": {"allowPrivilegeEscalation": False},
                }
            ],
            'restartPolicy': 'OnFailure',
            'securityContext': {
                'supplementalGroups': [200],
                'fsGroup': 200,
                'fsGroupChangePolicy': "OnRootMismatch",
                'sysctls': [{"name": "kernel.msgmax", "value": "65536"}],
                "runAsUser": 2000,
                "runAsGroup": 200,
                "runAsNonRoot": False,
                "seLinuxOptions": {"level": "s0:c123,c456"},
                "seccompProfile": {"type": "RuntimeDefault"},
                "windowsOptions": {"gmsaCredentialSpecName": "gmsa-webapp1"},
            },
            'volumes': [],
        },
        "kind": "Pod",
        "apiVersion": "v1",
    }


def test_container_security_context_container():
    """
    Test specification of the container to run with a security context.

    ref: https://kubernetes.io/docs/reference/generated/kubernetes-api/v1.20/#securitycontext-v1-core
    """
    assert api_client.sanitize_for_serialization(
        make_pod(
            name='test',
            image='jupyter/singleuser:latest',
            image_pull_policy='IfNotPresent',
            cmd=['jupyterhub-singleuser'],
            port=8888,
            uid=1000,
            gid=100,
            privileged=True,
            allow_privilege_escalation=False,
            container_security_context={
                "privileged": False,
                "allowPrivilegeEscalation": True,
                "capabilities": {"add": ["KILL"], "drop": ["SYS_CHROOT"]},
                "procMount": "DefaultProcMount",
                "readOnlyRootFilesystem": True,
                "runAsUser": 2000,
                "runAsGroup": 200,
                "runAsNonRoot": False,
                "seLinuxOptions": {"level": "s0:c123,c456"},
                "seccompProfile": {"type": "RuntimeDefault"},
                "windowsOptions": {"gmsaCredentialSpecName": "gmsa-webapp1"},
            },
        )
    ) == {
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
                    "name": "notebook",
                    "image": "jupyter/singleuser:latest",
                    "imagePullPolicy": "IfNotPresent",
                    "args": ["jupyterhub-singleuser"],
                    "ports": [{"name": "notebook-port", "containerPort": 8888}],
                    'volumeMounts': [],
                    "resources": {"limits": {}, "requests": {}},
                    'securityContext': {
                        "privileged": False,
                        "allowPrivilegeEscalation": True,
                        "capabilities": {"add": ["KILL"], "drop": ["SYS_CHROOT"]},
                        "procMount": "DefaultProcMount",
                        "readOnlyRootFilesystem": True,
                        "runAsUser": 2000,
                        "runAsGroup": 200,
                        "runAsNonRoot": False,
                        "seLinuxOptions": {"level": "s0:c123,c456"},
                        "seccompProfile": {"type": "RuntimeDefault"},
                        "windowsOptions": {"gmsaCredentialSpecName": "gmsa-webapp1"},
                    },
                }
            ],
            'restartPolicy': 'OnFailure',
            'volumes': [],
        },
        "kind": "Pod",
        "apiVersion": "v1",
    }


def test_bad_pod_security_context_container():
    """
    Test specification of the container to run with a security context.

    ref: https://kubernetes.io/docs/reference/generated/kubernetes-api/v1.20/#securitycontext-v1-core
    """
    with pytest.raises(ValueError):
        assert api_client.sanitize_for_serialization(
            make_pod(
                name='test',
                image='jupyter/singleuser:latest',
                image_pull_policy='IfNotPresent',
                cmd=['jupyterhub-singleuser'],
                port=8888,
                pod_security_context={
                    "run_as_user": 1000,
                },
            )
        )


def test_bad_container_security_context_container():
    """
    Test specification of the container to run with a security context.

    ref: https://kubernetes.io/docs/reference/generated/kubernetes-api/v1.20/#securitycontext-v1-core
    """
    with pytest.raises(ValueError):
        assert api_client.sanitize_for_serialization(
            make_pod(
                name='test',
                image='jupyter/singleuser:latest',
                image_pull_policy='IfNotPresent',
                cmd=['jupyterhub-singleuser'],
                port=8888,
                container_security_context={
                    "allow_privilege_escalation": True,
                },
            )
        )


def test_make_pod_resources_all():
    """
    Test specifying all possible resource limits & guarantees
    """
    assert api_client.sanitize_for_serialization(
        make_pod(
            name='test',
            image='jupyter/singleuser:latest',
            cpu_limit=2,
            cpu_guarantee=1,
            cmd=['jupyterhub-singleuser'],
            port=8888,
            mem_limit='1Gi',
            mem_guarantee='512Mi',
            image_pull_policy='IfNotPresent',
            node_selector={"disk": "ssd"},
        )
    ) == {
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
                    "name": "notebook",
                    "image": "jupyter/singleuser:latest",
                    "imagePullPolicy": "IfNotPresent",
                    "args": ["jupyterhub-singleuser"],
                    "ports": [{"name": "notebook-port", "containerPort": 8888}],
                    'volumeMounts': [],
                    "resources": {
                        "limits": {"cpu": 2, "memory": '1Gi'},
                        "requests": {"cpu": 1, "memory": '512Mi'},
                    },
                    "securityContext": {"allowPrivilegeEscalation": False},
                }
            ],
            'restartPolicy': 'OnFailure',
            'volumes': [],
        },
        "kind": "Pod",
        "apiVersion": "v1",
    }


def test_make_pod_with_env():
    """
    Test specification of a pod with custom environment variables.
    """
    assert api_client.sanitize_for_serialization(
        make_pod(
            name='test',
            image='jupyter/singleuser:latest',
            env={
                'NAME_1': 'TEST_VALUE',
                'NAME_2': {
                    'value': 'TEST_VALUE',
                },
                'NAME_3': {
                    'valueFrom': {
                        'secretKeyRef': {
                            'name': 'my-k8s-secret',
                            'key': 'password',
                        },
                    },
                },
                'IGNORED_NAME_1': {
                    'name': 'NAME_4',
                    'value': 'TEST_VALUE',
                },
                'IGNORED_NAME_2': {
                    'name': 'NAME_5',
                    'valueFrom': {
                        'secretKeyRef': {
                            'name': 'my-k8s-secret',
                            'key': 'password',
                        },
                    },
                },
            },
            cmd=['jupyterhub-singleuser'],
            port=8888,
            image_pull_policy='IfNotPresent',
        )
    ) == {
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
                            'name': 'NAME_4',
                            'value': 'TEST_VALUE',
                        },
                        {
                            'name': 'NAME_5',
                            'valueFrom': {
                                'secretKeyRef': {
                                    'name': 'my-k8s-secret',
                                    'key': 'password',
                                },
                            },
                        },
                        {
                            'name': 'NAME_1',
                            'value': 'TEST_VALUE',
                        },
                        {
                            'name': 'NAME_2',
                            'value': 'TEST_VALUE',
                        },
                        {
                            'name': 'NAME_3',
                            'valueFrom': {
                                'secretKeyRef': {
                                    'name': 'my-k8s-secret',
                                    'key': 'password',
                                },
                            },
                        },
                    ],
                    "name": "notebook",
                    "image": "jupyter/singleuser:latest",
                    "imagePullPolicy": "IfNotPresent",
                    "args": ["jupyterhub-singleuser"],
                    "ports": [{"name": "notebook-port", "containerPort": 8888}],
                    'volumeMounts': [],
                    "resources": {"limits": {}, "requests": {}},
                    "securityContext": {"allowPrivilegeEscalation": False},
                }
            ],
            'restartPolicy': 'OnFailure',
            'volumes': [],
        },
        "kind": "Pod",
        "apiVersion": "v1",
    }


def test_make_pod_with_env_dependency_sorted():
    """
    Test specification of a pod with custom environment variables that involve
    references to other environment variables. Note that KubeSpawner also tries
    to sort the environment variables in the rendered list in a way that helps
    maximize the amount of variables that are resolved.
    """
    assert api_client.sanitize_for_serialization(
        make_pod(
            name='test',
            image='jupyter/singleuser:latest',
            env={
                'NAME_SELF_REF': '$(NAME_SELF_REF)',
                'NAME_1B': '$(NAME_2)',
                'NAME_1A': '$(NAME_2)',
                'NAME_1C': {"name": "NAME_0", "value": "$(NAME_2)"},
                'NAME_2': '$(NAME_3A)',
                'NAME_3B': 'NAME_3B_VALUE',
                'NAME_3A': 'NAME_3A_VALUE',
                'NAME_CIRCLE_B': '$(NAME_CIRCLE_A)',
                'NAME_CIRCLE_A': '$(NAME_CIRCLE_B)',
            },
            cmd=['jupyterhub-singleuser'],
            port=8888,
            image_pull_policy='IfNotPresent',
        )
    ) == {
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
                            'name': 'NAME_3A',
                            'value': 'NAME_3A_VALUE',
                        },
                        {
                            'name': 'NAME_3B',
                            'value': 'NAME_3B_VALUE',
                        },
                        {
                            'name': 'NAME_SELF_REF',
                            'value': '$(NAME_SELF_REF)',
                        },
                        {
                            'name': 'NAME_2',
                            'value': '$(NAME_3A)',
                        },
                        {
                            'name': 'NAME_1A',
                            'value': '$(NAME_2)',
                        },
                        {
                            'name': 'NAME_1B',
                            'value': '$(NAME_2)',
                        },
                        {
                            'name': 'NAME_0',
                            'value': '$(NAME_2)',
                        },
                        {
                            'name': 'NAME_CIRCLE_A',
                            'value': '$(NAME_CIRCLE_B)',
                        },
                        {
                            'name': 'NAME_CIRCLE_B',
                            'value': '$(NAME_CIRCLE_A)',
                        },
                    ],
                    "name": "notebook",
                    "image": "jupyter/singleuser:latest",
                    "imagePullPolicy": "IfNotPresent",
                    "args": ["jupyterhub-singleuser"],
                    "ports": [{"name": "notebook-port", "containerPort": 8888}],
                    'volumeMounts': [],
                    "resources": {"limits": {}, "requests": {}},
                    "securityContext": {"allowPrivilegeEscalation": False},
                }
            ],
            'restartPolicy': 'OnFailure',
            'volumes': [],
        },
        "kind": "Pod",
        "apiVersion": "v1",
    }


def test_make_pod_with_lifecycle():
    """
    Test specification of a pod with lifecycle
    """
    assert api_client.sanitize_for_serialization(
        make_pod(
            name='test',
            image='jupyter/singleuser:latest',
            cmd=['jupyterhub-singleuser'],
            port=8888,
            image_pull_policy='IfNotPresent',
            lifecycle_hooks={'preStop': {'exec': {'command': ['/bin/sh', 'test']}}},
        )
    ) == {
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
                    "name": "notebook",
                    "image": "jupyter/singleuser:latest",
                    "imagePullPolicy": "IfNotPresent",
                    "args": ["jupyterhub-singleuser"],
                    "ports": [{"name": "notebook-port", "containerPort": 8888}],
                    'volumeMounts': [],
                    "resources": {"limits": {}, "requests": {}},
                    "lifecycle": {
                        "preStop": {"exec": {"command": ["/bin/sh", "test"]}}
                    },
                    "securityContext": {"allowPrivilegeEscalation": False},
                }
            ],
            'restartPolicy': 'OnFailure',
            'volumes': [],
        },
        "kind": "Pod",
        "apiVersion": "v1",
    }


def test_make_pod_with_init_containers():
    """
    Test specification of a pod with initContainers
    """
    assert api_client.sanitize_for_serialization(
        make_pod(
            name='test',
            image='jupyter/singleuser:latest',
            cmd=['jupyterhub-singleuser'],
            port=8888,
            image_pull_policy='IfNotPresent',
            init_containers=[
                {
                    'name': 'init-myservice',
                    'image': 'busybox',
                    'command': [
                        'sh',
                        '-c',
                        'until nslookup myservice; do echo waiting for myservice; sleep 2; done;',
                    ],
                },
                {
                    'name': 'init-mydb',
                    'image': 'busybox',
                    'command': [
                        'sh',
                        '-c',
                        'until nslookup mydb; do echo waiting for mydb; sleep 2; done;',
                    ],
                },
            ],
        )
    ) == {
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
                    "name": "notebook",
                    "image": "jupyter/singleuser:latest",
                    "imagePullPolicy": "IfNotPresent",
                    "args": ["jupyterhub-singleuser"],
                    "ports": [{"name": "notebook-port", "containerPort": 8888}],
                    'volumeMounts': [],
                    "resources": {"limits": {}, "requests": {}},
                    "securityContext": {"allowPrivilegeEscalation": False},
                }
            ],
            "initContainers": [
                {
                    "name": "init-myservice",
                    "image": "busybox",
                    "command": [
                        "sh",
                        "-c",
                        "until nslookup myservice; do echo waiting for myservice; sleep 2; done;",
                    ],
                },
                {
                    "name": "init-mydb",
                    "image": "busybox",
                    "command": [
                        "sh",
                        "-c",
                        "until nslookup mydb; do echo waiting for mydb; sleep 2; done;",
                    ],
                },
            ],
            'restartPolicy': 'OnFailure',
            'volumes': [],
        },
        "kind": "Pod",
        "apiVersion": "v1",
    }


def test_make_pod_with_extra_container_config():
    """
    Test specification of a pod with initContainers
    """
    assert api_client.sanitize_for_serialization(
        make_pod(
            name='test',
            image='jupyter/singleuser:latest',
            cmd=['jupyterhub-singleuser'],
            port=8888,
            image_pull_policy='IfNotPresent',
            extra_container_config={
                'envFrom': [{'configMapRef': {'name': 'special-config'}}]
            },
        )
    ) == {
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
                    "name": "notebook",
                    "image": "jupyter/singleuser:latest",
                    "imagePullPolicy": "IfNotPresent",
                    "args": ["jupyterhub-singleuser"],
                    "ports": [{"name": "notebook-port", "containerPort": 8888}],
                    'volumeMounts': [],
                    "resources": {"limits": {}, "requests": {}},
                    'envFrom': [{'configMapRef': {'name': 'special-config'}}],
                    "securityContext": {"allowPrivilegeEscalation": False},
                }
            ],
            'restartPolicy': 'OnFailure',
            'volumes': [],
        },
        "kind": "Pod",
        "apiVersion": "v1",
    }


def test_make_pod_with_extra_pod_config():
    """
    Test specification of a pod with initContainers
    """
    assert api_client.sanitize_for_serialization(
        make_pod(
            name='test',
            image='jupyter/singleuser:latest',
            cmd=['jupyterhub-singleuser'],
            port=8888,
            image_pull_policy='IfNotPresent',
            tolerations=[
                {'key': 'wrong_toleration', 'operator': 'Equal', 'value': 'wrong_value'}
            ],
            extra_pod_config={
                'dns_policy': 'ClusterFirstWithHostNet',
                'restartPolicy': 'Always',
                'tolerations': [
                    {
                        'key': 'correct_toleration',
                        'operator': 'Equal',
                        'value': 'correct_value',
                    }
                ],
            },
        )
    ) == {
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
                    "name": "notebook",
                    "image": "jupyter/singleuser:latest",
                    "imagePullPolicy": "IfNotPresent",
                    "args": ["jupyterhub-singleuser"],
                    "ports": [{"name": "notebook-port", "containerPort": 8888}],
                    'volumeMounts': [],
                    "resources": {"limits": {}, "requests": {}},
                    "securityContext": {"allowPrivilegeEscalation": False},
                }
            ],
            'volumes': [],
            'dnsPolicy': 'ClusterFirstWithHostNet',
            'restartPolicy': 'Always',
            'tolerations': [
                {
                    'key': 'correct_toleration',
                    'operator': 'Equal',
                    'value': 'correct_value',
                }
            ],
        },
        "kind": "Pod",
        "apiVersion": "v1",
    }


def test_make_pod_with_extra_containers():
    """
    Test specification of a pod with initContainers
    """
    assert api_client.sanitize_for_serialization(
        make_pod(
            name='test',
            image='jupyter/singleuser:latest',
            cmd=['jupyterhub-singleuser'],
            port=8888,
            image_pull_policy='IfNotPresent',
            extra_containers=[
                {
                    'name': 'crontab',
                    'image': 'supercronic',
                    'command': ['/usr/local/bin/supercronic', '/etc/crontab'],
                }
            ],
        )
    ) == {
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
                    "name": "notebook",
                    "image": "jupyter/singleuser:latest",
                    "imagePullPolicy": "IfNotPresent",
                    "args": ["jupyterhub-singleuser"],
                    "ports": [{"name": "notebook-port", "containerPort": 8888}],
                    'volumeMounts': [],
                    "resources": {"limits": {}, "requests": {}},
                    "securityContext": {"allowPrivilegeEscalation": False},
                },
                {
                    'name': 'crontab',
                    'image': 'supercronic',
                    'command': ['/usr/local/bin/supercronic', '/etc/crontab'],
                },
            ],
            'restartPolicy': 'OnFailure',
            'volumes': [],
        },
        "kind": "Pod",
        "apiVersion": "v1",
    }


def test_make_pod_with_extra_resources():
    """
    Test specification of extra resources (like GPUs)
    """
    assert api_client.sanitize_for_serialization(
        make_pod(
            name='test',
            image='jupyter/singleuser:latest',
            cpu_limit=2,
            cpu_guarantee=1,
            extra_resource_limits={"nvidia.com/gpu": "5", "k8s.io/new-resource": "1"},
            extra_resource_guarantees={"nvidia.com/gpu": "3"},
            cmd=['jupyterhub-singleuser'],
            port=8888,
            mem_limit='1Gi',
            mem_guarantee='512Mi',
            image_pull_policy='IfNotPresent',
            node_selector={"disk": "ssd"},
        )
    ) == {
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
                    "name": "notebook",
                    "image": "jupyter/singleuser:latest",
                    "imagePullPolicy": "IfNotPresent",
                    "args": ["jupyterhub-singleuser"],
                    "ports": [{"name": "notebook-port", "containerPort": 8888}],
                    'volumeMounts': [],
                    "resources": {
                        "limits": {
                            "cpu": 2,
                            "memory": '1Gi',
                            "nvidia.com/gpu": "5",
                            "k8s.io/new-resource": "1",
                        },
                        "requests": {
                            "cpu": 1,
                            "memory": '512Mi',
                            "nvidia.com/gpu": "3",
                        },
                    },
                    "securityContext": {"allowPrivilegeEscalation": False},
                }
            ],
            'restartPolicy': 'OnFailure',
            'volumes': [],
        },
        "kind": "Pod",
        "apiVersion": "v1",
    }


def test_make_pvc_simple():
    """
    Test specification of the simplest possible pvc specification
    """
    assert api_client.sanitize_for_serialization(
        make_pvc(
            name='test',
            storage_class=None,
            access_modes=[],
            selector=None,
            storage=None,
            labels={},
        )
    ) == {
        'kind': 'PersistentVolumeClaim',
        'apiVersion': 'v1',
        'metadata': {'name': 'test', 'annotations': {}, 'labels': {}},
        'spec': {'accessModes': [], 'resources': {'requests': {'storage': None}}},
    }


def test_make_pvc_empty_storage_class():
    """
    Test specification of pvc with empty storage class
    """
    assert api_client.sanitize_for_serialization(
        make_pvc(
            name='test',
            storage_class='',
            access_modes=[],
            selector=None,
            storage=None,
            labels={},
        )
    ) == {
        'kind': 'PersistentVolumeClaim',
        'apiVersion': 'v1',
        'metadata': {
            'name': 'test',
            'annotations': {'volume.beta.kubernetes.io/storage-class': ''},
            'labels': {},
        },
        'spec': {
            'accessModes': [],
            'resources': {'requests': {'storage': None}},
            'storageClassName': '',
        },
    }


def test_make_resources_all():
    """
    Test specifying all possible resource limits & guarantees
    """
    assert api_client.sanitize_for_serialization(
        make_pvc(
            name='test',
            storage_class='gce-standard-storage',
            access_modes=['ReadWriteOnce'],
            selector={'matchLabels': {'content': 'jupyter'}},
            storage='10Gi',
            labels={'key': 'value'},
        )
    ) == {
        'kind': 'PersistentVolumeClaim',
        'apiVersion': 'v1',
        'metadata': {
            'name': 'test',
            'annotations': {
                'volume.beta.kubernetes.io/storage-class': 'gce-standard-storage'
            },
            'labels': {'key': 'value'},
        },
        'spec': {
            'storageClassName': 'gce-standard-storage',
            'accessModes': ['ReadWriteOnce'],
            'selector': {'matchLabels': {'content': 'jupyter'}},
            'resources': {'requests': {'storage': '10Gi'}},
        },
    }


def test_make_pod_with_service_account():
    """
    Test specification of the simplest possible pod specification with non-default service account.
    """
    assert api_client.sanitize_for_serialization(
        make_pod(
            name='test',
            image='jupyter/singleuser:latest',
            cmd=['jupyterhub-singleuser'],
            port=8888,
            image_pull_policy='IfNotPresent',
            service_account='test',
        )
    ) == {
        "metadata": {"name": "test", "labels": {}, "annotations": {}},
        "spec": {
            "containers": [
                {
                    "env": [],
                    "name": "notebook",
                    "image": "jupyter/singleuser:latest",
                    "imagePullPolicy": "IfNotPresent",
                    "args": ["jupyterhub-singleuser"],
                    "ports": [{"name": "notebook-port", "containerPort": 8888}],
                    'volumeMounts': [],
                    "resources": {"limits": {}, "requests": {}},
                    "securityContext": {"allowPrivilegeEscalation": False},
                }
            ],
            'restartPolicy': 'OnFailure',
            'volumes': [],
            'serviceAccountName': 'test',
        },
        "kind": "Pod",
        "apiVersion": "v1",
    }


def test_make_pod_with_service_account_and_with_automount_sa_token():
    """
    Test specification of the simplest possible pod specification with non-default service account and automount service account token.
    """
    assert api_client.sanitize_for_serialization(
        make_pod(
            name='test',
            image='jupyter/singleuser:latest',
            cmd=['jupyterhub-singleuser'],
            port=8888,
            image_pull_policy='IfNotPresent',
            service_account='test',
            automount_service_account_token=True,
        )
    ) == {
        "metadata": {"name": "test", "labels": {}, "annotations": {}},
        "spec": {
            "automountServiceAccountToken": True,
            "containers": [
                {
                    "env": [],
                    "name": "notebook",
                    "image": "jupyter/singleuser:latest",
                    "imagePullPolicy": "IfNotPresent",
                    "args": ["jupyterhub-singleuser"],
                    "ports": [{"name": "notebook-port", "containerPort": 8888}],
                    'volumeMounts': [],
                    "resources": {"limits": {}, "requests": {}},
                    "securityContext": {"allowPrivilegeEscalation": False},
                }
            ],
            'restartPolicy': 'OnFailure',
            'volumes': [],
            'serviceAccountName': 'test',
        },
        "kind": "Pod",
        "apiVersion": "v1",
    }


def test_make_pod_with_service_account_and_with_negative_automount_sa_token():
    """
    Test specification of the simplest possible pod specification with non-default service account and negative automount service account token.
    """
    assert api_client.sanitize_for_serialization(
        make_pod(
            name='test',
            image='jupyter/singleuser:latest',
            cmd=['jupyterhub-singleuser'],
            port=8888,
            image_pull_policy='IfNotPresent',
            service_account='test',
            automount_service_account_token=False,
        )
    ) == {
        "metadata": {"name": "test", "labels": {}, "annotations": {}},
        "spec": {
            "automountServiceAccountToken": False,
            "containers": [
                {
                    "env": [],
                    "name": "notebook",
                    "image": "jupyter/singleuser:latest",
                    "imagePullPolicy": "IfNotPresent",
                    "args": ["jupyterhub-singleuser"],
                    "ports": [{"name": "notebook-port", "containerPort": 8888}],
                    'volumeMounts': [],
                    "resources": {"limits": {}, "requests": {}},
                    "securityContext": {"allowPrivilegeEscalation": False},
                }
            ],
            'restartPolicy': 'OnFailure',
            'volumes': [],
            'serviceAccountName': 'test',
        },
        "kind": "Pod",
        "apiVersion": "v1",
    }


def test_make_pod_with_automount_service_account_token():
    """
    Test specification of the simplest possible pod specification with automount service account token.
    """
    assert api_client.sanitize_for_serialization(
        make_pod(
            name='test',
            image='jupyter/singleuser:latest',
            cmd=['jupyterhub-singleuser'],
            port=8888,
            image_pull_policy='IfNotPresent',
            automount_service_account_token=True,
        )
    ) == {
        "metadata": {"name": "test", "labels": {}, "annotations": {}},
        "spec": {
            "automountServiceAccountToken": True,
            "containers": [
                {
                    "env": [],
                    "name": "notebook",
                    "image": "jupyter/singleuser:latest",
                    "imagePullPolicy": "IfNotPresent",
                    "args": ["jupyterhub-singleuser"],
                    "ports": [{"name": "notebook-port", "containerPort": 8888}],
                    'volumeMounts': [],
                    "resources": {"limits": {}, "requests": {}},
                    "securityContext": {"allowPrivilegeEscalation": False},
                }
            ],
            'restartPolicy': 'OnFailure',
            'volumes': [],
        },
        "kind": "Pod",
        "apiVersion": "v1",
    }


def test_make_pod_with_negative_automount_service_account_token():
    """
    Test specification of the simplest possible pod specification with negative automount service account token.
    """
    assert api_client.sanitize_for_serialization(
        make_pod(
            name='test',
            image='jupyter/singleuser:latest',
            cmd=['jupyterhub-singleuser'],
            port=8888,
            image_pull_policy='IfNotPresent',
            automount_service_account_token=False,
        )
    ) == {
        "metadata": {"name": "test", "labels": {}, "annotations": {}},
        "spec": {
            "automountServiceAccountToken": False,
            "containers": [
                {
                    "env": [],
                    "name": "notebook",
                    "image": "jupyter/singleuser:latest",
                    "imagePullPolicy": "IfNotPresent",
                    "args": ["jupyterhub-singleuser"],
                    "ports": [{"name": "notebook-port", "containerPort": 8888}],
                    'volumeMounts': [],
                    "resources": {"limits": {}, "requests": {}},
                    "securityContext": {"allowPrivilegeEscalation": False},
                }
            ],
            'restartPolicy': 'OnFailure',
            'volumes': [],
        },
        "kind": "Pod",
        "apiVersion": "v1",
    }


def test_make_pod_with_scheduler_name():
    """
    Test specification of the simplest possible pod specification with non-default scheduler name
    """
    assert api_client.sanitize_for_serialization(
        make_pod(
            name='test',
            image='jupyter/singleuser:latest',
            cmd=['jupyterhub-singleuser'],
            port=8888,
            image_pull_policy='IfNotPresent',
            scheduler_name='my-custom-scheduler',
        )
    ) == {
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
                    "name": "notebook",
                    "image": "jupyter/singleuser:latest",
                    "imagePullPolicy": "IfNotPresent",
                    "args": ["jupyterhub-singleuser"],
                    "ports": [{"name": "notebook-port", "containerPort": 8888}],
                    'volumeMounts': [],
                    "resources": {"limits": {}, "requests": {}},
                    "securityContext": {"allowPrivilegeEscalation": False},
                }
            ],
            'restartPolicy': 'OnFailure',
            'volumes': [],
            'schedulerName': 'my-custom-scheduler',
        },
        "kind": "Pod",
        "apiVersion": "v1",
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
            'effect': 'NoSchedule',
        },
        {'key': 'key', 'operator': 'Exists', 'effect': 'NoSchedule'},
    ]
    assert api_client.sanitize_for_serialization(
        make_pod(
            name='test',
            image='jupyter/singleuser:latest',
            cmd=['jupyterhub-singleuser'],
            port=8888,
            image_pull_policy='IfNotPresent',
            tolerations=tolerations,
        )
    ) == {
        "metadata": {"name": "test", "labels": {}, "annotations": {}},
        "spec": {
            "automountServiceAccountToken": False,
            "containers": [
                {
                    "env": [],
                    "name": "notebook",
                    "image": "jupyter/singleuser:latest",
                    "imagePullPolicy": "IfNotPresent",
                    "args": ["jupyterhub-singleuser"],
                    "ports": [{"name": "notebook-port", "containerPort": 8888}],
                    'volumeMounts': [],
                    "resources": {"limits": {}, "requests": {}},
                    "securityContext": {"allowPrivilegeEscalation": False},
                }
            ],
            'restartPolicy': 'OnFailure',
            'volumes': [],
            'tolerations': tolerations,
        },
        "kind": "Pod",
        "apiVersion": "v1",
    }


def test_make_pod_with_node_affinity_preferred():
    """
    Test specification of the simplest possible pod specification with non-empty node_affinity_preferred
    """
    node_affinity_preferred = [
        {
            "weight": 1,
            "preference": {
                "matchExpressions": [
                    {
                        "key": "hub.jupyter.org/node-purpose",
                        "operator": "In",
                        "values": ["user"],
                    }
                ],
            },
        }
    ]
    assert api_client.sanitize_for_serialization(
        make_pod(
            name='test',
            image='jupyter/singleuser:latest',
            cmd=['jupyterhub-singleuser'],
            port=8888,
            image_pull_policy='IfNotPresent',
            node_affinity_preferred=node_affinity_preferred,
        )
    ) == {
        "metadata": {"name": "test", "labels": {}, "annotations": {}},
        "spec": {
            "automountServiceAccountToken": False,
            "containers": [
                {
                    "env": [],
                    "name": "notebook",
                    "image": "jupyter/singleuser:latest",
                    "imagePullPolicy": "IfNotPresent",
                    "args": ["jupyterhub-singleuser"],
                    "ports": [{"name": "notebook-port", "containerPort": 8888}],
                    'volumeMounts': [],
                    "resources": {"limits": {}, "requests": {}},
                    "securityContext": {"allowPrivilegeEscalation": False},
                }
            ],
            'restartPolicy': 'OnFailure',
            "volumes": [],
            "affinity": {
                "nodeAffinity": {
                    "preferredDuringSchedulingIgnoredDuringExecution": node_affinity_preferred
                }
            },
        },
        "kind": "Pod",
        "apiVersion": "v1",
    }


def test_make_pod_with_node_affinity_required():
    """
    Test specification of the simplest possible pod specification with non-empty node_affinity_required
    """
    node_affinity_required = [
        {
            "matchExpressions": [
                {
                    "key": "hub.jupyter.org/node-purpose",
                    "operator": "In",
                    "values": ["user"],
                }
            ]
        }
    ]
    assert api_client.sanitize_for_serialization(
        make_pod(
            name='test',
            image='jupyter/singleuser:latest',
            cmd=['jupyterhub-singleuser'],
            port=8888,
            image_pull_policy='IfNotPresent',
            node_affinity_required=node_affinity_required,
        )
    ) == {
        "metadata": {"name": "test", "labels": {}, "annotations": {}},
        "spec": {
            "automountServiceAccountToken": False,
            "containers": [
                {
                    "env": [],
                    "name": "notebook",
                    "image": "jupyter/singleuser:latest",
                    "imagePullPolicy": "IfNotPresent",
                    "args": ["jupyterhub-singleuser"],
                    "ports": [{"name": "notebook-port", "containerPort": 8888}],
                    'volumeMounts': [],
                    "resources": {"limits": {}, "requests": {}},
                    "securityContext": {"allowPrivilegeEscalation": False},
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
            },
        },
        "kind": "Pod",
        "apiVersion": "v1",
    }


def test_make_pod_with_pod_affinity_preferred():
    """
    Test specification of the simplest possible pod specification with non-empty pod_affinity_preferred
    """
    pod_affinity_preferred = [
        {
            "weight": 100,
            "podAffinityTerm": {
                "labelSelector": {
                    "matchExpressions": [
                        {
                            "key": "hub.jupyter.org/pod-kind",
                            "operator": "In",
                            "values": ["user"],
                        }
                    ]
                },
                "topologyKey": "kubernetes.io/hostname",
            },
        }
    ]
    assert api_client.sanitize_for_serialization(
        make_pod(
            name='test',
            image='jupyter/singleuser:latest',
            cmd=['jupyterhub-singleuser'],
            port=8888,
            image_pull_policy='IfNotPresent',
            pod_affinity_preferred=pod_affinity_preferred,
        )
    ) == {
        "metadata": {"name": "test", "labels": {}, "annotations": {}},
        "spec": {
            "automountServiceAccountToken": False,
            "containers": [
                {
                    "env": [],
                    "name": "notebook",
                    "image": "jupyter/singleuser:latest",
                    "imagePullPolicy": "IfNotPresent",
                    "args": ["jupyterhub-singleuser"],
                    "ports": [{"name": "notebook-port", "containerPort": 8888}],
                    'volumeMounts': [],
                    "resources": {"limits": {}, "requests": {}},
                    "securityContext": {"allowPrivilegeEscalation": False},
                }
            ],
            'restartPolicy': 'OnFailure',
            "volumes": [],
            "affinity": {
                "podAffinity": {
                    "preferredDuringSchedulingIgnoredDuringExecution": pod_affinity_preferred
                }
            },
        },
        "kind": "Pod",
        "apiVersion": "v1",
    }


def test_make_pod_with_pod_affinity_required():
    """
    Test specification of the simplest possible pod specification with non-empty pod_affinity_required
    """
    pod_affinity_required = [
        {
            "labelSelector": {
                "matchExpressions": [
                    {
                        "key": "security",
                        "operator": "In",
                        "values": ["S1"],
                    }
                ]
            },
            "topologyKey": "failure-domain.beta.kubernetes.io/zone",
        }
    ]
    assert api_client.sanitize_for_serialization(
        make_pod(
            name='test',
            image='jupyter/singleuser:latest',
            cmd=['jupyterhub-singleuser'],
            port=8888,
            image_pull_policy='IfNotPresent',
            pod_affinity_required=pod_affinity_required,
        )
    ) == {
        "metadata": {"name": "test", "labels": {}, "annotations": {}},
        "spec": {
            "automountServiceAccountToken": False,
            "containers": [
                {
                    "env": [],
                    "name": "notebook",
                    "image": "jupyter/singleuser:latest",
                    "imagePullPolicy": "IfNotPresent",
                    "args": ["jupyterhub-singleuser"],
                    "ports": [{"name": "notebook-port", "containerPort": 8888}],
                    'volumeMounts': [],
                    "resources": {"limits": {}, "requests": {}},
                    "securityContext": {"allowPrivilegeEscalation": False},
                }
            ],
            'restartPolicy': 'OnFailure',
            "volumes": [],
            "affinity": {
                "podAffinity": {
                    "requiredDuringSchedulingIgnoredDuringExecution": pod_affinity_required
                }
            },
        },
        "kind": "Pod",
        "apiVersion": "v1",
    }


def test_make_pod_with_pod_anti_affinity_preferred():
    """
    Test specification of the simplest possible pod specification with non-empty pod_anti_affinity_preferred
    """
    pod_anti_affinity_preferred = [
        {
            "weight": 100,
            "podAffinityTerm": {
                "labelSelector": {
                    "matchExpressions": [
                        {
                            "key": "hub.jupyter.org/pod-kind",
                            "operator": "In",
                            "values": ["user"],
                        }
                    ]
                },
                "topologyKey": "kubernetes.io/hostname",
            },
        }
    ]
    assert api_client.sanitize_for_serialization(
        make_pod(
            name='test',
            image='jupyter/singleuser:latest',
            cmd=['jupyterhub-singleuser'],
            port=8888,
            image_pull_policy='IfNotPresent',
            pod_anti_affinity_preferred=pod_anti_affinity_preferred,
        )
    ) == {
        "metadata": {"name": "test", "labels": {}, "annotations": {}},
        "spec": {
            "automountServiceAccountToken": False,
            "containers": [
                {
                    "env": [],
                    "name": "notebook",
                    "image": "jupyter/singleuser:latest",
                    "imagePullPolicy": "IfNotPresent",
                    "args": ["jupyterhub-singleuser"],
                    "ports": [{"name": "notebook-port", "containerPort": 8888}],
                    'volumeMounts': [],
                    "resources": {"limits": {}, "requests": {}},
                    "securityContext": {"allowPrivilegeEscalation": False},
                }
            ],
            'restartPolicy': 'OnFailure',
            "volumes": [],
            "affinity": {
                "podAntiAffinity": {
                    "preferredDuringSchedulingIgnoredDuringExecution": pod_anti_affinity_preferred
                }
            },
        },
        "kind": "Pod",
        "apiVersion": "v1",
    }


def test_make_pod_with_pod_anti_affinity_required():
    """
    Test specification of the simplest possible pod specification with non-empty pod_anti_affinity_required
    """
    pod_anti_affinity_required = [
        {
            "labelSelector": {
                "matchExpressions": [
                    {
                        "key": "security",
                        "operator": "In",
                        "values": ["S1"],
                    }
                ]
            },
            "topologyKey": "failure-domain.beta.kubernetes.io/zone",
        }
    ]
    assert api_client.sanitize_for_serialization(
        make_pod(
            name='test',
            image='jupyter/singleuser:latest',
            cmd=['jupyterhub-singleuser'],
            port=8888,
            image_pull_policy='IfNotPresent',
            pod_anti_affinity_required=pod_anti_affinity_required,
        )
    ) == {
        "metadata": {"name": "test", "labels": {}, "annotations": {}},
        "spec": {
            "automountServiceAccountToken": False,
            "containers": [
                {
                    "env": [],
                    "name": "notebook",
                    "image": "jupyter/singleuser:latest",
                    "imagePullPolicy": "IfNotPresent",
                    "args": ["jupyterhub-singleuser"],
                    "ports": [{"name": "notebook-port", "containerPort": 8888}],
                    'volumeMounts': [],
                    "resources": {"limits": {}, "requests": {}},
                    "securityContext": {"allowPrivilegeEscalation": False},
                }
            ],
            'restartPolicy': 'OnFailure',
            "volumes": [],
            "affinity": {
                "podAntiAffinity": {
                    "requiredDuringSchedulingIgnoredDuringExecution": pod_anti_affinity_required
                }
            },
        },
        "kind": "Pod",
        "apiVersion": "v1",
    }


def test_make_pod_with_priority_class_name():
    """
    Test specification of the simplest possible pod specification with non-default priorityClassName set
    """
    assert api_client.sanitize_for_serialization(
        make_pod(
            name='test',
            image='jupyter/singleuser:latest',
            cmd=['jupyterhub-singleuser'],
            port=8888,
            image_pull_policy='IfNotPresent',
            priority_class_name='my-custom-priority-class',
        )
    ) == {
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
                    "name": "notebook",
                    "image": "jupyter/singleuser:latest",
                    "imagePullPolicy": "IfNotPresent",
                    "args": ["jupyterhub-singleuser"],
                    "ports": [{"name": "notebook-port", "containerPort": 8888}],
                    'volumeMounts': [],
                    "resources": {"limits": {}, "requests": {}},
                    "securityContext": {"allowPrivilegeEscalation": False},
                }
            ],
            'restartPolicy': 'OnFailure',
            'volumes': [],
            'priorityClassName': 'my-custom-priority-class',
        },
        "kind": "Pod",
        "apiVersion": "v1",
    }


@pytest.mark.parametrize(
    'target,ip',
    [
        ('http://192.168.1.10:9000', '192.168.1.10'),
        ('http://[2001:db8::dead:babe]:9000', '2001:db8::dead:babe'),
    ],
)
def test_make_ingress(target, ip):
    """
    Test specification of the ingress objects
    """
    labels = {
        'heritage': 'jupyterhub',
        'component': 'singleuser-server',
        'hub.jupyter.org/proxy-route': 'true',
    }
    endpoint, service, ingress = api_client.sanitize_for_serialization(
        make_ingress(
            name='jupyter-test',
            routespec='/my-path',
            target=target,
            labels=labels,
            data={"mykey": "myvalue"},
        )
    )

    assert endpoint == {
        'kind': 'Endpoints',
        'metadata': {
            'annotations': {
                'hub.jupyter.org/proxy-data': '{"mykey": "myvalue"}',
                'hub.jupyter.org/proxy-routespec': '/my-path',
                'hub.jupyter.org/proxy-target': target,
            },
            'labels': {
                'component': 'singleuser-server',
                'heritage': 'jupyterhub',
                'hub.jupyter.org/proxy-route': 'true',
            },
            'name': 'jupyter-test',
        },
        'subsets': [{'addresses': [{'ip': ip}], 'ports': [{'port': 9000}]}],
    }

    assert service == {
        'kind': 'Service',
        'metadata': {
            'annotations': {
                'hub.jupyter.org/proxy-data': '{"mykey": "myvalue"}',
                'hub.jupyter.org/proxy-routespec': '/my-path',
                'hub.jupyter.org/proxy-target': target,
            },
            'labels': {
                'component': 'singleuser-server',
                'heritage': 'jupyterhub',
                'hub.jupyter.org/proxy-route': 'true',
            },
            'name': 'jupyter-test',
        },
        'spec': {
            'externalName': '',
            'ports': [{'port': 9000, 'targetPort': 9000}],
            'type': 'ClusterIP',
        },
    }
    assert ingress == {
        'kind': 'Ingress',
        'metadata': {
            'annotations': {
                'hub.jupyter.org/proxy-data': '{"mykey": "myvalue"}',
                'hub.jupyter.org/proxy-routespec': '/my-path',
                'hub.jupyter.org/proxy-target': target,
            },
            'labels': {
                'component': 'singleuser-server',
                'heritage': 'jupyterhub',
                'hub.jupyter.org/proxy-route': 'true',
            },
            'name': 'jupyter-test',
        },
        'spec': {
            'rules': [
                {
                    'http': {
                        'paths': [
                            {
                                'backend': {
                                    'service': {
                                        'name': 'jupyter-test',
                                        'port': {
                                            'number': 9000,
                                        },
                                    },
                                },
                                'path': '/my-path',
                                'pathType': 'Prefix',
                            }
                        ]
                    }
                }
            ]
        },
    }


def test_make_ingress_external_name():
    """
    Test specification of the ingress objects
    """
    labels = {
        'heritage': 'jupyterhub',
        'component': 'singleuser-server',
        'hub.jupyter.org/proxy-route': 'true',
    }
    endpoint, service, ingress = api_client.sanitize_for_serialization(
        make_ingress(
            name='jupyter-test',
            routespec='/my-path',
            target='http://my-pod-name:9000',
            labels=labels,
            data={"mykey": "myvalue"},
        )
    )

    assert endpoint == None

    assert service == {
        'kind': 'Service',
        'metadata': {
            'annotations': {
                'hub.jupyter.org/proxy-data': '{"mykey": "myvalue"}',
                'hub.jupyter.org/proxy-routespec': '/my-path',
                'hub.jupyter.org/proxy-target': 'http://my-pod-name:9000',
            },
            'labels': {
                'component': 'singleuser-server',
                'heritage': 'jupyterhub',
                'hub.jupyter.org/proxy-route': 'true',
            },
            'name': 'jupyter-test',
        },
        'spec': {
            'externalName': 'my-pod-name',
            'clusterIP': '',
            'ports': [{'port': 9000, 'targetPort': 9000}],
            'type': 'ExternalName',
        },
    }
    assert ingress == {
        'kind': 'Ingress',
        'metadata': {
            'annotations': {
                'hub.jupyter.org/proxy-data': '{"mykey": "myvalue"}',
                'hub.jupyter.org/proxy-routespec': '/my-path',
                'hub.jupyter.org/proxy-target': 'http://my-pod-name:9000',
            },
            'labels': {
                'component': 'singleuser-server',
                'heritage': 'jupyterhub',
                'hub.jupyter.org/proxy-route': 'true',
            },
            'name': 'jupyter-test',
        },
        'spec': {
            'rules': [
                {
                    'http': {
                        'paths': [
                            {
                                'backend': {
                                    'service': {
                                        'name': 'jupyter-test',
                                        'port': {
                                            'number': 9000,
                                        },
                                    },
                                },
                                'path': '/my-path',
                                'pathType': 'Prefix',
                            }
                        ]
                    }
                }
            ]
        },
    }


def test_make_namespace():
    labels = {
        'heritage': 'jupyterhub',
        'component': 'singleuser-server',
    }
    namespace = api_client.sanitize_for_serialization(
        make_namespace(name='test-namespace', labels=labels)
    )
    assert namespace == {
        'metadata': {
            'annotations': {},
            'labels': {
                'component': 'singleuser-server',
                'heritage': 'jupyterhub',
            },
            'name': 'test-namespace',
        },
    }


def test_make_pod_with_ssl():
    """
    Test specification of a pod with ssl enabled
    """
    assert api_client.sanitize_for_serialization(
        make_pod(
            name='ssl',
            image='jupyter/singleuser:latest',
            env={
                'JUPYTERHUB_SSL_KEYFILE': 'TEST_VALUE',
                'JUPYTERHUB_SSL_CERTFILE': 'TEST',
                'JUPYTERHUB_USER': 'TEST',
            },
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
                    "env": [
                        {
                            'name': 'JUPYTERHUB_SSL_CERTFILE',
                            'value': '/etc/jupyterhub/ssl/ssl.crt',
                        },
                        {
                            'name': 'JUPYTERHUB_SSL_CLIENT_CA',
                            'value': '/etc/jupyterhub/ssl/notebooks-ca_trust.crt',
                        },
                        {
                            'name': 'JUPYTERHUB_SSL_KEYFILE',
                            'value': '/etc/jupyterhub/ssl/ssl.key',
                        },
                        {'name': 'JUPYTERHUB_USER', 'value': 'TEST'},
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
                    "securityContext": {"allowPrivilegeEscalation": False},
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
        'apiVersion': 'v1',
    }


@pytest.mark.parametrize(
    "service_type",
    [
        "ClusterIP",
        "NodePort",
    ],
)
def test_make_service_with_type(service_type):
    """
    Test specification of a service
    """

    assert api_client.sanitize_for_serialization(
        make_service(
            name='service',
            ports=[
                {
                    "port": 80,
                    "target_port": 80,
                }
            ],
            servername='some',
            type=service_type,
            labels={
                'hub.jupyter.org/username': 'user',
            },
        )
    ) == {
        "metadata": {
            "name": "service",
            "annotations": {},
            "labels": {
                'hub.jupyter.org/username': 'user',
            },
        },
        "spec": {
            "type": service_type,
            "ports": [
                {
                    "port": 80,
                    "targetPort": 80,
                }
            ],
            "selector": {
                'component': 'singleuser-server',
                'hub.jupyter.org/servername': 'some',
                'hub.jupyter.org/username': 'user',
            },
        },
        "kind": "Service",
    }


def test_make_service_with_owner_references():
    """
    Test specification of a service
    """

    assert api_client.sanitize_for_serialization(
        make_service(
            name='service',
            ports=[
                {
                    "port": 80,
                    "target_port": 80,
                }
            ],
            servername='some',
            owner_references="abc",
            labels={
                'hub.jupyter.org/username': 'user',
                'some/label': 'labeled',
            },
            annotations={
                'some/annotation': 'annotated',
            },
        )
    ) == {
        "metadata": {
            "name": "service",
            "annotations": {
                'some/annotation': 'annotated',
            },
            "labels": {
                'hub.jupyter.org/username': 'user',
                'some/label': 'labeled',
            },
            "ownerReferences": "abc",
        },
        "spec": {
            "ports": [
                {
                    "port": 80,
                    "targetPort": 80,
                }
            ],
            "type": 'ClusterIP',
            "selector": {
                'component': 'singleuser-server',
                'hub.jupyter.org/servername': 'some',
                'hub.jupyter.org/username': 'user',
            },
        },
        "kind": "Service",
    }
