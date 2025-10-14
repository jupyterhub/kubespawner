import copy

import pytest
from conftest import ExecError
from kubernetes_asyncio.client.models import (
    V1Capabilities,
    V1Container,
    V1Lifecycle,
    V1PodSpec,
    V1SecurityContext,
)

from kubespawner.utils import _get_k8s_model_attribute, get_k8s_model, update_k8s_model


class MockLogger:
    """Trivial class to store logs for inspection after a test run."""

    def __init__(self):
        self.info_logs = []

    def info(self, message):
        self.info_logs.append(message)


def print_hello():
    print("hello!")


def exec_error():
    1 / 0


async def test_exec(exec_python):
    """Test the exec fixture itself"""
    r = await exec_python(print_hello)
    print("result: %r" % r)


async def test_exec_error(exec_python):
    """Test the exec fixture error handling"""
    with pytest.raises(ExecError):
        await exec_python(exec_error)


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


def test_update_k8s_models_logger_message():
    """Ensure that the update_k8s_model function uses the logger to warn about
    overwriting previous values."""
    target = V1Container(name="mock_name")
    source = {"name": "new_mock_name", "image_pull_policy": "Always"}
    mock_logger = MockLogger()
    update_k8s_model(
        target,
        source,
        logger=mock_logger,
        target_name="notebook_container",
        changes_name="extra_container_config",
    )

    assert (
        mock_logger.info_logs[-1].find(
            "'notebook_container.name' current value: 'mock_name' is overridden with 'new_mock_name', which is the value of 'extra_container_config.name'"
        )
        != -1
    )


def test_get_k8s_model():
    """Thest that passing either a kubernetes.client.models object or as a
    dictionary to representing it get_k8s_model should work."""
    # verify get_k8s_model for when passing dict objects
    v1_lifecycle_from_dict = get_k8s_model(
        V1Lifecycle,
        {'preStop': {'exec': {'command': ['/bin/sh', 'test']}}},
    )

    assert isinstance(v1_lifecycle_from_dict, V1Lifecycle)
    lifecycle_from_dict = v1_lifecycle_from_dict.to_dict()
    # K8S 1.33 added stop signals
    # https://kubernetes.io/blog/2025/05/14/kubernetes-v1-33-updates-to-container-lifecycle/#container-stop-signals
    assert lifecycle_from_dict.pop('stop_signal', None) is None
    assert lifecycle_from_dict == {
        'post_start': None,
        'pre_stop': {'exec': {'command': ['/bin/sh', 'test']}},
    }

    # verify get_k8s_model for when passing model objects
    v1_lifecycle_from_model_object = get_k8s_model(V1Lifecycle, v1_lifecycle_from_dict)

    assert isinstance(v1_lifecycle_from_model_object, V1Lifecycle)
    lifecycle_from_model_object = v1_lifecycle_from_model_object.to_dict()
    assert lifecycle_from_model_object.pop('stop_signal', None) is None
    assert lifecycle_from_model_object == {
        'post_start': None,
        'pre_stop': {'exec': {'command': ['/bin/sh', 'test']}},
    }
