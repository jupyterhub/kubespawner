import os
import socket

c.JupyterHub.spawner_class = 'kubespawner.KubeSpawner'

c.JupyterHub.ip = '127.0.0.1'
c.JupyterHub.hub_ip = '127.0.0.1'

# Don't try to cleanup servers on exit - since in general for k8s, we want
# the hub to be able to restart without losing user containers
c.JupyterHub.cleanup_servers = False

# A small user image with jupyterlab that is easy to test against, assumed to be
# downloadable in less than 60 seconds.
c.KubeSpawner.image = 'jupyter/base-notebook:latest'
c.KubeSpawner.start_timeout = 60

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

# Simplify testing by using a dummy authenticator class where any username
# password combination will work and where we don't provide persistent storage.
c.JupyterHub.authenticator_class = 'dummy'
c.KubeSpawner.storage_pvc_ensure = False

c.JupyterHub.allow_named_servers = True

c.KubeSpawner.profile_list = [
    {
        'display_name': 'Demo - profile_list entry 1',
        'description': 'Demo description for profile_list entry 1, and it should look good even though it is a bit lengthy.',
        'slug': 'demo-1',
        'default': True,
        'profile_options': {
            'image': {
                'display_name': 'Image',
                'choices': {
                    'base': {
                        'display_name': 'jupyter/base-notebook:latest',
                        'kubespawner_override': {
                            'image': 'jupyter/base-notebook:latest'
                        },
                    },
                    'minimal': {
                        'display_name': 'jupyter/minimal-notebook:latest',
                        'default': True,
                        'kubespawner_override': {
                            'image': 'jupyter/minimal-notebook:latest'
                        },
                    },
                },
                'unlisted_choice': {
                    'enabled': True,
                    'display_name': 'Other image',
                    'validation_regex': '^jupyter/.+:.+$',
                    'validation_message': 'Must be an image matching ^jupyter/<name>:<tag>$',
                    'kubespawner_override': {'image': '{value}'},
                },
            },
        },
        'kubespawner_override': {
            'default_url': '/lab',
        },
    },
    {
        'display_name': 'Demo - profile_list entry 2',
        'slug': 'demo-2',
        'kubespawner_override': {
            'extra_resource_guarantees': {"nvidia.com/gpu": "1"},
        },
    },
]
