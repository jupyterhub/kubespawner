"""
Helper methods for generating k8s API objects.
"""
def make_pod_spec(
    name,
    image_spec,
    env,
    volumes,
    volume_mounts,
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
    return {
        'apiVersion': 'v1',
        'kind': 'Pod',
        'metadata': {
            'name': name,
        },
        'spec': {
            'containers': [
                {
                    'name': 'notebook',
                    'image': image_spec,
                    'ports': [{
                        'containerPort': 8888,
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