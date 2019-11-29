# Changes in KubeSpawner

## [0.11]

### [0.11.1] - 2019-11-29

0.11.1 consists of a small bugfix that made the progress reporting break.

#### Fixes

- Fix spawn progress events now showing up due to failure to serialize [#381](https://github.com/jupyterhub/kubespawner/pull/381) ([@consideRatio](https://github.com/consideRatio))

#### Maintenance

- Don't require deploy job to also run tests [#379](https://github.com/jupyterhub/kubespawner/pull/379) ([@consideRatio](https://github.com/consideRatio))

### [0.11.0] - 2019-11-28

0.11.0 features minor feature additions, compatebility measures, and fixes.
KubeSpawner now require Python 3.5 and is no longer actively tested against
Kubernetes clusters versioned 1.10 as before, but is now being tested against
version 1.12-1.16 with the [python kubernetes client
library](https://github.com/kubernetes-client/python) version 8-11 that is
compatible with k8s 1.11-1.15.

#### New

- Add `KubeSpawner.storage_selector` for matching persistent volume using storage selector. [#338](https://github.com/jupyterhub/kubespawner/pull/338) ([@GrahamDumpleton](https://github.com/GrahamDumpleton))
- Provide `raw_event` in spawner progress [#361](https://github.com/jupyterhub/kubespawner/pull/361) ([@clkao](https://github.com/clkao))
- Add `{username}` expansion to extra_pod_config [#321](https://github.com/jupyterhub/kubespawner/pull/321) ([@cgiraldo](https://github.com/cgiraldo))
- Configurable `delete_grace_period` [#310](https://github.com/jupyterhub/kubespawner/pull/310) ([@arturozv](https://github.com/arturozv))

#### Fixes

- Scope security context to container from pod where it is possible [#334](https://github.com/jupyterhub/kubespawner/pull/334) ([@shoelsch](https://github.com/shoelsch))
- Permit storage class to be empty string. [#337](https://github.com/jupyterhub/kubespawner/pull/337) ([@GrahamDumpleton](https://github.com/GrahamDumpleton))
- Fix pod name prefix escaping for named servers [#309](https://github.com/jupyterhub/kubespawner/pull/309) ([@dmarth](https://github.com/dmarth))
- Always load user_options [#301](https://github.com/jupyterhub/kubespawner/pull/301) ([@minrk](https://github.com/minrk))
- using user_options in kubespawner [#285](https://github.com/jupyterhub/kubespawner/pull/285) ([@hhuuggoo](https://github.com/hhuuggoo))
- Allow None on UID and GID [#286](https://github.com/jupyterhub/kubespawner/pull/286) ([@dtaniwaki](https://github.com/dtaniwaki))

#### Compatibility

- CI reworked, support modern k8s high resolution timestamps, event monitoring is made more reliable, kubernetes=>8 required, python>=3.6 required, inline docs added [#368](https://github.com/jupyterhub/kubespawner/pull/368) ([@consideRatio](https://github.com/consideRatio))
- Fix for Kubernetes 1.16 regarding datetime comparison [#362](https://github.com/jupyterhub/kubespawner/pull/362) ([@consideRatio](https://github.com/consideRatio))
- More idiomatic python syntax [#356](https://github.com/jupyterhub/kubespawner/pull/356) ([@AnotherCodeArtist](https://github.com/AnotherCodeArtist))
- Compatibility with kubernetes, jupyterhub prereleases [#314](https://github.com/jupyterhub/kubespawner/pull/314) ([@minrk](https://github.com/minrk))
- compatibility with kubernetes 9.0 [#294](https://github.com/jupyterhub/kubespawner/pull/294) ([@minrk](https://github.com/minrk))
- Pin kubernetes version to 8.0 [#292](https://github.com/jupyterhub/kubespawner/pull/292) ([@yuvipanda](https://github.com/yuvipanda))

#### Maintenance

- Iteration of local development instructions [#377](https://github.com/jupyterhub/kubespawner/pull/377) ([@consideRatio](https://github.com/consideRatio))
- Add RELEASE.md and utilize bump2version [#376](https://github.com/jupyterhub/kubespawner/pull/376) ([@consideRatio](https://github.com/consideRatio))
- Fix docs build [#371](https://github.com/jupyterhub/kubespawner/pull/371) ([@consideRatio](https://github.com/consideRatio))
- [MRG]: Travis pypi: only use pre for nightly [#369](https://github.com/jupyterhub/kubespawner/pull/369) ([@manics](https://github.com/manics))
- Add relevant badges to README.md [#365](https://github.com/jupyterhub/kubespawner/pull/365) ([@consideRatio](https://github.com/consideRatio))
- Update SETUP.md instructions to match current state of JupyterHub [#353](https://github.com/jupyterhub/kubespawner/pull/353) ([@yuvipanda](https://github.com/yuvipanda))
- codecov badge [#312](https://github.com/jupyterhub/kubespawner/pull/312) ([@choldgraf](https://github.com/choldgraf))
- Update documentation regarding run_as_gid behavior [#297](https://github.com/jupyterhub/kubespawner/pull/297) ([@kevin-bates](https://github.com/kevin-bates))
- build docs with python 3.6 [#295](https://github.com/jupyterhub/kubespawner/pull/295) ([@minrk](https://github.com/minrk))
- making kubespawner docs links more discoverable [#287](https://github.com/jupyterhub/kubespawner/pull/287) ([@choldgraf](https://github.com/choldgraf))

## [0.10]

### [0.10.1] 2018-12-11

0.10.1 is a tiny bugfix release, fixing regressions in 0.10.0.

- Fix deprecation of `KubeSpawner.hub_connect_ip`,
  which caused errors in 0.10 when the deprecated config was used.

### [0.10.1] 2018-12-05

0.10.0 is a small release, with minor changes and fixes.

- Deprecate `KubeSpawner.image_spec` configuration in favor of standard `KubeSpawner.image`. `image_spec` continues to work with deprecation warnings
- Stop pinning an exact kubernetes client version;
  instead, require kubernetes client >= 7.
  If desired, pinning should be done in images/installations
- Expand username template variables in extra_containers
- Set pod restart policy to OnFailure, so that notebook servers that terminate themselves cleanly do not restart automatically
- Formally deprecate ``KubeSpawner.hub_connect_ip`` and ``KubeSpawner.hub_connect_ip``
  in favor of ``JupyterHub.hub_connect_ip``,
  available in jupyterhub >= 0.8

## [0.9]

### [0.9.0] 2018-09-03

KubeSpawner 0.9.0 is a big release of KubeSpawner.

Change highlights:

- Require Kubernetes >= 1.6
- Require JupyterHub >= 0.8
- Require Python >= 3.5
- Expose lots more Kubernetes options
- Support configuration profiles via :attr:`.KubeSpawner.profile_list`
- Support Kubernetes events for the progress API in JupyterHub 0.9.
- Update Kubernetes Python client to 6.0 (supporting Kubernetes 1.10 APIs)
- Numerous bugfixes
