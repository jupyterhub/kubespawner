"""
Helper methods for generating k8s API objects.
"""

from kubernetes.client.models.v1_pod import V1Pod
from kubernetes.client.models.v1_pod_spec import V1PodSpec
from kubernetes.client.models.v1_object_meta import V1ObjectMeta
from kubernetes.client.models.v1_pod_security_context import V1PodSecurityContext
from kubernetes.client.models.v1_local_object_reference import V1LocalObjectReference
from kubernetes.client.models.v1_volume import V1Volume
from kubernetes.client.models.v1_volume_mount import V1VolumeMount

from kubernetes.client.models.v1_container import V1Container
from kubernetes.client.models.v1_security_context import V1SecurityContext
from kubernetes.client.models.v1_container_port import V1ContainerPort
from kubernetes.client.models.v1_env_var import V1EnvVar
from kubernetes.client.models.v1_resource_requirements import V1ResourceRequirements

from kubernetes.client.models.v1_persistent_volume_claim import V1PersistentVolumeClaim
from kubernetes.client.models.v1_persistent_volume_claim_spec import V1PersistentVolumeClaimSpec


def make_pod(
    name,
    cmd,
    port,
    image_spec,
    image_pull_policy,
    image_pull_secret=None,
    node_selector=None,
    run_as_uid=None,
    fs_gid=None,
    run_privileged=False,
    env={},
    working_dir=None,
    volumes=[],
    volume_mounts=[],
    labels={},
    annotations={},
    cpu_limit=None,
    cpu_guarantee=None,
    mem_limit=None,
    mem_guarantee=None,
    extra_resource_limits=None,
    extra_resource_guarantees=None,
    lifecycle_hooks=None,
    init_containers=None,
    service_account=None,
    extra_container_config=None,
    extra_pod_config=None,
    extra_containers=None
):
    """
    Make a k8s pod specification for running a user notebook.

    Parameters:
      - name:
        Name of pod. Must be unique within the namespace the object is
        going to be created in. Must be a valid DNS label.
      - image_spec:
        Image specification - usually a image name and tag in the form
        of image_name:tag. Same thing you would use with docker commandline
        arguments
      - image_pull_policy:
        Image pull policy - one of 'Always', 'IfNotPresent' or 'Never'. Decides
        when kubernetes will check for a newer version of image and pull it when
        running a pod.
      - image_pull_secret:
        Image pull secret - Default is None -- set to your secret name to pull
        from private docker registry.
      - port:
        Port the notebook server is going to be listening on
      - cmd:
        The command used to execute the singleuser server.
      - node_selector:
        Dictionary Selector to match nodes where to launch the Pods
      - run_as_uid:
        The UID used to run single-user pods. The default is to run as the user
        specified in the Dockerfile, if this is set to None.
      - fs_gid
        The gid that will own any fresh volumes mounted into this pod, if using
        volume types that support this (such as GCE). This should be a group that
        the uid the process is running as should be a member of, so that it can
        read / write to the volumes mounted.
      - run_privileged:
        Whether the container should be run in privileged mode.
      - env:
        Dictionary of environment variables.
      - volumes:
        List of dictionaries containing the volumes of various types this pod
        will be using. See k8s documentation about volumes on how to specify
        these
      - volume_mounts:
        List of dictionaries mapping paths in the container and the volume(
        specified in volumes) that should be mounted on them. See the k8s
        documentaiton for more details
      - working_dir:
        String specifying the working directory for the notebook container
      - labels:
        Labels to add to the spawned pod.
      - annotations:
        Annotations to add to the spawned pod.
      - cpu_limit:
        Float specifying the max number of CPU cores the user's pod is
        allowed to use.
      - cpu_guarentee:
        Float specifying the max number of CPU cores the user's pod is
        guaranteed to have access to, by the scheduler.
      - mem_limit:
        String specifying the max amount of RAM the user's pod is allowed
        to use. String instead of float/int since common suffixes are allowed
      - mem_guarantee:
        String specifying the max amount of RAM the user's pod is guaranteed
        to have access to. String ins loat/int since common suffixes
        are allowed
      - lifecycle_hooks:
        Dictionary of lifecycle hooks
      - init_containers:
        List of initialization containers belonging to the pod.
      - service_account:
        Service account to mount on the pod. None disables mounting
      - extra_container_config:
        Extra configuration (e.g. envFrom) for notebook container which is not covered by parameters above.
      - extra_pod_config:
        Extra configuration (e.g. tolerations) for pod which is not covered by parameters above.
      - extra_containers:
        Extra containers besides notebook container. Used for some housekeeping jobs (e.g. crontab).
    """

    pod = V1Pod()
    pod.kind = "Pod"
    pod.api_version = "v1"

    pod.metadata = V1ObjectMeta()
    pod.metadata.name = name
    pod.metadata.labels = labels.copy()
    if annotations:
        pod.metadata.annotations = annotations.copy()

    pod.spec = V1PodSpec()

    security_context = V1PodSecurityContext()
    if fs_gid is not None:
        security_context.fs_group = int(fs_gid)
    if run_as_uid is not None:
        security_context.run_as_user = int(run_as_uid)
    pod.spec.security_context = security_context

    if image_pull_secret is not None:
        pod.spec.image_pull_secrets = []
        image_secret = V1LocalObjectReference()
        image_secret.name = image_pull_secret
        pod.spec.image_pull_secrets.append(image_secret)

    if node_selector:
        pod.spec.node_selector = node_selector

    pod.spec.containers = []
    notebook_container = V1Container()
    notebook_container.name = "notebook"
    notebook_container.image = image_spec
    notebook_container.working_dir = working_dir
    notebook_container.ports = []
    port_ = V1ContainerPort()
    port_.name = "notebook-port"
    port_.container_port = port
    notebook_container.ports.append(port_)
    notebook_container.env = [V1EnvVar(k, v) for k, v in env.items()]
    notebook_container.args = cmd
    notebook_container.image_pull_policy = image_pull_policy
    notebook_container.lifecycle = lifecycle_hooks
    notebook_container.resources = V1ResourceRequirements()
    
    if service_account is None:
        # Add a hack to ensure that no service accounts are mounted in spawned pods
        # This makes sure that we don"t accidentally give access to the whole
        # kubernetes API to the users in the spawned pods.
        # Note: We don't simply use `automountServiceAccountToken` here since we wanna be compatible
        # with older kubernetes versions too for now.
        hack_volume = V1Volume()
        hack_volume.name =  "no-api-access-please"
        hack_volume.empty_dir = {}
        hack_volumes = [hack_volume]

        hack_volume_mount = V1VolumeMount()
        hack_volume_mount.name = "no-api-access-please"
        hack_volume_mount.mount_path = "/var/run/secrets/kubernetes.io/serviceaccount"
        hack_volume_mount.read_only = True
        hack_volume_mounts = [hack_volume_mount]
    else:
        hack_volumes = []
        hack_volume_mounts = []

        pod.service_account_name = service_account

    if run_privileged:
        container_security_context = V1SecurityContext()
        container_security_context.privileged = True
        notebook_container.security_context = container_security_context

    notebook_container.resources.requests = {}

    if cpu_guarantee:
        notebook_container.resources.requests['cpu'] = cpu_guarantee
    if mem_guarantee:
        notebook_container.resources.requests['memory'] = mem_guarantee
    if extra_resource_guarantees:
        for k in extra_resource_guarantees:
            notebook_container.resources.requests[k] = extra_resource_guarantees[k]

    notebook_container.resources.limits = {}
    if cpu_limit:
        notebook_container.resources.limits['cpu'] = cpu_limit
    if mem_limit:
        notebook_container.resources.limits['memory'] = mem_limit
    if extra_resource_limits:
        for k in extra_resource_limits:
            notebook_container.resources.limits[k] = extra_resource_limits[k]

    notebook_container.volume_mounts = volume_mounts + hack_volume_mounts
    pod.spec.containers.append(notebook_container)

    if extra_container_config:
        for key, value in extra_container_config.items():
            setattr(notebook_container, _map_attribute(notebook_container.attribute_map, key), value)
    if extra_pod_config:
        for key, value in extra_pod_config.items():
            setattr(pod.spec, _map_attribute(pod.spec.attribute_map, key), value)
    if extra_containers:
        pod.spec.containers.extend(extra_containers)

    pod.spec.init_containers = init_containers
    pod.spec.volumes = volumes + hack_volumes
    return pod


def _map_attribute(attribute_map, attribute):
    if attribute in attribute_map:
        return attribute

    for key, value in attribute_map.items():
        if value == attribute:
            return key
    else:
        raise ValueError('Attribute must be one of {}'.format(attribute_map.values()))


def make_pvc(
    name,
    storage_class,
    access_modes,
    storage,
    labels
    ):
    """
    Make a k8s pvc specification for running a user notebook.

    Parameters:
      - name:
        Name of persistent volume claim. Must be unique within the namespace the object is
        going to be created in. Must be a valid DNS label.
      - storage_class
        String of the name of the k8s Storage Class to use.
      - access_modes:
        A list of specifying what access mode the pod should have towards the pvc
      - storage
        The ammount of storage needed for the pvc

    """
    pvc = V1PersistentVolumeClaim()
    pvc.kind = "PersistentVolumeClaim"
    pvc.api_version = "v1"
    pvc.metadata = V1ObjectMeta()
    pvc.metadata.name = name
    pvc.metadata.annotations = {}
    if storage_class:
        pvc.metadata.annotations.update({"volume.beta.kubernetes.io/storage-class": storage_class})
    pvc.metadata.labels = {}
    pvc.metadata.labels.update(labels)
    pvc.spec = V1PersistentVolumeClaimSpec()
    pvc.spec.access_modes = access_modes
    pvc.spec.resources = V1ResourceRequirements()
    pvc.spec.resources.requests = {"storage": storage}

    return pvc
