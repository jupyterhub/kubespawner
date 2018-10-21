import os
import socket


c.JupyterHub.spawner_class = 'v3iokubespawner.KubeSpawner'

c.JupyterHub.ip = '0.0.0.0'
c.JupyterHub.hub_ip = '0.0.0.0'

# Don't try to cleanup servers on exit - since in general for k8s, we want
# the hub to be able to restart without losing user containers
c.JupyterHub.cleanup_servers = False

# First pulls can be really slow, so let's give it a big timeout
c.KubeSpawner.start_timeout = 60 * 5

# Our simplest user image! Optimized to just... start, and be small!
c.KubeSpawner.image_spec = 'jupyterhub/singleuser:0.8'

# Find the IP of the machine that minikube is most likely able to talk to
# Graciously used from https://stackoverflow.com/a/166589
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.connect(("8.8.8.8", 80))
host_ip = s.getsockname()[0]
s.close()

c.KubeSpawner.hub_connect_ip = host_ip
c.JupyterHub.hub_connect_ip = c.KubeSpawner.hub_connect_ip

c.KubeSpawner.service_account = 'default'
# Do not use any authentication at all - any username / password will work.
c.JupyterHub.authenticator_class = 'dummyauthenticator.DummyAuthenticator'

c.KubeSpawner.storage_pvc_ensure = False

c.JupyterHub.allow_named_servers = True

c.KubeSpawner.profile_list = [
    {
        'display_name': 'Training Env - Python',
        'default': True,
        'kubespawner_override': {
            'image_spec': 'training/python:label',
            'cpu_limit': 0.5,
        },
        'description': 'Something description of what is going on here, maybe a <a href="#">link too!</a>'
    }, {
        'display_name': 'Training Env - Datascience',
        'kubespawner_override': {
            'image_spec': 'training/datascience:label',
            'cpu_limit': 0.2,
        },
        'description': 'Something description of how this is different, maybe a <a href="#">link too!</a>'
    }
]
