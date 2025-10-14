"""
Helper methods for generating k8s API objects.
"""

import base64
import ipaddress
import json
import operator
import re
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

from kubernetes_asyncio.client.models import (
    V1Affinity,
    V1Container,
    V1ContainerPort,
    V1EndpointAddress,
    V1Endpoints,
    V1EndpointSubset,
    V1EnvVar,
    V1HTTPIngressPath,
    V1HTTPIngressRuleValue,
    V1Ingress,
    V1IngressBackend,
    V1IngressRule,
    V1IngressServiceBackend,
    V1IngressSpec,
    V1IngressTLS,
    V1Lifecycle,
    V1LocalObjectReference,
    V1Namespace,
    V1NodeAffinity,
    V1NodeSelector,
    V1NodeSelectorTerm,
    V1ObjectMeta,
    V1OwnerReference,
    V1PersistentVolumeClaim,
    V1PersistentVolumeClaimSpec,
    V1Pod,
    V1PodAffinity,
    V1PodAffinityTerm,
    V1PodSpec,
    V1PreferredSchedulingTerm,
    V1ResourceRequirements,
    V1Secret,
    V1Service,
    V1ServiceBackendPort,
    V1ServicePort,
    V1ServiceSpec,
    V1Toleration,
    V1Volume,
    V1VolumeMount,
    V1WeightedPodAffinityTerm,
)

# This is a hack we use for broader compatibility. The k8s Python clients
# libraries generated from an OpenAPI schema for k8s 1.21+ will name
# V1EndpointPort as CoreV1EndpointPort.
try:
    from kubernetes_asyncio.client.models import CoreV1EndpointPort
except ImportError:
    from kubernetes_asyncio.client.models import V1EndpointPort as CoreV1EndpointPort

from .utils import get_k8s_model, host_matching, update_k8s_model

# Matches Kubernetes DNS names template for services
# https://kubernetes.io/docs/concepts/services-networking/dns-pod-service/#namespaces-of-services:
# * service.namespace.svc.cluster.local
# * service.namespace.svc.cluster
# * service.namespace.svc
# * service.namespace
# * service
# User by `KubeIngressProxy.reuse_existing_services=True`
SERVICE_DNS_PATTERN = re.compile(
    r"(?P<service>[^.]+)\.?(?P<namespace>[^.]+)?(?P<rest>\.svc(\.cluster(\.local)?)?)?"
)


def make_pod(
    name,
    cmd,
    port,
    image,
    image_pull_policy=None,
    image_pull_secrets=None,
    node_selector=None,
    uid=None,
    gid=None,
    fs_gid=None,
    supplemental_gids=None,
    privileged=False,
    allow_privilege_escalation=False,
    container_security_context=None,
    pod_security_context=None,
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
    automount_service_account_token=None,
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
    ssl_secret_name=None,
    ssl_secret_mount_path=None,
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
        Image pull policy - one of None, 'Always', 'IfNotPresent' or 'Never'. Decides
        when kubernetes will check for a newer version of image and pull it when
        running a pod. If set to None, it will be omitted from the spec.

    image_pull_secrets:
        Image pull secrets - a list of references to Kubernetes Secret resources
        with credentials to pull images from image registries. This list can
        either have strings in it or objects with the string value nested under
        a name field.

    port:
        Port the notebook server is going to be listening on

    cmd:
        The command used to execute the singleuser server.

    node_selector:
        Dictionary Selector to match nodes where to launch the Pods

    uid:
        The UID used to run single-user pods. The default is to run as the user
        specified in the Dockerfile, if this is set to None.

    gid:
        The GID used to run single-user pods. The default is to run as the primary
        group of the user specified in the Dockerfile, if this is set to None.
        Setting this parameter requires that *feature-gate* **RunAsGroup** be enabled,
        otherwise the effective GID of the pod will be 0 (root).  In addition, not
        setting `gid` once feature-gate RunAsGroup is enabled will also
        result in an effective GID of 0 (root).

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

    privileged:
        Whether the container should be run in privileged mode.

    allow_privilege_escalation:
        Controls whether a process can gain more privileges than its parent process.
        Functionally, determines if setuid binaries (like sudo) work.

    container_security_context:
        A kubernetes securityContext to apply to the container.

    pod_security_context:
        A kubernetes securityContext to apply to the pod.

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

    cpu_guarantee:
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
        Pass this field an array of "Toleration" objects.

          * https://kubernetes.io/docs/reference/generated/kubernetes-api/v1.28/#toleration-v1-core

    node_affinity_preferred:
        Affinities describe where pods prefer or require to be scheduled, they
        may prefer or require a node to have a certain label or be in proximity
        / remoteness to another pod. To learn more visit
        https://kubernetes.io/docs/concepts/configuration/assign-pod-node/

        Pass this field an array of "PreferredSchedulingTerm" objects.

          * https://kubernetes.io/docs/reference/generated/kubernetes-api/v1.28#preferredschedulingterm-v1-core

    node_affinity_required:
        Affinities describe where pods prefer or require to be scheduled, they
        may prefer or require a node to have a certain label or be in proximity
        / remoteness to another pod. To learn more visit
        https://kubernetes.io/docs/concepts/configuration/assign-pod-node/

        Pass this field an array of "NodeSelectorTerm" objects.

          * https://kubernetes.io/docs/reference/generated/kubernetes-api/v1.28/#nodeselectorterm-v1-core

    pod_affinity_preferred:
        Affinities describe where pods prefer or require to be scheduled, they
        may prefer or require a node to have a certain label or be in proximity
        / remoteness to another pod. To learn more visit
        https://kubernetes.io/docs/concepts/configuration/assign-pod-node/

        Pass this field an array of "WeightedPodAffinityTerm" objects.

          * https://kubernetes.io/docs/reference/generated/kubernetes-api/v1.28/#weightedpodaffinityterm-v1-core

    pod_affinity_required:
        Affinities describe where pods prefer or require to be scheduled, they
        may prefer or require a node to have a certain label or be in proximity
        / remoteness to another pod. To learn more visit
        https://kubernetes.io/docs/concepts/configuration/assign-pod-node/

        Pass this field an array of "PodAffinityTerm" objects.

          * https://kubernetes.io/docs/reference/generated/kubernetes-api/v1.28/#podaffinityterm-v1-core

    pod_anti_affinity_preferred:
        Affinities describe where pods prefer or require to be scheduled, they
        may prefer or require a node to have a certain label or be in proximity
        / remoteness to another pod. To learn more visit
        https://kubernetes.io/docs/concepts/configuration/assign-pod-node/

        Pass this field an array of "WeightedPodAffinityTerm" objects.

          * https://kubernetes.io/docs/reference/generated/kubernetes-api/v1.28/#weightedpodaffinityterm-v1-core

    pod_anti_affinity_required:
        Affinities describe where pods prefer or require to be scheduled, they
        may prefer or require a node to have a certain label or be in proximity
        / remoteness to another pod. To learn more visit
        https://kubernetes.io/docs/concepts/configuration/assign-pod-node/

        Pass this field an array of "PodAffinityTerm" objects.
          * https://kubernetes.io/docs/reference/generated/kubernetes-api/v1.28/#podaffinityterm-v1-core

    priority_class_name:
        The name of the PriorityClass to be assigned the pod. This feature is Beta available in K8s 1.11 and GA in 1.14.

    ssl_secret_name:
        Specifies the name of the ssl secret

    ssl_secret_mount_path:
        Specifies the name of the ssl secret mount path for the pod
    """

    pod = V1Pod()
    pod.kind = "Pod"
    pod.api_version = "v1"

    pod.metadata = V1ObjectMeta(
        name=name,
        labels=(labels or {}).copy(),
        annotations=(annotations or {}).copy(),
    )

    pod.spec = V1PodSpec(containers=[])
    pod.spec.restart_policy = 'OnFailure'

    if image_pull_secrets is not None:
        # image_pull_secrets as received by the make_pod function should always
        # be a list, but it is allowed to have "a-string" elements or {"name":
        # "a-string"} elements.
        pod.spec.image_pull_secrets = [
            (
                V1LocalObjectReference(name=secret_ref)
                if type(secret_ref) == str
                else get_k8s_model(V1LocalObjectReference, secret_ref)
            )
            for secret_ref in image_pull_secrets
        ]

    if ssl_secret_name and ssl_secret_mount_path:
        if not volumes:
            volumes = []
        volumes.append(
            {
                'name': 'jupyterhub-internal-certs',
                'secret': {'secretName': ssl_secret_name, 'defaultMode': 511},
            }
        )

        env['JUPYTERHUB_SSL_KEYFILE'] = ssl_secret_mount_path + "ssl.key"
        env['JUPYTERHUB_SSL_CERTFILE'] = ssl_secret_mount_path + "ssl.crt"
        env['JUPYTERHUB_SSL_CLIENT_CA'] = (
            ssl_secret_mount_path + "notebooks-ca_trust.crt"
        )

        if not volume_mounts:
            volume_mounts = []
        volume_mounts.append(
            {
                'name': 'jupyterhub-internal-certs',
                'mountPath': ssl_secret_mount_path,
            }
        )

    if node_selector:
        pod.spec.node_selector = node_selector

    if lifecycle_hooks:
        lifecycle_hooks = get_k8s_model(V1Lifecycle, lifecycle_hooks)

    # Security contexts can be configured on Pod and Container level. The
    # Dedicated KubeSpawner API will bootstraps the container_security_context
    # except for if can only be configured on the Pod level, then it bootstraps
    # pod_security_context.
    #
    # The pod|container_security_context configuration is given a higher
    # priority than the dedicated KubeSpawner API options.
    #
    # Note that validation against the Python kubernetes-client isn't made as
    # the security contexts has evolved significantly and kubernetes-client is
    # too outdated.
    #
    # | Dedicated KubeSpawner API  | Kubernetes API           | Security contexts |
    # | -------------------------- | ------------------------ | ----------------- |
    # | supplemental_gids          | supplementalGroups       | Pod only          |
    # | fs_gid                     | fsGroup                  | Pod only          |
    # | -                          | fsGroupChangePolicy      | Pod only          |
    # | -                          | sysctls                  | Pod only          |
    # | privileged                 | privileged               | Container only    |
    # | allow_privilege_escalation | allowPrivilegeEscalation | Container only    |
    # | -                          | capabilities             | Container only    |
    # | -                          | procMount                | Container only    |
    # | -                          | readOnlyRootFilesystem   | Container only    |
    # | uid                        | runAsUser                | Pod and Container |
    # | gid                        | runAsGroup               | Pod and Container |
    # | -                          | runAsNonRoot             | Pod and Container |
    # | -                          | seLinuxOptions           | Pod and Container |
    # | -                          | seccompProfile           | Pod and Container |
    # | -                          | windowsOptions           | Pod and Container |
    #
    # ref: https://kubernetes.io/docs/tasks/configure-pod-container/security-context/
    # ref: https://kubernetes.io/docs/reference/generated/kubernetes-api/v1.28/#securitycontext-v1-core (container)
    # ref: https://kubernetes.io/docs/reference/generated/kubernetes-api/v1.28/#podsecuritycontext-v1-core (pod)
    #
    psc = {}
    # populate with fs_gid / supplemental_gids
    if fs_gid is not None:
        psc["fsGroup"] = int(fs_gid)
    if supplemental_gids:
        psc["supplementalGroups"] = [int(gid) for gid in supplemental_gids]
    if pod_security_context:
        for key in pod_security_context.keys():
            if "_" in key:
                raise ValueError(
                    f"pod_security_context's keys should have k8s camelCase names, got '{key}'"
                )
        psc.update(pod_security_context)
    if not psc:
        psc = None
    pod.spec.security_context = psc

    csc = {}
    # populate with uid / gid / privileged / allow_privilege_escalation
    if uid is not None:
        csc["runAsUser"] = int(uid)
    if gid is not None:
        csc["runAsGroup"] = int(gid)
    if privileged:  # false as default
        csc["privileged"] = True
    if allow_privilege_escalation is not None:  # false as default
        csc["allowPrivilegeEscalation"] = allow_privilege_escalation
    if container_security_context:
        for key in container_security_context.keys():
            if "_" in key:
                raise ValueError(
                    f"container_security_context's keys should have k8s camelCase names, got '{key}'"
                )
        csc.update(container_security_context)
    if not csc:
        csc = None

    def _get_env_var_deps(env):
        # only consider env var objects with an explicit string value
        if not env.value:
            return set()
        # $(MY_ENV) pattern: $( followed by non-)-characters to be captured, followed by )
        re_k8s_env_reference_pattern = r"\$\(([^\)]+)\)"
        deps = set(re.findall(re_k8s_env_reference_pattern, env.value))
        return deps - {env.name}

    unsorted_env = {}
    for key, env in (env or {}).items():
        # Normalize KubeSpawners env input to valid Kubernetes EnvVar Python
        # representations. They should have a "name" field as well as either a
        # "value" field or "value_from" field. For examples see the
        # test_make_pod_with_env function.
        if type(env) == dict:
            if not "name" in env:
                env["name"] = key
            env = get_k8s_model(V1EnvVar, env)
        else:
            env = V1EnvVar(name=key, value=env)

        # Extract information about references to other envs as we want to use
        # those to make an intelligent sorting before we render this into a list
        # with an order that matters.
        unsorted_env[env.name] = {
            "deps": _get_env_var_deps(env),
            "key": key,
            "env": env,
        }

    # We sort environment variables in a way that allows dependencies to other
    # env to resolve as much as possible. There could be circular dependencies
    # so we will just do our best and settle with that.
    #
    # Algorithm description:
    #
    # - loop step:
    #   - pop all unsorted_env entries with dependencies in sorted_env
    #   - sort popped env based on key and extend the sorted_env list
    # - loop exit:
    #   - exit if loop step didn't pop anything from unsorted_env
    #   - before exit, sort what remains and extending the sorted_env list
    #
    sorted_env = []
    while True:
        already_resolved_env_names = [e.name for e in sorted_env]

        extracted_env = {}
        for k, v in unsorted_env.copy().items():
            if v["deps"].issubset(already_resolved_env_names):
                extracted_env[k] = unsorted_env.pop(k)

        if extracted_env:
            extracted_env = [
                d["env"]
                for d in sorted(extracted_env.values(), key=operator.itemgetter("key"))
            ]
            sorted_env.extend(extracted_env)
        else:
            remaining_env = [
                d["env"]
                for d in sorted(unsorted_env.values(), key=operator.itemgetter("key"))
            ]
            sorted_env.extend(remaining_env)
            break

    notebook_container = V1Container(
        name='notebook',
        image=image,
        working_dir=working_dir,
        ports=[V1ContainerPort(name='notebook-port', container_port=port)],
        env=sorted_env,
        args=cmd,
        image_pull_policy=image_pull_policy,
        lifecycle=lifecycle_hooks,
        resources=V1ResourceRequirements(),
        volume_mounts=[
            get_k8s_model(V1VolumeMount, obj) for obj in (volume_mounts or [])
        ],
        security_context=csc,
    )

    if service_account is not None:
        pod.spec.service_account_name = service_account

    if automount_service_account_token is None:
        if service_account is None:
            # This makes sure that we don't accidentally give access to the whole
            # kubernetes API to the users in the spawned pods.
            pod.spec.automount_service_account_token = False
    else:
        pod.spec.automount_service_account_token = automount_service_account_token

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
        pod.spec.containers.extend(
            [get_k8s_model(V1Container, obj) for obj in extra_containers]
        )
    if tolerations:
        pod.spec.tolerations = [get_k8s_model(V1Toleration, obj) for obj in tolerations]
    if init_containers:
        pod.spec.init_containers = [
            get_k8s_model(V1Container, obj) for obj in init_containers
        ]
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
                node_selector_terms=[
                    get_k8s_model(V1NodeSelectorTerm, obj)
                    for obj in node_affinity_required
                ],
            )

        preferred_scheduling_terms = None
        if node_affinity_preferred:
            preferred_scheduling_terms = [
                get_k8s_model(V1PreferredSchedulingTerm, obj)
                for obj in node_affinity_preferred
            ]

        node_affinity = V1NodeAffinity(
            preferred_during_scheduling_ignored_during_execution=preferred_scheduling_terms,
            required_during_scheduling_ignored_during_execution=node_selector,
        )

    pod_affinity = None
    if pod_affinity_preferred or pod_affinity_required:
        weighted_pod_affinity_terms = None
        if pod_affinity_preferred:
            weighted_pod_affinity_terms = [
                get_k8s_model(V1WeightedPodAffinityTerm, obj)
                for obj in pod_affinity_preferred
            ]

        pod_affinity_terms = None
        if pod_affinity_required:
            pod_affinity_terms = [
                get_k8s_model(V1PodAffinityTerm, obj) for obj in pod_affinity_required
            ]

        pod_affinity = V1PodAffinity(
            preferred_during_scheduling_ignored_during_execution=weighted_pod_affinity_terms,
            required_during_scheduling_ignored_during_execution=pod_affinity_terms,
        )

    pod_anti_affinity = None
    if pod_anti_affinity_preferred or pod_anti_affinity_required:
        weighted_pod_affinity_terms = None
        if pod_anti_affinity_preferred:
            weighted_pod_affinity_terms = [
                get_k8s_model(V1WeightedPodAffinityTerm, obj)
                for obj in pod_anti_affinity_preferred
            ]

        pod_affinity_terms = None
        if pod_anti_affinity_required:
            pod_affinity_terms = [
                get_k8s_model(V1PodAffinityTerm, obj)
                for obj in pod_anti_affinity_required
            ]

        pod_anti_affinity = V1PodAffinity(
            preferred_during_scheduling_ignored_during_execution=weighted_pod_affinity_terms,
            required_during_scheduling_ignored_during_execution=pod_affinity_terms,
        )

    affinity = None
    if node_affinity or pod_affinity or pod_anti_affinity:
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

    pod.spec.hostname = name
    return pod


def make_pvc(
    name,
    storage_class,
    access_modes,
    selector,
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
    selector:
        Dictionary Selector to match pvc to pv.
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

    if storage_class is not None:
        pvc.metadata.annotations.update(
            {"volume.beta.kubernetes.io/storage-class": storage_class}
        )
        pvc.spec.storage_class_name = storage_class

    if selector:
        pvc.spec.selector = selector

    return pvc


def make_ingress(
    name: str,
    routespec: str,
    target: str,
    data: dict,
    namespace: str,
    common_labels: Optional[dict] = None,
    ingress_extra_labels: Optional[dict] = None,
    ingress_extra_annotations: Optional[dict] = None,
    ingress_class_name: Optional[str] = None,
    ingress_specifications: Optional[List[Dict]] = None,
    reuse_existing_services: bool = False,
) -> Tuple[Optional[V1Endpoints], Optional[V1Service], V1Ingress]:
    """
    Returns an ingress, service, endpoint object that'll work for this service
    """

    default_labels = {
        'hub.jupyter.org/proxy-route': 'true',
    }

    common_labels = (common_labels or {}).copy()
    common_labels.update(default_labels)

    common_annotations = {
        'hub.jupyter.org/proxy-data': json.dumps(data),
        'hub.jupyter.org/proxy-routespec': routespec,
        'hub.jupyter.org/proxy-target': target,
    }

    meta = V1ObjectMeta(
        name=name,
        annotations=common_annotations,
        labels=common_labels,
    )

    # /myuser/myserver or https://myuser.example.com/myserver for spawned server
    # /services/myservice or https://services.example.com/myservice for service
    # / or https://example.com/ for hub
    route_parts = urlparse(routespec)
    routespec_host = route_parts.netloc or None
    routespec_path = route_parts.path

    target_parts = urlparse(target)
    target_port = target_parts.port

    try:
        # Try to parse as an IP address
        target_ip = ipaddress.ip_address(target_parts.hostname)
    except ValueError:
        target_is_ip = False
    else:
        target_is_ip = True

    service_name = name

    if target_is_ip:
        # c.KubeSpawner.services_enabled = False
        # routespec='http://192.168.1.1:8888/'

        # ingress -> service -> endpoint -> pod
        # endpoint is used just to allow access from ingress to Pod IP (if PodNetworkPolicy is used)
        endpoint = V1Endpoints(
            kind='Endpoints',
            metadata=meta,
            subsets=[
                V1EndpointSubset(
                    addresses=[V1EndpointAddress(ip=target_ip.compressed)],
                    ports=[CoreV1EndpointPort(port=target_port)],
                )
            ],
        )

        service = V1Service(
            kind='Service',
            metadata=meta,
            spec=V1ServiceSpec(
                type='ClusterIP',
                external_name='',
                ports=[V1ServicePort(port=target_port, target_port=target_port)],
            ),
        )
    else:
        endpoint = None

        service_match = SERVICE_DNS_PATTERN.match(target_parts.hostname)
        if (
            reuse_existing_services
            and service_match
            and (
                not service_match.group("namespace")
                or service_match.group("namespace") == namespace
            )
        ):
            # c.KubeSpawner.services_enabled = True
            # routespec='http://myservice.mynamespace.svc.cluster.local:8888/'
            # routespec='http://myservice.mynamespace.svc.cluster:8888/'
            # routespec='http://myservice.mynamespace.svc:8888/'
            # routespec='http://myservice.mynamespace:8888/'
            # routespec='http://hub:8888/'

            # Ingress -> Service (same namespace, created by KubeSpawner)
            service = None  # just use this service in ingress, do not create it
            service_name = service_match.group("service")
        else:
            # config: c.KubeSpawner.namespace='another-namespace'
            # routespec: 'http://myservice.another-namespace...:8888/'
            # or
            # config: c.KubeSpawner.enable_user_namespaces=True
            # routespec: 'http://myservice.user-namespace...:8888/'
            # or
            # c.JupyterHub.services = [{"name": "my-service", "url": "http://some.domain:9000"}]
            # routespec: 'http://some.domain:9000/'

            # Ingress -> ExternalName -> Service (different namespace or some external domain)
            service = V1Service(
                kind='Service',
                metadata=meta,
                spec=V1ServiceSpec(
                    type='ExternalName',
                    external_name=target_parts.hostname,
                    cluster_ip='',
                    ports=[V1ServicePort(port=target_port, target_port=target_port)],
                ),
            )

    # Make Ingress object

    ingress_labels = common_labels.copy()
    ingress_labels.update(ingress_extra_labels or {})

    ingress_annotations = common_annotations.copy()
    ingress_annotations.update(ingress_extra_annotations or {})

    ingress_meta = V1ObjectMeta(
        name=name,
        annotations=ingress_annotations,
        labels=ingress_labels,
    )

    ingress_specifications = ingress_specifications or []

    hosts = []
    add_routespec_host = True
    for ingress_spec in ingress_specifications:
        if routespec_host and host_matching(routespec_host, ingress_spec["host"]):
            # if routespec is URL like "http[s]://user.example.com"
            # and ingress_specifications contains item like
            # {"host": "user.example.com"} or {"host": "*.example.com"},
            # prefer routespec_host over than wildcard
            if add_routespec_host:
                hosts.append(routespec_host)

            add_routespec_host = False
        elif ingress_spec["host"] not in hosts:
            hosts.append(ingress_spec["host"])

    if add_routespec_host and (routespec_host or not hosts):
        # if routespec is URL like "http[s]://user.example.com"
        # and does not match any host from ingress_specifications, create rule with routespec_host.

        # if routespec is path like /base/url, and ingress_specifications is empty,
        # create one ingress rule without host name.
        hosts.insert(0, routespec_host)

    rules = [
        V1IngressRule(
            host=host,
            http=V1HTTPIngressRuleValue(
                paths=[
                    V1HTTPIngressPath(
                        path=routespec_path,
                        path_type="Prefix",
                        backend=V1IngressBackend(
                            service=V1IngressServiceBackend(
                                name=service_name,
                                port=V1ServiceBackendPort(
                                    number=target_port,
                                ),
                            ),
                        ),
                    ),
                ],
            ),
        )
        for host in hosts
    ]

    tls = [
        V1IngressTLS(hosts=[spec["host"]], secret_name=spec["tlsSecret"])
        for spec in ingress_specifications
        if "tlsSecret" in spec
    ]

    ingress = V1Ingress(
        kind='Ingress',
        metadata=ingress_meta,
        spec=V1IngressSpec(
            rules=rules,
            tls=tls or None,
            ingress_class_name=ingress_class_name,
        ),
    )

    return endpoint, service, ingress


def make_owner_reference(name, uid):
    """
    Returns a owner reference object for garbage collection.
    """
    return V1OwnerReference(
        api_version="v1",
        kind="Pod",
        name=name,
        uid=uid,
        block_owner_deletion=True,
        controller=False,
    )


def make_secret(
    name,
    username,
    cert_paths,
    hub_ca,
    owner_references,
    labels=None,
    annotations=None,
):
    """
    Make a k8s secret specification using pre-existing ssl credentials for a given user.

    Parameters
    ----------
    name:
        Name of the secret. Must be unique within the namespace the object is
        going to be created in.
    username:
        The name of the user notebook.
    cert_paths:
        JupyterHub spawners cert_paths dictionary container certificate path references
    hub_ca:
        Path to the hub certificate authority
    labels:
        Labels to add to the secret.
    annotations:
        Annotations to add to the secret.
    """

    secret = V1Secret()
    secret.kind = "Secret"
    secret.api_version = "v1"
    secret.metadata = V1ObjectMeta()
    secret.metadata.name = name
    secret.metadata.annotations = (annotations or {}).copy()
    secret.metadata.labels = (labels or {}).copy()
    secret.metadata.owner_references = owner_references

    secret.data = {}

    with open(cert_paths['keyfile']) as file:
        encoded = base64.b64encode(file.read().encode("utf-8"))
        secret.data['ssl.key'] = encoded.decode("utf-8")

    with open(cert_paths['certfile']) as file:
        encoded = base64.b64encode(file.read().encode("utf-8"))
        secret.data['ssl.crt'] = encoded.decode("utf-8")

    with open(cert_paths['cafile']) as ca_file, open(hub_ca) as hub_ca_file:
        cas = ca_file.read().strip("\n") + "\n" + hub_ca_file.read()
        encoded = base64.b64encode(cas.encode("utf-8"))
        secret.data["notebooks-ca_trust.crt"] = encoded.decode("utf-8")

    return secret


def make_service(
    name: str,
    port: int,
    selector: dict,
    owner_references: List[V1OwnerReference],
    labels: Optional[dict] = None,
    annotations: Optional[dict] = None,
):
    """
    Make a k8s service specification for using dns to communicate with the notebook.

    Parameters
    ----------
    name:
        Name of the service. Must be unique within the namespace the object is
        going to be created in.
    selector:
        Labels of server pod to be used in spec.selector
    owner_references:
        Pod's owner references used to automatically remote service after pod removal
    labels:
        Labels to add to the service.
    annotations:
        Annotations to add to the service.

    """

    metadata = V1ObjectMeta(
        name=name,
        annotations=(annotations or {}).copy(),
        labels=(labels or {}).copy(),
        owner_references=owner_references,
    )

    service = V1Service(
        kind='Service',
        metadata=metadata,
        spec=V1ServiceSpec(
            type='ClusterIP',
            ports=[V1ServicePort(name='http', port=port, target_port=port)],
            selector=selector,
        ),
    )

    return service


def make_namespace(name, labels=None, annotations=None):
    """
    Make a k8s namespace specification for a user pod.
    """

    metadata = V1ObjectMeta(
        name=name, labels=(labels or {}).copy(), annotations=(annotations or {}).copy()
    )

    return V1Namespace(metadata=metadata)
