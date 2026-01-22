"""
Ditto 系统配置管理.

使用 Pydantic Settings 进行配置管理, 支持:
1. 环境变量自动加载
2. 类型验证和转换
3. 默认值设置
4. 配置分组管理
"""

import os
from pathlib import Path
from typing import Any

from dotenv import dotenv_values
from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

from ditto_foundation.config.environment import Environment
from ditto_foundation.config.loader import ConfigLoader
from ditto_foundation.config.paths import get_paths


class DatabaseSettings(BaseSettings):
    """数据库配置（遵循 XDG Base Directory 规范）."""

    model_config = SettingsConfigDict(
        env_prefix="DB_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @computed_field
    @property
    def duckdb_path(self) -> Path:
        """DuckDB 数据库文件路径."""
        return get_paths().data_subdir("db/duckdb/ditto.duckdb")

    @computed_field
    @property
    def sqlite_path(self) -> Path:
        """SQLite 数据库文件路径."""
        return get_paths().data_subdir("db/sqlite/hub.sqlite")


class DataSourceSettings(BaseSettings):
    """数据源配置."""

    model_config = SettingsConfigDict(
        env_prefix="", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    tushare_token: str = Field(default="", description="Tushare Pro API Token")


class SystemSettings(BaseSettings):
    """系统基础配置."""

    model_config = SettingsConfigDict(
        env_prefix="", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    ditto_env: Environment = Field(
        default=Environment.DEVELOPMENT, description="系统运行环境"
    )
    timezone: str = Field(default="Asia/Shanghai", description="系统时区")
    debug: bool = Field(default=False, description="调试模式")


class FileStorageSettings(BaseSettings):
    """文件存储配置（遵循 XDG Base Directory 规范）."""

    model_config = SettingsConfigDict(
        env_prefix="",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    @computed_field
    @property
    def data_root(self) -> Path:
        """数据存储根目录."""
        return get_paths().data_home

    @computed_field
    @property
    def log_root(self) -> Path:
        """日志存储根目录."""
        return get_paths().state_subdir("logs")

    @computed_field
    @property
    def backup_root(self) -> Path:
        """备份存储根目录."""
        return get_paths().state_subdir("backups")

    @computed_field
    @property
    def temp_root(self) -> Path:
        """临时文件存储根目录."""
        return get_paths().cache_subdir("temp")


class ObservabilitySettings(BaseSettings):
    """可观测性配置."""

    model_config = SettingsConfigDict(
        env_prefix="DITTO_OTEL_",
        env_file=".env",  # 会在 Settings.__init__ 中动态设置
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # 日志配置
    log_level: str = Field(default="INFO", description="日志级别")
    log_format: str = Field(default="console", description="日志格式 (console/json)")
    log_to_console: bool = Field(default=True, description="是否输出到控制台")
    log_to_file: bool = Field(default=True, description="是否输出到文件")

    # 追踪配置
    tracing_enabled: bool = Field(default=True, description="是否启用追踪")
    tracing_exporter: str = Field(default="otlp", description="追踪导出器 (otlp/none)")
    tracing_sample_rate: float = Field(default=1.0, description="追踪采样率")

    # 指标配置
    metrics_enabled: bool = Field(default=True, description="是否启用指标")
    metrics_exporter: str = Field(default="victoriametrics", description="指标导出器")
    vm_endpoint: str = Field(
        default="http://localhost:8428/opentelemetry/v1/metrics",
        description="VictoriaMetrics OTLP 端点",
    )


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
    system: SystemSettings = Field(default_factory=SystemSettings)
    file_storage: FileStorageSettings = Field(default_factory=FileStorageSettings)
    observability: ObservabilitySettings = Field(default_factory=ObservabilitySettings)

    def __init__(self, **kwargs: Any) -> None:
        """Initialize Settings and ensure directories exist."""
        # 获取环境配置
        env_str = os.getenv("DITTO_ENV", "development")
        environment = Environment.from_str(env_str)
        loader = ConfigLoader(environment)

        # 为每个配置子类设置正确的 env_file 路径
        # 直接在 kwargs 中提供已初始化的配置实例
        self._init_config_subsystems(loader, kwargs)

        super().__init__(**kwargs)
        self._ensure_directories()

    def _init_config_subsystems(
        self, loader: ConfigLoader, kwargs: dict[str, Any]
    ) -> None:
        """
        初始化配置子系统，提供正确的 env_file 路径.

        使用 model_validate 方法来加载指定 env_file 的配置.

        Args:
            loader: 配置加载器
            kwargs: 用户传入的配置参数（就地修改）

        """
        # 只在用户未提供时创建默认配置
        if "database" not in kwargs:
            db_values = dotenv_values(loader.get_env_file("database"))
            kwargs["database"] = DatabaseSettings.model_validate(db_values)

        if "data_source" not in kwargs:
            ds_values = dotenv_values(loader.get_env_file("data_source"))
            kwargs["data_source"] = DataSourceSettings.model_validate(ds_values)

        if "system" not in kwargs:
            sys_values = dotenv_values(loader.get_env_file("system"))
            kwargs["system"] = SystemSettings.model_validate(sys_values)

        if "file_storage" not in kwargs:
            # file_storage 和 system 共用同一个 env_file
            sys_values = dotenv_values(loader.get_env_file("system"))
            kwargs["file_storage"] = FileStorageSettings.model_validate(sys_values)

        if "observability" not in kwargs:
            obs_values = dotenv_values(loader.get_env_file("observability"))
            kwargs["observability"] = ObservabilitySettings.model_validate(obs_values)

    def _ensure_directories(self) -> None:
        """确保必要的目录存在."""
        # XDGPaths 已经在 get_paths() 中创建了目录
        # 这里只需确保数据库目录存在
        directories = [
            self.database.duckdb_path.parent,
            self.database.sqlite_path.parent,
        ]

        for directory in directories:
            if isinstance(directory, str):
                Path(directory).mkdir(parents=True, exist_ok=True)
            elif hasattr(directory, "mkdir"):
                directory.mkdir(parents=True, exist_ok=True)

    @property
    def is_development(self) -> bool:
        """是否为开发环境."""
        return self.system.ditto_env.is_development

    @property
    def is_production(self) -> bool:
        """是否为生产环境."""
        return self.system.ditto_env.is_production

    @property
    def is_testing(self) -> bool:
        """是否为测试环境."""
        return self.system.ditto_env.is_testing


__all__ = [
    "DataSourceSettings",
    "DatabaseSettings",
    "FileStorageSettings",
    "ObservabilitySettings",
    "Settings",
    "SystemSettings",
]
