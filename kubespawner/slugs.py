"""Tools for generating slugs like k8s object names and labels

Requirements:

- always valid for arbitary strings
- no collisions
"""

import hashlib
import re
import string

_alphanum = tuple(string.ascii_letters + string.digits)
_alphanum_lower = tuple(string.ascii_lowercase + string.digits)
_lower_plus_hyphen = _alphanum_lower + ('-',)

# patterns _do not_ need to cover length or start/end conditions,
# which are handled separately
_object_pattern = re.compile(r'^[a-z0-9\.-]+$')
_label_pattern = re.compile(r'^[a-z0-9\.-_]+$', flags=re.IGNORECASE)

# match two or more hyphens
_hyphen_plus_pattern = re.compile('--+')

# length of hash suffix
_hash_length = 8


def _is_valid_general(
    s, starts_with=None, ends_with=None, pattern=None, min_length=None, max_length=None
):
    """General is_valid check

    Checks rules:
    """
    if min_length and len(s) < min_length:
        return False
    if max_length and len(s) > max_length:
        return False
    if starts_with and not s.startswith(starts_with):
        return False
    if ends_with and not s.endswith(ends_with):
        return False
    if pattern and not pattern.match(s):
        return False
    return True


def is_valid_object_name(s):
    """is_valid check for object names"""
    # object rules: https://kubernetes.io/docs/concepts/overview/working-with-objects/names/#names
    return _is_valid_general(
        s,
        starts_with=_alphanum_lower,
        ends_with=_alphanum_lower,
        pattern=_object_pattern,
        max_length=255,
        min_length=1,
    )


def is_valid_label(s):
    """is_valid check for label values"""
    # label rules: https://kubernetes.io/docs/concepts/overview/working-with-objects/labels/#syntax-and-character-set
    if not s:
        # empty strings are valid labels
        return True
    return _is_valid_general(
        s,
        starts_with=_alphanum,
        ends_with=_alphanum,
        pattern=_label_pattern,
        max_length=63,
    )


def is_valid_default(s):
    """Strict is_valid

    Returns True if it's valid for _all_ our known uses

    So we can more easily have a single is_valid check.

    - object names have stricter character rules, but have longer max length
    - labels have short max length, but allow uppercase
    """
    return _is_valid_general(
        s,
        starts_with=_alphanum_lower,
        ends_with=_alphanum_lower,
        pattern=_object_pattern,
        min_length=1,
        max_length=63,
    )


def strip_and_hash(name, max_length=32):
    """Generate an always-safe, unique string for any input

    truncates name to max_length - len(hash_suffix) to fit in max_length
    after adding hash suffix
    """
    name_length = max_length - (_hash_length + 3)
    if name_length < 1:
        raise ValueError(f"Cannot make safe names shorter than {_hash_length + 4}")
    # quick, short hash to avoid name collisions
    name_hash = hashlib.sha256(name.encode("utf8")).hexdigest()[:_hash_length]
    # compute safe slug from name (don't worry about collisions, hash handles that)
    # cast to lowercase, exclude all but lower & hyphen
    safe_name = ''.join([c for c in name.lower() if c in _lower_plus_hyphen])
    # strip leading '-'
    # squash repeated '--' to one
    safe_name = _hyphen_plus_pattern.sub("-", safe_name.lstrip("-"))
    # truncate to 24 chars, strip trailing '-'
    safe_name = safe_name[:name_length].rstrip("-")
    if not safe_name:
        # make sure it's non-empty
        safe_name = 'x'
    # due to stripping of '-' above,
    # the result will always have _exactly_ '---', never '--' nor '----'
    # use '---' to avoid colliding with `{username}--{servername}` template join
    return f"{safe_name}---{name_hash}"


def safe_slug(name, is_valid=is_valid_default, max_length=None):
    """Always generate a safe slug

    is_valid should be a callable that returns True if a given string follows appropriate rules,
    and False if it does not.

    Given a string, if it's already valid, use it.
    If it's not valid, follow a safe encoding scheme that ensures:

    1. validity, and
    2. no collisions
    """
    if '--' in name:
        # don't accept any names that could collide with the safe slug
        return strip_and_hash(name, max_length=max_length or 32)
    # allow max_length override for truncated sub-strings
    if is_valid(name) and (max_length is None or len(name) <= max_length):
        return name
    else:
        return strip_and_hash(name, max_length=max_length or 32)
