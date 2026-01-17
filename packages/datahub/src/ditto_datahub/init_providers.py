"""
DataHub 配置初始化提供者.

实现 DQ 配置和数据库 Schema 的初始化提供者。
"""

from __future__ import annotations

import shutil
from pathlib import Path

from ditto_foundation import logger
from ditto_foundation.config.initializer import (
    ConfigInitProvider,
    InitResult,
    InitScope,
    get_config_coordinator,
)

from ditto_datahub.runtime.sqlite_pool import SQLitePool


class DQConfigProvider(ConfigInitProvider):
    """
    DQ 配置初始化提供者.

    负责将包内默认 DQ 配置复制到 {data_root}/config/dq/。
    """

    @property
    def name(self) -> str:
        """返回提供者名称."""
        return "dq_config"

    @property
    def scope(self) -> InitScope:
        """返回初始化作用域."""
        return InitScope.STARTUP

    def check(self, data_root: Path) -> bool:
        """
        检查 DQ 配置是否已存在.

        Args:
            data_root: 数据根目录

        Returns:
            True 表示需要初始化，False 表示已存在

        """
        config_dir = data_root / "config" / "dq"

        # 如果目录不存在，需要初始化
        if not config_dir.exists():
            return True

        # 如果目录为空（没有 .yml 或 .yaml 文件），需要初始化
        config_files = list(config_dir.glob("*.yml")) + list(config_dir.glob("*.yaml"))
        return len(config_files) == 0

    def initialize(self, data_root: Path) -> InitResult:
        """
        初始化 DQ 配置.

        Args:
            data_root: 数据根目录

        Returns:
            初始化结果

        """
        logger.info(
            "Initializing DQ config",
            event="dq_config_init_start",
            data_root=str(data_root),
        )

        # 创建用户配置目录
        user_config_dir = data_root / "config" / "dq"
        user_config_dir.mkdir(parents=True, exist_ok=True)

        # 获取包内配置目录
        package_config_dir = self._get_package_config_dir()

        if not package_config_dir.exists():
            error_msg = f"Package config directory not found: {package_config_dir}"
            logger.error(
                "DQ config initialization failed",
                event="dq_config_init_failed",
                reason="package_config_not_found",
                package_config_dir=str(package_config_dir),
            )
            return InitResult(
                provider=self.name,
                success=False,
                message=error_msg,
            )

        # 复制配置文件（跳过已存在的）
        copied_count = 0
        skipped_count = 0
        extensions = ["*.yml", "*.yaml"]

        for ext in extensions:
            for config_file in package_config_dir.glob(ext):
                target = user_config_dir / config_file.name
                if not target.exists():
                    shutil.copy(config_file, target)
                    logger.debug(
                        "Copied DQ config file",
                        event="dq_config_file_copied",
                        source=str(config_file),
                        target=str(target),
                    )
                    copied_count += 1
                else:
                    logger.debug(
                        "Skipped existing DQ config file",
                        event="dq_config_file_skipped",
                        file=str(target),
                    )
                    skipped_count += 1

        message = (
            f"DQ config initialized: {copied_count} files copied, "
            f"{skipped_count} files skipped"
        )
        logger.info(
            "DQ config initialized successfully",
            event="dq_config_init_complete",
            copied_count=copied_count,
            skipped_count=skipped_count,
        )

        return InitResult(
            provider=self.name,
            success=True,
            message=message,
        )

    def _get_package_config_dir(self) -> Path:
        """
        获取包内配置目录.

        Returns:
            包内配置目录路径

        """
        # 从当前文件位置推导包根目录
        # 当前文件: packages/datahub/src/ditto_datahub/init_providers.py
        # 包根目录: packages/datahub/
        # 配置目录: packages/datahub/config/dq_rules/
        current_file = Path(__file__)
        return current_file.parent.parent.parent / "config" / "dq_rules"


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

            # 创建 SQLitePool 并初始化 schema
            pool = SQLitePool(str(db_path))
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

    此函数应在应用启动时调用，用于注册 DataHub 层的配置初始化提供者。
    """
    coordinator = get_config_coordinator()
    coordinator.register(DQConfigProvider())
    coordinator.register(DatabaseSchemaProvider())

    logger.debug(
        "DataHub config init providers registered",
        event="datahub_providers_registered",
        providers=["dq_config", "database_schema"],
    )
