"""
Test functions used to create k8s objects
"""
from kubernetesspawner.objects import make_pod_spec


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
