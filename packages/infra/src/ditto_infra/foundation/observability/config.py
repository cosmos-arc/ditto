"""可观测性配置模型."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypeGuard, TypeVar

from pydantic import BaseModel, ConfigDict

from ditto_infra.foundation.config.environment import Environment

T = TypeVar("T", str, bool, float)


def _is_not_none(value: T | None) -> TypeGuard[T]:  # noqa: UP047
    """类型守卫：检查值是否不是 None。"""
    return value is not None


@dataclass(frozen=True)
class _Preset:
    log_level: str
    log_format: str
    log_to_console: bool
    log_to_file: bool
    tracing_enabled: bool
    tracing_exporter: str
    tracing_sample_rate: float
    metrics_enabled: bool
    metrics_exporter: str
    vm_endpoint: str
    assertions_enabled: bool
    verbose_logging: bool


class ObservabilityConfig(BaseModel):
    """观测配置（纯模型，不读环境/文件）。"""

    model_config = ConfigDict(extra="ignore")

    # 基础配置
    service_name: str = "ditto"
    environment: Environment = Environment.DEVELOPMENT
    log_dir: str = "logs"
    metrics_export_interval_ms: int = 15000

    # 可选覆盖项（None 表示使用环境默认值）
    log_level: str | None = None
    log_format: Literal["console", "json"] | None = None
    log_to_console: bool | None = None
    log_to_file: bool | None = None

    tracing_enabled: bool | None = None
    tracing_exporter: Literal["otlp", "none"] | None = None
    tracing_sample_rate: float | None = None

    metrics_enabled: bool | None = None
    metrics_exporter: Literal["otlp", "none"] | None = None
    vm_endpoint: str | None = None

    # 运行时标志
    pytest_running: bool = False
    assertions_enabled: bool | None = None
    verbose_logging: bool | None = None

    def get_effective_config(self) -> EffectiveConfig:
        """合并默认值与覆盖项，生成最终配置。"""
        presets = {
            Environment.DEVELOPMENT: _Preset(
                log_level="DEBUG",
                log_format="console",
                log_to_console=True,
                log_to_file=True,
                tracing_enabled=True,
                tracing_exporter="otlp",
                tracing_sample_rate=1.0,
                metrics_enabled=True,
                metrics_exporter="otlp",
                vm_endpoint="http://localhost:8428/opentelemetry/v1/metrics",
                assertions_enabled=True,
                verbose_logging=True,
            ),
            Environment.TESTING: _Preset(
                log_level="WARNING",
                log_format="console",
                log_to_console=True,
                log_to_file=False,
                tracing_enabled=False,
                tracing_exporter="none",
                tracing_sample_rate=0.0,
                metrics_enabled=False,
                metrics_exporter="none",
                vm_endpoint="http://localhost:8428/opentelemetry/v1/metrics",
                assertions_enabled=True,
                verbose_logging=False,
            ),
            Environment.PRODUCTION: _Preset(
                log_level="INFO",
                log_format="json",
                log_to_console=True,
                log_to_file=True,
                tracing_enabled=True,
                tracing_exporter="otlp",
                tracing_sample_rate=0.1,
                metrics_enabled=True,
                metrics_exporter="otlp",
                vm_endpoint="http://localhost:8428/opentelemetry/v1/metrics",
                assertions_enabled=False,
                verbose_logging=False,
            ),
        }

        preset = presets[self.environment]

        def _resolve(value: T | None, preset_value: T) -> T:
            if _is_not_none(value):
                return value
            return preset_value

        return EffectiveConfig(
            log_level=_resolve(self.log_level, preset.log_level),
            log_format=_resolve(self.log_format, preset.log_format),
            log_to_console=_resolve(self.log_to_console, preset.log_to_console),
            log_to_file=_resolve(self.log_to_file, preset.log_to_file),
            tracing_enabled=_resolve(self.tracing_enabled, preset.tracing_enabled),
            tracing_exporter=_resolve(self.tracing_exporter, preset.tracing_exporter),
            tracing_sample_rate=_resolve(
                self.tracing_sample_rate, preset.tracing_sample_rate
            ),
            metrics_enabled=_resolve(self.metrics_enabled, preset.metrics_enabled),
            metrics_exporter=_resolve(self.metrics_exporter, preset.metrics_exporter),
            vm_endpoint=self.vm_endpoint or preset.vm_endpoint,
            assertions_enabled=_resolve(
                self.assertions_enabled, preset.assertions_enabled
            ),
            verbose_logging=_resolve(self.verbose_logging, preset.verbose_logging),
            pytest_running=self.pytest_running,
        )


@dataclass(frozen=True)
class EffectiveConfig:
    """生效后的观测配置。"""

    log_level: str
    log_format: str
    log_to_console: bool
    log_to_file: bool
    tracing_enabled: bool
    tracing_exporter: str
    tracing_sample_rate: float
    metrics_enabled: bool
    metrics_exporter: str
    vm_endpoint: str
    assertions_enabled: bool
    verbose_logging: bool
    pytest_running: bool


__all__ = ["EffectiveConfig", "ObservabilityConfig"]
