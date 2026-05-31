"""观测系统 Provider。"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterator
from typing import Any

from dishka import Provider, Scope, provide
from ditto_data.config.data_store import DataStoreSettings
from ditto_data.observability.metrics import METRIC_DEFINITIONS as DATA_METRICS
from ditto_features.observability.metrics import METRIC_DEFINITIONS as FEATURE_METRICS
from ditto_kernel.tracing import install_trace_handler, reset_trace_handler
from ditto_platform.foundation import (
    ObservabilityConfig,
    Settings,
    init,
    register_metric_definitions,
    shutdown,
)
from ditto_platform.foundation import (
    traced as infra_traced,
)
from ditto_portfolio.observability import (
    METRIC_DEFINITIONS as PORTFOLIO_METRICS,
)
from ditto_risk.observability.metrics import METRIC_DEFINITIONS as RISK_METRICS
from ditto_strategy.observability.metrics import METRIC_DEFINITIONS as STRATEGY_METRICS

from ditto_apps.registry.infra.config import RuntimeFlags

__all__ = ["ObservabilityProvider", "register_app_metric_definitions"]

_LATE_HISTOGRAM_REGISTRATION_ERROR = (
    "Histogram metric definitions must be registered before configure_metrics()"
)


class ObservabilityProvider(Provider):
    """观测系统 Provider。"""

    scope = Scope.APP

    @provide
    def observability_config(
        self,
        settings: Settings,
        data_store_settings: DataStoreSettings,
        runtime_flags: RuntimeFlags,
    ) -> ObservabilityConfig:
        """构建观测配置对象。"""
        obs = settings.observability
        env = settings.system.environment

        return ObservabilityConfig(
            service_name="ditto-server",
            environment=env,
            log_dir=str(data_store_settings.paths.utility.logs),
            log_level=obs.log_level,
            log_format=obs.log_format,
            log_to_console=obs.log_to_console,
            log_to_file=obs.log_to_file,
            tracing_enabled=obs.tracing_enabled,
            tracing_exporter=obs.tracing_exporter,
            tracing_sample_rate=obs.tracing_sample_rate,
            metrics_enabled=obs.metrics_enabled,
            metrics_exporter=obs.metrics_exporter,
            vm_endpoint=obs.vm_endpoint,
            # 使用注入的 runtime_flags，替代重复计算
            pytest_running=runtime_flags.pytest_running,
            assertions_enabled=runtime_flags.assertions_enabled,
            verbose_logging=runtime_flags.verbose_logging,
        )

    @provide
    def observability(self, config: ObservabilityConfig) -> Iterator[None]:
        """初始化并在生命周期结束时关闭观测系统。"""
        register_app_metric_definitions()
        init(config)
        install_trace_handler(_make_kernel_bridge())
        yield
        reset_trace_handler()
        shutdown()


def register_app_metric_definitions() -> None:
    """注册应用组合根持有的能力包指标目录。"""
    try:
        _register_app_metric_definitions()
    except RuntimeError as exc:
        if (
            _LATE_HISTOGRAM_REGISTRATION_ERROR not in str(exc)
            or "PYTEST_CURRENT_TEST" not in os.environ
        ):
            raise

        from ditto_platform.foundation.observability.testing import (  # noqa: PLC0415
            reset_for_testing,
        )

        reset_for_testing()
        _register_app_metric_definitions()


def _register_app_metric_definitions() -> None:
    """执行组合根能力包指标目录注册。"""
    for definitions in (
        DATA_METRICS,
        FEATURE_METRICS,
        STRATEGY_METRICS,
        PORTFOLIO_METRICS,
        RISK_METRICS,
    ):
        register_metric_definitions(definitions)


def _make_kernel_bridge() -> Callable[[str, Callable[..., Any], Any], Any]:
    """创建 kernel tracing → infra OTel 的桥接 handler."""

    def handle(
        operation: str,
        fn: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        decorated = infra_traced(operation)(fn)
        return decorated(*args, **kwargs)

    return handle
