"""
Ditto 系统配置管理.

使用 Pydantic Settings 进行配置管理, 支持:
1. 环境变量自动加载
2. 类型验证和转换
3. 默认值设置
4. 配置分组管理
"""

from pathlib import Path
from typing import Any

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    """数据库配置."""

    model_config = SettingsConfigDict(
        env_prefix="DB_", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    duckdb_path: str = Field(
        default="./data/duckdb/ditto.duckdb", description="DuckDB数据库文件路径"
    )

    sqlite_path: str = Field(
        default="./data/sqlite/ditto.sqlite", description="SQLite数据库文件路径"
    )


class DataSourceSettings(BaseSettings):
    """数据源配置."""

    model_config = SettingsConfigDict(
        env_prefix="", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    tushare_token: str = Field(default="", description="Tushare Pro API Token")


class APISettings(BaseSettings):
    """FastAPI 服务配置."""

    model_config = SettingsConfigDict(
        env_prefix="", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    host: str = Field(default="0.0.0.0", description="服务器监听地址")
    port: int = Field(default=8000, ge=1, le=65535, description="服务器监听端口")


class SystemSettings(BaseSettings):
    """系统基础配置."""

    model_config = SettingsConfigDict(
        env_prefix="", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    ditto_env: str = Field(default="development", description="系统运行环境")

    log_level: str = Field(default="INFO", description="日志级别")

    timezone: str = Field(default="Asia/Shanghai", description="系统时区")

    debug: bool = Field(default=False, description="是否启用调试模式")


class FileStorageSettings(BaseSettings):
    """文件存储配置."""

    model_config = SettingsConfigDict(
        env_prefix="",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    data_root: str = Field(
        default="./data", description="数据存储根目录", alias="DITTO_DATA_ROOT"
    )

    log_root: str = Field(
        default="./logs", description="日志存储根目录", alias="DITTO_LOG_ROOT"
    )

    backup_root: str = Field(
        default="./backups", description="备份存储根目录", alias="DITTO_BACKUP_ROOT"
    )

    temp_root: str = Field(
        default="./temp", description="临时文件存储根目录", alias="DITTO_TEMP_ROOT"
    )


class ObservabilitySettings(BaseSettings):
    """可观测性配置."""

    model_config = SettingsConfigDict(
        env_prefix="OBSERVABILITY_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    enabled: bool = Field(default=True, description="是否启用可观测性")
    mode: str = Field(
        default="auto", description="运行模式 (auto/production/development/testing)"
    )
    log_level: str = Field(default="INFO", description="日志级别")
    vm_endpoint: str = Field(
        default="http://localhost:8428/opentelemetry/v1/metrics",
        description="VictoriaMetrics OTLP 端点",
    )
    metrics_interval_ms: int = Field(default=15000, description="指标导出间隔(毫秒)")


class Settings(BaseSettings):
    """
    Ditto系统主配置类.

    集成所有配置子模块, 提供统一的配置访问接口
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    data_source: DataSourceSettings = Field(default_factory=DataSourceSettings)
    api: APISettings = Field(default_factory=APISettings)
    system: SystemSettings = Field(default_factory=SystemSettings)
    file_storage: FileStorageSettings = Field(default_factory=FileStorageSettings)
    observability: ObservabilitySettings = Field(default_factory=ObservabilitySettings)

    def __init__(self, **kwargs: Any) -> None:
        """Initialize Settings and ensure directories exist."""
        super().__init__(**kwargs)
        self._ensure_directories()

    def _ensure_directories(self) -> None:
        """确保必要的目录存在."""
        directories = [
            self.file_storage.data_root,
            self.file_storage.log_root,
            Path(self.database.duckdb_path).parent,
            Path(self.database.sqlite_path).parent,
        ]

        for directory in directories:
            if isinstance(directory, str):
                Path(directory).mkdir(parents=True, exist_ok=True)
            elif hasattr(directory, "mkdir"):
                directory.mkdir(parents=True, exist_ok=True)

    @property
    def is_development(self) -> bool:
        """是否为开发环境."""
        return self.system.ditto_env == "development"

    @property
    def is_production(self) -> bool:
        """是否为生产环境."""
        return self.system.ditto_env == "production"

    @property
    def is_testing(self) -> bool:
        """是否为测试环境."""
        return self.system.ditto_env == "testing"


# 全局配置实例
_settings: Settings | None = None


def get_settings() -> Settings:
    """
    获取全局配置实例.

    使用单例模式, 避免重复加载配置

    Returns
    -------
        Settings: 配置实例

    """
    global _settings  # noqa: PLW0603
    if _settings is None:
        _settings = Settings()
    return _settings


def reload_settings() -> Settings:
    """
    重新加载配置.

    主要用于测试或配置热更新场景

    Returns
    -------
        Settings: 新的配置实例

    """
    global _settings  # noqa: PLW0603
    _settings = Settings()
    return _settings
