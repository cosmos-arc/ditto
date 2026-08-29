"""DI 容器工厂."""

from __future__ import annotations

from dishka import (
    AsyncContainer,
    Container,
    Provider,
    make_async_container,
    make_container,
)
from ditto_analysis.di import get_analysis_providers
from ditto_application.providers import get_app_providers
from ditto_data.di import get_data_providers
from ditto_execution.di import get_execution_providers
from ditto_features.di import get_features_providers
from ditto_strategy.di import get_strategy_providers

from .agent.provider import AgentRuntimeProvider
from .infra import R2LiveGateEvidenceProvider, get_infra_providers
from .infra.risk_persistence import RiskPersistenceProvider

__all__ = ["make_app_container", "make_async_app_container"]


def _get_base_providers() -> tuple[Provider, ...]:
    """获取所有 Provider（按层级组装）."""
    return (
        *get_infra_providers(),  # Infrastructure 层
        *get_data_providers(),  # Data 层（含原 Core + Data DQ）
        *get_strategy_providers(),  # Strategy 存储层
        *get_features_providers(),  # Features 存储层
        *get_analysis_providers(),  # Analysis 存储层
        *get_execution_providers(),  # Execution 存储层
        *get_app_providers(),  # App 层
        AgentRuntimeProvider(),  # R5 Agent 默认关闭并结构化 fail closed
        RiskPersistenceProvider(),  # 显式覆盖 V3 fail-closed reader
        R2LiveGateEvidenceProvider(),  # 显式实盘证据覆盖 fail-closed 默认值
    )


def make_app_container() -> Container:
    """创建同步容器."""
    return make_container(*_get_base_providers())


def make_async_app_container() -> AsyncContainer:
    """创建异步容器."""
    return make_async_container(*_get_base_providers())
