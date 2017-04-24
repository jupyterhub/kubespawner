"""
Tests for kubespawner.utils
"""
from sqrekubespawner.utils import k8s_url


def test_k8s_url():
    assert k8s_url('default', 'pods') == '/api/v1/namespaces/default/pods'
    assert k8s_url('jupyter', 'pods',
                   'test') == '/api/v1/namespaces/jupyter/pods/test'
    assert k8s_url('default', 'persistentvolumeclaims',
                   'test') == '/api/v1/namespaces/default/persistentvolumeclaims/test'
    assert k8s_url('jupyter', 'persistentvolumeclaims',
                   'test') == '/api/v1/namespaces/jupyter/persistentvolumeclaims/test'
