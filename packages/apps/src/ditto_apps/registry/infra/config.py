"""配置 Provider（Composition Root）。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dishka import Provider, Scope, provide
from ditto_application.settings import TradingSettings
from ditto_data.config import DataSourceSettings, FileStorageSettings
from ditto_data.config.data_source_validation import DataSourceValidationProvider
from ditto_data.config.data_store import DataStoreSettings
from ditto_data.quality.config import DQSettings
from ditto_platform.foundation import logger
from ditto_platform.foundation.cache import DataCache
from ditto_platform.foundation.config import (
    ConfigInitCoordinator,
    ConfigLoader,
    Environment,
    get_environment,
)
from ditto_platform.foundation.config.providers import DataRootInitProvider
from ditto_platform.foundation.config.settings import (
    ObservabilitySettings,
    Settings,
    SystemSettings,
)
from ditto_platform.services.notification import NotificationSettings

from ditto_apps.config import load_env_file
from ditto_apps.registry.init_providers import MetadataDbInitProvider

__all__ = ["ConfigProvider", "DataStoreSettings", "RuntimeFlags"]


def _load_keyring_secret(service: str, key: str) -> str | None:
    """
    从 keyring 加载密钥（运行时降级）。

    Args:
        service: keyring 服务名称
        key: keyring 密钥名称

    Returns:
        密钥值，如果 keyring 不可用或读取失败则返回 None

    """
    try:
        import keyring  # noqa: PLC0415  # 可选依赖延迟加载
    except ImportError:
        logger.debug("keyring not available, skipping", service=service)
        return None

    try:
        return keyring.get_password(service, key)
    except Exception as e:
        logger.warning("keyring read failed", service=service, error=str(e))
        return None


@dataclass(frozen=True)
class RuntimeFlags:
    """运行时标志。"""

    pytest_running: bool
    assertions_enabled: bool
    verbose_logging: bool


def _detect_runtime_flags(environment: Environment) -> RuntimeFlags:
    pytest_running = "PYTEST_CURRENT_TEST" in os.environ

    if environment == Environment.TESTING:
        return RuntimeFlags(
            pytest_running=pytest_running,
            assertions_enabled=True,
            verbose_logging=False,
        )
    if environment == Environment.PRODUCTION:
        return RuntimeFlags(
            pytest_running=pytest_running,
            assertions_enabled=False,
            verbose_logging=False,
        )
    return RuntimeFlags(
        pytest_running=pytest_running,
        assertions_enabled=True,
        verbose_logging=True,
    )


class ConfigProvider(Provider):
    """统一配置提供者（仅在 Port 层加载配置）。"""

    scope = Scope.APP

    @provide
    def environment(self) -> Environment:
        """提供运行环境枚举。"""
        return get_environment()

    @provide
    def config_loader(self, environment: Environment) -> ConfigLoader:
        """提供配置文件加载器。"""
        return ConfigLoader(environment)

    @provide
    def init_coordinator(
        self, data_store_settings: DataStoreSettings
    ) -> ConfigInitCoordinator:
        """配置初始化协调器（注册所有 providers）."""
        coordinator = ConfigInitCoordinator()
        coordinator.register(
            DataRootInitProvider(data_store_settings.all_directories())
        )
        coordinator.register(DataSourceValidationProvider())
        coordinator.register(MetadataDbInitProvider())
        return coordinator

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
    def data_store_settings(self, config_loader: ConfigLoader) -> DataStoreSettings:
        """加载数据存储配置。"""
        values: dict[str, Any] = load_env_file(config_loader, "data_store")

        # 支持 CLI 透传的环境变量覆盖
        if override := os.getenv("DITTO_DATA_ROOT"):
            values["data_root"] = override
        if override := os.getenv("SQLITE_PATH"):
            values["sqlite_path"] = override
        if override := os.getenv("DUCKDB_PATH"):
            values["duckdb_path"] = override
        # 支持 LOG_DIR 环境变量（Docker 部署用）
        if override := os.getenv("LOG_DIR"):
            values["logs_path_override"] = override

        return DataStoreSettings.model_validate(values)

    @provide
    def data_root(self, settings: DataStoreSettings) -> Path:
        """提供数据根目录路径。"""
        return settings.data_root

    @provide
    def data_source_settings(self, config_loader: ConfigLoader) -> DataSourceSettings:
        """加载数据源配置。"""
        data_source_values = load_env_file(config_loader, "data_source")

        # Token 加载优先级：环境变量 > keyring > 配置文件
        # 安全规范：Token 不应明文存储在配置文件中

        # Tushare Token
        token: str | None = os.getenv("TUSHARE_TOKEN") or _load_keyring_secret(
            "tushare", "token"
        )
        if token:
            data_source_values["tushare_token"] = token

        # FRED API Key
        fred_api_key: str | None = os.getenv("FRED_API_KEY") or _load_keyring_secret(
            "fred", "api_key"
        )
        if fred_api_key:
            data_source_values["fred_api_key"] = fred_api_key

        return DataSourceSettings.model_validate(data_source_values)

    @provide
    def file_storage_settings(
        self,
        settings: DataStoreSettings,
    ) -> FileStorageSettings:
        """派生文件存储路径配置。"""
        return FileStorageSettings(
            data_root=settings.data_root,
            log_root=settings.logs_path,
            backup_root=settings.backups_path,
            temp_root=settings.temp_path,
        )

    @provide
    def dq_settings(
        self,
        config_loader: ConfigLoader,
        environment: Environment,
    ) -> DQSettings:
        """加载 DQ 配置并注入环境与项目根目录。"""
        dq_values = load_env_file(config_loader, "dq")
        settings = DQSettings.model_validate(dq_values)
        return settings.model_copy(
            update={
                "environment": environment.value,
                "config_root": config_loader.config_root,
            }
        )

    @provide
    def notification_settings(
        self,
        config_loader: ConfigLoader,
    ) -> NotificationSettings:
        """加载通知配置。"""
        values = load_env_file(config_loader, "notification")
        return NotificationSettings.model_validate(values)

    @provide
    def trading_settings(self) -> TradingSettings:
        """加载交易配置（通过环境变量覆盖，无需配置文件）。"""
        values: dict[str, Any] = {}
        if override := os.getenv("DITTO_TRADING_CALENDAR_START"):
            values["trading_calendar_start"] = override
        if override := os.getenv("DITTO_TRADING_CALENDAR_END"):
            values["trading_calendar_end"] = override
        return TradingSettings(**values) if values else TradingSettings()

    @provide
    def runtime_flags(self, environment: Environment) -> RuntimeFlags:
        """提供运行时标志。"""
        return _detect_runtime_flags(environment)

    @provide
    def data_cache(self) -> DataCache[Any]:
        """提供数据缓存实例（应用级单例）。"""
        return DataCache[Any](ttl_seconds=300, max_size=10000)
