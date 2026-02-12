"""配置 Provider（Composition Root）。"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from dishka import Provider, Scope, provide
from ditto_core.quality.config import DQSettings
from ditto_datahub.config import (
    DatabaseSettings,
    DataRootConfig,
    DataSourceSettings,
    FileStorageSettings,
)
from ditto_foundation.cache import DataCache
from ditto_foundation.config import ConfigInitCoordinator, ConfigLoader, Environment
from ditto_foundation.config.settings import (
    ObservabilitySettings,
    Settings,
    SystemSettings,
)
from ditto_foundation.notification import NotificationSettings
from ditto_foundation.observability import init, shutdown
from ditto_foundation.observability.config import ObservabilityConfig

from ditto_port.config import load_env_file

__all__ = ["ConfigProvider"]


def _detect_runtime_flags(environment: Environment) -> dict[str, bool]:
    pytest_running = "PYTEST_CURRENT_TEST" in os.environ

    if environment == Environment.TESTING:
        return {
            "pytest_running": pytest_running,
            "assertions_enabled": True,
            "verbose_logging": False,
        }
    if environment == Environment.PRODUCTION:
        return {
            "pytest_running": pytest_running,
            "assertions_enabled": False,
            "verbose_logging": False,
        }
    return {
        "pytest_running": pytest_running,
        "assertions_enabled": True,
        "verbose_logging": True,
    }


class ConfigProvider(Provider):
    """统一配置提供者（仅在 Port 层加载配置）。"""

    scope = Scope.APP

    @provide
    def environment(self) -> Environment:
        """提供运行环境枚举。"""
        env_str = os.getenv("ENVIRONMENT", "development")
        return Environment.from_str(env_str)

    @provide
    def config_loader(self, environment: Environment) -> ConfigLoader:
        """提供配置文件加载器。"""
        return ConfigLoader(environment)

    @provide
    def init_coordinator(self) -> ConfigInitCoordinator:
        """提供配置初始化协调器。"""
        return ConfigInitCoordinator()

    @provide
    def settings(
        self,
        config_loader: ConfigLoader,
        environment: Environment,
    ) -> Settings:
        """加载系统与观测配置。"""
        system_values = load_env_file(config_loader, "system")
        system = SystemSettings.model_validate(system_values)
        system = system.model_copy(update={"environment": environment})

        observability_values = load_env_file(config_loader, "observability")
        observability = ObservabilitySettings.model_validate(observability_values)

        return Settings(system=system, observability=observability)

    @provide
    def data_root_config(self, config_loader: ConfigLoader) -> DataRootConfig:
        """加载数据根目录配置。"""
        data_store_values = load_env_file(config_loader, "data_store")
        return DataRootConfig.model_validate(data_store_values)

    @provide
    def data_root(self, data_root_config: DataRootConfig) -> Path:
        """提供数据根目录路径。"""
        return data_root_config.data_root

    @provide
    def database_settings(
        self,
        config_loader: ConfigLoader,
        data_root_config: DataRootConfig,
    ) -> DatabaseSettings:
        """加载数据库配置并补齐默认路径。"""
        database_values = load_env_file(config_loader, "database")
        base = DatabaseSettings.model_validate(database_values)

        sqlite_path = base.sqlite_path or data_root_config.metadata_db_path
        duckdb_path = base.duckdb_path or (
            data_root_config.db_path / "duckdb/ditto.duckdb"
        )

        return DatabaseSettings(
            sqlite_path=sqlite_path,
            duckdb_path=duckdb_path,
        )

    @provide
    def data_source_settings(self, config_loader: ConfigLoader) -> DataSourceSettings:
        """加载数据源配置。"""
        data_source_values = load_env_file(config_loader, "data_source")
        return DataSourceSettings.model_validate(data_source_values)

    @provide
    def file_storage_settings(
        self,
        data_root_config: DataRootConfig,
    ) -> FileStorageSettings:
        """派生文件存储路径配置。"""
        return FileStorageSettings(
            data_root=data_root_config.data_root,
            log_root=data_root_config.logs_path,
            backup_root=data_root_config.backups_path,
            temp_root=data_root_config.temp_path,
        )

    @provide
    def dq_settings(
        self,
        config_loader: ConfigLoader,
        environment: Environment,
    ) -> DQSettings:
        """加载 DQ 配置并注入环境。"""
        dq_values = load_env_file(config_loader, "dq")
        settings = DQSettings.model_validate(dq_values)
        return settings.model_copy(update={"environment": environment.value})

    @provide
    def notification_settings(
        self,
        config_loader: ConfigLoader,
    ) -> NotificationSettings:
        """加载通知配置。"""
        values = load_env_file(config_loader, "notification")
        return NotificationSettings.model_validate(values)

    @provide
    def observability_config(
        self,
        settings: Settings,
        data_root_config: DataRootConfig,
    ) -> ObservabilityConfig:
        """构建观测配置对象。"""
        obs = settings.observability
        env = settings.system.environment
        flags = _detect_runtime_flags(env)

        return ObservabilityConfig(
            service_name="ditto-server",
            environment=env,
            log_dir=str(data_root_config.logs_path),
            log_level=obs.log_level,
            log_format=obs.log_format,
            log_to_console=obs.log_to_console,
            log_to_file=obs.log_to_file,
            tracing_enabled=obs.tracing_enabled,
            tracing_exporter=obs.tracing_exporter,
            tracing_sample_rate=obs.tracing_sample_rate,
            metrics_enabled=obs.metrics_enabled,
            metrics_exporter=obs.metrics_exporter,
            vm_endpoint=obs.vm_endpoint,
            pytest_running=flags["pytest_running"],
            assertions_enabled=flags["assertions_enabled"],
            verbose_logging=flags["verbose_logging"],
        )

    @provide
    def observability(self, config: ObservabilityConfig) -> Iterator[None]:
        """初始化并在生命周期结束时关闭观测系统。"""
        init(config)
        yield
        shutdown()

    @provide
    def data_cache(self) -> DataCache[Any]:
        """提供数据缓存实例（应用级单例）。"""
        return DataCache[Any](ttl_seconds=300, max_size=10000)
