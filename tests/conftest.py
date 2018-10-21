"""pytest fixtures for kubespawner"""

import os

from kubernetes.client import V1Namespace
from kubernetes.config import load_kube_config
import pytest
from traitlets.config import Config

from v3iokubespawner.clients import shared_client


@pytest.fixture(scope="session")
def kube_ns():
    """Fixture for the kubernetes namespace"""
    return os.environ.get("KUBESPAWNER_TEST_NAMESPACE") or "kubespawner-test"


@pytest.fixture
def config(kube_ns):
    """Return a traitlets Config object

    The base configuration for testing.
    Use when constructing Spawners for tests
    """
    cfg = Config()
    cfg.KubeSpawner.namespace = kube_ns
    return cfg


@pytest.fixture(scope="session")
def kube_client(request, kube_ns):
    """fixture for the Kubernetes client object.

    skips test that require kubernetes if kubernetes cannot be contacted
    """
    load_kube_config()
    client = shared_client('CoreV1Api')
    try:
        namespaces = client.list_namespace(_request_timeout=3)
    except Exception as e:
        pytest.skip("Kubernetes not found: %s" % e)
    if not any(ns.metadata.name == kube_ns for ns in namespaces.items):
        print("Creating namespace %s" % kube_ns)
        client.create_namespace(V1Namespace(metadata=dict(name=kube_ns)))
    else:
        print("Using existing namespace %s" % kube_ns)
    # delete the test namespace when we finish
    request.addfinalizer(lambda: client.delete_namespace(kube_ns, {}))
    return client
