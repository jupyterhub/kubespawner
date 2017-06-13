"""
Helper methods for generating k8s API objects.
"""

from kubernetes.client import ApiClient
from kubernetes.client.models.v1_pod import V1Pod
from kubernetes.client.models.v1_pod_spec import V1PodSpec
from kubernetes.client.models.v1_object_meta import V1ObjectMeta
from kubernetes.client.models.v1_pod_security_context import V1PodSecurityContext
from kubernetes.client.models.v1_local_object_reference import V1LocalObjectReference

from kubernetes.client.models.v1_container import V1Container
from kubernetes.client.models.v1_container_port import V1ContainerPort
from kubernetes.client.models.v1_env_var import V1EnvVar
from kubernetes.client.models.v1_resource_requirements import V1ResourceRequirements

from kubernetes.client.models.v1_persistent_volume_claim import V1PersistentVolumeClaim
from kubernetes.client.models.v1_persistent_volume_claim_spec import V1PersistentVolumeClaimSpec


def make_pod_spec(
    name,
    image_spec,
    image_pull_policy,
    image_pull_secret,
    port,
    cmd,
    run_as_uid,
    fs_gid,
    env,
    working_dir,
    volumes,
    volume_mounts,
    labels,
    cpu_limit,
    cpu_guarantee,
    mem_limit,
    mem_guarantee,
    lifecycle_hooks,
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
      - run_as_uid:
        The UID used to run single-user pods. The default is to run as the user
        specified in the Dockerfile, if this is set to None.
      - fs_gid
        The gid that will own any fresh volumes mounted into this pod, if using
        volume types that support this (such as GCE). This should be a group that
        the uid the process is running as should be a member of, so that it can
        read / write to the volumes mounted.
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
      - cpu_limit:
        Float specifying the max number of CPU cores the user's pod is
        allowed to use.
      - cpu_guarantee:
        Float specifying the max number of CPU cores the user's pod is
        guaranteed to have access to, by the scheduler.
      - mem_limit:
        String specifying the max amount of RAM the user's pod is allowed
        to use. String instead of float/int since common suffixes are allowed
      - mem_guarantee:
        String specifying the max amount of RAM the user's pod is guaranteed
        to have access to. String instead of float/int since common suffixes
        are allowed
      - lifecycle_hooks:
        Dictionary of lifecycle hooks
    """
    api_client = ApiClient()

    pod = V1Pod()
    pod.kind = "Pod"
    pod.api_version = "v1"

    pod.metadata = V1ObjectMeta()
    pod.metadata.name = name
    pod.metadata.labels = labels.copy()

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

    notebook_container.resources.requests = {}

    if cpu_guarantee:
        notebook_container.resources.requests['cpu'] = cpu_guarantee
    if mem_guarantee:
        notebook_container.resources.requests['memory'] = mem_guarantee

    notebook_container.resources.limits = {}
    if cpu_limit:
        notebook_container.resources.limits['cpu'] = cpu_limit
        if not cpu_guarantee:
            notebook_container.resources.requests['cpu'] = 0.0
    if mem_limit:
        notebook_container.resources.limits['memory'] = mem_limit
        if not mem_guarantee:
            notebook_container.resources.requests['memory'] = 0
    notebook_container.volume_mounts = volume_mounts
    pod.spec.containers.append(notebook_container)

    pod.spec.volumes = volumes
    return api_client.sanitize_for_serialization(pod)


def make_pvc_spec(
        name,
        storage_class,
        access_modes,
        storage):
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
    api_client = ApiClient()

    pvc = V1PersistentVolumeClaim()
    pvc.kind = "PersistentVolumeClaim"
    pvc.api_version = "v1"
    pvc.metadata = V1ObjectMeta()
    pvc.metadata.name = name
    pvc.metadata.annotations = {}
    if storage_class:
        pvc.metadata.annotations.update(
            {"volume.beta.kubernetes.io/storage-class": storage_class})
    pvc.spec = V1PersistentVolumeClaimSpec()
    pvc.spec.access_modes = access_modes
    pvc.spec.resources = V1ResourceRequirements()
    pvc.spec.resources.requests = {"storage": storage}

    return api_client.sanitize_for_serialization(pvc)
