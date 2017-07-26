"""
Misc. general utility functions, not tied to Kubespawner directly
"""
from concurrent.futures import ThreadPoolExecutor
import random

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
def exponential_backoff(pass_func, fail_message, timeout=10, *args, **kwargs):
    """
    Exponentially backoff until pass_func is true.

    This function will wait with exponential backoff + random jitter for as
    many iterations as needed, with maximum timeout timeout. If pass_func is
    still returning false at the end of timeout, a TimeoutError will be raised.

    *args and **kwargs are passed to pass_func.
    """
    loop = ioloop.IOLoop.current()
    start_tic = loop.time()
    dt = DT_MIN
    while True:
        if (loop.time() - start_tic) > timeout:
            # We time out!
            break
        if pass_func(*args, **kwargs):
            return
        else:
            yield gen.sleep(dt)
        # Add some random jitter to improve performance
        # This makes sure that we don't overload any single iteration
        # of the tornado loop with too many things
        # See https://www.awsarchitectureblog.com/2015/03/backoff.html
        # for a good example of why and how this helps
        dt = min(DT_MAX, (1 + random.random()) * (dt * DT_SCALE))
    raise TimeoutError(fail_message)
