"""BacktestRuntimeBuilder 单元测试。"""

from __future__ import annotations

from dataclasses import asdict
from unittest.mock import MagicMock

import pytest
from ditto_application.builders import (
    BacktestRuntimeBuilder,
    PublishedStrategyRuntime,
)
from ditto_application.exceptions import AppBuilderError
from ditto_application.processes.execution.backtest_process import BacktestServiceConfig
from ditto_backtest.brokerage import BacktestBrokerage
from ditto_backtest.data_feed import ProviderBackedDataFeed
from ditto_backtest.result import (
    BacktestAccountStateSnapshot,
    BacktestFrozenQuantitySnapshot,
    BacktestPendingOrderSnapshot,
    BacktestPositionSnapshot,
    BacktestRuntimeStateSnapshot,
    BacktestSettlementStateSnapshot,
)
from ditto_backtest.simulation.fill import AShareFillModel
from ditto_data.catalog.promotion import DatasetMaturityPromotion
from ditto_data.provider import DataProvider
from ditto_data.services.metadata_service import MetadataService
from ditto_execution.planner import SimpleExecutionPlanner
from ditto_execution.reality import AShareFeeModel
from ditto_kernel.identity import InstrumentId
from ditto_risk.pre_trade import CompositePreTradeCheck
from ditto_strategy.alpha.pipeline import StrategyPipeline
from ditto_strategy.alpha.specs import StrategySpec
from ditto_strategy.models import StrategySpecRecord


def _make_strategy_spec(
    *,
    strategy_id: str = "momentum-etf",
    name: str = "Momentum ETF",
    template: str = "etf_rotation",
    universe: str = "cn_etf",
    asset_class: str = "etf",
) -> StrategySpec:
    """构造测试用 StrategySpec。"""
    return StrategySpec(
        strategy_id=strategy_id,
        name=name,
        template=template,
        universe=universe,
        asset_class=asset_class,
        benchmark="000300.SH",
        params={"top_k": 3},
        tags=("momentum", asset_class),
    )


class _MaturityPromotionReader:
    def __init__(self, promoted_dataset_ids: set[str]) -> None:
        self._promoted_dataset_ids = promoted_dataset_ids

    def get_dataset_maturity_promotion(
        self,
        dataset_id: str,
    ) -> DatasetMaturityPromotion | None:
        if dataset_id not in self._promoted_dataset_ids:
            return None
        return DatasetMaturityPromotion(
            dataset_id=dataset_id,
            previous_maturity="experimental",
            promoted_maturity="initial-focus",
            promoted_by="architecture-review",
        )


class TestBacktestRuntimeBuilder:
    """published backtest runtime 装配测试。"""

    def test_build_published_runtime_creates_minimal_backtest_components(self) -> None:
        """builder 应从 published runtime 构造可跑的 backtest 依赖。"""
        spec = _make_strategy_spec()
        strategy_runtime_builder = MagicMock()
        strategy_runtime_builder.build_published_runtime.return_value = (
            PublishedStrategyRuntime(
                record=StrategySpecRecord(
                    strategy_id=spec.strategy_id,
                    name=spec.name,
                    spec_json=asdict(spec),
                    version=2,
                    status="published",
                    tags=spec.tags,
                ),
                spec=spec,
                pipeline=MagicMock(spec=StrategyPipeline),
            )
        )
        metadata_service = MagicMock(spec=MetadataService)
        metadata_service.resolve_instrument_id.return_value = 3_000_001
        metadata_service.get_universe.return_value = [2_000_001, 2_000_002]
        metadata_service.instrument.get_instrument.return_value = {
            "ticker": "510300",
            "exchange": "XSHG",
        }
        data_provider = MagicMock(spec=DataProvider)
        builder = BacktestRuntimeBuilder(
            strategy_runtime_builder=strategy_runtime_builder,
            metadata_service=metadata_service,
            data_provider=data_provider,
        )

        runtime = builder.build_published_runtime(
            config=BacktestServiceConfig(
                strategy_id="momentum-etf",
                start_date="2026-01-10",
                end_date="2026-01-13",
                initial_cash=2_000_000.0,
            ),
            version=2,
        )

        assert runtime.config.strategy_version == "2"
        assert runtime.config.benchmark_id == 3_000_001
        # data_feed 是 ProviderBackedDataFeed 实例
        assert isinstance(runtime.data_feed, ProviderBackedDataFeed)
        assert hasattr(runtime.data_feed, "trading_days")
        assert hasattr(runtime.data_feed, "get_slice")
        # display_map 是 dict[InstrumentId, str]
        assert isinstance(runtime.display_map, dict)
        assert isinstance(runtime.planner, SimpleExecutionPlanner)
        assert isinstance(runtime.brokerage, BacktestBrokerage)
        assert isinstance(runtime.pre_trade_check, CompositePreTradeCheck)
        assert isinstance(runtime.fee_model, AShareFeeModel)
        assert runtime.brokerage.get_account().cash.available == 2_000_000.0
        fill_model = runtime.brokerage._model.fill_model
        assert isinstance(fill_model, AShareFillModel)
        assert fill_model.participation_rate == pytest.approx(0.05)
        strategy_runtime_builder.build_published_runtime.assert_called_once_with(
            "momentum-etf",
            2,
        )

    def test_all_or_nothing_fill_mode_disables_participation_cap(self) -> None:
        """fill_mode=all_or_nothing 应保留旧的不限流成交行为。"""
        spec = _make_strategy_spec()
        strategy_runtime_builder = MagicMock()
        strategy_runtime_builder.build_published_runtime.return_value = (
            PublishedStrategyRuntime(
                record=StrategySpecRecord(
                    strategy_id=spec.strategy_id,
                    name=spec.name,
                    spec_json=asdict(spec),
                    version=2,
                    status="published",
                    tags=spec.tags,
                ),
                spec=spec,
                pipeline=MagicMock(spec=StrategyPipeline),
            )
        )
        metadata_service = MagicMock(spec=MetadataService)
        metadata_service.resolve_instrument_id.return_value = 3_000_001
        metadata_service.get_universe.return_value = [2_000_001, 2_000_002]
        metadata_service.instrument.get_instrument.return_value = {
            "ticker": "510300",
            "exchange": "XSHG",
        }
        data_provider = MagicMock(spec=DataProvider)
        builder = BacktestRuntimeBuilder(
            strategy_runtime_builder=strategy_runtime_builder,
            metadata_service=metadata_service,
            data_provider=data_provider,
        )

        runtime = builder.build_published_runtime(
            config=BacktestServiceConfig(
                strategy_id="momentum-etf",
                start_date="2026-01-10",
                end_date="2026-01-13",
                initial_cash=2_000_000.0,
                participation_rate=0.25,
                fill_mode="all_or_nothing",
            ),
            version=2,
        )

        fill_model = runtime.brokerage._model.fill_model
        assert isinstance(fill_model, AShareFillModel)
        assert fill_model.participation_rate == pytest.approx(0.0)

    def test_build_published_runtime_restores_checkpoint_state(self) -> None:
        """resume config 应恢复账户、结算冻结队列和 pending OMS orders。"""
        spec = _make_strategy_spec()
        strategy_runtime_builder = MagicMock()
        strategy_runtime_builder.build_published_runtime.return_value = (
            PublishedStrategyRuntime(
                record=StrategySpecRecord(
                    strategy_id=spec.strategy_id,
                    name=spec.name,
                    spec_json=asdict(spec),
                    version=2,
                    status="published",
                    tags=spec.tags,
                ),
                spec=spec,
                pipeline=MagicMock(spec=StrategyPipeline),
            )
        )
        metadata_service = MagicMock(spec=MetadataService)
        metadata_service.resolve_instrument_id.return_value = 3_000_001
        metadata_service.get_universe.return_value = [2_000_001]
        metadata_service.instrument.get_instrument.return_value = {
            "ticker": "510300",
            "exchange": "XSHG",
        }
        data_provider = MagicMock(spec=DataProvider)
        account_state = BacktestAccountStateSnapshot(
            cash_available=910_000.0,
            cash_settled=900_000.0,
            cash_frozen=10_000.0,
            total_value=1_110_000.0,
            nav=1_110_000.0,
            exposure=200_000.0,
            positions=(
                BacktestPositionSnapshot(
                    instrument_id=InstrumentId(2_000_001),
                    quantity=1000,
                    available_quantity=200,
                    average_cost=200.0,
                    market_value=200_000.0,
                    unrealized_pnl=0.0,
                    realized_pnl=1_500.0,
                    total_fees=23.5,
                ),
            ),
        )
        settlement_state = BacktestSettlementStateSnapshot(
            frozen_quantities=(
                BacktestFrozenQuantitySnapshot(
                    instrument_id=InstrumentId(2_000_001),
                    settle_date="2026-01-14",
                    quantity=800,
                ),
            )
        )
        runtime_state = BacktestRuntimeStateSnapshot(
            pending_orders=(
                BacktestPendingOrderSnapshot(
                    client_order_id="restore-order-1",
                    instrument_id=InstrumentId(2_000_001),
                    order_type="limit",
                    direction="buy",
                    quantity=300,
                    price=201.5,
                    stop_price=None,
                    trade_date="2026-01-13",
                    status="submitted",
                    filled_quantity=0,
                    leaves_quantity=300,
                    filled_price=None,
                    average_fill_price=None,
                ),
            )
        )
        builder = BacktestRuntimeBuilder(
            strategy_runtime_builder=strategy_runtime_builder,
            metadata_service=metadata_service,
            data_provider=data_provider,
        )

        runtime = builder.build_published_runtime(
            config=BacktestServiceConfig(
                strategy_id="momentum-etf",
                start_date="2026-01-13",
                end_date="2026-01-15",
                initial_cash=2_000_000.0,
                resume_account_state_json=account_state.to_json(),
                resume_account_state_hash=account_state.state_hash,
                resume_settlement_state_json=settlement_state.to_json(),
                resume_settlement_state_hash=settlement_state.state_hash,
                resume_runtime_state_json=runtime_state.to_json(),
                resume_runtime_state_hash=runtime_state.state_hash,
            ),
            version=2,
        )

        account = runtime.brokerage.get_account()
        assert account.cash.available == 910_000.0
        assert account.cash.settled == 900_000.0
        assert account.cash.frozen == 10_000.0
        assert account.positions[InstrumentId(2_000_001)].quantity == 1000
        assert runtime.brokerage.get_settlement_state_snapshot() == settlement_state
        pending = runtime.brokerage.get_order_book().get_pending()
        assert len(pending) == 1
        assert pending[0].order.order_id == "restore-order-1"
        assert pending[0].leaves_quantity == 300

    def test_rejects_experimental_stock_data_by_default(self) -> None:
        """默认回测入口不得静默使用 experimental 股票数据集。"""
        spec = _make_strategy_spec(
            strategy_id="stock-alpha",
            name="Stock Alpha",
            template="stock_selection",
            universe="cn_stock",
            asset_class="stock",
        )
        strategy_runtime_builder = MagicMock()
        strategy_runtime_builder.build_published_runtime.return_value = (
            PublishedStrategyRuntime(
                record=StrategySpecRecord(
                    strategy_id=spec.strategy_id,
                    name=spec.name,
                    spec_json=asdict(spec),
                    version=1,
                    status="published",
                    tags=spec.tags,
                ),
                spec=spec,
                pipeline=MagicMock(spec=StrategyPipeline),
            )
        )
        metadata_service = MagicMock(spec=MetadataService)
        data_provider = MagicMock(spec=DataProvider)
        builder = BacktestRuntimeBuilder(
            strategy_runtime_builder=strategy_runtime_builder,
            metadata_service=metadata_service,
            data_provider=data_provider,
        )

        with pytest.raises(AppBuilderError, match="experimental dataset"):
            builder.build_published_runtime(
                config=BacktestServiceConfig(
                    strategy_id="stock-alpha",
                    start_date="2026-01-10",
                    end_date="2026-01-13",
                ),
                version=1,
            )

        metadata_service.get_universe.assert_not_called()
        data_provider.get_bars.assert_not_called()

    def test_allows_experimental_stock_data_when_explicit(self) -> None:
        """研究场景可显式 opt in 使用 experimental 股票数据集。"""
        spec = _make_strategy_spec(
            strategy_id="stock-alpha",
            name="Stock Alpha",
            template="stock_selection",
            universe="cn_stock",
            asset_class="stock",
        )
        strategy_runtime_builder = MagicMock()
        strategy_runtime_builder.build_published_runtime.return_value = (
            PublishedStrategyRuntime(
                record=StrategySpecRecord(
                    strategy_id=spec.strategy_id,
                    name=spec.name,
                    spec_json=asdict(spec),
                    version=1,
                    status="published",
                    tags=spec.tags,
                ),
                spec=spec,
                pipeline=MagicMock(spec=StrategyPipeline),
            )
        )
        metadata_service = MagicMock(spec=MetadataService)
        metadata_service.resolve_instrument_id.return_value = 3_000_001
        metadata_service.get_universe.return_value = [1_000_001]
        metadata_service.instrument.get_instrument.return_value = {
            "ticker": "600000",
            "exchange": "XSHG",
        }
        data_provider = MagicMock(spec=DataProvider)
        builder = BacktestRuntimeBuilder(
            strategy_runtime_builder=strategy_runtime_builder,
            metadata_service=metadata_service,
            data_provider=data_provider,
        )

        runtime = builder.build_published_runtime(
            config=BacktestServiceConfig(
                strategy_id="stock-alpha",
                start_date="2026-01-10",
                end_date="2026-01-13",
            ),
            version=1,
            allow_experimental_data=True,
        )

        assert runtime.spec.asset_class == "stock"

    def test_allows_promoted_stock_data_without_research_opt_in(self) -> None:
        """已完成 metadata promotion 的股票回测不需要 research opt-in。"""
        spec = _make_strategy_spec(
            strategy_id="stock-alpha",
            name="Stock Alpha",
            template="stock_selection",
            universe="cn_stock",
            asset_class="stock",
        )
        strategy_runtime_builder = MagicMock()
        strategy_runtime_builder.build_published_runtime.return_value = (
            PublishedStrategyRuntime(
                record=StrategySpecRecord(
                    strategy_id=spec.strategy_id,
                    name=spec.name,
                    spec_json=asdict(spec),
                    version=1,
                    status="published",
                    tags=spec.tags,
                ),
                spec=spec,
                pipeline=MagicMock(spec=StrategyPipeline),
            )
        )
        metadata_service = MagicMock(spec=MetadataService)
        metadata_service.resolve_instrument_id.return_value = 3_000_001
        metadata_service.get_universe.return_value = [1_000_001]
        metadata_service.instrument.get_instrument.return_value = {
            "ticker": "600000",
            "exchange": "XSHG",
        }
        data_provider = MagicMock(spec=DataProvider)
        builder = BacktestRuntimeBuilder(
            strategy_runtime_builder=strategy_runtime_builder,
            metadata_service=metadata_service,
            data_provider=data_provider,
            maturity_promotion_reader=_MaturityPromotionReader(
                {"stock_daily", "stock_basic"}
            ),
        )

        runtime = builder.build_published_runtime(
            config=BacktestServiceConfig(
                strategy_id="stock-alpha",
                start_date="2026-01-10",
                end_date="2026-01-13",
            ),
            version=1,
        )

        assert runtime.spec.asset_class == "stock"
