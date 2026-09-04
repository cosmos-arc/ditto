"""Registry composition for creating one empty current-schema runtime."""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from pathlib import Path

import orjson
from ditto_agent.storage.sqlite.decision_opinion_store import (
    DecisionOpinionShadowDatabase,
)
from ditto_analysis.storage.sqlite.experiments import ResearchExperimentDatabase
from ditto_data.config.data_store import DataStoreSettings
from ditto_execution.di import initialize_execution_storage
from ditto_platform.foundation import (
    ConfigInitCoordinator,
    DataRootInitProvider,
    InitScope,
    SQLitePool,
)

from ditto_apps.registry.agent.database_provider import build_agent_database
from ditto_apps.registry.infra.config import (
    data_root_init_directories_from_data_store,
)
from ditto_apps.registry.infra.init_providers import (
    MetadataDbInitProvider,
    R4RiskSchemaInitProvider,
)


class FreshRuntimeNotEmptyError(ValueError):
    """Raised when greenfield creation would touch pre-existing content."""


@dataclass(frozen=True, slots=True)
class FreshRuntimeSchema:
    """Authenticated SQLite schema created in the fresh runtime."""

    relative_path: str
    application_id: int
    user_version: int
    object_count: int


@dataclass(frozen=True, slots=True)
class FreshRuntimeManifest:
    """Stable receipt for an empty current-schema runtime creation."""

    schema_version: int
    data_root: Path
    schemas: tuple[FreshRuntimeSchema, ...]
    manifest_hash: str


def _schema_record(root: Path, relative_path: str) -> FreshRuntimeSchema:
    database = root / relative_path
    with sqlite3.connect(f"file:{database}?mode=ro", uri=True) as connection:
        application_id = int(connection.execute("PRAGMA application_id").fetchone()[0])
        user_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        object_count = int(
            connection.execute(
                "SELECT count(*) FROM sqlite_schema WHERE name NOT LIKE 'sqlite_%'"
            ).fetchone()[0]
        )
        integrity = str(connection.execute("PRAGMA integrity_check").fetchone()[0])
        foreign_key_violations = connection.execute(
            "PRAGMA foreign_key_check"
        ).fetchall()
    if integrity != "ok" or foreign_key_violations:
        raise RuntimeError(f"fresh runtime schema integrity failed: {relative_path}")
    return FreshRuntimeSchema(
        relative_path=relative_path,
        application_id=application_id,
        user_version=user_version,
        object_count=object_count,
    )


def _manifest_hash(root: Path, schemas: tuple[FreshRuntimeSchema, ...]) -> str:
    payload = {
        "schema_version": 1,
        "data_root": str(root),
        "schemas": [
            {
                "relative_path": item.relative_path,
                "application_id": item.application_id,
                "user_version": item.user_version,
                "object_count": item.object_count,
            }
            for item in schemas
        ],
    }
    return hashlib.sha256(
        orjson.dumps(payload, option=orjson.OPT_SORT_KEYS)
    ).hexdigest()


def create_fresh_runtime(data_root: Path) -> FreshRuntimeManifest:
    """Create current schemas only when the exact data root is absent or empty."""
    root = data_root.resolve(strict=False)
    if root.exists() and (not root.is_dir() or any(root.iterdir())):
        raise FreshRuntimeNotEmptyError(
            f"fresh runtime root must be absent or empty: {root}"
        )

    settings = DataStoreSettings(data_root=root)
    coordinator = ConfigInitCoordinator()
    coordinator.register(
        DataRootInitProvider(data_root_init_directories_from_data_store(settings))
    )
    coordinator.register(MetadataDbInitProvider())
    coordinator.register(R4RiskSchemaInitProvider())
    coordinator.initialize(scope=InitScope.STARTUP, data_root=root)

    research = ResearchExperimentDatabase(root)
    try:
        research.initialize()
    finally:
        research.close_all()

    trading_database = root / "trading" / "trading.sqlite"
    trading_database.parent.mkdir(parents=True, exist_ok=True)
    trading_pool = SQLitePool(str(trading_database))
    try:
        initialize_execution_storage(trading_pool)
    finally:
        trading_pool.close_all()

    agent = build_agent_database(root)
    agent.close()

    shadow = DecisionOpinionShadowDatabase(root)
    try:
        shadow.initialize()
    finally:
        shadow.close_all()

    schemas = tuple(
        _schema_record(root, relative_path)
        for relative_path in (
            "metadata/metadata.sqlite",
            "research/research.sqlite",
            "trading/trading.sqlite",
            "agent/agent.sqlite",
            "agent/agent-presentation.sqlite3",
            "agent-shadow/decision-opinion.sqlite",
        )
    )
    return FreshRuntimeManifest(
        schema_version=1,
        data_root=root,
        schemas=schemas,
        manifest_hash=_manifest_hash(root, schemas),
    )


__all__ = [
    "FreshRuntimeManifest",
    "FreshRuntimeNotEmptyError",
    "FreshRuntimeSchema",
    "create_fresh_runtime",
]
