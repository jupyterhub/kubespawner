from jupyterhub.spawner import Spawner
from tornado import gen
from tornado.httputil import url_concat
from tornado.httpclient import AsyncHTTPClient
from kubespawner.utils import request_maker, k8s_url
from urllib.parse import urlparse, urlunparse
import json
import time
import string
from traitlets import Unicode, List, Integer


class KubeSpawner(Spawner):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # By now, all the traitlets have been set, so we can use them to compute
        # other attributes
        self.httpclient = AsyncHTTPClient()
        # FIXME: Support more than just kubeconfig
        self.request = request_maker()
        self.pod_name = self._expand_user_properties(self.pod_name_template)
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
        'default',
        config=True,
        help='Kubernetes Namespace to create pods in'
    )

    pod_name_template = Unicode(
        'jupyter-{username}-{userid}',
        config=True,
        help='Template to generate pod names. Supports: {user} for username'
    )

    hub_connect_ip = Unicode(
        "",
        config=True,
        help='IP that containers should use to contact the hub'
    )

    hub_connect_port = Integer(
        config=True,
        help='Port that containers should use to contact the hub. Defaults to the hub_port parameter'
    )

    def _hub_connect_port_default(self):
        return self.hub.server.port


    singleuser_image_spec = Unicode(
        'jupyter/singleuser',
        config=True,
        help='Name of Docker image to use when spawning user pods'
    )

    kube_termination_grace = Integer(
        0,
        config=True,
        help='Number of seconds to wait before terminating a pod'
    )

    cpu_limit = Unicode(
        "2000m",
        config=True,
        help='Max number of CPU cores that a single user can use'
    )

    cpu_request = Unicode(
        "200m",
        config=True,
        help='Min nmber of CPU cores that a single user is guaranteed'
    )

    mem_limit = Unicode(
        "1Gi",
        config=True,
        help='Max amount of memory a single user can use'
    )

    mem_request = Unicode(
        "128Mi",
        config=True,
        help='Min amount of memory a single user is guaranteed'
    )

    volumes = List(
        [],
        config=True,
        help='Config for volumes present in the spawned user pod.' +
             '{username} and {userid} are expanded.'
    )
    volume_mounts = List(
        [],
        config=True,
        help='Config for volume mounts in the spawned user pod.' +
             '{username} and {userid} are expanded.'
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
        # Add a hack to ensure that no service accounts are mounted in spawned pods
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

        return {
            'apiVersion': 'v1',
            'kind': 'Pod',
            'metadata': {
                'name': self.pod_name,
                'labels': {
                    'name': self.pod_name
                }
            },
            'spec': {
                'containers': [
                    {
                        'name': 'jupyter',
                        'image': self.singleuser_image_spec,
                        'ports': [
                            {
                                'containerPort': 8888,
                            }
                        ],
                        'resources': {
                            'requests': {
                                'memory': self.mem_request,
                                'cpu': self.cpu_request,
                            },
                            'limits': {
                                'memory': self.mem_limit,
                                'cpu': self.cpu_limit
                            }
                        },
                        'env': [
                            {'name': k, 'value': v}
                            for k, v in self.get_env().items()
                        ],
                        'volumeMounts': self._expand_all(self.volume_mounts) + hack_volume_mounts
                    }
                ],
                'volumes': self._expand_all(self.volumes) + hack_volumes
            }
        }

    @gen.coroutine
    def get_pod_info(self, pod_name):
        resp = yield self.httpclient.fetch(self.request(
            k8s_url(
                self.namespace,
                'pods',
                label_selector='name={name}'.format(name=self.pod_name)
            )
        ))
        data = resp.body.decode('utf-8')
        return json.loads(data)

    def is_pod_running(self, pod_info):
        return 'items' in pod_info and len(pod_info['items']) > 0 and \
            pod_info['items'][0]['status']['phase'] == 'Running'

    @gen.coroutine
    def poll(self):
        data = yield self.get_pod_info(self.pod_name)
        if self.is_pod_running(data):
            return None
        return 1

    @gen.coroutine
    def start(self):
        pod_manifest = self.get_pod_manifest()
        resp = yield self.httpclient.fetch(self.request(
            url=k8s_url(self.namespace, 'pods'),
            body=json.dumps(pod_manifest),
            method='POST',
            headers={'Content-Type': 'application/json'}
        ))
        while True:
            data = yield self.get_pod_info(self.pod_name)
            if self.is_pod_running(data):
                break
            time.sleep(5)
        self.user.server.ip = data['items'][0]['status']['podIP']
        self.user.server.port = 8888
        self.db.commit()

    @gen.coroutine
    def stop(self):
        body = {
            'kind': "DeleteOptions",
            'apiVersion': 'v1',
            'gracePeriodSeconds': self.kube_termination_grace
        }
        resp = yield self.httpclient.fetch(
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
        while True:
            data = yield self.get_pod_info(self.pod_name)
            if 'items' not in data or len(data['items']) == 0:
                break
            time.sleep(5)

    def _env_keep_default(self):
        return []

    def get_env(self):
        env = super(KubeSpawner, self).get_env()
        env.update(dict(
                    JPY_USER=self.user.name,
                    JPY_COOKIE_NAME=self.user.server.cookie_name,
                    JPY_BASE_URL=self.user.server.base_url,
                    JPY_HUB_PREFIX=self.hub.server.base_url,
                    JPY_HUB_API_URL=self.accessible_hub_api_url))
        return env
