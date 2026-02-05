"""
Ditto configuration models.

说明: 配置模型为纯 BaseModel，不读取环境或文件。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ditto_foundation.config.environment import Environment


class SystemSettings(BaseModel):
    """系统基础配置。"""

    model_config = ConfigDict(extra="ignore")

    environment: Environment = Field(
        default=Environment.DEVELOPMENT,
        description="系统运行环境",
    )
    timezone: str = Field(default="Asia/Shanghai", description="系统时区")
    debug: bool = Field(default=False, description="调试模式")


class ObservabilitySettings(BaseModel):
    """观测配置（来自配置文件，不读环境）。"""

    model_config = ConfigDict(extra="ignore")

    # 日志配置
    log_level: str = Field(default="INFO", description="日志级别")
    log_format: Literal["console", "json"] = Field(
        default="console",
        description="日志格式 (console/json)",
    )
    log_to_console: bool = Field(default=True, description="是否输出到控制台")
    log_to_file: bool = Field(default=True, description="是否输出到文件")

    # Tracing 配置
    tracing_enabled: bool = Field(default=True, description="是否启用 tracing")
    tracing_exporter: Literal["otlp", "none"] = Field(
        default="otlp",
        description="tracing exporter (otlp/none)",
    )
    tracing_sample_rate: float = Field(default=1.0, description="tracing 采样率")

    # Metrics 配置
    metrics_enabled: bool = Field(default=True, description="是否启用 metrics")
    metrics_exporter: Literal["otlp", "none"] = Field(
        default="otlp",
        description="metrics exporter (otlp/none)",
    )
    vm_endpoint: str = Field(
        default="http://localhost:8428/opentelemetry/v1/metrics",
        description="OTLP 端点",
    )


class Settings(BaseModel):
    """应用配置聚合。"""

    model_config = ConfigDict(extra="ignore")

    system: SystemSettings
    observability: ObservabilitySettings

    @property
    def is_development(self) -> bool:
        """是否为开发环境。"""
        return self.system.environment.is_development

    @property
    def is_production(self) -> bool:
        """是否为生产环境。"""
        return self.system.environment.is_production

    @property
    def is_testing(self) -> bool:
        """是否为测试环境。"""
        return self.system.environment.is_testing


__all__ = [
    "ObservabilitySettings",
    "Settings",
    "SystemSettings",
]
