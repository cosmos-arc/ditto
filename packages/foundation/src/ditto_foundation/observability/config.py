"""
可观测性配置模块.

定义配置类，支持预设配置和独立开关覆盖.
"""

import os
from dataclasses import dataclass
from typing import Literal

from ditto_foundation.config.environment import Environment


@dataclass(frozen=True)
class _Preset:
    """
    预设配置（内部使用）.

    定义不同环境下的默认配置值，遵循 OTEL 风格的独立开关模式.
    """

    log_level: str
    tracing_enabled: bool
    tracing_sample_rate: float
    metrics_enabled: bool
    vm_endpoint: str = "http://localhost:8428/opentelemetry/v1/metrics"
    assertions_enabled: bool = True
    verbose_logging: bool = True


@dataclass
class ObservabilityConfig:
    """
    可观测性配置类（预设 + 独立开关覆盖）.

    设计原则：
    - 使用预设配置（profile）提供合理的默认值
    - 使用独立开关（optional fields）支持细粒度覆盖
    - None 值表示使用预设值，非 None 值表示用户显式设置
    - environment 字段保持向后兼容，与 profile 同步

    示例:
        >>> # 使用预设
        >>> config = ObservabilityConfig(profile="development")
        >>> effective = config.get_effective_config()
        >>> effective.log_level  # "DEBUG"（预设值）
        >>>
        >>> # 覆盖预设
        >>> config = ObservabilityConfig(profile="development", log_level="WARNING")
        >>> effective = config.get_effective_config()
        >>> effective.log_level  # "WARNING"（覆盖值）
    """

    # === 基础配置 ===
    service_name: str = "ditto"
    environment: Environment = Environment.DEVELOPMENT
    log_dir: str = "logs"
    metrics_export_interval_ms: int = 15000

    # === 预设配置 ===
    profile: Literal["development", "testing", "production"] = "development"

    # === 独立开关（None 表示使用预设值） ===
    log_level: str | None = None
    tracing_enabled: bool | None = None
    tracing_sample_rate: float | None = None
    metrics_enabled: bool | None = None
    vm_endpoint: str | None = None

    # === 运行时标志 ===
    pytest_running: bool = False
    assertions_enabled: bool | None = None
    verbose_logging: bool | None = None

    def get_effective_config(self) -> "EffectiveConfig":
        """
        获取生效配置（预设 + 覆盖）.

        Returns:
            EffectiveConfig: 合并预设和覆盖后的最终配置

        """
        presets = {
            "development": _Preset(
                log_level="DEBUG",
                tracing_enabled=True,
                tracing_sample_rate=1.0,
                metrics_enabled=True,
                assertions_enabled=True,
                verbose_logging=True,
            ),
            "testing": _Preset(
                log_level="WARNING",
                tracing_enabled=False,
                tracing_sample_rate=0.0,
                metrics_enabled=False,
                assertions_enabled=False,
                verbose_logging=False,
            ),
            "production": _Preset(
                log_level="INFO",
                tracing_enabled=True,
                tracing_sample_rate=0.1,
                metrics_enabled=True,
                assertions_enabled=False,
                verbose_logging=False,
            ),
        }

        preset = presets[self.profile]

        # 辅助函数：合并可选值和预设值
        def _resolve(
            value: str | bool | float | None,
            preset_value: str | bool | float,
        ) -> str | bool | float:
            """解析配置值：None 时使用预设值，否则使用显式设置的值."""
            return value if value is not None else preset_value

        return EffectiveConfig(
            log_level=self.log_level or preset.log_level,
            tracing_enabled=_resolve(  # type: ignore[arg-type]
                self.tracing_enabled,
                preset.tracing_enabled,
            ),
            tracing_sample_rate=_resolve(  # type: ignore[arg-type]
                self.tracing_sample_rate,
                preset.tracing_sample_rate,
            ),
            metrics_enabled=_resolve(  # type: ignore[arg-type]
                self.metrics_enabled,
                preset.metrics_enabled,
            ),
            vm_endpoint=self.vm_endpoint or preset.vm_endpoint,
            assertions_enabled=_resolve(  # type: ignore[arg-type]
                self.assertions_enabled,
                preset.assertions_enabled,
            ),
            verbose_logging=_resolve(  # type: ignore[arg-type]
                self.verbose_logging,
                preset.verbose_logging,
            ),
            pytest_running=self.pytest_running,
        )

    @classmethod
    def detect_runtime_flags(cls, environment: Environment) -> dict[str, bool]:
        """
        自动检测运行时行为标志.

        Args:
            environment: 运行环境

        Returns:
            包含 pytest_running, assertions_enabled, verbose_logging 的字典

        """
        # 检查是否在 pytest 中运行
        pytest_running = "PYTEST_CURRENT_TEST" in os.environ

        # 根据环境确定默认值
        if environment == Environment.TESTING:
            return {
                "pytest_running": pytest_running,
                "assertions_enabled": True,
                "verbose_logging": False,  # 静默模式
            }
        elif environment == Environment.PRODUCTION:
            return {
                "pytest_running": pytest_running,
                "assertions_enabled": False,
                "verbose_logging": False,  # 生产环境不需要详细日志
            }
        else:  # DEVELOPMENT
            return {
                "pytest_running": pytest_running,
                "assertions_enabled": True,
                "verbose_logging": True,  # 开发环境详细日志
            }


@dataclass
class EffectiveConfig:
    """
    生效配置（预设合并后的结果）.

    这是 get_effective_config() 的返回类型，包含最终的配置值.
    """

    log_level: str
    tracing_enabled: bool
    tracing_sample_rate: float
    metrics_enabled: bool
    vm_endpoint: str
    assertions_enabled: bool
    verbose_logging: bool
    pytest_running: bool
