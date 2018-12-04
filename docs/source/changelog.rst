.. _changelog:

======================
Changes in KubeSpawner
======================

.. _changelog_09:

KubeSpawner 0.10
================

0.10 is a small release, with minor changes and fixes.

- Stop pinning an exact kubernetes client version;
  instead, require kubernetes client >= 7.
  If desired, pinning should be done in images/installations
- Expand username template variables in extra_containers
- Set pod restart policy to OnFailure, so that notebook servers that terminate themselves cleanly do not restart automatically
- Formally deprecate ``KubeSpawner.hub_connect_ip`` and ``KubeSpawner.hub_connect_ip``
  in favor of ``JupyterHub.hub_connect_ip``,
  available in jupyterhub >= 0.8

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

