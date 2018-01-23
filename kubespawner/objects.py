"""
Helper methods for generating k8s API objects.
"""
import json
from urllib.parse import urlparse
import escapism
import string

from kubernetes.client.models import (
    V1Pod, V1PodSpec, V1PodSecurityContext,
    V1ObjectMeta,
    V1LocalObjectReference,
    V1Volume, V1VolumeMount,
    V1Container, V1ContainerPort, V1SecurityContext, V1EnvVar, V1ResourceRequirements,
    V1PersistentVolumeClaim, V1PersistentVolumeClaimSpec,
    V1Endpoints, V1EndpointSubset, V1EndpointAddress, V1EndpointPort,
    V1Service, V1ServiceSpec, V1ServicePort,
    V1beta1Ingress, V1beta1IngressSpec, V1beta1IngressRule,
    V1beta1HTTPIngressRuleValue, V1beta1HTTPIngressPath,
    V1beta1IngressBackend
)

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

    pod.metadata = V1ObjectMeta(
        name=name,
        labels=labels.copy(),
        annotations=annotations.copy()
    )

    pod.spec = V1PodSpec(containers=[])

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

    notebook_container = V1Container(
        name='notebook',
        image=image_spec,
        working_dir=working_dir,
        ports=[V1ContainerPort(name='notebook-port', container_port=port)],
        env=[V1EnvVar(k, v) for k, v in env.items()],
        args=cmd,
        image_pull_policy=image_pull_policy,
        lifecycle=lifecycle_hooks,
        resources=V1ResourceRequirements()
    )

    if service_account is None:
        # Add a hack to ensure that no service accounts are mounted in spawned pods
        # This makes sure that we don"t accidentally give access to the whole
        # kubernetes API to the users in the spawned pods.
        # Note: We don't simply use `automountServiceAccountToken` here since we wanna be compatible
        # with older kubernetes versions too for now.
        hack_volume = V1Volume(name='no-api-access-please', empty_dir={})
        hack_volumes = [hack_volume]

        hack_volume_mount = V1VolumeMount(
            name='no-api-access-please',
            mount_path="/var/run/secrets/kubernetes.io/serviceaccount",
            read_only=True
        )
        hack_volume_mounts = [hack_volume_mount]

        # Non-hacky way of not mounting service accounts
        pod.spec.automount_service_account_token = False
    else:
        hack_volumes = []
        hack_volume_mounts = []

        pod.spec.service_account_name = service_account

    if run_privileged:
        notebook_container.security_context = V1SecurityContext(
            privileged=True
        )

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
    labels,
    annotations={}
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
    pvc.metadata.annotations = annotations
    pvc.metadata.labels = {}
    pvc.metadata.labels.update(labels)
    pvc.spec = V1PersistentVolumeClaimSpec()
    pvc.spec.access_modes = access_modes
    pvc.spec.resources = V1ResourceRequirements()
    pvc.spec.resources.requests = {"storage": storage}

    if storage_class:
        pvc.metadata.annotations.update({"volume.beta.kubernetes.io/storage-class": storage_class})
        pvc.spec.storage_class_name = storage_class

    return pvc

def make_ingress(
        name,
        routespec,
        target,
        data
):
    """
    Returns an ingress, service, endpoint object that'll work for this service
    """
    meta = V1ObjectMeta(
        name=name,
        annotations={
            'hub.jupyter.org/proxy-data': json.dumps(data),
            'hub.jupyter.org/proxy-routespec': routespec,
            'hub.jupyter.org/proxy-target': target
        },
        labels={
            'heritage': 'jupyterhub',
            'component': 'singleuser-server',
            'hub.jupyter.org/proxy-route': 'true'
        }
    )

    if routespec.startswith('/'):
        host = None
        path = routespec
    else:
        host, path = routespec.split('/', 1)

    target_parts = urlparse(target)

    target_ip = target_parts.hostname
    target_port = target_parts.port

    # Make endpoint object
    endpoint = V1Endpoints(
        kind='Endpoints',
        metadata=meta,
        subsets=[
            V1EndpointSubset(
                addresses=[V1EndpointAddress(ip=target_ip)],
                ports=[V1EndpointPort(port=target_port)]
            )
        ]
    )

    # Make service object
    service = V1Service(
        kind='Service',
        metadata=meta,
        spec=V1ServiceSpec(
            ports=[V1ServicePort(port=target_port, target_port=target_port)]
        )
    )

    # Make Ingress object
    ingress = V1beta1Ingress(
        kind='Ingress',
        metadata=meta,
        spec=V1beta1IngressSpec(
            rules=[V1beta1IngressRule(
                host=host,
                http=V1beta1HTTPIngressRuleValue(
                    paths=[
                        V1beta1HTTPIngressPath(
                            path=path,
                            backend=V1beta1IngressBackend(
                                service_name=name,
                                service_port=target_port
                            )
                        )
                    ]
                )
            )]
        )
    )

    return endpoint, service, ingress
