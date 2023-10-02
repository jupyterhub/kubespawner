# Internal SSL

JupyterHub 1.0 introduces the internal_ssl configuration for encryption and authentication of all internal communication via mutual TLS.

If enabled, the Kubespawner will mount the internal_ssl certificates as Kubernetes secrets into the jupyter user's pod.

## Setup

To enable, use the following settings:
```
c.JupyterHub.internal_ssl = True

c.JupyterHub.spawner_class = 'kubespawner.KubeSpawner'
```

Further configuration can be specified with the following (listed with their default values):
```
c.KubeSpawner.secret_name_template = "jupyter-{username}{servername}"

c.KubeSpawner.secret_mount_path =  "/etc/jupyterhub/ssl/"
```

The Kubespawner sets the `JUPYTERHUB_SSL_KEYFILE`, `JUPYTERHUB_SSL_CERTFILE` and `JUPYTERHUB_SSL_CLIENT_CA` environment variables, with the appropriate paths, on the user's notebook server. 
