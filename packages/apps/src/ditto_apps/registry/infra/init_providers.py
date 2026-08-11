"""Port 层初始化提供者."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from importlib.resources import files
from pathlib import Path

from ditto_platform.foundation import (
    InitResult,
    InitScope,
    SQLitePool,
    logger,
)

from ditto_apps.registry.infra.risk_persistence import initialize_r4_risk_schema

_R4_RISK_TABLES = frozenset(
    {"risk_events", "risk_state_snapshots", "daily_risk_reports"}
)


class MetadataDbInitProvider:
    """
    元数据库 Schema 初始化.

    职责：创建 metadata.sqlite 并初始化 schema。
    注意：如果数据库已存在且 schema 匹配，则跳过。
    """

    @property
    def name(self) -> str:
        """返回初始化提供者名称."""
        return "metadata_db"

    @property
    def scope(self) -> InitScope:
        """返回初始化作用域."""
        return InitScope.STARTUP

    def check(self, data_root: Path) -> bool:
        """检查数据库是否需要初始化."""
        db_path = data_root / "metadata" / "metadata.sqlite"
        return not db_path.exists()

    def initialize(self, data_root: Path) -> InitResult:
        """初始化数据库 schema."""
        try:
            db_path = data_root / "metadata" / "metadata.sqlite"
            db_path.parent.mkdir(parents=True, exist_ok=True)

            # 获取 schema.sql 路径
            schema_traversable = files("ditto_data.scripts") / "schema.sql"
            schema_path = Path(str(schema_traversable))

            pool = SQLitePool(str(db_path), schema_path=schema_path)
            pool.init_schema()
            pool.close()

            logger.info(
                "Metadata database initialized",
                event="metadata_db_init",
                db_path=str(db_path),
            )

            return InitResult(
                provider=self.name,
                success=True,
                message=f"Database initialized at {db_path}",
            )

        except Exception as e:
            logger.exception("Failed to initialize metadata database")
            return InitResult(
                provider=self.name,
                success=False,
                message=f"Failed: {e}",
            )


class R4RiskSchemaInitProvider:
    """Create the development-stage R4 risk tables during startup init."""

    @property
    def name(self) -> str:
        """Return the stable coordinator result key."""
        return "r4_risk_schema"

    @property
    def scope(self) -> InitScope:
        """Initialize alongside the metadata database at startup."""
        return InitScope.STARTUP

    def check(self, data_root: Path) -> bool:
        """Return whether any required R4 table is absent."""
        database = data_root / "metadata" / "metadata.sqlite"
        if not database.exists():
            return True
        with closing(sqlite3.connect(database)) as connection:
            existing = {
                str(row[0])
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
        return not existing >= _R4_RISK_TABLES

    def initialize(self, data_root: Path) -> InitResult:
        """Create R4 tables directly; no migration path is required in dev."""
        database = data_root / "metadata" / "metadata.sqlite"
        try:
            database.parent.mkdir(parents=True, exist_ok=True)
            with closing(sqlite3.connect(database)) as connection:
                initialize_r4_risk_schema(connection)
            return InitResult(
                provider=self.name,
                success=True,
                message=f"R4 risk schema initialized at {database}",
            )
        except Exception as exc:
            logger.exception("Failed to initialize R4 risk schema")
            return InitResult(
                provider=self.name,
                success=False,
                message=f"Failed: {exc}",
            )
