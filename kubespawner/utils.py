"""
Misc. general utility functions, not tied to Kubespawner directly
"""
from concurrent.futures import ThreadPoolExecutor

from jupyterhub.utils import DT_MIN, DT_MAX, DT_SCALE
from tornado import gen, ioloop
from traitlets.config import SingletonConfigurable

class SingletonExecutor(SingletonConfigurable, ThreadPoolExecutor):
    """
    Simple wrapper to ThreadPoolExecutor that is also a singleton.

    We want one ThreadPool that is used by all the spawners, rather
    than one ThreadPool per spawner!
    """
    pass

@gen.coroutine
def exponential_backoff(func, fail_message, timeout=10, *args, **kwargs):
    loop = ioloop.IOLoop.current()
    tic = loop.time()
    dt = DT_MIN
    while dt > 0:
        if func(*args, **kwargs):
            return
        else:
            yield gen.sleep(dt)
        dt = min(dt * DT_SCALE, DT_MAX, timeout - (loop.time() - tic))
    raise TimeoutError(fail_message)
