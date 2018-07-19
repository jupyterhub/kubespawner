import copy
from kubespawner.utils import get_k8s_model, update_k8s_model, _get_k8s_model_attribute
from kubernetes.client.models import (
    V1PodSpec, V1SecurityContext, V1Container, V1Capabilities, V1Lifecycle
)

def test__get_k8s_model_attribute():
    """Verifies fundamental behavior"""
    assert _get_k8s_model_attribute(V1PodSpec, "service_account") == "service_account"
    assert _get_k8s_model_attribute(V1PodSpec, "serviceAccount") == "service_account"

def test_update_k8s_model():
    """Updates an attributes using update_k8s_model and manually and verifies
    output matches."""
    manually_updated_target = V1Container(
        name="mock_name",
        image="mock_image",
        command=['iptables'],
        security_context=V1SecurityContext(
            privileged=True,
            run_as_user=0,
            capabilities=V1Capabilities(add=['NET_ADMIN'])
        )
    )
    target = copy.deepcopy(manually_updated_target)
    source = {"name": "new_mock_name"}
    update_k8s_model(target, source)

    manually_updated_target.name = "new_mock_name"
    
    assert target == manually_updated_target

def test_get_k8s_model():
    """Passing an model type and a dictionary to model it."""
    v1_lifecycle = get_k8s_model(
        V1Lifecycle,
        {
            'preStop': {
                'exec': {
                    'command': ['/bin/sh', 'test']
                }
            }
        },
    ) 
    
    assert isinstance(v1_lifecycle, V1Lifecycle)
    assert v1_lifecycle.to_dict() == {
        'post_start': None,
        'pre_stop': {
            'exec': {
                'command': ['/bin/sh', 'test']
            }
        },
    }
