"""
JupyterHub Spawner to spawn user notebooks on a Kubernetes cluster.

This module exports `KubeSpawner` class, which is the actual spawner
implementation that should be used by JupyterHub.
"""
import os
import json
import string
from urllib.parse import urlparse, urlunparse

from tornado import gen
from tornado.httpclient import AsyncHTTPClient, HTTPError
from traitlets import Unicode, List, Integer, Float
from jupyterhub.spawner import Spawner

from kubespawner.utils import request_maker, k8s_url
from kubespawner.objects import make_pod_spec, make_pvc_spec


class KubeSpawner(Spawner):
    """
    Implement a JupyterHub spawner to spawn pods in a Kubernetes Cluster.

    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # By now, all the traitlets have been set, so we can use them to compute
        # other attributes
        self.httpclient = AsyncHTTPClient()
        # FIXME: Support more than just kubeconfig
        self.request = request_maker()
        self.pod_name = self._expand_user_properties(self.pod_name_template)
        self.pvc_name = self._expand_user_properties(self.pvc_name_template)
        if self.hub_connect_ip:
            scheme, netloc, path, params, query, fragment = urlparse(self.hub.api_url)
            netloc = '{ip}:{port}'.format(
                ip=self.hub_connect_ip,
                port=self.hub_connect_port,
            )
            self.accessible_hub_api_url = urlunparse((scheme, netloc, path, params, query, fragment))
        else:
            self.accessible_hub_api_url = self.hub.api_url

    namespace = Unicode(
        config=True,
        help="""
        Kubernetes namespace to spawn user pods in.

        If running inside a kubernetes cluster with service accounts enabled,
        defaults to the current namespace. If not, defaults to 'default'
        """
    )

    def _namespace_default(self):
        """
        Set namespace default to current namespace if running in a k8s cluster

        If not in a k8s cluster with service accounts enabled, default to
        'default'
        """
        ns_path = '/var/run/secrets/kubernetes.io/serviceaccount/namespace'
        if os.path.exists(ns_path):
            with open(ns_path) as f:
                return f.read().strip()
        return 'default'

    pod_name_template = Unicode(
        'jupyter-{username}-{userid}',
        config=True,
        help="""
        Template to use to form the name of user's pods.

        {username} and {userid} are expanded to the escaped, dns-label safe
        username & integer user id respectively.

        This must be unique within the namespace the pods are being spawned
        in, so if you are running multiple jupyterhubs spawning in the
        same namespace, consider setting this to be something more unique.
        """
    )

    pvc_name_template = Unicode(
        'claim-{username}-{userid}',
        config=True,
        help="""
        Template to use to form the name of user's pvc.

        {username} and {userid} are expanded to the escaped, dns-label safe
        username & integer user id respectively.

        This must be unique within the namespace the pvc are being spawned
        in, so if you are running multiple jupyterhubs spawning in the
        same namespace, consider setting this to be something more unique.
        """
    )

    hub_connect_ip = Unicode(
        None,
        config=True,
        allow_none=True,
        help="""
        IP/DNS hostname to be used by pods to reach out to the hub API.

        Defaults to `None`, in which case the `hub_ip` config is used.

        In kubernetes contexts, this is often not the same as `hub_ip`,
        since the hub runs in a pod which is fronted by a service. This IP
        should be something that pods can access to reach the hub process.
        This can also be through the proxy - API access is authenticated
        with a token that is passed only to the hub, so security is fine.

        Usually set to the service IP / DNS name of the service that fronts
        the hub pod (deployment/replicationcontroller/replicaset)

        Used together with `hub_connect_port` configuration.
        """
    )

    hub_connect_port = Integer(
        config=True,
        help="""
        Port to use by pods to reach out to the hub API.

        Defaults to be the same as `hub_port`.

        In kubernetes contexts, this is often not the same as `hub_port`,
        since the hub runs in a pod which is fronted by a service. This
        allows easy port mapping, and some systems take advantage of it.

        This should be set to the `port` attribute of a service that is
        fronting the hub pod.
        """
    )

    def _hub_connect_port_default(self):
        """
        Set default port on which pods connect to hub to be the hub port

        The hub needs to be accessible to the pods at this port. We default
        to the port the hub is listening on. This would be overriden in case
        some amount of port mapping is happening.
        """
        return self.hub.server.port

    singleuser_image_spec = Unicode(
        'jupyter/singleuser:latest',
        config=True,
        help="""
        Docker image spec to use for spawning user's containers.

        Defaults to `jupyter/singleuser:latest`

        Name of the container + a tag, same as would be used with
        a `docker pull` command. If tag is set to `latest`, kubernetes will
        check the registry each time a new user is spawned to see if there
        is a newer image available. If available, new image will be pulled.
        Note that this could cause long delays when spawning, especially
        if the image is large. If you do not specify a tag, whatever version
        of the image is first pulled on the node will be used, thus possibly
        leading to inconsistent images on different nodes. For all these
        reasons, it is recommended to specify a specific immutable tag
        for the imagespec.

        If your image is very large, you might need to increase the timeout
        for starting the single user container from the default. You can
        set this with:

        ```
        c.KubeSpawner.start_timeout = 60 * 5  # Upto 5 minutes
        ```
        """
    )

    volumes = List(
        [],
        config=True,
        help="""
        List of Kubernetes Volume specifications that will be mounted in the user pod.

        This list will be directly added under `volumes` in the kubernetes pod spec,
        so you should use the same structure. Each item in the list must have the
        following two keys:
          - name
            Name that'll be later used in the `volume_mounts` config to mount this
            volume at a specific path.
          - <name-of-a-supported-volume-type> (such as `hostPath`, `persistentVolumeClaim`,
            etc)
            The key name determines the type of volume to mount, and the value should
            be an object specifying the various options available for that kind of
            volume.

        See http://kubernetes.io/docs/user-guide/volumes/ for more information on the
        various kinds of volumes available and their options. Your kubernetes cluster
        must already be configured to support the volume types you want to use.

        {username} and {userid} are expanded to the escaped, dns-label safe
        username & integer user id respectively, wherever they are used.
        """
    )

    volume_mounts = List(
        [],
        config=True,
        help="""
        List of paths on which to mount volumes in the user notebook's pod.

        This list will be added to the values of the `volumeMounts` key under the user's
        container in the kubernetes pod spec, so you should use the same structure as that.
        Each item in the list should be a dictionary with at least these two keys:
          - mountPath
            The path on the container in which we want to mount the volume.
          - name
            The name of the volume we want to mount, as specified in the `volumes`
            config.

        See http://kubernetes.io/docs/user-guide/volumes/ for more information on how
        the volumeMount item works.

        {username} and {userid} are expanded to the escaped, dns-label safe
        username & integer user id respectively, wherever they are used.
        """
    )

    user_storage_capacity = Unicode(
        None,
        config=True,
        allow_none=True,
        help="""
        The ammount of storage space to request from the volume that the pvc will
        mount to. This ammount will be the ammount of storage space the user has
        to work with on their notebook. If left blank, the kubespawner will not
        create a pvc for the pod.

        This will be added to the `resources: requests: storage:` in the k8s pod spec.

        See http://kubernetes.io/docs/user-guide/persistent-volumes/#persistentvolumeclaims
        for more information on how storage works.

        Quantities can be represented externally as unadorned integers, or as fixed-point
        integers with one of these SI suffices (E, P, T, G, M, K, m) or their power-of-two
        equivalents (Ei, Pi, Ti, Gi, Mi, Ki). For example, the following represent roughly
        'the same value: 128974848, "129e6", "129M" , "123Mi".
        (https://github.com/kubernetes/kubernetes/blob/master/docs/design/resources.md)
        """
    )

    user_storage_class = Unicode(
        None,
        config=True,
        allow_none=True,
        help="""
        The storage class that the pvc will use. If left blank, the kubespawner will not
        create a pvc for the pod.

        This will be added to the `annotations: volume.beta.kubernetes.io/storage-class:`
        in the pvc metadata.

        This will determine what type of volume the pvc will request to use. If one exists
        that matches the criteria of the StorageClass, the pvc will mount to that. Otherwise,
        b/c it has a storage class, k8s will dynamicallly spawn a pv for the pvc to bind to
        and a machine in the cluster for the pv to bind to.

        See http://kubernetes.io/docs/user-guide/persistent-volumes/#storageclasses for
        more information on how StorageClasses work.
        """
    )

    user_storage_access_modes = List(
        ["ReadWriteOnce"],
        config=True,
        help="""
        List of access modes the user has for the pvc.

        The access modes are:
            The access modes are:
                ReadWriteOnce – the volume can be mounted as read-write by a single node
                ReadOnlyMany – the volume can be mounted read-only by many nodes
                ReadWriteMany – the volume can be mounted as read-write by many nodes

        See http://kubernetes.io/docs/user-guide/persistent-volumes/#access-modes for
        more information on how access modes work.
        """
    )

    def _expand_user_properties(self, template):
        # Make sure username matches the restrictions for DNS labels
        safe_chars = set(string.ascii_lowercase + string.digits)
        safe_username = ''.join([s if s in safe_chars else '-' for s in self.user.name.lower()])
        return template.format(
            userid=self.user.id,
            username=safe_username
        )

    def _expand_all(self, src):
        if isinstance(src, list):
            return [self._expand_all(i) for i in src]
        elif isinstance(src, dict):
            return {k: self._expand_all(v) for k, v in src.items()}
        elif isinstance(src, str):
            return self._expand_user_properties(src)
        else:
            return src

    def get_pod_manifest(self):
        """
        Make a pod manifest that will spawn current user's notebook pod.
        """
        # Add a hack to ensure that no service accounts are mounted in spawned pods
        # This makes sure that we don't accidentally give access to the whole
        # kubernetes API to the users in the spawned pods.
        # See https://github.com/kubernetes/kubernetes/issues/16779#issuecomment-157460294
        hack_volumes = [{
            'name': 'no-api-access-please',
            'emptyDir': {}
        }]
        hack_volume_mounts = [{
            'name': 'no-api-access-please',
            'mountPath': '/var/run/secrets/kubernetes.io/serviceaccount',
            'readOnly': True
        }]
        return make_pod_spec(
            self.pod_name,
            self.singleuser_image_spec,
            self.get_env(),
            self._expand_all(self.volumes) + hack_volumes,
            self._expand_all(self.volume_mounts) + hack_volume_mounts,
            self.cpu_limit,
            self.cpu_guarantee,
            self.mem_limit,
            self.mem_guarantee,
        )

    def get_pvc_manifest(self):
        """
        Make a pvc manifest that will spawn current user's pvc.
        """
        return make_pvc_spec(
            self.pvc_name,
            self.user_storage_class,
            self.user_storage_access_modes,
            self.user_storage_capacity
        )


    @gen.coroutine
    def get_pod_info(self, pod_name):
        """
        Fetch info about a specific pod with the given pod name in current namespace

        Return `None` if pod with given name does not exist in current namespace
        """
        try:
            response = yield self.httpclient.fetch(self.request(
                k8s_url(
                    self.namespace,
                    'pods',
                    pod_name,
                )
            ))
        except HTTPError as e:
            if e.code == 404:
                return None
            raise
        data = response.body.decode('utf-8')
        return json.loads(data)

    @gen.coroutine
    def get_pvc_info(self, pvc_name):
        """
        Fetch info about a specific pvc with the given pvc name in current namespace

        Return `None` if pvc with given name does not exist in current namespace
        """
        try:
            response = yield self.httpclient.fetch(self.request(
                k8s_url(
                    self.namespace,
                    'persistentvolumeclaims',
                    pvc_name,
                )
            ))
        except HTTPError as e:
            if e.code == 404:
                return None
            raise
        data = response.body.decode('utf-8')
        return json.loads(data)

    def is_pod_running(self, pod):
        """
        Check if the given pod is running

        pod must be a dictionary representing a Pod kubernetes API object.
        """
        return pod['status']['phase'] == 'Running'

    def get_state(self):
        """
        Save state required to reinstate this user's pod from scratch

        We save the pod_name, even though we could easily compute it,
        because JupyterHub requires you save *some* state! Otherwise
        it assumes your server is dead. This works around that.

        It's also useful for cases when the pod_template changes between
        restarts - this keeps the old pods around.
        """
        state = super().get_state()
        state['pod_name'] = self.pod_name
        return state

    def load_state(self, state):
        """
        Load state from storage required to reinstate this user's pod

        Since this runs after __init__, this will override the generated pod_name
        if there's one we have saved in state. These are the same in most cases,
        but if the pod_template has changed in between restarts, it will no longer
        be the case. This allows us to continue serving from the old pods with
        the old names.
        """
        if 'pod_name' in state:
            self.pod_name = state['pod_name']

    @gen.coroutine
    def poll(self):
        """
        Check if the pod is still running.

        Returns None if it is, and 1 if it isn't. These are the return values
        JupyterHub expects.
        """
        data = yield self.get_pod_info(self.pod_name)
        if data is not None and self.is_pod_running(data):
            return None
        return 1

    @gen.coroutine
    def start(self):
        if self.user_storage_class is not None and self.user_storage_capacity is not None:
            pvc_manifest = self.get_pvc_manifest()
            try:
                yield self.httpclient.fetch(self.request(
                    url=k8s_url(self.namespace, 'persistentvolumeclaims'),
                    body=json.dumps(pvc_manifest),
                    method='POST',
                    headers={'Content-Type': 'application/json'}
                ))
            except:
                self.log.info("Pvc " + self.pvc_name + " already exists, so did not create new pod.")
        pod_manifest = self.get_pod_manifest()
        yield self.httpclient.fetch(self.request(
            url=k8s_url(self.namespace, 'pods'),
            body=json.dumps(pod_manifest),
            method='POST',
            headers={'Content-Type': 'application/json'}
        ))
        while True:
            data = yield self.get_pod_info(self.pod_name)
            if data is not None and self.is_pod_running(data):
                break
            yield gen.sleep(1)
        self.user.server.ip = data['status']['podIP']
        self.user.server.port = 8888
        self.db.commit()

    @gen.coroutine
    def stop(self, now=False):
        body = {
            'kind': "DeleteOptions",
            'apiVersion': 'v1',
            'gracePeriodSeconds': 0
        }
        yield self.httpclient.fetch(
            self.request(
                url=k8s_url(self.namespace, 'pods', self.pod_name),
                method='DELETE',
                body=json.dumps(body),
                headers={'Content-Type': 'application/json'},
                # Tornado's client thinks DELETE requests shouldn't have a body
                # which is a bogus restriction
                allow_nonstandard_methods=True,
            )
        )
        if not now:
            # If now is true, just return immediately, do not wait for
            # shut down to complete
            while True:
                data = yield self.get_pod_info(self.pod_name)
                if data is None:
                    break
                yield gen.sleep(1)

    def _env_keep_default(self):
        return []

    def get_env(self):
        env = super(KubeSpawner, self).get_env()
        env.update({
            'JPY_USER': self.user.name,
            'JPY_COOKIE_NAME': self.user.server.cookie_name,
            'JPY_BASE_URL': self.user.server.base_url,
            'JPY_HUB_PREFIX': self.hub.server.base_url,
            'JPY_HUB_API_URL': self.accessible_hub_api_url
        })
        return env
