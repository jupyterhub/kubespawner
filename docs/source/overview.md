# Overview

The _kubespawner_ (also known as JupyterHub Kubernetes Spawner) enables JupyterHub to spawn
single-user notebook servers on a [Kubernetes](https://kubernetes.io/)
cluster.

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
  [namespaces](https://kubernetes.io/docs/tasks/administer-cluster/namespaces/). You can limit the
  amount of resources each namespace can use, effectively limiting the amount
  of resources a single JupyterHub (and its users) can use. This allows
  organizations to easily maintain multiple JupyterHubs with just one
  kubernetes cluster, allowing for easy maintenance & high resource
  utilization.

- Provide guarantees and limits on the amount of resources (CPU / RAM) that
  single-user notebooks can use. Kubernetes has comprehensive [resource control](https://kubernetes.io/docs/concepts/configuration/manage-compute-resources-container/) that can
  be used from the spawner.

- Mount various types of
  [persistent volumes](https://kubernetes.io/docs/concepts/storage/persistent-volumes/)
  onto the single-user notebook's container.

- Control various security parameters (such as userid/groupid, SELinux, etc)
  via flexible [Pod Security Policies](https://kubernetes.io/docs/concepts/policy/pod-security-policy/).

- Run easily in multiple clouds (or on your own machines). Helps avoid vendor
  lock-in. You can even spread out your cluster across
  [multiple clouds at the same time](https://kubernetes.io/docs/concepts/cluster-administration/federation/).

- Internal SSL configuration supported

In general, Kubernetes provides a ton of well thought out, useful features -
and you can use all of them along with this spawner.

## Requirements

### Kubernetes

Everything should work from Kubernetes v1.6+.

The [Kube DNS addon](https://kubernetes.io/docs/concepts/services-networking/connect-applications-service/#dns)
is not strictly required - the spawner uses
[environment variable](https://kubernetes.io/docs/concepts/services-networking/connect-applications-service/#environment-variables)
based discovery instead. Your kubernetes cluster will need to be configured to
support the types of volumes you want to use.

If you are just getting started and want a kubernetes cluster to play with,
[Google Container Engine](https://cloud.google.com/kubernetes-engine/) is
probably the nicest option. For AWS/Azure,
[kops](https://github.com/kubernetes/kops) is probably the way to go.
