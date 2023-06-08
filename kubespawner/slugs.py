"""Tools for generating

Requirements:

- always valid for arbitary strings
- no collisions
"""
import hashlib
import re
import string

_alphanum = set(string.ascii_letters + string.digits)
_alphanum_lower = set(string.ascii_lowercase + string.digits)
_lower_plus_hyphen = _alphanum_lower | {'-'}

# patterns _do not_ need to cover length or start/end conditions,
# which are handled separately
_object_pattern = re.compile(r'^[a-z0-9\.-]+$')
_label_pattern = re.compile(r'^[a-z0-9\.-_]+$', flags=re.IGNORECASE)


def _is_valid_general(
    s, starts_with=None, ends_with=None, pattern=None, max_length=None
):
    """General is_valid check

    Checks rules:
    """
    if not 1 <= len(s) <= max_length:
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
    )


def is_valid_label(s):
    """is_valid check for label values"""
    # label rules: https://kubernetes.io/docs/concepts/overview/working-with-objects/labels/#syntax-and-character-set
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
        max_length=63,
    )


def strip_and_hash(name):
    """Generate an always-safe, unique string for any input"""
    # make sure we start with a prefix
    # quick, short hash to avoid name collsions
    name_hash = hashlib.sha256(name).hexdigest()[:8]
    safe_chars = [c for c in name.lower() if c in _lower_plus_hyphen]
    safe_name = ''.join(safe_chars[:24])
    if not safe_name:
        safe_name = 'x'
    if safe_name.startswith('-'):
        # starting with '-' is generally not allowed,
        # start with 'j-' instead
        # Question: always do this so it's consistent, instead of as-needed?
        safe_name = f"j{safe_name}"
    return f"{safe_name}--{name_hash}"


def safe_slug(name, is_valid=is_valid_default):
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
        return strip_and_hash(name)
    if is_valid(name):
        return name
    else:
        return strip_and_hash(name)
