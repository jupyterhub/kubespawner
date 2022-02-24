"""Patch asyncio to add atexit-like functionality

Callbacks registered with `asyncio_atexit(f)`
will run when the current event loop closes,
immediately prior to cleaning up the loop's resources.

Callbacks _may_ be coroutines.
"""
import asyncio
import inspect
import sys
from functools import partial

__all__ = ["asyncio_atexit"]


def asyncio_atexit(callback):
    """
    Like atexit, but run when the asyncio loop is closing,
    rather than process cleanup.
    """

    loop = asyncio.get_running_loop()
    _patch_asyncio_atexit(loop)
    loop._asyncio_atexit_callbacks.append(callback)


async def _run_asyncio_atexits(loop):
    """Run asyncio atexit callbacks

    This runs in EventLoop.close() prior to actually closing the loop
    """
    for callback in loop._asyncio_atexit_callbacks:
        try:
            f = callback()
            if inspect.isawaitable(f):
                await f
        except Exception as e:
            print(
                f"Unhandled exception in asyncio atexit callback {callback}: {e}",
                file=sys.stderr,
            )


def _asyncio_atexit_close(loop):
    """Patched EventLoop.close method to run atexit callbacks

    prior to the unpatched close method.
    """
    if loop._asyncio_atexit_callbacks:
        loop.run_until_complete(loop._run_asyncio_atexits())
    loop._asyncio_atexit_callbacks = None
    return loop._orig_close()


def _patch_asyncio_atexit(loop):
    """Patch an asyncio.EventLoop to support atexit callbacks"""
    if hasattr(loop, "_run_asyncio_atexits"):
        return

    loop._run_asyncio_atexits = partial(_run_asyncio_atexits, loop)
    loop._asyncio_atexit_callbacks = []
    loop._orig_close = loop.close
    loop.close = partial(_asyncio_atexit_close, loop)
