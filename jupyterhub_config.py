import os


c.JupyterHub.spawner_class = 'kubespawner.KubeSpawner'

c.JupyterHub.ip = '0.0.0.0'
c.JupyterHub.hub_ip = '0.0.0.0'

# Don't try to cleanup servers on exit - since in general for k8s, we want
# the hub to be able to restart without losing user containers
c.JupyterHub.cleanup_servers = False

# First pulls can be really slow, so let's give it a big timeout
c.KubeSpawner.start_timeout = 60 * 5

# Our simplest user image! Optimized to just... start, and be small!
c.KubeSpawner.singleuser_image_spec = 'jupyterhub/singleuser:0.8'

# The spawned containers need to be able to talk to the hub through the proxy!
c.KubeSpawner.hub_connect_ip = os.environ['HUB_CONNECT_IP']
c.JupyterHub.hub_connect_ip = os.environ['HUB_CONNECT_IP']

c.KubeSpawner.singleuser_service_account = 'default'
# Do not use any authentication at all - any username / password will work.
c.JupyterHub.authenticator_class = 'dummyauthenticator.DummyAuthenticator'

c.KubeSpawner.user_storage_pvc_ensure = False

c.JupyterHub.allow_named_servers = True

c.KubeSpawner.profile_list = [
    {
        'display_name': 'Training Env - Python',
        'default': True,
        'kubespawner_override': {
            'singleuser_image_spec': 'training/python:label',
            'cpu_limit': 0.5,
        },
        'description': 'Something description of what is going on here, maybe a <a href="#">link too!</a>'
    }, {
        'display_name': 'Training Env - Datascience',
        'kubespawner_override': {
            'singleuser_image_spec': 'training/datascience:label',
            'cpu_limit': 0.2,
        },
        'description': 'Something description of how this is different, maybe a <a href="#">link too!</a>'
    }
]