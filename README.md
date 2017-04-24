# sqrekubespawner (jupyterhub-kubernetes-spawner) #

The *sqrekubespawner* is a slight variant of the standard JupyterHub 
Kubernetes Spawner.  Its differences are the following: it uses
GHOWLAuth, if that was used, to make the GitHub ID of the user the ID
that is passed to the spawned container, and it acquires and passes a
GitHub token for the use of the spawned container.

The *kubespawner* (also known as JupyterHub Kubernetes Spawner) enables JupyterHub to spawn
single-user notebook servers on a [Kubernetes](https://kubernetes.io/)
cluster.

## Features ##

Kubernetes is an open-source system for automating deployment, scaling, and
management of containerized applications. If you want to run a JupyterHub
setup that needs to scale across multiple nodes (anything with over ~50
simultaneous users), Kubernetes is a wonderful way to do it. Features include:

* Easily and elasticly run anywhere between 2 and thousands of nodes with the
  same set of powerful abstractions. Scale up and down as required by simply
  adding or removing nodes.

* Run JupyterHub itself inside Kubernetes easily. This allows you to manage
  many JupyterHub deployments with only Kubernetes, without requiring an extra
  layer of Ansible / Puppet / Bash scripts. This also provides easy integrated
  monitoring and failover for the hub process itself.

* Spawn multiple hubs in the same kubernetes cluster, with support for
  [namespaces](http://kubernetes.io/docs/admin/namespaces/). You can limit the
  amount of resources each namespace can use, effectively limiting the amount
  of resources a single JupyterHub (and its users) can use. This allows
  organizations to easily maintain multiple JupyterHubs with just one
  kubernetes cluster, allowing for easy maintenance & high resource
  utilization.

* Provide guarantees and limits on the amount of resources (CPU / RAM) that
  single-user notebooks can use. Kubernetes has comprehensive [resource control](http://kubernetes.io/docs/user-guide/compute-resources/) that can
  be used from the spawner.

* Mount various types of [persistent volumes](http://kubernetes.io/docs/user-guide/persistent-volumes/)
  onto the single-user notebook's container.

* Control various security parameters (such as userid/groupid, SELinux, etc)
  via flexible [Pod Security Policies](http://kubernetes.io/docs/user-guide/pod-security-policy/).

* Run easily in multiple clouds (or on your own machines). Helps avoid vendor
  lock-in. You can even spread out your cluster across
  [multiple clouds at the same time](http://kubernetes.io/docs/user-guide/federation/).

In general, Kubernetes provides a ton of well thought out, useful features -
and you can use all of them along with this spawner.

## Requirements ##

### Kubernetes ###

Everything should work from Kubernetes v1.2+.

The [Kube DNS addon](http://kubernetes.io/docs/user-guide/connecting-applications/#dns)
is not strictly required - the spawner uses
[environment variable](http://kubernetes.io/docs/user-guide/connecting-applications/#environment-variables)
based discovery instead. Your kubernetes cluster will need to be configured to
support the types of volumes you want to use.

If you are just getting started and want a kubernetes cluster to play with,
[Google Container Engine](https://cloud.google.com/container-engine/) is
probably the nicest option. For AWS/Azure,
[kops](https://github.com/kubernetes/kops) is probably the way to go.

### Python dependencies ###

[pycurl](http://pycurl.io/) needs to be installed for KubeSpawner to work.

If you are on debian / ubuntu and use pip to install KubeSpawner, you also need the following packages
to be installed: `python3-dev libcurl4-openssl-dev libssl-dev`

## Getting help ##

We encourage you to ask questions on the
[Jupyter mailing list](https://groups.google.com/forum/#!forum/jupyter).
You can also participate in development discussions or get live help on
[Gitter](https://gitter.im/jupyterhub/jupyterhub).

## License ##

We use a shared copyright model that enables all contributors to maintain the
copyright on their contributions.

All code is licensed under the terms of the revised BSD license.

## Resources

#### JupyterHub and kubespawner

- [Reporting Issues](https://github.com/jupyterhub/kubespawner/issues)
- [Documentation for JupyterHub](http://jupyterhub.readthedocs.io/en/latest/) | [PDF (latest)](https://media.readthedocs.org/pdf/jupyterhub/latest/jupyterhub.pdf) | [PDF (stable)](https://media.readthedocs.org/pdf/jupyterhub/stable/jupyterhub.pdf)
- [Documentation for JupyterHub's REST API](http://petstore.swagger.io/?url=https://raw.githubusercontent.com/jupyter/jupyterhub/master/docs/rest-api.yml#/default)

#### Jupyter

- [Documentation for Project Jupyter](http://jupyter.readthedocs.io/en/latest/index.html) | [PDF](https://media.readthedocs.org/pdf/jupyter/latest/jupyter.pdf)
- [Project Jupyter website](https://jupyter.org)
