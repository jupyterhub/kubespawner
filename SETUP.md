# Setting up a development environment

## Setting up Kubernetes for development
Setting up a dev environment to work with the Kubernetes Spawner can be a bit
tricky, since normally you'd run JupyterHub in a container in the Kubernetes
cluster itself. But the dev cycle for that is longer than comfortable, since
you've to rebuild the container and redeploy.

There is an easier way, with minikube and some networking tricks. Only tested on
Linux at this time, but should work for OS X too.

1.  Install [minikube](http://kubernetes.io/docs/getting-started-guides/minikube/). Use the
    [VirtualBox](https://virtualbox.org) provider. This will set up a kubernetes cluster inside
    a VM on your machine.

2.  Run `minikube start`. This will start your kubernetes cluster if it isn't
    already up. Run `kubectl get node` to make sure it is.
    
    Note that the `minikube start` command will also setup `kubectl` on your
    host machine to interact with the kubernetes cluster along with a
    `~/.kube/config` file with credentials for connecting to this cluster. 

3.  Make it possible for your host to talk to the pods on minikube.

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
   # Clone over HTTPS
   https://github.com/v3io/kubespawner.git

   # Clone over SSH
   git clone git@github.com:v3io/kubespawner.git
   ```

2. Setup a virtualenv
   ```sh
   cd kubespawner

   python3 -m venv .
   source bin/activate
   ```

3. Setup a development installation of the Kubernetes spawner:
   ```sh
   pip install jupyterhub jupyterhub-dummyauthenticator
   pip install -e .
   ```

4. Install the nodejs configurable HTTP proxy:
   ```sh
   sudo npm install -g configurable-http-proxy
   ```

5. Ensure user pods can communicate with the hub:
   ```sh
   # LINUX:
   export HUB_CONNECT_IP=`ip addr show vboxnet0 | grep 'scope global' | awk '{ print $2; }' | sed 's/\/.*$//'`

   # MACOS:
   export HUB_CONNECT_IP=`ifconfig vboxnet0 | grep inet | awk '{ print $2; }' | sed 's/\/.*$//'`
   ```

   JupyterHub will read that environment variable and use it to tell the spawned
   user pods to connect to communicate with JupyterHub on that address.

6. Start JupyterHub and start spawning user pods your Kubernetes cluster:
   ```sh
   # Make sure jupyterhub finds the provided jupyterhub_config.py and run this
   # from the repo's root directory.
   jupyterhub --no-ssl
   ```

   The `jupyterhub_config.py` file that ships in this repo will read that environment variable to figure out what IP the pods should connect to the JupyterHub on. Replace `vboxnet4` with whatever interface name you used in step 4 of the previous section.

   This will give you a running JupyterHub that spawns nodes inside the minikube VM! It'll be setup with [DummyAuthenticator](http://github.com/yuvipanda/jupyterhub-dummy-authenticator), so any user + password combo will allow you to log in. You can make changes to the spawner and restart jupyterhub, and rapidly iterate :)

## Running tests

```sh
python setup.py test
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
