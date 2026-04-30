"""验证 ObservabilityProvider 安装 kernel tracing bridge。"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from dishka import Provider, Scope, make_container, provide
from ditto_apps.registry.infra.observability import ObservabilityProvider
from ditto_kernel.tracing import reset_trace_handler, traced
from ditto_platform.foundation import (
    ObservabilityConfig,
    get_recorded_spans,
    reset_for_testing,
)
from ditto_platform.foundation.config.environment import Environment


class _TestingObservabilityConfigProvider(Provider):
    """为 provider 生命周期测试提供可记录 span 的观测配置。"""

    scope = Scope.APP

    @provide(override=True)
    def observability_config(self) -> ObservabilityConfig:
        """覆盖真实配置读取，避免测试依赖 Settings 图。"""
        return ObservabilityConfig(
            environment=Environment.TESTING,
            pytest_running=True,
            assertions_enabled=True,
            verbose_logging=False,
            tracing_enabled=True,
            tracing_sample_rate=1.0,
            metrics_enabled=False,
        )


@pytest.fixture(autouse=True)
def _clean_observability() -> Generator[None, None, None]:
    """隔离 infra observability 与 kernel trace handler 的进程级状态。"""
    reset_trace_handler()
    reset_for_testing()
    yield
    reset_trace_handler()
    reset_for_testing()


def test_observability_provider_bridges_kernel_traces_to_infra_spans() -> None:
    """ObservabilityProvider 启动后，kernel @traced 应记录 infra span。"""
    container = make_container(
        ObservabilityProvider(),
        _TestingObservabilityConfigProvider(),
    )

    try:
        container.get(None)

        @traced("kernel.bridge.provider")
        def sample(value: int) -> int:
            return value + 1

        assert sample(41) == 42
        assert [span.name for span in get_recorded_spans()] == [
            "kernel.bridge.provider"
        ]
    finally:
        container.close()
