"""
Misc. general utility functions, not tied to Kubespawner directly
"""
from concurrent.futures import ThreadPoolExecutor
import random

from tornado import gen, ioloop
from traitlets.config import SingletonConfigurable

class SingletonExecutor(SingletonConfigurable, ThreadPoolExecutor):
    """
    Simple wrapper to ThreadPoolExecutor that is also a singleton.

    We want one ThreadPool that is used by all the spawners, rather
    than one ThreadPool per spawner!
    """
    pass
