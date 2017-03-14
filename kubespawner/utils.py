"""
Misc. general utility functions, not tied to Kubespawner directly
"""
import os
import yaml

from tornado.httpclient import HTTPRequest
from traitlets import TraitType


def request_maker():
    """
    Return a k8s api aware HTTPRequest factory that autodiscovers connection info
    """
    if os.path.exists('/var/run/secrets/kubernetes.io/serviceaccount/token'):
        # We are running in a pod, and have access to a service account!
        return request_maker_serviceaccount()
    else:
        return request_maker_kubeconfig()


def request_maker_serviceaccount():
    """
    Return a k8s api aware HTTPRequest factory that discovers connection info from a service account

    Discovers the hostname, port, protocol & authentication details for talking to
    the kubernetes API from a ServiceAccount. This requires that service accounts are
    turned on in your kubernetes cluster and that the calling code is running in a pod.
    """
    with open('/var/run/secrets/kubernetes.io/serviceaccount/token') as f:
        token = f.read()
    api_url = 'https://{host}:{port}'.format(
        host=os.environ['KUBERNETES_SERVICE_HOST'],
        port=os.environ['KUBERNETES_SERVICE_PORT']
    )

    def make_request(url, **kwargs):
        """
        Make & return a HTTPRequest object suited to making requests to a Kubernetes cluster

        The following changes are made to the passed in arguments
         * url
           No hostname / protocol should be provided, only path (and query strings, if any).
           The hostname / protocol / port will be automatically provided.
         * headers
           Appropriate Authorization header will be added
         * ca_certs
           Appropriate CA bundle path will be set
        """
        headers = kwargs.get('headers', {})
        headers['Authorization'] = 'Bearer {token}'.format(token=token)
        kwargs.update({
            'url': api_url + url,
            'ca_certs': '/var/run/secrets/kubernetes.io/serviceaccount/ca.crt',
            'headers': headers,
        })
        return HTTPRequest(**kwargs)

    return make_request


def request_maker_kubeconfig():
    """
    Return a k8s api aware HTTPRequest factory that discovers connection info from a .kube/config file

    Reads a .kube/config file from the given path, and constructs a function
    that can make HTTPRequest objects with all the authentication stuff
    filled in to the kubernetes context set as current-context in that .kube/config
    file.
    """
    with open(os.path.expanduser('~/.kube/config')) as f:
        config = yaml.safe_load(f)

    current_context = config['current-context']

    context = [c for c in config['contexts'] if c['name'] == current_context][0]['context']
    cluster = [c for c in config['clusters'] if c['name'] == context['cluster']][0]['cluster']
    if 'user' in context and context['user']:  # Since user accounts aren't strictly required
        user = [u for u in config['users'] if u['name'] == context['user']][0]['user']
    else:
        user = {}

    def make_request(url, **kwargs):
        """
        Make & return a HTTPRequest object suited to making requests to a Kubernetes cluster

        The following changes are made to the passed in arguments
         * url
           No hostname / protocol should be provided, only path (and query strings, if any).
           The hostname / protocol / port will be automatically provided.
         * client_key / client_cert:
           Appropriate client certificate / key will be set if specified in .kube/config
         * ca_certs
           Appropriate ca will be set if specified in .kube/config
        """
        kwargs.update({
            'url': cluster['server'] + url,
            'ca_certs': cluster.get('certificate-authority', None),
            'client_key': user.get('client-key', None),
            'client_cert': user.get('client-certificate', None)
        })
        if 'token' in user:
            headers = kwargs.get('headers', {})
            headers['Authorization'] = 'Bearer {token}'.format(token=user['token'])
            kwargs.update({
                'headers': headers
            })
        return HTTPRequest(**kwargs)

    return make_request


def k8s_url(namespace, kind, name=None):
    """
    Construct URL referring to a set of kubernetes resources

    Only supports the subset of URLs that we need to generate for use
    in kubespawner. This currently covers:
      - All resources of a specific kind in a namespace
      - A resource with a specific name of a specific kind
    """
    url_parts = [
        'api',
        'v1',
        'namespaces',
        namespace,
        kind
    ]
    if name is not None:
        url_parts.append(name)
    return '/' + '/'.join(url_parts)


class Callable(TraitType):
    """
    A trait which is callable.

    Classes are callable, as are instances
    with a __call__() method.
    """

    info_text = 'a callable'

    def validate(self, obj, value):
        if callable(value):
           return value
        else:
            self.error(obj, value)
