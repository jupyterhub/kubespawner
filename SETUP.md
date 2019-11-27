# Setting up a development environment

## Setting up Kubernetes for development
Setting up a dev environment to work with the Kubernetes Spawner can be a bit
tricky, since normally you'd run JupyterHub in a container in the Kubernetes
cluster itself. But the dev cycle for that is longer than comfortable, since
you've to rebuild the container and redeploy.

There is an easier way, with minikube and some networking tricks. We can run
JupyterHub locally on your computer, using an editable installation of
kubespawner, that interacts with pods in a kubernetes cluster!

1.  Install VirtualBox by [downloading and running an
    installer](https://www.virtualbox.org/wiki/Downloads).

2.  Install
    [minikube](https://kubernetes.io/docs/tasks/tools/install-minikube/).

3.  Run `minikube start`. This will start your kubernetes cluster if it isn't
    already up. Run `kubectl get node` to make sure it is.
    
    Note that the `minikube start` command will also setup `kubectl` on your
    host machine to interact with the kubernetes cluster along with a
    `~/.kube/config` file with credentials for connecting to this cluster. 

4.  Make it possible for your host to talk to the pods on minikube.

    ```bash
    # Linux
    sudo ip route add 172.17.0.0/16 via $(minikube ip)
    
    # MACOS
    sudo route -n add -net 172.17.0.0/16 $(minikube ip)
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

## Setting up JupyterHub for development

Once you have Kubernetes setup this way, you can setup JupyterHub for
development fairly easily on your host machine.

1. Clone this repository
   ```sh
   git clone https://github.com/jupyterhub/kubespawner.git
   ```

2. Setup a virtualenv
   ```sh
   cd kubespawner

   python3 -m venv .
   source bin/activate
   ```

3. Install a locally editable version of kubespawner and dependencies for
   running it and testing it.
   ```sh
   pip install -e .[test]
   ```

4. Install the nodejs based [Configurable HTTP Proxy
   (CHP)](https://github.com/jupyterhub/configurable-http-proxy), and make it
   accessible to JupyterHub.

   ```sh
   npm install configurable-http-proxy
   export PATH=$(pwd)/node_modules/.bin:$PATH
   ```

6. Start JupyterHub
   ```sh
   # Run this from the repo's root directory where the preconfigured
   # jupyterhub_config.py file resides!
   jupyterhub
   ```

7. Try visit [http://localhost:8000/](http://localhost:8000/)!

You should now have a JupyterHub running directly on your computer outside of
the Kubernetes cluster, using a locally editable kubespawner code base. It'll is
setup with
[DummyAuthenticator](http://github.com/yuvipanda/jupyterhub-dummy-authenticator),
so any user + password combo will allow you to log in. You can make changes to
the spawner and restart jupyterhub, and rapidly iterate :)

## Running tests

```sh
pytest
```

### Troubleshooting
If you a huge amount of errors, make sure your minikube is up and running and see it if helps to clear your .eggs
directory.

```sh
rm -rf .eggs
```

## Build documentation
```sh
cd docs
conda env update --file environment.yml
conda activate kubespawner
make html
```
