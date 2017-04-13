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
3. Run `minikube stop`. This will stop the VM, allowing us to perform some amount of surgery
   on it to setup networking as we want.
4. Run `VBoxManage hostonlyif create`. This will create a network interface to communicate
   between your VM and your host. Note the output of this command - it will mention the name of
   your hostonly interface. For example, your output might be:
   
   ```
   Interface 'vboxnet4' was successfully created
   ```
   
   In this case, our interface name is `vboxnet4`.
5. Run the following command on your host
   ```
   VBoxManage modifyvm  minikube --nic3 hostonly --cableconnected3 on --hostonlyadapter3 vboxnet4
   ```
   Instead of `vboxnet4` use whatever the output from step 4 was.
6. Start up minikube again with `minikube start`.
7. Now the containers running on kubernetes can connect to your host, via the IP address for `vboxnet4`
   interface. You can find this IP with: 
   ```
   LINUX:
   ip addr show vboxnet4 | grep 'scope global' | awk '{ print $2; }' | sed 's/\/.*$//'

   MACOS:
   ifconfig vboxnet4 | grep inet | awk '{ print $2; }' | sed 's/\/.*$//'
   ```
   Substituting vboxnet4 with whatever was the output of step 4.
8. Now, we need to be able to access pod ips from your host. We can do this by adding a static route
   directly on your host. First we delete any existing routes for 172.17.0.0/16 (which is the pod network),
   with:
   ```
   sudo ip route delete 172.17.0.0/16
   ```
   Note that if you had docker installed on your host, this *will* futz with it! You might have to stop
   the docker daemon before doing it. Restarting the docker daemon should bring it back to working order,
   however.
   
   Then, we can add a static route that routes all pod traffic to the virtual machine, with:
   ```
   LINUX:
   sudo ip route add 172.17.0.0/16 via $(minikube ip)

   MACOS:
   sudo route -n add -net 172.17.0.0/16 $(minikube ip)
   ```
   
TADA! Now you have a kubernetes cluster that has two way communication with your host! This lets you
run JupyterHub on your host (for faster development) while spawning pods inside Kubernetes in the
VM.
   
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

Note for MacOS/OS X: There is some known issues with Curl on MacOS (https://github.com/curl/curl/issues/283)so you might need to set the HttpClient in the `jupyterhub_config.py` like this:

```python
from tornado.simple_httpclient import SimpleAsyncHTTPClient
c.KubeSpawner.httpclient_class = SimpleAsyncHTTPClient
```
