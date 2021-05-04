# Contributing

:sparkles: Thank you for thinking about contributing to kubespawner! :sparkles:

Welcome! As a [Jupyter](https://jupyter.org) project, we follow the [Jupyter contributor guide](https://jupyter.readthedocs.io/en/latest/contributor/content-contributor.html).

## Types of contribution

There are many ways to contribute to kubespawner, here are some of them:

- **Update the documentation.**
  If you're reading a page or docstring and it doesn't make sense (or doesn't exist!), please let us know by opening a bug report.
  It's even more amazing if you can give us a suggested change.
- **Fix bugs or add requested features.**
  Have a look through the [issue tracker](https://github.com/jupyterhub/kubespawner/issues) and see if there are any tagged as ["help wanted"](https://github.com/jupyterhub/kubespawner/issues?q=is%3Aissue+is%3Aopen+label%3A%22help+wanted%22).
  As the label suggests, we'd love your help!
- **Report a bug.**
  If kubespawner isn't doing what you thought it would do then open a [bug report](https://github.com/jupyterhub/kubespawner/issues/new).
  Please provide details on what you were trying to do, what goal you were trying to achieve and how we can reproduce the problem.
- **Suggest a new feature.**
  We know that there are lots of ways to extend kubespawner!
  If you're interested in adding a feature then please open a [feature request](https://github.com/jupyterhub/kubespawner/issues/new?template=feature_request.md).
  Try to explain what the feature is, what alternatives you have though about, what skills are required to work on this task and how big a task you estimate it to be.
- **Review someone's Pull Request.**
  Whenever somebody proposes changes to the kubespawner codebase, the community reviews
  the changes, and provides feedback, edits, and suggestions. Check out the
  [open pull requests](https://github.com/jupyterhub/kubespawner/pulls?q=is%3Apr+is%3Aopen+sort%3Aupdated-desc)
  and provide feedback that helps improve the PR and get it merged. Please keep your
  feedback positive and constructive!
- **Tell people about kubespawner.**
  Kubespawner is built by and for its community.
  If you know anyone who would like to use kubespawner, please tell them about the project!
  You could give a talk about it or run a demonstration or make a poster.
  The sky is the limit :rocket::star2:.

## Setting up for documentation changes

We use Sphinx to build the kubespawner documentation. You can make changes to
the documentation with any text editor and directly through the GitHub website.

For small changes (like typos) you do not need to setup anything locally. For
larger changes we recommend you build the documentation locally so you can see
the end product in its full glory.

To make edits through the GitHub website visit https://github.com/jupyterhub/kubespawner/tree/master/docs/source, open the file you would like to edit and then click "edit". GitHub will
walk you through the process of proposing your change ("making a Pull Request").

A brief guide to setting up for local development

```sh
git clone https://github.com/jupyterhub/kubespawner.git
cd kubespawner/docs
# create a new environment ...
conda create -n kubespawner --file environment.yml
# ... or update your environment
conda env update --file environment.yml
# activate the environment
conda activate kubespawner
# build the documentation
make html
```

## Setting up a local development environment

To work on kubespawner's code you can run JupyterHub locally on your computer,
using an editable installation of kubespawner, that interacts with pods in a
local kubernetes cluster!

You need to have a local kubernetes cluster and be able to edit networking
rules on your computer. We will now walk you through the steps to get going:

1.  Install VirtualBox by [downloading and running an
    installer](https://www.virtualbox.org/wiki/Downloads).

1.  Install
    [minikube](https://kubernetes.io/docs/tasks/tools/install-minikube/).

1.  Run `minikube start`. This will start your kubernetes cluster if it isn't
    already up. Run `kubectl get node` to make sure it is.

    Note that the `minikube start` command will also setup `kubectl` on your
    host machine to interact with the kubernetes cluster along with a
    `~/.kube/config` file with credentials for connecting to this cluster.

1.  Setup a networking route so that a program on your host can talk to the
    pods inside minikube.

    ```bash
    # Linux
    sudo ip route add 172.17.0.0/16 via $(minikube ip)
    # later on you can undo this with
    sudo ip route del 172.17.0.0/16

    # MACOS
    sudo route -n add -net 172.17.0.0/16 $(minikube ip)
    # later on you can undo this with
    sudo route delete -net 172.17.0.0
    ```

    ### Troubleshooting

    Got an error like below?

    ```
    RTNETLINK answers: File exists
    ```

    It most likely means you have Docker running on your host using the same
    IP range minikube is using. You can fix this by editing your
    `/etc/docker/daemon.json` file to add the following:

    ```json
    {
      "bip": "172.19.1.1/16"
    }
    ```

    If some JSON already exists in that file, make sure to just add the
    `bip` key rather than replace it all. The final file needs to be valid
    JSON.

    Once edited, restart docker with `sudo systemctl restart docker`. It
    should come up using a different IP range, and you can run the
    `sudo ip route add` command again. Note that restarting docker will
    restart all your running containers by default.

1.  Clone this repository

    ```sh
    git clone https://github.com/jupyterhub/kubespawner.git
    ```

1.  Setup a virtual environment. After cloning the repository, you should set up an
    isolated environment to install libraries required for running / developing
    kubespawner.

    There are many ways of doing this: conda envs, virtualenv, pipenv, etc. Pick
    your favourite. We show you how to use venv:

    ```sh
    cd kubespawner

    python3 -m venv .
    source bin/activate
    ```

1.  Install a locally editable version of kubespawner and its dependencies for
    running it and testing it.

    ```sh
    pip install -e ".[test]"
    ```

1.  Install the nodejs based [Configurable HTTP Proxy
    (CHP)](https://github.com/jupyterhub/configurable-http-proxy), and make it
    accessible to JupyterHub.

    ```sh
    npm install configurable-http-proxy
    export PATH=$(pwd)/node_modules/.bin:$PATH
    ```

1.  Start JupyterHub

    ```sh
    # Run this from the repo's root directory where the preconfigured
    # jupyterhub_config.py file resides!
    jupyterhub
    ```

1.  Visit [http://localhost:8000/](http://localhost:8000/)!

You should now have a JupyterHub running directly on your computer outside of
the Kubernetes cluster, using a locally editable kubespawner code base. The
JupyterHub is setup with
[DummyAuthenticator](http://github.com/yuvipanda/jupyterhub-dummy-authenticator),
so any user + password combination will allow you to log in. You can make changes to
kubespawner and restart the jupyterhub, and rapidly iterate :)

## Running tests

To run our automated test-suite you need to have a local development setup.

Run all tests with:

```sh
pytest
```

### Troubleshooting

If you a huge amount of errors, make sure your minikube is up and running and see it if helps to clear your .eggs
directory.

```sh
rm -rf .eggs
```
