"""
Misc. general utility functions, not tied to Kubespawner directly
"""
import random
import hashlib

def generate_hashed_slug(slug, limit=63, hash_length=6):
    """
    Generate a unique name that's within a certain length limit

    Most k8s objects have a 63 char name limit. We wanna be able to compress
    larger names down to that if required, while still maintaining some
    amount of legibility about what the objects really are.
    """
    # if the length of the slug is shorter than limit - hash_length, we just
    # use it directly. Good enough!
    if len(slug) < (limit - hash_length):
        return slug

    # If not, we pick the first limit - hash_length chars from slug & hash the rest.
    # This means that any name over (limit - hash_length) chars will always be length long.

    slug_hash = hashlib.sha256(slug.encode('utf-8')).hexdigest()

    return '{prefix}-{hash}'.format(
        prefix=slug[:limit - hash_length - 1],
        hash=slug_hash[:hash_length],
    ).lower()
