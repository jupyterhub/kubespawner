"""
SQuaRE JupyterHub Spawner to spawn user notebooks on a Kubernetes cluster.

After installation, you can enable it by adding:

```
c.JupyterHub.spawner_class = 'sqrekubespawner.SQREKubeSpawner'
```

in your `jupyterhub_config.py` file.

We export SQREKubeSpawner specifically here. This simplifies import for users.
Users can simply import kubespawner.SQREKubeSpawner in their applications
instead of the more verbose import kubespawner.spawner.SQREKubeSpawner.
"""
from sqrekubespawner.spawner import SQREKubeSpawner

__all__ = [SQREKubeSpawner]
