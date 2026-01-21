"""
DataHub 配置初始化提供者.

实现数据库 Schema 的初始化提供者.
"""

from __future__ import annotations

from pathlib import Path

from ditto_foundation import SQLitePool, logger
from ditto_foundation.config.initializer import (
    ConfigInitProvider,
    InitResult,
    InitScope,
    get_config_coordinator,
)


class DatabaseSchemaProvider(ConfigInitProvider):
    """
    数据库 Schema 初始化提供者.

    负责初始化数据库 Schema。
    """

    @property
    def name(self) -> str:
        """返回提供者名称."""
        return "database_schema"

    @property
    def scope(self) -> InitScope:
        """返回初始化作用域."""
        return InitScope.STARTUP

    def check(self, data_root: Path) -> bool:
        """
        检查数据库 Schema 是否已存在.

        Args:
            data_root: 数据根目录

        Returns:
            True 表示需要初始化，False 表示已存在

        """
        db_path = data_root / "meta" / "hub.sqlite"
        return not db_path.exists()

    def initialize(self, data_root: Path) -> InitResult:
        """
        初始化数据库 Schema.

        Args:
            data_root: 数据根目录

        Returns:
            初始化结果

        """
        logger.info(
            "Initializing database schema",
            event="database_schema_init_start",
            data_root=str(data_root),
        )

        try:
            # 数据库路径
            db_path = data_root / "meta" / "hub.sqlite"

            # 创建父目录
            meta_dir = data_root / "meta"
            meta_dir.mkdir(parents=True, exist_ok=True)

            # 获取 schema.sql 路径
            # 当前文件: packages/datahub/src/ditto_datahub/init_providers.py
            # schema.sql: packages/datahub/src/ditto_datahub/scripts/schema.sql
            schema_path = Path(__file__).parent / "scripts" / "schema.sql"

            # 创建 SQLitePool 并初始化 schema
            pool = SQLitePool(str(db_path), schema_path=schema_path)
            pool.init_schema()
            pool.close()

            logger.info(
                "Database schema initialized successfully",
                event="database_schema_init_complete",
                db_path=str(db_path),
            )

            return InitResult(
                provider=self.name,
                success=True,
                message=f"Database schema initialized at {db_path}",
            )

        except Exception as e:
            logger.error(
                "Database schema initialization failed",
                event="database_schema_init_failed",
                error=str(e),
                error_type=type(e).__name__,
            )
            return InitResult(
                provider=self.name,
                success=False,
                message=f"{type(e).__name__}: {e}",
            )


def register_datahub_providers() -> None:
    """
    注册 DataHub 配置初始化提供者到全局协调器.

    此函数应在应用启动时调用，用于注册 DataHub 层的配置初始化提供者.

    Note: DQ 配置初始化已移到 Core 包或应用层(Port)。
    """
    coordinator = get_config_coordinator()
    coordinator.register(DatabaseSchemaProvider())

    logger.debug(
        "DataHub config init providers registered",
        event="datahub_providers_registered",
        providers=["database_schema"],
    )
