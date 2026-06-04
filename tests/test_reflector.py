"""
Unit tests for ResourceReflector — early-close backoff (PR #920).

These tests do not require a running Kubernetes cluster; the k8s client and
watch stream are mocked so the backoff logic can be exercised in isolation.
"""

import asyncio
import time
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
# Early-close backoff
# ---------------------------------------------------------------------------


async def test_early_close_triggers_backoff_sleep():
    """When the watch stream closes in < 30s, asyncio.sleep is called."""
    r = make_reflector()
    r._list_and_update = AsyncMock(return_value="1")

    sleep_calls = []

    async def capture_sleep(delay):
        sleep_calls.append(delay)
        r._stopping = True  # stop after the first backoff sleep

    class QuickWatch:
        def stream(self, *a, **kw):
            return stream_yielding([])  # exits immediately (0 events)

        def stop(self):
            pass

        async def close(self):
            pass

    real_start = time.monotonic()
    call_count = 0

    def fake_monotonic():
        nonlocal call_count
        call_count += 1
        # First call sets `start`; subsequent calls return start + 1s.
        return real_start if call_count == 1 else real_start + 1

    with patch("kubespawner.reflector.watch.Watch", QuickWatch):
        with patch("kubespawner.reflector.time.monotonic", side_effect=fake_monotonic):
            with patch("asyncio.sleep", side_effect=capture_sleep):
                try:
                    await asyncio.wait_for(r._watch_and_update(), timeout=3)
                except (asyncio.TimeoutError, asyncio.CancelledError):
                    pass

    assert len(sleep_calls) >= 1, "Expected at least one backoff sleep on early close"
    assert sleep_calls[0] == pytest.approx(
        0.1, rel=1e-3
    ), "Initial early-close backoff should be 0.1s"


async def test_normal_close_does_not_trigger_backoff():
    """Watch streams that run >= 30s reconnect immediately without extra sleep."""
    r = make_reflector()
    r._list_and_update = AsyncMock(return_value="1")

    sleep_calls = []
    watch_cycles = 0

    async def capture_sleep(delay):
        sleep_calls.append(delay)

    class QuickWatch:
        def stream(self, *a, **kw):
            nonlocal watch_cycles
            watch_cycles += 1
            if watch_cycles >= 2:
                r._stopping = True
            return stream_yielding([])

        def stop(self):
            pass

        async def close(self):
            pass

    real_start = time.monotonic()
    call_count = 0

    def fake_monotonic():
        nonlocal call_count
        call_count += 1
        # Make watch_duration appear to be 35s (>= 30s threshold → normal exit).
        return real_start if call_count == 1 else real_start + 35

    with patch("kubespawner.reflector.watch.Watch", QuickWatch):
        with patch("kubespawner.reflector.time.monotonic", side_effect=fake_monotonic):
            with patch("asyncio.sleep", side_effect=capture_sleep):
                try:
                    await asyncio.wait_for(r._watch_and_update(), timeout=3)
                except (asyncio.TimeoutError, asyncio.CancelledError):
                    pass

    assert (
        len(sleep_calls) == 0
    ), f"Normal exit should not trigger backoff sleep, got: {sleep_calls}"


async def test_early_close_backoff_doubles_on_repeat():
    """Consecutive early closes double the backoff delay (0.1 → 0.2 → 0.4)."""
    r = make_reflector()
    r._list_and_update = AsyncMock(return_value="1")

    sleep_calls = []

    async def capture_sleep(delay):
        sleep_calls.append(delay)
        if len(sleep_calls) >= 3:
            r._stopping = True

    class QuickWatch:
        def stream(self, *a, **kw):
            return stream_yielding([])  # always exits immediately

        def stop(self):
            pass

        async def close(self):
            pass

    real_start = time.monotonic()
    call_count = 0

    def fake_monotonic():
        nonlocal call_count
        # Alternate start (0s) and end (1s) — always an early close.
        val = real_start + (0 if call_count % 2 == 0 else 1)
        call_count += 1
        return val

    with patch("kubespawner.reflector.watch.Watch", QuickWatch):
        with patch("kubespawner.reflector.time.monotonic", side_effect=fake_monotonic):
            with patch("asyncio.sleep", side_effect=capture_sleep):
                try:
                    await asyncio.wait_for(r._watch_and_update(), timeout=5)
                except (asyncio.TimeoutError, asyncio.CancelledError):
                    pass

    assert len(sleep_calls) >= 3, "Expected at least 3 consecutive backoff sleeps"
    assert sleep_calls[1] == pytest.approx(sleep_calls[0] * 2, rel=1e-3)
    assert sleep_calls[2] == pytest.approx(sleep_calls[1] * 2, rel=1e-3)


async def test_early_close_backoff_resets_after_normal_exit():
    """After a normal (>=30s) watch exit, early-close backoff resets to 0.1s."""
    r = make_reflector()
    r._list_and_update = AsyncMock(return_value="1")

    sleep_calls = []

    async def capture_sleep(delay):
        sleep_calls.append(delay)
        if len(sleep_calls) >= 2:
            r._stopping = True

    class QuickWatch:
        def stream(self, *a, **kw):
            return stream_yielding([])

        def stop(self):
            pass

        async def close(self):
            pass

    real_start = time.monotonic()
    # durations per watch cycle: early(1s), normal(35s), early(1s)
    durations = [1, 35, 1]
    call_count = 0

    def fake_monotonic():
        nonlocal call_count
        idx = call_count // 2
        is_start = call_count % 2 == 0
        call_count += 1
        d = durations[min(idx, len(durations) - 1)]
        return real_start + (0 if is_start else d)

    with patch("kubespawner.reflector.watch.Watch", QuickWatch):
        with patch("kubespawner.reflector.time.monotonic", side_effect=fake_monotonic):
            with patch("asyncio.sleep", side_effect=capture_sleep):
                try:
                    await asyncio.wait_for(r._watch_and_update(), timeout=5)
                except (asyncio.TimeoutError, asyncio.CancelledError):
                    pass

    assert len(sleep_calls) >= 2, "Expected sleeps from cycle 1 and cycle 3"
    # First early-close sleep: 0.1s.
    assert sleep_calls[0] == pytest.approx(0.1, rel=1e-3)
    # After normal exit reset, third cycle should be back to 0.1s.
    assert sleep_calls[1] == pytest.approx(
        0.1, rel=1e-3
    ), "Backoff should reset to 0.1s after a normal (>=30s) exit"
