import copy

import pytest
from conftest import ExecError
from kubernetes.client.models import V1Capabilities
from kubernetes.client.models import V1Container
from kubernetes.client.models import V1Lifecycle
from kubernetes.client.models import V1PodSpec
from kubernetes.client.models import V1SecurityContext

from kubespawner.utils import _get_k8s_model_attribute
from kubespawner.utils import get_k8s_model
from kubespawner.utils import update_k8s_model


class MockLogger(object):
    """Trivial class to store logs for inspection after a test run."""

    def __init__(self):
        self.warning_count = 0

    def warning(self, message):
        """Remembers the most recent warning."""
        self.most_recent_warning = message
        self.warning_count += 1


def print_hello():
    print("hello!")


def exec_error():
    1 / 0


def test_exec(exec_python):
    """Test the exec fixture itself"""
    r = exec_python(print_hello)
    print("result: %r" % r)


def test_exec_error(exec_python):
    """Test the exec fixture error handling"""
    with pytest.raises(ExecError) as e:
        exec_python(exec_error)


def test__get_k8s_model_attribute():
    """Verifies fundamental behavior"""
    assert _get_k8s_model_attribute(V1PodSpec, "service_account") == "service_account"
    assert _get_k8s_model_attribute(V1PodSpec, "serviceAccount") == "service_account"


def test_update_k8s_model():
    """Ensure update_k8s_model does what it should. The test is first updating
    attributes using the function and then and manually verifies that the
    correct changes have been made."""
    manually_updated_target = V1Container(
        name="mock_name",
        image="mock_image",
        command=['iptables'],
        security_context=V1SecurityContext(
            privileged=True,
            run_as_user=0,
            capabilities=V1Capabilities(add=['NET_ADMIN']),
        ),
    )
    target = copy.deepcopy(manually_updated_target)
    source = {"name": "new_mock_name"}
    update_k8s_model(target, source)

    manually_updated_target.name = "new_mock_name"

    assert target == manually_updated_target


def test_update_k8s_models_logger_warning():
    """Ensure that the update_k8s_model function uses the logger to warn about
    overwriting previous values."""
    target = V1Container(name="mock_name")
    source = {"name": "new_mock_name", "image_pull_policy": "Always"}
    mock_locker = MockLogger()
    update_k8s_model(
        target,
        source,
        logger=mock_locker,
        target_name="notebook_container",
        changes_name="extra_container_config",
    )

    assert (
        mock_locker.most_recent_warning.find(
            "'notebook_container.name' current value: 'mock_name' is overridden with 'new_mock_name', which is the value of 'extra_container_config.name'"
        )
        != -1
    )
    assert mock_locker.warning_count == 1


def test_get_k8s_model():
    """Thest that passing either a kubernetes.client.models object or as a
    dictionary to representing it get_k8s_model should work."""
    # verify get_k8s_model for when passing dict objects
    v1_lifecycle_from_dict = get_k8s_model(
        V1Lifecycle,
        {'preStop': {'exec': {'command': ['/bin/sh', 'test']}}},
    )

    assert isinstance(v1_lifecycle_from_dict, V1Lifecycle)
    assert v1_lifecycle_from_dict.to_dict() == {
        'post_start': None,
        'pre_stop': {'exec': {'command': ['/bin/sh', 'test']}},
    }

    # verify get_k8s_model for when passing model objects
    v1_lifecycle_from_model_object = get_k8s_model(V1Lifecycle, v1_lifecycle_from_dict)

    assert isinstance(v1_lifecycle_from_model_object, V1Lifecycle)
    assert v1_lifecycle_from_model_object.to_dict() == {
        'post_start': None,
        'pre_stop': {'exec': {'command': ['/bin/sh', 'test']}},
    }
