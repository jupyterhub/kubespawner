"""
JupyterHub Spawner to spawn user notebooks on a Kubernetes cluster.

After installation, you can enable it by adding:

```
c.JupyterHub.spawner_class = 'kubernetesspawner.KubernetesSpawner'
```

in your `jupyterhub_config.py` file.

We export KubernetesSpawner specifically here, so people can import kubernetesspawner.KubernetesSpawner
instead of kubernetesspawner.spawner.KubernetesSpawner
"""
from kubernetesspawner.spawner import KubernetesSpawner

__all__ = [KubernetesSpawner]
