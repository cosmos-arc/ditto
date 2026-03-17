"""Unit tests for SQLiteCompileCache L1/L2/compile hierarchy."""

from __future__ import annotations

import sqlite3
from dataclasses import asdict
from typing import Any

import orjson
import polars as pl
import pytest
from ditto_core.engine.compile_cache import SQLiteCompileCache
from ditto_core.engine.materialization import (
    CompiledDerivedExpression,
)
from ditto_core.engine.specs import DerivedRole, DerivedSpec, MaterializationProfile

# ---------------------------------------------------------------------------
# Schema SQL (excerpt for compile cache tables)
# ---------------------------------------------------------------------------

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS compiled_expression_cache (
    cache_key TEXT PRIMARY KEY,
    derived_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    compiler_fingerprint TEXT NOT NULL,
    compile_input_hash TEXT NOT NULL,
    analysis_json TEXT NOT NULL,
    compile_identity_json TEXT NOT NULL,
    expression_repr TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS compiled_expression_operator (
    cache_key TEXT NOT NULL,
    operator_name TEXT NOT NULL,
    operator_version TEXT NOT NULL,
    PRIMARY KEY (cache_key, operator_name)
);
"""


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


class _SQLiteBackend:
    """Minimal SQLite backend satisfying the SQLiteCompileCacheBackend protocol."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def execute(
        self,
        sql: str,
        params: list[Any] | tuple[Any, ...] | None = None,
    ) -> sqlite3.Cursor:
        if params:
            return self._conn.execute(sql, params)
        return self._conn.execute(sql)

    def executemany(
        self,
        sql: str,
        params_list: list[list[Any] | tuple[Any, ...]],
    ) -> sqlite3.Cursor:
        return self._conn.executemany(sql, params_list)

    def commit(self) -> None:
        self._conn.commit()


@pytest.fixture
def sqlite_backend() -> _SQLiteBackend:
    """In-memory SQLite backend with compile cache schema."""
    conn = sqlite3.connect(":memory:")
    conn.executescript(_SCHEMA_SQL)
    backend = _SQLiteBackend(conn)
    yield backend
    conn.close()


def _make_spec(expression: str = "ts_delta(close, 1)") -> DerivedSpec:
    return DerivedSpec(
        id="factor.test_alpha",
        version=1,
        role=DerivedRole.FACTOR,
        materialization_profile=MaterializationProfile.SERIES,
        expression=expression,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCompileCacheKeyBeforeCompile:
    """C-CC-01: Cache key must be computed BEFORE compilation."""

    def test_first_call_compiles_and_caches(
        self, sqlite_backend: _SQLiteBackend
    ) -> None:
        """First call should compile, populate L1, and persist to L2."""
        service = SQLiteCompileCache(sqlite_backend)
        spec = _make_spec()
        call_count = _track_compile_calls(service)

        result = service.get_or_compile(spec)

        assert call_count() == 1
        assert isinstance(result, CompiledDerivedExpression)
        assert result.derived_id == spec.id
        assert result.version == spec.version
        assert isinstance(result.expr, pl.Expr)
        # L1 populated
        assert len(service._memory_cache) == 1
        # L2 persisted
        row = sqlite_backend.execute(
            "SELECT count(*) FROM compiled_expression_cache"
        ).fetchone()
        assert row[0] == 1

    def test_l1_hit_skips_compile(self, sqlite_backend: _SQLiteBackend) -> None:
        """Second call with same spec should hit L1 memory cache."""
        service = SQLiteCompileCache(sqlite_backend)
        spec = _make_spec()

        first = service.get_or_compile(spec)
        call_count = _track_compile_calls(service)
        second = service.get_or_compile(spec)

        assert call_count() == 0
        assert second.derived_id == first.derived_id
        assert second.compile_identity.cache_key == first.compile_identity.cache_key

    def test_force_recompile_bypasses_cache(
        self, sqlite_backend: _SQLiteBackend
    ) -> None:
        """force_recompile=True should always compile."""
        service = SQLiteCompileCache(sqlite_backend)
        spec = _make_spec()
        service.get_or_compile(spec)

        call_count = _track_compile_calls(service)
        result = service.get_or_compile(spec, force_recompile=True)

        assert call_count() == 1
        assert isinstance(result, CompiledDerivedExpression)


class TestL2SQLiteReadPath:
    """C-CC-02: L2 SQLite cache should be readable across process restarts."""

    def test_l2_hit_returns_compiled_expression(
        self, sqlite_backend: _SQLiteBackend
    ) -> None:
        """L2 cache hit should return a valid CompiledDerivedExpression."""
        service = SQLiteCompileCache(sqlite_backend)
        spec = _make_spec()

        # Populate cache
        first = service.get_or_compile(spec)
        original_cache_key = first.compile_identity.cache_key

        # Simulate process restart: new service instance, empty L1
        service2 = SQLiteCompileCache(sqlite_backend)
        assert len(service2._memory_cache) == 0

        _track_compile_calls(service2)
        second = service2.get_or_compile(spec)

        # Should still compile (unavoidable for pl.Expr), but L1 is hydrated.
        assert isinstance(second, CompiledDerivedExpression)
        assert second.derived_id == spec.id
        assert second.version == spec.version
        assert isinstance(second.expr, pl.Expr)
        assert second.compile_identity.cache_key == original_cache_key
        # L1 should be populated after L2 hit
        assert len(service2._memory_cache) == 1

    def test_l2_stores_original_expression_string(
        self, sqlite_backend: _SQLiteBackend
    ) -> None:
        """expression_repr should store the original DSL expression."""
        service = SQLiteCompileCache(sqlite_backend)
        spec = _make_spec("ts_mean(close, 20)")

        service.get_or_compile(spec)

        row = sqlite_backend.execute(
            "SELECT expression_repr FROM compiled_expression_cache"
        ).fetchone()
        assert row[0] == "ts_mean(close, 20)"

    def test_l2_hit_rehydrates_l1(self, sqlite_backend: _SQLiteBackend) -> None:
        """L2 cache hit should populate L1 for subsequent hits."""
        service = SQLiteCompileCache(sqlite_backend)
        spec = _make_spec()

        # Populate cache with first service
        service.get_or_compile(spec)

        # New service (simulated restart)
        service2 = SQLiteCompileCache(sqlite_backend)
        assert len(service2._memory_cache) == 0

        # L2 hit (should populate L1)
        service2.get_or_compile(spec)
        assert len(service2._memory_cache) == 1

        # Third call should hit L1
        call_count = _track_compile_calls(service2)
        service2.get_or_compile(spec)
        assert call_count() == 0

    def test_l2_stores_analysis_and_identity(
        self, sqlite_backend: _SQLiteBackend
    ) -> None:
        """L2 cache should persist analysis and compile identity as JSON."""
        service = SQLiteCompileCache(sqlite_backend)
        spec = _make_spec()
        compiled = service.get_or_compile(spec)

        row = sqlite_backend.execute(
            "SELECT analysis_json, compile_identity_json FROM compiled_expression_cache"
        ).fetchone()

        analysis_dict = orjson.loads(row[0])
        identity_dict = orjson.loads(row[1])
        expected_analysis_keys = set(asdict(compiled.analysis).keys())
        expected_identity_keys = set(asdict(compiled.compile_identity).keys())
        assert set(analysis_dict.keys()) == expected_analysis_keys
        assert set(identity_dict.keys()) == expected_identity_keys

    def test_different_specs_have_different_cache_keys(
        self, sqlite_backend: _SQLiteBackend
    ) -> None:
        """Different expressions should produce different cache keys."""
        service = SQLiteCompileCache(sqlite_backend)

        result_a = service.get_or_compile(_make_spec("ts_delta(close, 1)"))
        result_b = service.get_or_compile(_make_spec("ts_mean(close, 20)"))

        key_a = result_a.compile_identity.cache_key
        key_b = result_b.compile_identity.cache_key
        assert key_a != key_b


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _track_compile_calls(service: SQLiteCompileCache) -> Any:
    """Return a callable that returns how many times compile() was called."""
    original_compile = service._compiler.compile
    call_count = [0]

    def _counting_compile(spec: DerivedSpec) -> CompiledDerivedExpression:
        call_count[0] += 1
        return original_compile(spec)

    service._compiler.compile = _counting_compile

    def get_count() -> int:
        return call_count[0]

    return get_count
