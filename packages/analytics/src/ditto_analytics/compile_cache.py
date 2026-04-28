"""
Compile cache for unified derived expressions.

Implements a two-tier cache hierarchy:

1. **L1 (memory)**: In-process LRU cache keyed by cache key.  O(1) lookup.
2. **L2 (SQLite)**: Persistent cache across process restarts.

Lookup order: L1 -> L2 -> full compile.  On L2 hit the expression is
re-compiled (unavoidable -- ``pl.Expr`` cannot be deserialized from a
string), but the L1 cache is re-hydrated so subsequent calls within the
same process avoid compilation entirely.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any, Protocol

import cachebox
import orjson
from ditto_kernel.strategy import DerivedSpec

from ditto_analytics.expression import ExpressionCompiler, compute_compile_cache_key
from ditto_analytics.materialization import CompiledDerivedExpression

__all__ = ["SQLiteCompileCache", "SQLiteCompileCacheBackend"]


class SQLiteCompileCacheBackend(Protocol):
    """Minimal SQL client contract needed by the compile cache."""

    def execute(
        self,
        sql: str,
        params: list[Any] | tuple[Any, ...] | None = None,
    ) -> CursorLike:
        """Execute one SQL statement."""
        ...

    def executemany(
        self,
        sql: str,
        params_list: list[list[Any] | tuple[Any, ...]],
    ) -> object:
        """Execute one SQL statement against multiple parameter sets."""
        ...

    def commit(self) -> None:
        """Commit the current transaction."""
        ...


class CursorLike(Protocol):
    """Minimal cursor contract for reading SQL results."""

    def fetchone(self) -> tuple[Any, ...] | None:
        """Return the next row or None."""
        ...


class SQLiteCompileCache:
    """Persist compile metadata while keeping an in-process L1 LRU cache."""

    def __init__(
        self,
        sqlite_client: SQLiteCompileCacheBackend,
        *,
        max_cache_size: int = 256,
    ) -> None:
        self._sqlite_client = sqlite_client
        self._memory_cache = cachebox.LRUCache[str, CompiledDerivedExpression](
            maxsize=max_cache_size,
        )
        self._compiler = ExpressionCompiler()

    def get_or_compile(
        self,
        spec: DerivedSpec,
        *,
        force_recompile: bool = False,
    ) -> CompiledDerivedExpression:
        """
        Return a compiled expression, checking L1 then L2 before compiling.

        Lookup order:
        1. L1 memory cache (LRU lookup)
        2. L2 SQLite cache (confirms entry exists, then re-compiles)
        3. Full compile + persist to L1 and L2
        """
        # Pre-compute cache key and AST to avoid double-parsing.
        cache_key, _analysis, _identity, ast = compute_compile_cache_key(spec)

        # L1 hit
        if not force_recompile and cache_key in self._memory_cache:
            return self._memory_cache[cache_key]

        # L2 hit: if the key exists in SQLite we know the expression
        # was previously compiled successfully.  Re-compile using the
        # pre-parsed AST (avoids redundant tokenization + parsing) and
        # re-hydrate L1.
        if not force_recompile and self._has_sqlite_entry(cache_key):
            compiled = self._compiler.compile(spec, ast=ast)
            self._memory_cache[cache_key] = compiled
            return compiled

        # Full compile + persist to L1 and L2
        compiled = self._compiler.compile(spec, ast=ast)
        self._memory_cache[cache_key] = compiled
        self._persist_to_sqlite(spec, compiled)
        return compiled

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _has_sqlite_entry(self, cache_key: str) -> bool:
        """Check whether a cache key exists in the L2 SQLite backend."""
        row = self._sqlite_client.execute(
            "SELECT 1 FROM compiled_expression_cache WHERE cache_key = ?",
            (cache_key,),
        )
        result = _fetch_one(row)
        return result is not None

    def _persist_to_sqlite(
        self,
        spec: DerivedSpec,
        compiled: CompiledDerivedExpression,
    ) -> None:
        """Write compiled metadata to the L2 SQLite backend."""
        cache_key = compiled.compile_identity.cache_key
        self._sqlite_client.execute(
            """
            INSERT OR REPLACE INTO compiled_expression_cache (
                cache_key, derived_id, version,
                compiler_fingerprint, compile_input_hash,
                analysis_json, compile_identity_json,
                expression_repr, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                cache_key,
                compiled.derived_id,
                compiled.version,
                compiled.compile_identity.compiler_fingerprint,
                compiled.compile_identity.compile_input_hash,
                orjson.dumps(asdict(compiled.analysis)).decode(),
                orjson.dumps(asdict(compiled.compile_identity)).decode(),
                spec.expression,
                datetime.now(UTC).isoformat(),
            ),
        )
        self._sqlite_client.execute(
            "DELETE FROM compiled_expression_operator WHERE cache_key = ?",
            (cache_key,),
        )
        self._sqlite_client.executemany(
            """
            INSERT INTO compiled_expression_operator (
                cache_key, operator_name, operator_version
            ) VALUES (?, ?, ?)
            """,
            [
                (cache_key, name, version)
                for name, version in compiled.compile_identity.operator_versions
            ],
        )
        self._sqlite_client.commit()


# ------------------------------------------------------------------
# Module-level helpers
# ------------------------------------------------------------------


def _fetch_one(cursor: CursorLike) -> tuple[Any, ...] | None:
    """Extract the first row from a cursor-like object."""
    try:
        return cursor.fetchone()
    except AttributeError:
        return None
