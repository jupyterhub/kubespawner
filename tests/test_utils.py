"""
Tests for kubernetesspawner.utils
"""
from kubernetesspawner.utils import k8s_url


def test_k8s_url():
    assert k8s_url('default', 'pods') == '/api/v1/namespaces/default/pods'
    assert k8s_url('jupyter', 'pods', 'test') == '/api/v1/namespaces/jupyter/pods/test'
