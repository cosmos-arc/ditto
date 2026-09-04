"""配置 Provider（Composition Root）。"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dishka import Provider, Scope, provide
from ditto_application.settings import ResearchExecutionSettings, TradingSettings
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

from ditto_apps.config import RuntimePaths, load_env_file, load_runtime_paths
from ditto_apps.config.runtime import RuntimeConfigurationError
from ditto_apps.registry.infra.init_providers import (
    MetadataDbInitProvider,
    R4RiskSchemaInitProvider,
)

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
    runtime_paths: RuntimePaths | None = None,
) -> _DataStoreSettings:
    """加载数据存储配置。"""
    environment = get_environment()
    paths = runtime_paths or load_runtime_paths(environment)
    loader = config_loader or ConfigLoader(
        environment,
        config_root=paths.config_root,
    )
    values: dict[str, Any] = load_env_file(loader, "data_store")

    values["data_root"] = paths.state_root
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


_RUNTIME_SECRET_REFS = (("tushare", "token"), ("fred", "api_key"))
_PRELOADED_KEYRING_SECRETS: dict[tuple[str, str], str] = {}


def _load_keyring_secret(service: str, key: str) -> str | None:
    """
    从 keyring 加载密钥（运行时降级）。

    Args:
        service: keyring 服务名称
        key: keyring 密钥名称

    Returns:
        密钥值，如果 keyring 不可用或读取失败则返回 None

    """
    secret_ref = (service, key)
    if secret_ref in _PRELOADED_KEYRING_SECRETS:
        return _PRELOADED_KEYRING_SECRETS[secret_ref]
    return _read_keyring_secret(service, key)


def _read_keyring_secret(service: str, key: str) -> str | None:
    """Read one secret from the platform backend without caching it."""
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


def preload_runtime_secrets() -> None:
    """Resolve server secrets before Granian forks its worker processes."""
    for service, key in _RUNTIME_SECRET_REFS:
        if secret := _read_keyring_secret(service, key):
            _PRELOADED_KEYRING_SECRETS[(service, key)] = secret


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
    def config_loader(
        self,
        environment: Environment,
        runtime_paths: RuntimePaths,
    ) -> ConfigLoader:
        """提供配置文件加载器。"""
        return ConfigLoader(environment, config_root=runtime_paths.config_root)

    @provide
    def runtime_paths(self, environment: Environment) -> RuntimePaths:
        """提供部署层显式运行时路径。"""
        return load_runtime_paths(environment)

    @provide
    def init_coordinator(
        self,
        data_store_settings: _DataStoreSettings,
        feature_artifact_store_settings: FeatureArtifactStoreSettings,
        data_source_settings: DataSourceSettings,
        environment: Environment,
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
        coordinator.register(
            DataSourceValidationProvider(
                data_source_settings,
                environment=environment,
            )
        )
        coordinator.register(MetadataDbInitProvider())
        coordinator.register(R4RiskSchemaInitProvider())
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
    def data_store_settings(
        self,
        config_loader: ConfigLoader,
        runtime_paths: RuntimePaths,
    ) -> _DataStoreSettings:
        """加载数据存储配置。"""
        return load_data_store_settings(config_loader, runtime_paths)

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
        for secret_key in ("tushare_token", "fred_api_key"):
            if data_source_values.get(secret_key) is None:
                data_source_values.pop(secret_key, None)

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
        """加载 DQ 配置并在验证前注入部署层配置根目录。"""
        dq_values = load_env_file(config_loader, "dq")
        dq_values.update(
            environment=environment.value,
            config_root=config_loader.config_root,
        )
        return DQSettings.model_validate(dq_values)

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
    def research_execution_settings(
        self,
        environment: Environment,
    ) -> ResearchExecutionSettings:
        """
        R3 研究执行 bundle 配置.

        解析优先级（每个字段独立）::

            production: 完整且同提交的 Git SHA + pixi.lock SHA-256
            development/testing: 环境变量 > 确定性 fallback

        构建系统负责注入版本；运行时不读取 checkout 或工具链文件。
        """
        code_version = _resolve_research_code_version(environment)
        lock_hash = _resolve_research_environment_lock_hash(environment)
        if environment is Environment.PRODUCTION:
            return _production_research_execution_settings(
                code_version=code_version,
                environment_lock_hash=lock_hash,
            )

        values: dict[str, Any] = {}
        if code_version:
            values["code_version"] = code_version
        if lock_hash:
            values["environment_lock_hash"] = lock_hash
        return (
            ResearchExecutionSettings(**values)
            if values
            else ResearchExecutionSettings()
        )

    @provide
    def runtime_flags(self, environment: Environment) -> RuntimeFlags:
        """提供运行时标志。"""
        return _detect_runtime_flags(environment)

    @provide
    def data_cache(self) -> DataCache[Any]:
        """提供数据缓存实例（应用级单例）。"""
        return DataCache[Any](ttl_seconds=300, max_size=10000)


_FULL_GIT_SHA = re.compile(r"[0-9a-f]{40}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def _production_research_execution_settings(
    *,
    code_version: str | None,
    environment_lock_hash: str | None,
) -> ResearchExecutionSettings:
    """Require one exact release commit and dependency lock in production."""
    if code_version is None or _FULL_GIT_SHA.fullmatch(code_version) is None:
        raise RuntimeConfigurationError(
            "DITTO_RESEARCH_CODE_VERSION must be a full lowercase Git SHA in production"
        )
    if (
        environment_lock_hash is None
        or _SHA256.fullmatch(environment_lock_hash) is None
    ):
        raise RuntimeConfigurationError(
            "DITTO_RESEARCH_ENVIRONMENT_LOCK_HASH must be a production SHA-256"
        )
    product_git_sha = os.getenv("DITTO_GIT_SHA")
    if product_git_sha != code_version:
        raise RuntimeConfigurationError(
            "DITTO_GIT_SHA must equal DITTO_RESEARCH_CODE_VERSION in production"
        )
    return ResearchExecutionSettings(
        code_version=code_version,
        environment_lock_hash=environment_lock_hash,
    )


def _resolve_research_code_version(environment: Environment) -> str | None:
    """Resolve code version only from deployment metadata."""
    del environment
    return os.getenv("DITTO_RESEARCH_CODE_VERSION") or None


def _resolve_research_environment_lock_hash(environment: Environment) -> str | None:
    """Resolve lock hash only from deployment metadata."""
    del environment
    return os.getenv("DITTO_RESEARCH_ENVIRONMENT_LOCK_HASH") or None
