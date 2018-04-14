# Setting up a dev environment #

## Setting up kubernetes for development ##
Setting up a dev environment to work with the Kubernetes Spawner can be a bit tricky,
since normally you'd run JupyterHub in a container in the kubernetes cluster itself.
But the dev cycle for that is longer than comfortable, since you've to rebuild
the container and redeploy.

There is an easier way, with minikube and some networking tricks. Only tested on Linux
at this time, but should work for OS X too.

1. Install [minikube](http://kubernetes.io/docs/getting-started-guides/minikube/). Use the
   [VirtualBox](https://virtualbox.org) provider. This will set up a kubernetes cluster inside
   a VM on your machine. It'll also setup `kubectl` on your host machine to interact with
   the kubernetes cluster, and a `~/.kube/config` file with credentials for connecting to this
   cluster.
2. Run `minikube start`. This will start your kubernetes cluster if it isn't already up. Run
   `kubectl get node` to make sure it is.
3.  Make it possible for your host to be able to talk to the pods on minikube.

    On Linux::

       sudo ip route add 172.17.0.0/16 via $(minikube ip)

    On OS X::

       sudo route -n add -net 172.17.0.0/16 $(minikube ip)

    If you get an error message like the following::

       RTNETLINK answers: File exists

    it most likely means you have docker running on your host using the same
    IP range minikube is using. You can fix this by editing your
    ``/etc/docker/daemon.json`` file to add the following:

    .. code-block:: json

       {
           "bip": "172.19.1.1/16"
       }

    If some JSON already exists in that file, make sure to just add the
    ``bip`` key rather than replace it all. The final file needs to be valid
    JSON.

    Once edited, restart docker with ``sudo systemctl restart docker``. It
    should come up using a different IP range, and you can run the
    ``sudo ip route add`` command again. Note that restarting docker will
    restart all your running containers by default.

## Setting up JupyterHub for development ##

Once you have kubernetes setup this way, you can stup JupyterHub for development fairly easily on your
host machine.

1. Clone this repository
2. Setup a virtualenv
   ```
   python3 -m venv .
   source bin/activate
   ```
3. Setup a dev installation of the kubernetes spawner:
   ```
   pip install jupyterhub-dummyauthenticator
   pip install -e .
   ```
4. Install the nodejs configurable HTTP proxy:
   ```
   sudo npm install -g configurable-http-proxy
   ```
5. You can now test run a jupyterhub with the kubernetes spawner by running:
   ```
   LINUX:
   export HUB_CONNECT_IP=`ip addr show vboxnet4 | grep 'scope global' | awk '{ print $2; }' | sed 's/\/.*$//'`

   MACOS:
   export HUB_CONNECT_IP=`ifconfig vboxnet4 | grep inet | awk '{ print $2; }' | sed 's/\/.*$//'`
   ```

   And then starting the Hub:
   ```
   jupyterhub --no-ssl
   ```

   The `jupyterhub_config.py` file that ships in this repo will read that environment variable to figure out what IP the pods should connect to the JupyterHub on. Replace `vboxnet4` with whatever interface name you used in step 4 of the previous section.

This will give you a running JupyterHub that spawns nodes inside the minikube VM! It'll be setup with [DummyAuthenticator](http://github.com/yuvipanda/jupyterhub-dummy-authenticator), so any user + password combo will allow you to log in. You can make changes to the spawner and restart jupyterhub, and rapidly iterate :)
