# How to make a release

`jupyterhub-kubespawner` is a package [available on
PyPI](https://pypi.org/project/jupyterhub-kubespawner/). These are instructions
on how to make a release on PyPI.

For you to follow along according to these instructions, you need:
- To have push rights to the [kubespawner GitHub
  repository](https://github.com/jupyterhub/kubespawner).

## Steps to make a release

1. Update [CHANGELOG.md](CHANGELOG.md) if it is not up to date. Make a PR to
   review the CHANGELOG notes.

1. Once the changelog is up to date, checkout master and make sure it is up to date and clean.

   ```bash
   ORIGIN=${ORIGIN:-origin} # set to the canonical remote, e.g. 'upstream' if 'origin' is not the official repo
   git checkout master
   git fetch $ORIGIN master
   git reset --hard $ORIGIN/master
   # WARNING! This next command deletes any untracked files in the repo
   git clean -xfd
   ```

1. Update the version with `bump2version`.

   ```bash
   VERSION=...  # e.g. 1.2.3
   bump2version --tag --new-version $VERSION -
   ```

1. Reset the version to the next development version with `bump2version`

   ```bash
   bump2version --no-tag patch
   ```

1. Push your two commits to master along with the annotated tags referencing
   commits on master. TravisCI will trigger automatic deployment of the pushed
   tag.

   ```
   git push --follow-tags $ORIGIN master
   ```
