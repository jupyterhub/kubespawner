"""
Misc. general utility functions, not tied to Kubespawner directly
"""
import hashlib
import copy

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
        prefix=slug[:limit - hash_length - 1],
        hash=slug_hash[:hash_length],
    ).lower()


def update_k8s_model(target, source, logger=None, origin=None):
    """
    Takes a model instance such as V1PodSpec() and updates it with another
    model representation. The origin parameter could be "extra_pod_config" for
    example.
    """
    model = type(target)
    if not hasattr(target, 'attribute_map'):
        raise AttributeError("Attribute 'target' ({}) must be an object (such as 'V1PodSpec') with an attribute 'attribute_map'.".format(model.__name__))
    if not isinstance(source, model) and not isinstance(source, dict):
        raise AttributeError("Attribute 'source' ({}) must be an object of the same type as 'target' ({}) or a 'dict'.".format(type(source).__name__, model.__name__))

    source_dict = _get_k8s_model_dict(model, source)
    for key, value in source_dict.items():
        if key not in target.attribute_map:
            raise ValueError("The attribute 'source' ({}) contained '{}' not modeled by '{}'.".format(type(source).__name__, key, model.__name__))
        if getattr(target, key):
            if logger and origin:
                logger.warning("Overriding KubeSpawner.{}'s value '{getattr(target,key)}' with '{}'.".format(origin, value))
        setattr(target, key, value)

    return target

def get_k8s_model(model, model_dict):
    """
    Returns a model object from an model instance or represantative dictionary.
    """
    model_dict = copy.deepcopy(model_dict)

    if isinstance(model_dict, model):
        return model_dict
    elif isinstance(model_dict, dict):
        _map_dict_keys_to_model_attributes(model, model_dict)
        return model(**model_dict)
    else:
        raise AttributeError("Expected object of type 'dict' (or '{}') but got '{}'.".format(model.__type__.__name__, model_dict.__type__.__name__))

def _get_k8s_model_dict(model, obj):
    """
    Returns a model of dictionary kind
    """
    obj = copy.deepcopy(obj)

    if isinstance(obj, model):
        return obj.to_dict()
    elif isinstance(obj, dict):
        return _map_dict_keys_to_model_attributes(model, obj)
    else:
        raise AttributeError("Expected object of type '{}' (or 'dict') but got '{}'.".format(model.__type__.__name__, obj.__type__.__name__))

def _map_dict_keys_to_model_attributes(model, model_dict):
    """
    Maps a dict's keys to the provided models attributes using its attribute_map
    attribute. This is (always?) the same as converting camelCase to snake_case.
    Note that the function will not influence nested object's keys.
    """

    for key in list(model_dict.keys()):
        model_dict[_get_k8s_model_attribute(model, key)] = model_dict.pop(key)

    return model_dict

def _get_k8s_model_attribute(model, field_name):
    """
    Takes an kubernetes resource field name such as "serviceAccount" and returns
    its associated attribute name "service_account" used by the provided
    kubernetes.client.models object representing the resource.

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
    if field_name in model.attribute_map:
        return field_name

    # if we get "serviceAccount", then return "service_account"
    for key, value in model.attribute_map.items():
        if value == field_name:
            return key
    else:
        raise ValueError("'{}' does not model '{}'".format(model.__name__, field_name))
