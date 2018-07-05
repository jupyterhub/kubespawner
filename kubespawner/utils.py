"""
Misc. general utility functions, not tied to Kubespawner directly
"""
import hashlib
import re
import copy


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


_underscorer1 = re.compile(r'(.)([A-Z][a-z]+)')
_underscorer2 = re.compile('([a-z0-9])([A-Z])')

def from_camel_to_snake_case(str):
    """
    Convert a string from camelCase to snake_case.
    """
    subbed = _underscorer1.sub(r'\1_\2', str)
    return _underscorer2.sub(r'\1_\2', subbed).lower()

def convert_keys_from_camel_to_snake_case(obj):
    """
    Returns a shallow copy of an dict object with the object's keys converted
    from camelCase to snake_case. Note that the function will not influence
    nested object's keys.
    """

    obj = copy.deepcopy(obj)

    for old_key in obj.keys():
        obj[from_camel_to_snake_case(old_key)] = obj.pop(old_key)

    return obj