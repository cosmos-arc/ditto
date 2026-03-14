"""Port-side compile cache service for unified derived expressions."""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any, Protocol

import orjson
from ditto_core.engine.expression import ExpressionCompiler
from ditto_core.engine.materialization import CompiledDerivedExpression
from ditto_core.engine.specs import DerivedSpec

__all__ = ["SQLiteCompileCacheBackend", "SQLiteCompileCacheService"]


class SQLiteCompileCacheBackend(Protocol):
    """Minimal SQL client contract needed by the compile cache service."""

    def execute(
        self,
        sql: str,
        params: list[Any] | tuple[Any, ...] | None = None,
    ) -> object:
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


class SQLiteCompileCacheService:
    """Persist compile metadata while keeping an in-process L1 cache."""

    def __init__(self, sqlite_client: SQLiteCompileCacheBackend) -> None:
        self._sqlite_client = sqlite_client
        self._memory_cache: dict[str, CompiledDerivedExpression] = {}
        self._compiler = ExpressionCompiler()

    def get_or_compile(
        self,
        spec: DerivedSpec,
        *,
        force_recompile: bool = False,
    ) -> CompiledDerivedExpression:
        """Return a compiled expression, storing metadata on cache miss."""
        compiled = self._compiler.compile(spec)
        cache_key = compiled.compile_identity.cache_key
        if not force_recompile and cache_key in self._memory_cache:
            return self._memory_cache[cache_key]

        self._memory_cache[cache_key] = compiled
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
                str(compiled.expr),
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
        return compiled
