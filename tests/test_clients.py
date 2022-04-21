import asyncio

from conftest import cancel_tasks

from kubespawner.clients import load_config, shared_client


async def test_shared_client():
    load_config()
    core = shared_client("CoreV1Api")
    core2 = shared_client("CoreV1Api")
    assert core2 is core
    ext = shared_client("NetworkingV1Api")
    ext2 = shared_client("NetworkingV1Api")
    assert ext is ext2
    assert ext is not core


def test_shared_client_close():
    load_config()
    # this test must be sync so we can call asyncio.run
    core = None

    async def test():
        nonlocal core
        core = shared_client("CoreV1Api")

    loop = asyncio.new_event_loop()
    loop.run_until_complete(test())
    loop.run_until_complete(cancel_tasks())
    loop.close()
    # asyncio.run(test())
    assert core is not None
    # no public API to check if it's closed
    assert core.api_client._pool is None
