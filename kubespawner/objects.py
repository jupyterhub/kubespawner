"""
Helper methods for generating k8s API objects.
"""
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
    volumes,
    volume_mounts,
    labels,
    cpu_limit,
    cpu_guarantee,
    mem_limit,
    mem_guarantee
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
      - labels:
        Labels to add to the spawned pod.
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
    """
    pod_security_context = {}
    if run_as_uid is not None:
        pod_security_context['runAsUser'] = int(run_as_uid)
    if fs_gid is not None:
        pod_security_context['fsGroup'] = int(fs_gid)
    image_secret = []
    if image_pull_secret is not None:
        image_secret = [{"name": image_pull_secret}]
    return {
        'apiVersion': 'v1',
        'kind': 'Pod',
        'metadata': {
            'name': name,
            'labels': labels,
        },
        'spec': {
            'securityContext': pod_security_context,
            "imagePullSecrets": image_secret,
            'containers': [
                {
                    'name': 'notebook',
                    'image': image_spec,
                    'args': cmd,
                    'imagePullPolicy': image_pull_policy,
                    'ports': [{
                        'containerPort': port,
                    }],
                    'resources': {
                        'requests': {
                            # If these are None, it's ok. the k8s API
                            # seems to interpret that as 'no limit',
                            # which is what we want.
                            'memory': mem_guarantee,
                            'cpu': cpu_guarantee,
                        },
                        'limits': {
                            'memory': mem_limit,
                            'cpu': cpu_limit,
                        }
                    },
                    'env': [
                        {'name': k, 'value': v}
                        for k, v in env.items()
                    ],
                    'volumeMounts': volume_mounts
                }
            ],
            'volumes': volumes
        }
    }


def make_pvc_spec(
    name,
    storage_class,
    access_modes,
    storage
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
    return {
        'kind': 'PersistentVolumeClaim',
        'apiVersion': 'v1',
        'metadata': {
            'name': name,
            'annotations': {
                'volume.beta.kubernetes.io/storage-class': storage_class
            }
        },
        'spec': {
            'accessModes': access_modes,
            'resources': {
                'requests': {
                    'storage': storage
                }
            }
        }
    }
