# How to make a release

`jupyterhub-kubespawner` is a package [available on
PyPI](https://pypi.org/project/jupyterhub-kubespawner/). These are instructions
on how to make a release on PyPI.

For you to follow along according to these instructions, you need:

- To have push rights to the [kubespawner GitHub
  repository](https://github.com/jupyterhub/kubespawner).

## Steps to make a release

1. Update [CHANGELOG.md](CHANGELOG.md). Doing this can be made easier with the
   help of the
   [choldgraf/github-activity](https://github.com/choldgraf/github-activity)
   utility to list merged PRs and generate a list of contributors.

   ```bash
   github-activity jupyterhub/kubespawner --output tmp-changelog-prep.md
   ```

1. Once the changelog is up to date, checkout master and make sure it is up to date and clean.

   ```bash
   ORIGIN=${ORIGIN:-origin} # set to the canonical remote, e.g. 'upstream' if 'origin' is not the official repo
   git checkout master
   git fetch $ORIGIN master
   git reset --hard $ORIGIN/master
   # WARNING! This next command deletes any untracked files in the repo
   git clean -xfd
   ```

1. Update version and tag, and return to a dev version, with `bump2version`.

   ```bash
   VERSION=...  # e.g. 1.2.3
   bump2version --tag --new-version $VERSION -
   bump2version --no-tag patch

   # verify tags, commits, and version tagged
   git log
   ```

1. Push your two commits to master along with the annotated tags referencing
   commits on master. TravisCI will trigger automatic deployment of the pushed
   tag.

   ```bash
   # pushing the commits standalone allows you to
   # ensure you don't end up only pushing the tag
   # because the commit were rejected but the tag
   # wasn't
   git push $ORIGIN master

   # if you could push the commits without issues
   # go ahead and push the tag also
   git push --follow-tags $ORIGIN master
   ```

1. Verify that [the GitHub
   workflow](https://github.com/jupyterhub/kubespawner/actions?query=workflow%3APublish)
   triggers and succeeds and that that PyPI received a [new
   release](https://pypi.org/project/jupyterhub-kubespawner/).
