"""观测系统 Provider。"""

from __future__ import annotations

from collections.abc import Iterator

from dishka import Provider, Scope, provide
from ditto_datahub.config import DataRootConfig
from ditto_infra.foundation.config.settings import Settings
from ditto_infra.foundation.observability import init, shutdown
from ditto_infra.foundation.observability.config import ObservabilityConfig

from ditto_port.registry.infra.config import RuntimeFlags

__all__ = ["ObservabilityProvider"]


class ObservabilityProvider(Provider):
    """观测系统 Provider。"""

    scope = Scope.APP

    @provide
    def observability_config(
        self,
        settings: Settings,
        data_root_config: DataRootConfig,
        runtime_flags: RuntimeFlags,
    ) -> ObservabilityConfig:
        """构建观测配置对象。"""
        obs = settings.observability
        env = settings.system.environment

        return ObservabilityConfig(
            service_name="ditto-server",
            environment=env,
            log_dir=str(data_root_config.logs_path),
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
        init(config)
        yield
        shutdown()
