# Internal SSL

JupyterHub 1.0 introduces internal_ssl configuration for encryption and authentication of all internal communication.

Kubespawner can mount the internal_ssl certificates as Kubernetes secrets into the jupyter user's pod.

## Setup

```
c.JupyterHub.internal_ssl = True

c.JupyterHub.spawner_class = 'kubespawner.KubeSpawner'
```
