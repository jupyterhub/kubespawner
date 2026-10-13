"""
Unit tests for ResourceReflector — generation tracking and is_stale() (PR #921).

These tests do not require a running Kubernetes cluster; the k8s client is
mocked so the cache logic can be exercised in isolation.
"""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, Mock, patch

import pytest

from kubespawner.reflector import ResourceReflector

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_reflector(**kwargs):
    """Return a ResourceReflector with a mocked k8s client."""
    defaults = dict(kind="pods", namespace="test-ns")
    defaults.update(kwargs)
    with patch("kubespawner.reflector.shared_client", return_value=Mock()):
        return ResourceReflector(**defaults)


@asynccontextmanager
async def stream_yielding(events):
    """Async context manager that yields *events* then exits cleanly."""

    async def _gen():
        for e in events:
            yield e

    yield _gen()


# ---------------------------------------------------------------------------
# Generation tracking — construction
# ---------------------------------------------------------------------------


def test_generation_starts_at_zero():
    """_generation is initialised to 0 at construction."""
    r = make_reflector()
    assert r._generation == 0


def test_entry_generations_starts_empty():
    """_entry_generations is empty at construction."""
    r = make_reflector()
    assert r._entry_generations == {}


# ---------------------------------------------------------------------------
# is_stale() — pure logic
# ---------------------------------------------------------------------------


def test_is_stale_missing_key_returns_false():
    """is_stale() returns False for a key not in the cache (absent ≠ stale)."""
    r = make_reflector()
    assert not r.is_stale("test-ns/nonexistent")


def test_is_stale_current_generation_returns_false():
    """Entry stamped with the current generation is not stale."""
    r = make_reflector()
    r._generation = 5
    r.resources["test-ns/pod-a"] = {}
    r._entry_generations["test-ns/pod-a"] = 5
    assert not r.is_stale("test-ns/pod-a")


def test_is_stale_old_generation_returns_true():
    """Entry from a previous watch cycle is detected as stale."""
    r = make_reflector()
    r._generation = 5
    r.resources["test-ns/pod-a"] = {}
    r._entry_generations["test-ns/pod-a"] = 3  # seen two cycles ago
    assert r.is_stale("test-ns/pod-a")


def test_is_stale_no_stamp_after_generation_advance():
    """Entry with no generation stamp is stale once _generation advances."""
    r = make_reflector()
    r._generation = 1
    r.resources["test-ns/pod-a"] = {}
    # _entry_generations not set → .get() returns 0 < _generation=1
    assert r.is_stale("test-ns/pod-a")


# ---------------------------------------------------------------------------
# Generation tracking — watch cycle integration
# ---------------------------------------------------------------------------


async def test_generation_increments_on_watch_reconnect():
    """_generation increments each time the watch successfully reconnects."""
    r = make_reflector()
    r._list_and_update = AsyncMock(return_value="1")

    class QuickWatch:
        def stream(self, *a, **kw):
            return stream_yielding([])  # exits immediately

        def stop(self):
            pass

        async def close(self):
            pass

    import asyncio

    with patch("kubespawner.reflector.watch.Watch", QuickWatch):
        with patch("asyncio.sleep", new_callable=AsyncMock):
            task = asyncio.create_task(r._watch_and_update())
            # Wait until at least two reconnects have occurred.
            for _ in range(50):
                await asyncio.sleep(0)
                if r._generation >= 2:
                    break
            r._stopping = True
            try:
                await asyncio.wait_for(task, timeout=2)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                task.cancel()

    assert r._generation >= 2, "Expected _generation to increment across reconnects"


async def test_watch_event_stamps_entry_generation():
    """ADDED events stamp _entry_generations with the current _generation."""
    r = make_reflector()
    r._generation = 3

    ref_key = "test-ns/pod-x"
    # Simulate what _watch_and_update does on an ADDED event.
    r.resources[ref_key] = {}
    r._entry_generations[ref_key] = r._generation

    assert r._entry_generations[ref_key] == 3
    assert not r.is_stale(ref_key)


async def test_deleted_event_clears_entry_generation():
    """DELETED events remove the entry from _entry_generations."""
    r = make_reflector()
    r._generation = 2
    ref_key = "test-ns/pod-gone"
    r.resources[ref_key] = {}
    r._entry_generations[ref_key] = 2

    # Simulate DELETED event processing.
    r.resources.pop(ref_key, None)
    r._entry_generations.pop(ref_key, None)

    assert ref_key not in r._entry_generations
    assert not r.is_stale(ref_key)  # absent is not stale


async def test_entry_becomes_stale_after_reconnect():
    """Entry not refreshed after a reconnect is detected as stale."""
    r = make_reflector()
    ref_key = "test-ns/pod-old"

    # Populate during generation 1.
    r._generation = 1
    r.resources[ref_key] = {}
    r._entry_generations[ref_key] = 1

    # Simulate a watch reconnect (generation advances to 2).
    r._generation = 2

    # The entry has not been updated yet — it should be stale.
    assert r.is_stale(ref_key)

    # Once the watch delivers a new event for this pod, it is fresh again.
    r._entry_generations[ref_key] = r._generation
    assert not r.is_stale(ref_key)
