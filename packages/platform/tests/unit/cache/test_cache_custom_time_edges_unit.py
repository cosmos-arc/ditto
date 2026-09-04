"""Deterministic custom-clock and recovery edges for ``DataCache``."""

from __future__ import annotations

import pytest
from ditto_platform.foundation.cache import DataCache


class _Clock:
    def __init__(self, now: float = 100.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


@pytest.mark.parametrize("enable_metrics", [False, True])
def test_custom_clock_missing_key_returns_default_and_records_a_miss(
    *,
    enable_metrics: bool,
) -> None:
    cache: DataCache[str] = DataCache(
        enable_metrics=enable_metrics,
        time_source=_Clock(),
    )

    assert cache.get("missing", "fallback") == "fallback"
    assert cache.get_stats().miss_count == 1


def test_expired_custom_clock_entry_tolerates_an_absent_backing_cache_entry() -> None:
    clock = _Clock()
    cache: DataCache[str] = DataCache(enable_metrics=False, time_source=clock)
    cache.set("stale", "value", ttl=1)
    cache._cache.clear()

    clock.now += 1

    assert cache.get("stale", "fallback") == "fallback"
    assert cache.get_stats().miss_count == 1
    assert len(cache) == 0


def test_custom_clock_metadata_tracks_invalidation_pattern_clear_and_length() -> None:
    cache: DataCache[str] = DataCache(enable_metrics=False, time_source=_Clock())
    cache.set("user:1", "alice")
    cache.set("user:2", "bob")
    cache.set("session:1", "token")

    assert len(cache) == 3
    assert cache.invalidate("user:1") is True
    assert cache.invalidate_pattern("user:*") == 1
    assert len(cache) == 1

    cache.clear()

    assert len(cache) == 0


def test_custom_clock_helpers_fail_closed_when_internal_state_is_incomplete() -> None:
    missing_entries: DataCache[str] = DataCache(
        enable_metrics=False,
        time_source=_Clock(),
    )
    missing_entries._ttl_entries = None

    with pytest.raises(RuntimeError, match="ttl_entries"):
        missing_entries._get_with_custom_time("key", None)
    with pytest.raises(RuntimeError, match="ttl_entries"):
        missing_entries._set_with_custom_time("key", "value", None)

    missing_clock: DataCache[str] = DataCache(
        enable_metrics=False,
        time_source=_Clock(),
    )
    missing_clock._time_source = None

    with pytest.raises(RuntimeError, match="time_source"):
        missing_clock._get_with_custom_time("key", None)
    with pytest.raises(RuntimeError, match="time_source"):
        missing_clock._set_with_custom_time("key", "value", None)
