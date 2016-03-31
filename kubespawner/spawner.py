from jupyterhub.spawner import Spawner
from tornado import gen
from requests_futures.sessions import FuturesSession
import json
import time
import string
from traitlets import Unicode, List, Integer, Dict


class UnicodeOrFalse(Unicode):
    info_text = 'a unicode string or False'

    def validate(self, obj, value):
        if value is False:
            return value
        return super(UnicodeOrFalse, self).validate(obj, value)


class KubeSpawner(Spawner):
    kube_api_endpoint = Unicode(
        config=True,
        help='Endpoint to use for kubernetes API calls'
    )

    kube_api_version = Unicode(
        'v1',
        config=True,
        help='Kubernetes API version to use'
    )

    kube_namespace = Unicode(
        'jupyter',
        config=True,
        help='Kubernetes Namespace to create pods in'
    )

    pod_name_template = Unicode(
        'jupyter-{username}-{userid}',
        config=True,
        help='Template to generate pod names. Supports: {user} for username'
    )

    hub_ip_connect = Unicode(
        "",
        config=True,
        help='Endpoint that containers should use to contact the hub'
    )

    kube_ca_path = UnicodeOrFalse(
        '/var/run/secrets/kubernetes.io/serviceaccount/ca.crt',
        config=True,
        help='Path to the CA crt to use to connect to the kube API server'
    )

    kube_token = Unicode(
        config=True,
        help='Kubernetes API authorization token'
    )

    def _kube_token_default(self):
        try:
            with open('/var/run/secrets/kubernetes.io/serviceaccount/token') as f:
                return f.read().strip()
        except:
            return ''

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

    extra_env = Dict(
        {},
        config=True,
        help='Extra environment variables to be added to the user environments. ' +
             'Values can be simple strings or a callable that will be called ' +
             'with current spawner instance as a parameter to produce a string.'
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
        # Allow environment variables to contain callable functions,
        # which can get info about current spawner state and set up
        # accordingly
        realized_env = self.env.copy()
        for k, v in self.extra_env.items():
            if callable(v):
                realized_env[k] = v(self)
            else:
                realized_env[k] = v
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
                            for k, v in realized_env.items()
                        ],
                        'volumeMounts': self._expand_all(self.volume_mounts)
                    }
                ],
                'volumes': self._expand_all(self.volumes)
            }
        }

    def _get_pod_url(self, pod_name=None):
        url = '{host}/api/{version}/namespaces/{namespace}/pods'.format(
            host=self.kube_api_endpoint,
            version=self.kube_api_version,
            namespace=self.kube_namespace
        )
        if pod_name:
            return url + '/' + pod_name
        return url

    @property
    def session(self):
        if hasattr(self, '_session'):
            return self._session
        else:
            self._session = FuturesSession()
            auth_header = 'Bearer %s' % self.kube_token
            self._session.headers['Authorization'] = auth_header
            self._session.verify = self.kube_ca_path
            return self._session

    def load_state(self, state):
        super(KubeSpawner, self).load_state(state)

    def get_state(self):
        state = super(KubeSpawner, self).get_state()
        state['hi'] = 'hello'
        return state

    @gen.coroutine
    def get_pod_info(self, pod_name):
        resp = self.session.get(
            self._get_pod_url(),
            params={'labelSelector': 'name = %s' % pod_name})
        data = yield resp
        return data.json()

    def is_pod_running(self, pod_info):
        return 'items' in pod_info and len(pod_info['items']) > 0 and \
            pod_info['items'][0]['status']['phase'] == 'Running' and \
            pod_info['items'][0]['status']['conditions'][0]['type'] == 'Ready'

    @property
    def pod_name(self):
        return self._expand_user_properties(self.pod_name_template)

    @gen.coroutine
    def poll(self):
        data = yield self.get_pod_info(self.pod_name)
        if self.is_pod_running(data):
            return None
        return 1

    @gen.coroutine
    def start(self):
        pod_manifest = self.get_pod_manifest()
        resp = yield self.session.post(
            self._get_pod_url(),
            data=json.dumps(pod_manifest))
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
        resp = yield self.session.delete(self._get_pod_url(self.pod_name), data=json.dumps(body))
        while True:
            data = yield self.get_pod_info(self.pod_name)
            if 'items' not in data or len(data['items']) == 0:
                break
            time.sleep(5)

    def _public_hub_api_url(self):
        if self.hub_ip_connect:
            proto, path = self.hub.api_url.split('://', 1)
            ip, rest = path.split('/', 1)
            return '{proto}://{ip}/{rest}'.format(
                    proto=proto,
                    ip=self.hub_ip_connect,
                    rest=rest
                )
        else:
            return self.hub.api_url

    def _env_keep_default(self):
        return []

    def get_env(self):
        env = super(KubeSpawner, self).get_env()
        env.update(dict(
                    JPY_USER=self.user.name,
                    JPY_COOKIE_NAME=self.user.server.cookie_name,
                    JPY_BASE_URL=self.user.server.base_url,
                    JPY_HUB_PREFIX=self.hub.server.base_url,
                    JPY_HUB_API_URL=self._public_hub_api_url()
                ))
        return env
