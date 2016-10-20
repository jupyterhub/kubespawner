"""
Misc. general utility functions, not tied to Kubespawner directly
"""
import os
import yaml

from tornado.httpclient import HTTPRequest


def request_maker(path='~/.kube/config'):
    """
    Return a function that creates Kubernetes API aware HTTPRequest objects

    Reads a .kube/config file from the given path, and constructs a function
    that can make HTTPRequest objects with all the authentication stuff
    filled in to the kubernetes context set as current-context in that .kube/config
    file.

    TODO: Pick up info from service accounts + env variables too
    """
    with open(os.path.expanduser(path)) as f:
        config = yaml.safe_load(f)

    current_context = config['current-context']

    context = [c for c in config['contexts'] if c['name'] == current_context][0]['context']
    cluster = [c for c in config['clusters'] if c['name'] == context['cluster']][0]['cluster']
    if 'user' in context:  # Since user accounts aren't strictly required
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
           These will be automatically set if required
         * ca_certs
           This will also be automatically set if required
        """
        kwargs.update({
            'url': cluster['server'] + url,
            'ca_certs': cluster.get('certificate-authority', None),
            'client_key': user.get('client-key', None),
            'client_cert': user.get('client-certificate', None)
        })
        return HTTPRequest(**kwargs)

    return make_request
