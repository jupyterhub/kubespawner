"""
JupyterHub Spawner to spawn user notebooks on a Kubernetes cluster.

After installation, you can enable it by adding:

```
c.JupyterHub.spawner_class = 'kubespawner.KubeSpawner'
```

in your `jupyterhub_config.py` file.

We export KubeSpawner specifically here. This simplifies import for users.
Users can simply import kubespawner.KubeSpawner in their applications
instead of the more verbose import kubespawner.spawner.KubeSpawner.
"""
from kubespawner.spawner import KubeSpawner

__all__ = [KubeSpawner]
