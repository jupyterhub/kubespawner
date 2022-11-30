# How to make a release

`jupyterhub-kubespawner` is a package available on [PyPI][] and [conda-forge][].
These are instructions on how to make a release.

## Pre-requisites

- Push rights to [github.com/jupyterhub/kubespawner][]
- Push rights to [conda-forge/jupyterhub-kubespawner-feedstock][]

## Steps to make a release

1. Create a PR updating `docs/source/changelog.md` with [github-activity][] and
   continue only when its merged.

1. Checkout main and make sure it is up to date.

   ```shell
   git checkout main
   git fetch origin main
   git reset --hard origin/main
   ```

1. Update the version, make commits, and push a git tag with `tbump`.

   ```shell
   pip install tbump
   tbump --dry-run ${VERSION}

   # run
   tbump ${VERSION}
   ```

   Following this, the [CI system][] will build and publish a release.

1. Reset the version back to dev, e.g. `2.0.1.dev0` after releasing `2.0.0`.

   ```shell
   tbump --no-tag ${NEXT_VERSION}.dev0
   ```

1. Following the release to PyPI, an automated PR should arrive to
   [conda-forge/jupyterhub-kubespawner-feedstock][] with instructions.

[github-activity]: https://github.com/executablebooks/github-activity
[github.com/jupyterhub/kubespawner]: https://github.com/jupyterhub/kubespawner
[pypi]: https://pypi.org/project/jupyterhub-kubespawner/
[conda-forge]: https://anaconda.org/conda-forge/jupyterhub-kubespawner
[conda-forge/jupyterhub-kubespawner-feedstock]: https://github.com/conda-forge/jupyterhub-kubespawner-feedstock
[ci system]: https://github.com/jupyterhub/kubespawner/actions/workflows/publish.yaml
