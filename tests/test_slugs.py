import pytest

from kubespawner.slugs import safe_slug


@pytest.mark.parametrize(
    "name, expected",
    [
        ("jupyter-alex", "jupyter-alex"),
        ("jupyter-Alex", "jupyter-alex--3a1c285c"),
        ("jupyter-üni", "jupyter-ni--a5aaf5dd"),
        ("endswith-", "endswith---165f1166"),
        ("-start", "j-start--f587e2dc"),
        ("j-start--f587e2dc", "j-start--f587e2dc--f007ef7c"),
        ("x" * 65, "xxxxxxxxxxxxxxxxxxxxxxxx--9537c5fd"),
        ("x" * 66, "xxxxxxxxxxxxxxxxxxxxxxxx--6eb879f1"),
    ],
)
def test_safe_slug(name, expected):
    slug = safe_slug(name)
    assert slug == expected
