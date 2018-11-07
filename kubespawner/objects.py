"""
Helper methods for generating k8s API objects.
"""
import json
from urllib.parse import urlparse
import escapism
import re
import string
from kubespawner.utils import get_k8s_model, update_k8s_model

from kubernetes.client.models import (
    V1Pod, V1PodSpec, V1PodSecurityContext,
    V1ObjectMeta,
    V1LocalObjectReference,
    V1Volume, V1VolumeMount,
    V1Container, V1ContainerPort, V1SecurityContext, V1EnvVar, V1ResourceRequirements, V1Lifecycle,
    V1PersistentVolumeClaim, V1PersistentVolumeClaimSpec,
    V1Endpoints, V1EndpointSubset, V1EndpointAddress, V1EndpointPort,
    V1Service, V1ServiceSpec, V1ServicePort,
    V1beta1Ingress, V1beta1IngressSpec, V1beta1IngressRule,
    V1beta1HTTPIngressRuleValue, V1beta1HTTPIngressPath,
    V1beta1IngressBackend,
    V1Toleration,
    V1Affinity,
    V1NodeAffinity, V1NodeSelector, V1NodeSelectorTerm, V1PreferredSchedulingTerm, V1NodeSelectorRequirement,
    V1PodAffinity, V1PodAntiAffinity, V1WeightedPodAffinityTerm, V1PodAffinityTerm,
)

def make_pod(
    name,
    cmd,
    port,
    image,
    image_pull_policy,
    image_pull_secret=None,
    node_selector=None,
    run_as_uid=None,
    run_as_gid=None,
    fs_gid=None,
    supplemental_gids=None,
    run_privileged=False,
    env=None,
    working_dir=None,
    volumes=None,
    volume_mounts=None,
    labels=None,
    annotations=None,
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
    extra_containers=None,
    scheduler_name=None,
    tolerations=None,
    node_affinity_preferred=None,
    node_affinity_required=None,
    pod_affinity_preferred=None,
    pod_affinity_required=None,
    pod_anti_affinity_preferred=None,
    pod_anti_affinity_required=None,
    priority_class_name=None,
    logger=None,
):
    """
    Make a k8s pod specification for running a user notebook.

    Parameters
    ----------
    name:
        Name of pod. Must be unique within the namespace the object is
        going to be created in. Must be a valid DNS label.
    image:
        Image specification - usually a image name and tag in the form
        of image_name:tag. Same thing you would use with docker commandline
        arguments
    image_pull_policy:
        Image pull policy - one of 'Always', 'IfNotPresent' or 'Never'. Decides
        when kubernetes will check for a newer version of image and pull it when
        running a pod.
    image_pull_secret:
        Image pull secret - Default is None -- set to your secret name to pull
        from private docker registry.
    port:
        Port the notebook server is going to be listening on
    cmd:
        The command used to execute the singleuser server.
    node_selector:
        Dictionary Selector to match nodes where to launch the Pods
    run_as_uid:
        The UID used to run single-user pods. The default is to run as the user
        specified in the Dockerfile, if this is set to None.
    run_as_gid:
        The GID used to run single-user pods. The default is to run as the primary
        group of the user specified in the Dockerfile, if this is set to None.
    fs_gid
        The gid that will own any fresh volumes mounted into this pod, if using
        volume types that support this (such as GCE). This should be a group that
        the uid the process is running as should be a member of, so that it can
        read / write to the volumes mounted.
    supplemental_gids:
        A list of GIDs that should be set as additional supplemental groups to
        the user that the container runs as. You may have to set this if you are
        deploying to an environment with RBAC/SCC enforced and pods run with a
        'restricted' SCC which results in the image being run as an assigned
        user ID. The supplemental group IDs would need to include the
        corresponding group ID of the user ID the image normally would run as.
        The image must setup all directories/files any application needs access
        to, as group writable.
    run_privileged:
        Whether the container should be run in privileged mode.
    env:
        Dictionary of environment variables.
    volumes:
        List of dictionaries containing the volumes of various types this pod
        will be using. See k8s documentation about volumes on how to specify
        these
    volume_mounts:
        List of dictionaries mapping paths in the container and the volume(
        specified in volumes) that should be mounted on them. See the k8s
        documentaiton for more details
    working_dir:
        String specifying the working directory for the notebook container
    labels:
        Labels to add to the spawned pod.
    annotations:
        Annotations to add to the spawned pod.
    cpu_limit:
        Float specifying the max number of CPU cores the user's pod is
        allowed to use.
    cpu_guarentee:
        Float specifying the max number of CPU cores the user's pod is
        guaranteed to have access to, by the scheduler.
    mem_limit:
        String specifying the max amount of RAM the user's pod is allowed
        to use. String instead of float/int since common suffixes are allowed
    mem_guarantee:
        String specifying the max amount of RAM the user's pod is guaranteed
        to have access to. String ins loat/int since common suffixes
        are allowed
    lifecycle_hooks:
        Dictionary of lifecycle hooks
    init_containers:
        List of initialization containers belonging to the pod.
    service_account:
        Service account to mount on the pod. None disables mounting
    extra_container_config:
        Extra configuration (e.g. envFrom) for notebook container which is not covered by parameters above.
    extra_pod_config:
        Extra configuration (e.g. tolerations) for pod which is not covered by parameters above.
    extra_containers:
        Extra containers besides notebook container. Used for some housekeeping jobs (e.g. crontab).
    scheduler_name:
        The pod's scheduler explicitly named.
    tolerations:
        Tolerations can allow a pod to schedule or execute on a tainted node. To
        learn more about pod tolerations, see
        https://kubernetes.io/docs/concepts/configuration/taint-and-toleration/.

        Pass this field an array of "Toleration" objects.*
        * https://kubernetes.io/docs/reference/generated/kubernetes-api/v1.10/#nodeselectorterm-v1-core
    node_affinity_preferred:
        Affinities describe where pods prefer or require to be scheduled, they
        may prefer or require a node to have a certain label or be in proximity
        / remoteness to another pod. To learn more visit
        https://kubernetes.io/docs/concepts/configuration/assign-pod-node/

        Pass this field an array of "PreferredSchedulingTerm" objects.*
        * https://kubernetes.io/docs/reference/generated/kubernetes-api/v1.10/#preferredschedulingterm-v1-core
    node_affinity_required:
        Affinities describe where pods prefer or require to be scheduled, they
        may prefer or require a node to have a certain label or be in proximity
        / remoteness to another pod. To learn more visit
        https://kubernetes.io/docs/concepts/configuration/assign-pod-node/

        Pass this field an array of "NodeSelectorTerm" objects.*
        * https://kubernetes.io/docs/reference/generated/kubernetes-api/v1.10/#nodeselectorterm-v1-core
    pod_affinity_preferred:
        Affinities describe where pods prefer or require to be scheduled, they
        may prefer or require a node to have a certain label or be in proximity
        / remoteness to another pod. To learn more visit
        https://kubernetes.io/docs/concepts/configuration/assign-pod-node/

        Pass this field an array of "WeightedPodAffinityTerm" objects.*
        * https://kubernetes.io/docs/reference/generated/kubernetes-api/v1.10/#weightedpodaffinityterm-v1-core
    pod_affinity_required:
        Affinities describe where pods prefer or require to be scheduled, they
        may prefer or require a node to have a certain label or be in proximity
        / remoteness to another pod. To learn more visit
        https://kubernetes.io/docs/concepts/configuration/assign-pod-node/

        Pass this field an array of "PodAffinityTerm" objects.*
        * https://kubernetes.io/docs/reference/generated/kubernetes-api/v1.10/#podaffinityterm-v1-core
    pod_anti_affinity_preferred:
        Affinities describe where pods prefer or require to be scheduled, they
        may prefer or require a node to have a certain label or be in proximity
        / remoteness to another pod. To learn more visit
        https://kubernetes.io/docs/concepts/configuration/assign-pod-node/

        Pass this field an array of "WeightedPodAffinityTerm" objects.*
        * https://kubernetes.io/docs/reference/generated/kubernetes-api/v1.10/#weightedpodaffinityterm-v1-core
    pod_anti_affinity_required:
        Affinities describe where pods prefer or require to be scheduled, they
        may prefer or require a node to have a certain label or be in proximity
        / remoteness to another pod. To learn more visit
        https://kubernetes.io/docs/concepts/configuration/assign-pod-node/

        Pass this field an array of "PodAffinityTerm" objects.*
        * https://kubernetes.io/docs/reference/generated/kubernetes-api/v1.10/#podaffinityterm-v1-core
    priority_class_name:
        The name of the PriorityClass to be assigned the pod. This feature is Beta available in K8s 1.11.
    """

    pod = V1Pod()
    pod.kind = "Pod"
    pod.api_version = "v1"

    pod.metadata = V1ObjectMeta(
        name=name,
        labels=(labels or {}).copy(),
        annotations=(annotations or {}).copy()
    )

    pod.spec = V1PodSpec(containers=[])
    pod.spec.restart_policy = 'OnFailure'

    security_context = V1PodSecurityContext()
    if fs_gid is not None:
        security_context.fs_group = int(fs_gid)
    if supplemental_gids is not None and supplemental_gids:
        security_context.supplemental_groups = [int(gid) for gid in supplemental_gids]
    if run_as_uid is not None:
        security_context.run_as_user = int(run_as_uid)
    if run_as_gid is not None:
        security_context.run_as_group = int(run_as_gid)
    pod.spec.security_context = security_context

    if image_pull_secret is not None:
        pod.spec.image_pull_secrets = []
        image_secret = V1LocalObjectReference()
        image_secret.name = image_pull_secret
        pod.spec.image_pull_secrets.append(image_secret)

    if node_selector:
        pod.spec.node_selector = node_selector

    if lifecycle_hooks:
        lifecycle_hooks = get_k8s_model(V1Lifecycle, lifecycle_hooks)
    notebook_container = V1Container(
        name='notebook',
        image=image,
        working_dir=working_dir,
        ports=[V1ContainerPort(name='notebook-port', container_port=port)],
        env=[V1EnvVar(k, v) for k, v in (env or {}).items()],
        args=cmd,
        image_pull_policy=image_pull_policy,
        lifecycle=lifecycle_hooks,
        resources=V1ResourceRequirements(),
        volume_mounts=[get_k8s_model(V1VolumeMount, obj) for obj in (volume_mounts or [])],
    )

    if service_account is None:
        # This makes sure that we don't accidentally give access to the whole
        # kubernetes API to the users in the spawned pods.
        pod.spec.automount_service_account_token = False
    else:
        pod.spec.service_account_name = service_account

    if run_privileged:
        notebook_container.security_context = V1SecurityContext(privileged=True)

    notebook_container.resources.requests = {}
    if cpu_guarantee:
        notebook_container.resources.requests['cpu'] = cpu_guarantee
    if mem_guarantee:
        notebook_container.resources.requests['memory'] = mem_guarantee
    if extra_resource_guarantees:
        notebook_container.resources.requests.update(extra_resource_guarantees)

    notebook_container.resources.limits = {}
    if cpu_limit:
        notebook_container.resources.limits['cpu'] = cpu_limit
    if mem_limit:
        notebook_container.resources.limits['memory'] = mem_limit
    if extra_resource_limits:
        notebook_container.resources.limits.update(extra_resource_limits)

    if extra_container_config:
        notebook_container = update_k8s_model(
            target=notebook_container,
            changes=extra_container_config,
            logger=logger,
            target_name="notebook_container",
            changes_name="extra_container_config",
        )

    pod.spec.containers.append(notebook_container)

    if extra_containers:
        pod.spec.containers.extend([get_k8s_model(V1Container, obj) for obj in extra_containers])
    if tolerations:
        pod.spec.tolerations = [get_k8s_model(V1Toleration, obj) for obj in tolerations]
    if init_containers:
        pod.spec.init_containers = [get_k8s_model(V1Container, obj) for obj in init_containers]
    if volumes:
        pod.spec.volumes = [get_k8s_model(V1Volume, obj) for obj in volumes]
    else:
        # Keep behaving exactly like before by not cleaning up generated pod
        # spec by setting the volumes field even though it is an empty list.
        pod.spec.volumes = []
    if scheduler_name:
        pod.spec.scheduler_name = scheduler_name

    node_affinity = None
    if node_affinity_preferred or node_affinity_required:
        node_selector = None
        if node_affinity_required:
            node_selector = V1NodeSelector(
                node_selector_terms=[get_k8s_model(V1NodeSelectorTerm, obj) for obj in node_affinity_required],
            )

        preferred_scheduling_terms = None
        if node_affinity_preferred:
            preferred_scheduling_terms = [get_k8s_model(V1PreferredSchedulingTerm, obj) for obj in node_affinity_preferred]

        node_affinity = V1NodeAffinity(
            preferred_during_scheduling_ignored_during_execution=preferred_scheduling_terms,
            required_during_scheduling_ignored_during_execution=node_selector,
        )

    pod_affinity = None
    if pod_affinity_preferred or pod_affinity_required:
        weighted_pod_affinity_terms = None
        if pod_affinity_preferred:
            weighted_pod_affinity_terms = [get_k8s_model(V1WeightedPodAffinityTerm, obj) for obj in pod_affinity_preferred]

        pod_affinity_terms = None
        if pod_affinity_required:
            pod_affinity_terms = [get_k8s_model(V1PodAffinityTerm, obj) for obj in pod_affinity_required]

        pod_affinity = V1PodAffinity(
            preferred_during_scheduling_ignored_during_execution=weighted_pod_affinity_terms,
            required_during_scheduling_ignored_during_execution=pod_affinity_terms,
        )

    pod_anti_affinity = None
    if pod_anti_affinity_preferred or pod_anti_affinity_required:
        weighted_pod_affinity_terms = None
        if pod_anti_affinity_preferred:
            weighted_pod_affinity_terms = [get_k8s_model(V1WeightedPodAffinityTerm, obj) for obj in pod_anti_affinity_preferred]

        pod_affinity_terms = None
        if pod_anti_affinity_required:
            pod_affinity_terms = [get_k8s_model(V1PodAffinityTerm, obj) for obj in pod_anti_affinity_required]

        pod_anti_affinity = V1PodAffinity(
            preferred_during_scheduling_ignored_during_execution=weighted_pod_affinity_terms,
            required_during_scheduling_ignored_during_execution=pod_affinity_terms,
        )

    affinity = None
    if (node_affinity or pod_affinity or pod_anti_affinity):
        affinity = V1Affinity(
            node_affinity=node_affinity,
            pod_affinity=pod_affinity,
            pod_anti_affinity=pod_anti_affinity,
        )

    if affinity:
        pod.spec.affinity = affinity

    if priority_class_name:
        pod.spec.priority_class_name = priority_class_name

    if extra_pod_config:
        pod.spec = update_k8s_model(
            target=pod.spec,
            changes=extra_pod_config,
            logger=logger,
            target_name="pod.spec",
            changes_name="extra_pod_config",
        )

    return pod


def make_pvc(
    name,
    storage_class,
    access_modes,
    storage,
    labels=None,
    annotations=None,
):
    """
    Make a k8s pvc specification for running a user notebook.

    Parameters
    ----------
    name:
        Name of persistent volume claim. Must be unique within the namespace the object is
        going to be created in. Must be a valid DNS label.
    storage_class:
        String of the name of the k8s Storage Class to use.
    access_modes:
        A list of specifying what access mode the pod should have towards the pvc
    storage:
        The ammount of storage needed for the pvc

    """
    pvc = V1PersistentVolumeClaim()
    pvc.kind = "PersistentVolumeClaim"
    pvc.api_version = "v1"
    pvc.metadata = V1ObjectMeta()
    pvc.metadata.name = name
    pvc.metadata.annotations = (annotations or {}).copy()
    pvc.metadata.labels = (labels or {}).copy()
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

    target_is_ip = re.match('^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', target_ip) is not None

    # Make endpoint object
    if target_is_ip:
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
    else:
        endpoint = None

    # Make service object
    if target_is_ip:
        service = V1Service(
            kind='Service',
            metadata=meta,
            spec=V1ServiceSpec(
                type='ClusterIP',
                external_name='',
                ports=[V1ServicePort(port=target_port, target_port=target_port)]
            )
        )
    else:
        service = V1Service(
            kind='Service',
            metadata=meta,
            spec=V1ServiceSpec(
                type='ExternalName',
                external_name=target_ip,
                cluster_ip='',
                ports=[V1ServicePort(port=target_port, target_port=target_port)],
            ),
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
