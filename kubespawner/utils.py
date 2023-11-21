"""
Misc. general utility functions, not tied to KubeSpawner directly
"""
import copy
import hashlib


def generate_hashed_slug(slug, limit=63, hash_length=6):
    """
    Generate a unique name that's within a certain length limit

    Most k8s objects have a 63 char name limit. We wanna be able to compress
    larger names down to that if required, while still maintaining some
    amount of legibility about what the objects really are.

    If the length of the slug is shorter than the limit - hash_length, we just
    return slug directly. If not, we truncate the slug to (limit - hash_length)
    characters, hash the slug and append hash_length characters from the hash
    to the end of the truncated slug. This ensures that these names are always
    unique no matter what.
    """
    if len(slug) < (limit - hash_length):
        return slug

    slug_hash = hashlib.sha256(slug.encode('utf-8')).hexdigest()

    return '{prefix}-{hash}'.format(
        prefix=slug[: limit - hash_length - 1],
        hash=slug_hash[:hash_length],
    ).lower()


def update_k8s_model(target, changes, logger=None, target_name=None, changes_name=None):
    """
    Takes a model instance such as V1PodSpec() and updates it with another
    model, which is allowed to be a dict or another model instance of the same
    type. The logger is used to warn if any truthy value in the target is is
    overridden. The target_name parameter can for example be "pod.spec", and
    changes_name parameter could be "extra_pod_config". These parameters allows
    the logger to write out something more meaningful to the user whenever
    something is about to become overridden.
    """
    model_type = type(target)
    if not hasattr(target, 'attribute_map'):
        raise AttributeError(
            "Attribute 'target' ({}) must be an object (such as 'V1PodSpec') with an attribute 'attribute_map'.".format(
                model_type.__name__
            )
        )
    if not isinstance(changes, model_type) and not isinstance(changes, dict):
        raise AttributeError(
            "Attribute 'changes' ({}) must be an object of the same type as 'target' ({}) or a 'dict'.".format(
                type(changes).__name__, model_type.__name__
            )
        )

    changes_dict = _get_k8s_model_dict(model_type, changes)
    for key, value in changes_dict.items():
        if key not in target.attribute_map:
            raise ValueError(
                "The attribute 'changes' ({}) contained '{}' not modeled by '{}'.".format(
                    type(changes).__name__, key, model_type.__name__
                )
            )

        # If changes are passed as a dict, they will only have a few keys/value
        # pairs representing the specific changes. If the changes parameter is a
        # model instance on the other hand, the changes parameter will have a
        # lot of default values as well. These default values, which are also
        # falsy, should not use to override the target's values.
        if isinstance(changes, dict) or value:
            if getattr(target, key):
                if logger and changes_name:
                    msg = "'{}.{}' current value: '{}' is overridden with '{}', which is the value of '{}.{}'.".format(
                        target_name, key, getattr(target, key), value, changes_name, key
                    )
                    logger.info(msg)
            setattr(target, key, value)

    return target


def get_k8s_model(model_type, model_dict):
    """
    Returns an instance of type specified model_type from an model instance or
    represantative dictionary.
    """
    model_dict = copy.deepcopy(model_dict)

    if isinstance(model_dict, model_type):
        return model_dict
    elif isinstance(model_dict, dict):
        # convert the dictionaries camelCase keys to snake_case keys
        model_dict = _map_dict_keys_to_model_attributes(model_type, model_dict)
        # use the dictionary keys to initialize a model of given type
        return model_type(**model_dict)
    else:
        raise AttributeError(
            "Expected object of type 'dict' (or '{}') but got '{}'.".format(
                model_type.__name__, type(model_dict).__name__
            )
        )


def _get_k8s_model_dict(model_type, model):
    """
    Returns a dictionary representation of a provided model type
    """
    model = copy.deepcopy(model)

    if isinstance(model, model_type):
        return model.to_dict()
    elif isinstance(model, dict):
        return _map_dict_keys_to_model_attributes(model_type, model)
    else:
        raise AttributeError(
            "Expected object of type '{}' (or 'dict') but got '{}'.".format(
                model_type.__name__, type(model).__name__
            )
        )


def _map_dict_keys_to_model_attributes(model_type, model_dict):
    """
    Maps a dict's keys to the provided models attributes using its attribute_map
    attribute. This is (always?) the same as converting camelCase to snake_case.
    Note that the function will not influence nested object's keys.
    """

    new_dict = {}
    for key, value in model_dict.items():
        new_dict[_get_k8s_model_attribute(model_type, key)] = value

    return new_dict


def _get_k8s_model_attribute(model_type, field_name):
    """
    Takes a model type and a Kubernetes API resource field name (such as
    "serviceAccount") and returns a related attribute name (such as
    "service_account") to be used with  kubernetes.client.models objects. It is
    impossible to prove a negative but it seems like it is always a question of
    making camelCase to snake_case but by using the provided 'attribute_map' we
    also ensure that the fields actually exist.

    Example of V1PodSpec's attribute_map:
    {
        'active_deadline_seconds': 'activeDeadlineSeconds',
        'affinity': 'affinity',
        'automount_service_account_token': 'automountServiceAccountToken',
        'containers': 'containers',
        'dns_policy': 'dnsPolicy',
        'host_aliases': 'hostAliases',
        'host_ipc': 'hostIPC',
        'host_network': 'hostNetwork',
        'host_pid': 'hostPID',
        'hostname': 'hostname',
        'image_pull_secrets': 'imagePullSecrets',
        'init_containers': 'initContainers',
        'node_name': 'nodeName',
        'node_selector': 'nodeSelector',
        'priority': 'priority',
        'priority_class_name': 'priorityClassName',
        'restart_policy': 'restartPolicy',
        'scheduler_name': 'schedulerName',
        'security_context': 'securityContext',
        'service_account': 'serviceAccount',
        'service_account_name': 'serviceAccountName',
        'subdomain': 'subdomain',
        'termination_grace_period_seconds': 'terminationGracePeriodSeconds',
        'tolerations': 'tolerations',
        'volumes': 'volumes'
    }
    """
    # if we get "service_account", return
    if field_name in model_type.attribute_map:
        return field_name

    # if we get "serviceAccount", then return "service_account"
    for key, value in model_type.attribute_map.items():
        if value == field_name:
            return key
    else:
        raise ValueError(
            "'{}' did not have an attribute matching '{}'".format(
                model_type.__name__, field_name
            )
        )


def host_matching(host: str, wildcard: str) -> bool:
    # user.example.com == user.example.com
    # user.example.com != wrong.example.com
    # user.example.com != example.com
    if not wildcard.startswith("*."):
        return host == wildcard

    host_parts = host.split(".")
    wildcard_parts = wildcard.split(".")

    # user.example.com =~ *.example.com
    # user.example.com !~ *.user.example.com
    # user.example.com !~ *.example
    return host_parts[1:] == wildcard_parts[1:]


# From https://github.com/jupyter-server/jupyter_server/blob/fc0ac3236fdd92778ea765db6e8982212c8389ee/jupyter_server/config_manager.py#L14
def recursive_update(target, new):
    """
    Recursively update one dictionary in-place using another.

    None values will delete their keys.
    """
    for k, v in new.items():
        if isinstance(v, dict):
            if k not in target:
                target[k] = {}
            recursive_update(target[k], v)

        elif v is None:
            target.pop(k, None)

        else:
            target[k] = v


class IgnoreMissing(dict):
    """
    Dictionary subclass for use with format_map

    Returns missing dictionary keys' values as "{key}", so format strings with
    missing values just get rendered as is.

    Stolen from https://docs.python.org/3/library/stdtypes.html#str.format_map
    """

    def __missing__(self, key):
        return f"{{{key}}}"


def recursive_format(format_object, **kwargs):
    """
    Recursively format given object with values provided as keyword arguments.

    If the given object (string, list, set, or dict) has items that do not have
    placeholders for passed in kwargs, no formatting is performed.

    recursive_format("{v}", v=5) -> Returns "5"
    recrusive_format("{a}") -> Returns "{a}" rather than erroring, as is
    the behavior of "format"
    """
    if isinstance(format_object, str):
        return format_object.format_map(IgnoreMissing(kwargs))
    elif isinstance(format_object, list):
        return [recursive_format(i, **kwargs) for i in format_object]
    elif isinstance(format_object, set):
        return {recursive_format(i, **kwargs) for i in format_object}
    elif isinstance(format_object, dict):
        return {
            recursive_format(k, **kwargs): recursive_format(v, **kwargs)
            for k, v in format_object.items()
        }
    else:
        # Everything else just gets returned as is, unformatted
        return format_object
