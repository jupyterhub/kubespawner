import os
import socket

c.JupyterHub.spawner_class = 'kubespawner.KubeSpawner'

c.JupyterHub.ip = '127.0.0.1'
c.JupyterHub.hub_ip = '127.0.0.1'

# Don't try to cleanup servers on exit - since in general for k8s, we want
# the hub to be able to restart without losing user containers
c.JupyterHub.cleanup_servers = False

# First pulls can be really slow, so let's give it a big timeout
c.KubeSpawner.start_timeout = 60 * 5

# Our simplest user image! Optimized to just... start, and be small!
c.KubeSpawner.image = 'jupyterhub/singleuser:1.0'

if os.environ.get("CI"):
    # In the CI system we use k3s which will be accessible on localhost.
    c.JupyterHub.hub_connect_ip = "127.0.0.1"
else:
    # Find the IP of the machine that minikube is most likely able to talk to
    # Graciously used from https://stackoverflow.com/a/166589
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(("8.8.8.8", 80))
    host_ip = s.getsockname()[0]
    s.close()

    c.JupyterHub.hub_connect_ip = host_ip

c.KubeSpawner.service_account = 'default'
# Do not use any authentication at all - any username / password will work.
c.JupyterHub.authenticator_class = 'dummy'

c.KubeSpawner.storage_pvc_ensure = False

c.JupyterHub.allow_named_servers = True

c.KubeSpawner.profile_list = [
    {
        'display_name': 'Training Env',
        'description': 'This is the description for the training env profile list choice. This should look good even though it is a bit lengthy.',
        'slug': 'training-python',
        'default': True,
        'profile_options': {
            'image': {
                'display_name': 'Image',
                'free_form': {
                    'enabled': True,
                    'display_name': 'Image Location',
                    'match_regex': '^pangeo/.*$',
                    'validation_message': 'Must be a pangeo image, matching ^pangeo/.*$',
                    'kubespawner_override': {'image': '{value}'},
                },
                'choices': {
                    'pytorch': {
                        'display_name': 'Python 3 Training Notebook',
                        'kubespawner_override': {'image': 'training/python:2022.01.01'},
                    },
                    'tf': {
                        'display_name': 'R 4.2 Training Notebook',
                        'default': True,
                        'kubespawner_override': {'image': 'training/r:2021.12.03'},
                    },
                },
            },
        },
        'kubespawner_override': {
            'cpu_limit': 1,
            'mem_limit': '512M',
        },
    },
    {
        'display_name': 'Python DataScience',
        'slug': 'datascience-small',
        'profile_options': {
            'memory': {
                'display_name': 'Memory',
                'choices': {
                    '1Gi': {
                        'display_name': '1GB',
                        'kubespawner_override': {'mem_limit': '1G'},
                    },
                    '2Gi': {
                        'display_name': '2GB',
                        'kubespawner_override': {'mem_limit': '2G'},
                    },
                },
            },
            'cpu': {
                'display_name': 'CPUs',
                'choices': {
                    '2': {
                        'display_name': '2 CPUs',
                        'kubespawner_override': {
                            'cpu_limit': 2,
                            'cpu_guarantee': 1.8,
                            'node_selectors': {
                                'node.kubernetes.io/instance-type': 'n1-standard-2'
                            },
                        },
                    },
                    '4': {
                        'display_name': '4 CPUs',
                        'kubespawner_override': {
                            'cpu_limit': 4,
                            'cpu_guarantee': 3.5,
                            'node_selectors': {
                                'node.kubernetes.io/instance-type': 'n1-standard-4'
                            },
                        },
                    },
                },
            },
        },
        'kubespawner_override': {
            'image': 'datascience/small:label',
        },
    },
    {
        'display_name': 'DataScience - Medium instance (GPUx2)',
        'slug': 'datascience-gpu2x',
        'kubespawner_override': {
            'image': 'datascience/medium:label',
            'cpu_limit': 48,
            'mem_limit': '96G',
            'extra_resource_guarantees': {"nvidia.com/gpu": "2"},
        },
    },
]
