.. _changelog:

======================
Changes in KubeSpawner
======================

.. _changelog_09:

KubeSpawner 0.9
===============

KubeSpawner 0.9 is a big release of KubeSpawner.

Change highlights:

- Require Kubernetes >= 1.6
- Require JupyterHub >= 0.8
- Require Python >= 3.5
- Expose lots more Kubernetes options
- Support configuration profiles via :attr:`.KubeSpawner.profile_list`
- Support Kubernetes events for the progress API in JupyterHub 0.9.
- Update Kubernetes Python client to 6.0 (supporting Kubernetes 1.10 APIs)
- Numerous bugfixes

