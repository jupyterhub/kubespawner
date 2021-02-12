# [kubespawner](https://github.com/jupyterhub/kubespawner) (jupyterhub-kubespawner @ PyPI)

[![Documentation status](https://img.shields.io/readthedocs/jupyterhub-kubespawner?logo=read-the-docs)](https://jupyterhub-kubespawner.readthedocs.io/en/latest/?badge=latest)
[![GitHub Workflow Status](https://img.shields.io/github/workflow/status/jupyterhub/kubespawner/Test?logo=github)](https://github.com/jupyterhub/kubespawner/actions)
[![Code coverage](https://codecov.io/gh/jupyterhub/kubespawner/branch/master/graph/badge.svg)](https://codecov.io/gh/jupyterhub/kubespawner)
[![](https://img.shields.io/pypi/v/jupyterhub-kubespawner.svg?logo=pypi)](https://pypi.python.org/pypi/jupyterhub-kubespawner)

The _kubespawner_ (also known as JupyterHub Kubernetes Spawner) enables JupyterHub to spawn
single-user notebook servers on a [Kubernetes](https://kubernetes.io/)
cluster.

See the [KubeSpawner documentation](https://jupyterhub-kubespawner.readthedocs.io) for more
information about features and usage. In particular, here is [a list of all the spawner options](https://jupyterhub-kubespawner.readthedocs.io/en/latest/spawner.html#module-kubespawner.spawner).

## Features

Kubernetes is an open-source system for automating deployment, scaling, and
management of containerized applications. If you want to run a JupyterHub
setup that needs to scale across multiple nodes (anything with over ~50
simultaneous users), Kubernetes is a wonderful way to do it. Features include:

- Easily and elasticly run anywhere between 2 and thousands of nodes with the
  same set of powerful abstractions. Scale up and down as required by simply
  adding or removing nodes.

- Run JupyterHub itself inside Kubernetes easily. This allows you to manage
  many JupyterHub deployments with only Kubernetes, without requiring an extra
  layer of Ansible / Puppet / Bash scripts. This also provides easy integrated
  monitoring and failover for the hub process itself.

- Spawn multiple hubs in the same kubernetes cluster, with support for
  [namespaces](https://kubernetes.io/docs/admin/namespaces/). You can limit the
  amount of resources each namespace can use, effectively limiting the amount
  of resources a single JupyterHub (and its users) can use. This allows
  organizations to easily maintain multiple JupyterHubs with just one
  kubernetes cluster, allowing for easy maintenance & high resource
  utilization.

- Provide guarantees and limits on the amount of resources (CPU / RAM) that
  single-user notebooks can use. Kubernetes has comprehensive [resource control](https://kubernetes.io/docs/user-guide/compute-resources/) that can
  be used from the spawner.

- Mount various types of [persistent volumes](https://kubernetes.io/docs/user-guide/persistent-volumes/)
  onto the single-user notebook's container.

- Control various security parameters (such as userid/groupid, SELinux, etc)
  via flexible [Pod Security Policies](https://kubernetes.io/docs/user-guide/pod-security-policy/).

- Run easily in multiple clouds (or on your own machines). Helps avoid vendor
  lock-in. You can even spread out your cluster across
  [multiple clouds at the same time](https://kubernetes.io/docs/user-guide/federation/).

In general, Kubernetes provides a ton of well thought out, useful features -
and you can use all of them along with this spawner.

## Requirements

### Kubernetes

Everything should work from Kubernetes v1.6+.

The [Kube DNS addon](https://kubernetes.io/docs/user-guide/connecting-applications/#dns)
is not strictly required - the spawner uses
[environment variable](https://kubernetes.io/docs/user-guide/connecting-applications/#environment-variables)
based discovery instead. Your kubernetes cluster will need to be configured to
support the types of volumes you want to use.

If you are just getting started and want a kubernetes cluster to play with,
[Google Container Engine](https://cloud.google.com/container-engine/) is
probably the nicest option. For AWS/Azure,
[kops](https://github.com/kubernetes/kops) is probably the way to go.

## Getting help

We encourage you to ask questions on the
[Jupyter mailing list](https://groups.google.com/forum/#!forum/jupyter).
You can also participate in development discussions or get live help on
[Gitter](https://gitter.im/jupyterhub/jupyterhub).

## License

We use a shared copyright model that enables all contributors to maintain the
copyright on their contributions.

All code is licensed under the terms of the revised BSD license.

## Resources

#### JupyterHub and kubespawner

- [Reporting Issues](https://github.com/jupyterhub/kubespawner/issues)
- [Documentation for JupyterHub](https://jupyterhub.readthedocs.io)
- [Documentation for JupyterHub's REST API](https://petstore.swagger.io/?url=https://raw.githubusercontent.com/jupyter/jupyterhub/master/docs/rest-api.yml#/default)

#### Jupyter

- [Documentation for Project Jupyter](https://jupyter.readthedocs.io/en/latest/index.html) | [PDF](https://media.readthedocs.org/pdf/jupyter/latest/jupyter.pdf)
- [Project Jupyter website](https://jupyter.org)
