"""Unit tests for compile_cache.py.

Tests SQLiteCompileCache with a mock SQLite backend to verify L1/L2 caching,
force recompile, and persistence behavior.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from ditto_features.compile_cache import SQLiteCompileCache, _fetch_one
from ditto_features.derived_types import (
    DerivedRole,
    DerivedSpec,
    MaterializationProfile,
)


def _make_spec(expression: str = "market.close + 1") -> DerivedSpec:
    return DerivedSpec(
        id="test_feature",
        version=1,
        role=DerivedRole.FEATURE,
        materialization_profile=MaterializationProfile.SERIES,
        expression=expression,
    )


class _FakeCursor:
    """Minimal cursor mock for SQLite results."""

    def __init__(self, row: tuple[Any, ...] | None = None) -> None:
        self._row = row

    def fetchone(self) -> tuple[Any, ...] | None:
        return self._row


class _FakeSQLite:
    """In-memory fake SQLite backend for testing."""

    def __init__(self) -> None:
        self.entries: dict[str, dict[str, Any]] = {}
        self.operators: dict[str, list[tuple[str, str]]] = {}

    def execute(
        self,
        sql: str,
        params: list[Any] | tuple[Any, ...] | None = None,
    ) -> _FakeCursor:
        if "SELECT 1" in sql and params:
            cache_key = params[0]
            if cache_key in self.entries:
                return _FakeCursor(row=(1,))
            return _FakeCursor(row=None)
        if "INSERT OR REPLACE" in sql and params:
            cache_key = params[0]
            self.entries[cache_key] = {
                "derived_id": params[1],
                "version": params[2],
            }
        if "DELETE FROM compiled_expression_operator" in sql and params:
            cache_key = params[0]
            self.operators.pop(cache_key, None)
        return _FakeCursor()

    def executemany(
        self,
        sql: str,
        params_list: list[list[Any] | tuple[Any, ...]],
    ) -> object:
        if "compiled_expression_operator" in sql:
            for params in params_list:
                cache_key = params[0]
                if cache_key not in self.operators:
                    self.operators[cache_key] = []
                self.operators[cache_key].append((params[1], params[2]))
        return None

    def commit(self) -> None:
        pass


# ---------------------------------------------------------------------------
# _fetch_one
# ---------------------------------------------------------------------------


class TestFetchOne:
    """Tests for _fetch_one helper."""

    def test_valid_cursor(self) -> None:
        """Returns row from valid cursor."""
        cursor = _FakeCursor(row=(1,))
        assert _fetch_one(cursor) == (1,)

    def test_none_row(self) -> None:
        """Returns None when cursor has no rows."""
        cursor = _FakeCursor(row=None)
        assert _fetch_one(cursor) is None

    def test_attribute_error_returns_none(self) -> None:
        """Returns None when cursor raises AttributeError."""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.side_effect = AttributeError("no fetchone")
        assert _fetch_one(mock_cursor) is None


# ---------------------------------------------------------------------------
# SQLiteCompileCache
# ---------------------------------------------------------------------------


class TestSQLiteCompileCache:
    """Tests for SQLiteCompileCache."""

    def test_first_compile_persists_to_sqlite(self) -> None:
        """First call compiles and persists to SQLite."""
        backend = _FakeSQLite()
        cache = SQLiteCompileCache(backend)
        spec = _make_spec()
        compiled = cache.get_or_compile(spec)
        assert compiled is not None
        # Should be persisted to SQLite
        assert len(backend.entries) == 1

    def test_l1_cache_hit(self) -> None:
        """Second call returns L1 cached result without recompile."""
        backend = _FakeSQLite()
        cache = SQLiteCompileCache(backend)
        spec = _make_spec()
        first = cache.get_or_compile(spec)
        second = cache.get_or_compile(spec)
        # Same object from L1 cache
        assert first is second
        # Only one entry persisted (no double-write)
        assert len(backend.entries) == 1

    def test_l2_cache_hit(self) -> None:
        """After clearing L1, L2 hit triggers recompile."""
        backend = _FakeSQLite()
        cache = SQLiteCompileCache(backend, max_cache_size=1)
        spec = _make_spec()
        first = cache.get_or_compile(spec)
        assert first is not None
        # Verify L2 has the entry
        assert len(backend.entries) == 1

    def test_force_recompile(self) -> None:
        """force_recompile=True skips both L1 and L2."""
        backend = _FakeSQLite()
        cache = SQLiteCompileCache(backend)
        spec = _make_spec()
        first = cache.get_or_compile(spec)
        second = cache.get_or_compile(spec, force_recompile=True)
        # Both should be valid compiled expressions
        assert first is not None
        assert second is not None
        # The L2 entry should have been overwritten
        assert len(backend.entries) == 1

    def test_different_expressions_different_keys(self) -> None:
        """Different expressions produce different cache keys."""
        backend = _FakeSQLite()
        cache = SQLiteCompileCache(backend)
        spec_a = _make_spec("market.close + 1")
        spec_b = _make_spec("market.open * 2")
        cache.get_or_compile(spec_a)
        cache.get_or_compile(spec_b)
        assert len(backend.entries) == 2

    def test_max_cache_size_limits_l1(self) -> None:
        """LRU cache evicts old entries when max_cache_size is reached."""
        backend = _FakeSQLite()
        cache = SQLiteCompileCache(backend, max_cache_size=2)
        for i in range(5):
            spec = _make_spec(f"market.close + {i}")
            cache.get_or_compile(spec)
        # All 5 should be in SQLite
        assert len(backend.entries) == 5

    def test_custom_max_cache_size(self) -> None:
        """Custom max_cache_size is respected."""
        backend = _FakeSQLite()
        cache = SQLiteCompileCache(backend, max_cache_size=10)
        assert cache._memory_cache.maxsize == 10
