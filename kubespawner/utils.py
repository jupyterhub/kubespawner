"""
Misc. general utility functions, not tied to Kubespawner directly
"""
import random
import hashlib

from tornado import gen
from traitlets import TraitType
from kubernetes import client

def generate_hashed_slug(slug, limit=63, hash_length=6):
    """
    Generate a unique name that's within a certain length limit

    Most k8s objects have a 63 char name limit. We wanna be able to compress
    larger names down to that if required, while still maintaining some
    amount of legibility about what the objects really are.

    If the length of the slug is shorter than the limit - hash_length, we just
    return slug directly. If not, we truncate the slug to (limit - hash_length)
    characters, hash the slug and append hash_length characters from the hash
    to the end of the truncated slug. This ensures that these names are always
    unique no matter what.
    """
    if len(slug) < (limit - hash_length):
        return slug

    slug_hash = hashlib.sha256(slug.encode('utf-8')).hexdigest()

    return '{prefix}-{hash}'.format(
        prefix=slug[:limit - hash_length - 1],
        hash=slug_hash[:hash_length],
    ).lower()


class Callable(TraitType):
    """A trait which is callable.
    Notes
    -----
    Classes are callable, as are instances
    with a __call__() method."""

    info_text = 'a callable'

    def validate(self, obj, value):
        if callable(value):
            return value
        else:
            self.error(obj, value)

@gen.coroutine
def ensure_object(
    asynchronize_func,
    create_func,
    patch_func,
    body,
    ifexists='patch',
    namespace=None
):
    """
    Ensure a given k8s object exists

    create_func - the API function for creating the object
    patch_fun - API method for patching the object (if required)
    body - the object to be created
    ifexists - what to do if the object already exists.
               Supported options are 'patch' and 'ignore'
    namespace - Namespace to create object in, if it is a namespaced object
    """
    name = body.metadata.name
    try:
        create_kwargs = {'body': body}
        if namespace:
            create_kwargs['namespace'] = namespace
        resp = yield asynchronize_func(
            create_func,
            **create_kwargs
        )
    except client.rest.ApiException as e:
        if e.status == 409:
            if ifexists == 'patch':
                # This object already exists, we should patch it to make it be what we want
                patch_kwargs = {'body': body, 'name': body.metadata.name}
                if namespace:
                    patch_kwargs['namespace'] = namespace
                resp = yield asynchronize_func(
                    patch_func,
                    **patch_kwargs
                )
            elif ifexists == 'ignore':
                pass
            else:
                raise
        else:
            raise
