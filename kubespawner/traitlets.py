"""
Traitlets that are used in Kubespawner
"""
from traitlets import TraitType


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
