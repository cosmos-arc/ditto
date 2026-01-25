"""
Ditto 系统配置管理.

使用 Pydantic Settings 进行配置管理, 支持:
1. 环境变量自动加载
2. 类型验证和转换
3. 默认值设置
4. 配置分组管理
"""

import os
from typing import Any

from dotenv import dotenv_values
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from ditto_foundation.config.environment import Environment
from ditto_foundation.config.loader import ConfigLoader


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

    ⚠️ 注意：database、data_source、file_storage 配置已迁移到 DataHub 层
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    system: SystemSettings = Field(default_factory=SystemSettings)
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
        if "system" not in kwargs:
            sys_values = dotenv_values(loader.get_env_file("system"))
            kwargs["system"] = SystemSettings.model_validate(sys_values)

        if "observability" not in kwargs:
            obs_values = dotenv_values(loader.get_env_file("observability"))
            kwargs["observability"] = ObservabilitySettings.model_validate(obs_values)

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
    "ObservabilitySettings",
    "Settings",
    "SystemSettings",
]
