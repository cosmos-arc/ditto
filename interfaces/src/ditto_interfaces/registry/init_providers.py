"""Port 层初始化提供者."""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path

from ditto_infra.foundation.config.initializer import (
    ConfigInitProvider,
    InitResult,
    InitScope,
)
from ditto_infra.foundation.db.sqlite_pool import SQLitePool
from loguru import logger


class MetadataDbInitProvider(ConfigInitProvider):
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
