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
from ditto_data.config.data_store import DataStoreSettings as _DataStoreSettings
from ditto_data.quality.config import DQSettings
from ditto_features.config import FeatureArtifactStoreSettings
from ditto_platform.foundation import (
    ConfigInitCoordinator,
    ConfigLoader,
    DataCache,
    DataRootInitProvider,
    Environment,
    ObservabilitySettings,
    Settings,
    SystemSettings,
    get_environment,
    logger,
)
from ditto_platform.services import NotificationSettings

from ditto_apps.config import load_env_file
from ditto_apps.registry.infra.init_providers import MetadataDbInitProvider

__all__ = [
    "ConfigProvider",
    "RuntimeFlags",
    "data_root_init_directories",
    "data_root_init_directories_from_data_store",
    "data_store_settings_type",
    "load_data_store_settings",
]


def data_store_settings_type() -> type[_DataStoreSettings]:
    """Return the DI key for data store settings without re-exporting it."""
    return _DataStoreSettings


def load_data_store_settings(
    config_loader: ConfigLoader | None = None,
) -> _DataStoreSettings:
    """加载数据存储配置。"""
    loader = (
        config_loader if config_loader is not None else ConfigLoader(get_environment())
    )
    values: dict[str, Any] = load_env_file(loader, "data_store")

    # 支持 CLI/API 透传的环境变量覆盖
    if override := os.getenv("DITTO_DATA_ROOT"):
        values["data_root"] = override
    if override := os.getenv("SQLITE_PATH"):
        values["sqlite_path"] = override
    if override := os.getenv("DUCKDB_PATH"):
        values["duckdb_path"] = override
    if override := os.getenv("LOG_DIR"):
        values["logs_path_override"] = override

    return _DataStoreSettings.model_validate(values)


def data_root_init_directories(
    data_store_settings: _DataStoreSettings,
    feature_artifact_store_settings: FeatureArtifactStoreSettings,
) -> list[str]:
    """返回组合根需要初始化的所有 data-root 相对目录。"""
    directories: list[str] = []
    seen: set[str] = set()
    for directory in (
        *data_store_settings.all_directories(),
        *feature_artifact_store_settings.all_directories(),
    ):
        if directory in seen:
            continue
        seen.add(directory)
        directories.append(directory)
    return directories


def data_root_init_directories_from_data_store(
    data_store_settings: _DataStoreSettings,
) -> list[str]:
    """从 DataStoreSettings 派生完整 data-root 初始化目录清单。"""
    return data_root_init_directories(
        data_store_settings,
        FeatureArtifactStoreSettings(data_root=data_store_settings.data_root),
    )


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
        self,
        data_store_settings: _DataStoreSettings,
        feature_artifact_store_settings: FeatureArtifactStoreSettings,
    ) -> ConfigInitCoordinator:
        """配置初始化协调器（注册所有 providers）."""
        coordinator = ConfigInitCoordinator()
        coordinator.register(
            DataRootInitProvider(
                data_root_init_directories(
                    data_store_settings,
                    feature_artifact_store_settings,
                )
            )
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
    def data_store_settings(self, config_loader: ConfigLoader) -> _DataStoreSettings:
        """加载数据存储配置。"""
        return load_data_store_settings(config_loader)

    @provide
    def feature_artifact_store_settings(
        self,
        data_store_settings: _DataStoreSettings,
    ) -> FeatureArtifactStoreSettings:
        """派生 features/factors artifact 存储配置。"""
        return FeatureArtifactStoreSettings(data_root=data_store_settings.data_root)

    @provide
    def data_root(self, settings: _DataStoreSettings) -> Path:
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
        settings: _DataStoreSettings,
    ) -> FileStorageSettings:
        """派生文件存储路径配置。"""
        return FileStorageSettings(
            data_root=settings.data_root,
            log_root=settings.paths.utility.logs,
            backup_root=settings.paths.utility.backups,
            temp_root=settings.paths.utility.temp,
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
