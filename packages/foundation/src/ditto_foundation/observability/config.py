"""
可观测性配置模块.

定义运行模式枚举和配置类，支持自动检测运行环境.
"""

import os
from dataclasses import dataclass
from enum import Enum


class Mode(Enum):
    """可观测性运行模式."""

    PRODUCTION = "production"
    DEVELOPMENT = "development"
    TESTING = "testing"
    TESTING_WITH_ASSERTIONS = "testing_assertions"

    def is_testing(self) -> bool:
        """是否为测试模式."""
        return self in (Mode.TESTING, Mode.TESTING_WITH_ASSERTIONS)

    def is_silent(self) -> bool:
        """是否为静默模式（不输出日志）."""
        return self == Mode.TESTING


@dataclass
class ObservabilityConfig:
    """可观测性配置类."""

    service_name: str = "ditto"
    environment: str = "dev"
    log_level: str = "INFO"
    log_dir: str = "logs"
    vm_endpoint: str = "http://localhost:8428/opentelemetry/v1/metrics"
    tracing_enabled: bool = True
    metrics_enabled: bool = True
    metrics_export_interval_ms: int = 15000

    def detect_mode(self) -> Mode:
        """
        自动检测运行模式.

        Returns
        -------
            Mode: 检测到的运行模式

        """
        # 优先检查显式设置的模式环境变量
        explicit_mode = os.environ.get("DITTO_OBSERVABILITY_MODE")
        if explicit_mode:
            mode_map = {
                "production": Mode.PRODUCTION,
                "development": Mode.DEVELOPMENT,
                "testing": Mode.TESTING,
                "testing_assertions": Mode.TESTING_WITH_ASSERTIONS,
            }
            if explicit_mode in mode_map:
                return mode_map[explicit_mode]

        # pytest 测试环境
        if "PYTEST_CURRENT_TEST" in os.environ:
            return Mode.TESTING

        # 根据环境变量判断
        if self.environment == "production":
            return Mode.PRODUCTION
        return Mode.DEVELOPMENT
