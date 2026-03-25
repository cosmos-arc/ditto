"""Port 层策略运行 facade。"""

from __future__ import annotations

from ditto_core.backtest.data_feed import Slice
from ditto_core.backtest.statistics import BacktestReport

from ditto_port.services.strategy.backtest_service import (
    BacktestServiceConfig,
    BacktestServiceOptions,
)
from ditto_port.services.strategy.factory import StrategyServiceFactory
from ditto_port.services.strategy.slice_builder import StrategySliceBuilder
from ditto_port.services.strategy.strategy_run_service import (
    StrategyRunResult,
    StrategyRunServiceConfig,
)

__all__ = ["StrategyFacade"]


class StrategyFacade:
    """对外暴露 catalog-backed 策略执行入口。"""

    def __init__(
        self,
        *,
        factory: StrategyServiceFactory,
        slice_builder: StrategySliceBuilder | None = None,
    ) -> None:
        self._factory = factory
        self._slice_builder = slice_builder

    def run_strategy_from_catalog(
        self,
        *,
        config: StrategyRunServiceConfig,
        trade_date: str,
        slice_: Slice,
        version: int | None = None,
    ) -> StrategyRunResult:
        """从 published catalog 构造并执行 research/recommendation。"""
        service = self._factory.build_strategy_run_service_from_catalog(
            config=config,
            version=version,
        )
        return service.run(trade_date, slice_)

    def run_strategy_for_date_from_catalog(
        self,
        *,
        config: StrategyRunServiceConfig,
        trade_date: str,
        version: int | None = None,
        source: str = "tushare",
    ) -> StrategyRunResult:
        """从 published catalog 自动组装单日 Slice 并执行 research/recommendation。"""
        if self._slice_builder is None:
            msg = "StrategySliceBuilder 未配置, 无法自动组装单日 Slice"
            raise ValueError(msg)
        slice_ = self._slice_builder.build_published_slice(
            config.strategy_id,
            trade_date=trade_date,
            version=version,
            source=source,
        )
        return self.run_strategy_from_catalog(
            config=config,
            trade_date=trade_date,
            slice_=slice_,
            version=version,
        )

    def run_backtest_from_catalog(
        self,
        *,
        config: BacktestServiceConfig,
        version: int | None = None,
        options: BacktestServiceOptions | None = None,
        source: str = "tushare",
    ) -> BacktestReport:
        """从 published catalog 构造并执行完整回测。"""
        service = self._factory.build_backtest_service_from_catalog(
            config=config,
            version=version,
            options=options,
            source=source,
        )
        return service.run()
