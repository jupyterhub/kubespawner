"""
Helper methods for generating k8s API objects.
"""
def make_pod_spec(
    name,
    image_spec,
    env,
    volumes,
    volume_mounts,
    resources
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
      - resources:
        Dictionary containing the pod's resource requirements.
    """
    pod_spec = {
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

    if resources:
        pod_spec['spec']['containers'][0]['resources'] = resources

    return pod_spec

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
