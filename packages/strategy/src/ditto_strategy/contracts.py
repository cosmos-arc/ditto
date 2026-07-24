"""Strategy domain contracts — Protocol definitions for strategy consumers."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ditto_strategy.alpha.context import StrategyContext
from ditto_strategy.alpha.models import TargetPortfolio
from ditto_strategy.alpha.pipeline import StrategyInputBundle
from ditto_strategy.models import StrategySpecRecord

__all__ = [
    "SignalProvider",
    "StrategyCatalogReader",
    "StrategyCatalogWriter",
    "StrategyRunStatusWriter",
]


@runtime_checkable
class SignalProvider(Protocol):
    """策略信号生成接口 — 输入上下文与数据包，输出目标组合."""

    def run(
        self,
        context: StrategyContext,
        input_bundle: StrategyInputBundle,
    ) -> TargetPortfolio:
        """执行策略评估，返回目标组合权重."""
        ...


@runtime_checkable
class StrategyCatalogReader(Protocol):
    """Stable strategy catalog query contract for application composition."""

    def get_spec(
        self, strategy_id: str, version: int | None = None
    ) -> StrategySpecRecord | None:
        """获取策略 Spec，version=None 返回最新版本."""
        ...

    def list_specs(self) -> list[StrategySpecRecord]:
        """列出所有策略 Spec（最新版本）."""
        ...

    def list_versions(self, strategy_id: str) -> list[StrategySpecRecord]:
        """列出策略的所有版本."""
        ...

    def get_active_published(self, strategy_id: str) -> StrategySpecRecord | None:
        """
        获取 governance active pointer 指向的 published payload.

        无 active pointer 时返回 None（调用方走 fail-closed）。
        这是生产读取的唯一入口（R1/EOD/backtest）。
        """
        ...


@runtime_checkable
class StrategyCatalogWriter(Protocol):
    """Stable strategy catalog write contract for application composition."""

    def save(self, record: StrategySpecRecord) -> None:
        """保存策略 Spec 记录（append-only immutable payload）."""
        ...


@runtime_checkable
class StrategyRunStatusWriter(Protocol):
    """Stable strategy run status writer contract for orchestration fallbacks."""

    def update_status(
        self,
        run_id: str,
        status: str,
        error_message: str = "",
    ) -> bool:
        """更新运行状态，成功返回 True."""
        ...
