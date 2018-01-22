import os
import socket
from kubernetes import client

from utils import wat
wat()


c.JupyterHub.spawner_class = 'kubespawner.KubeSpawner'

c.JupyterHub.ip = '0.0.0.0'
c.JupyterHub.hub_ip = '0.0.0.0'

# Don't try to cleanup servers on exit - since in general for k8s, we want
# the hub to be able to restart without losing user containers
c.JupyterHub.cleanup_servers = False

# First pulls can be really slow, so let's give it a big timeout
c.KubeSpawner.start_timeout = 60 * 5

# Our simplest user image! Optimized to just... start, and be small!
c.KubeSpawner.singleuser_image_spec = 'jupyterhub/k8s-singleuser-sample:8b3b2ab'

# The spawned containers need to be able to talk to the hub through the proxy!

s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.connect(("8.8.8.8", 80))
hub_connect_ip = s.getsockname()[0]
s.close()

c.KubeSpawner.hub_connect_ip = hub_connect_ip
c.JupyterHub.hub_connect_ip = hub_connect_ip

c.KubeSpawner.singleuser_service_account = 'default'
# Do not use any authentication at all - any username / password will work.
c.JupyterHub.authenticator_class = 'dummyauthenticator.DummyAuthenticator'

c.KubeSpawner.user_storage_pvc_ensure = True

c.JupyterHub.allow_named_servers = True

def extra_objects_hook(spawner):
    ns = client.V1Namespace(
        metadata=client.V1ObjectMeta(name=spawner.user.name)
    )
    return [
        {
            'kind': 'Namespace',
            'api_version': 'v1',
            'namespaced': False,
            'object': ns
        }
    ]

#c.KubeSpawner.extra_objects_hook = extra_objects_hook
