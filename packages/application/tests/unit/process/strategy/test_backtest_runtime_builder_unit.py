"""BacktestRuntimeBuilder 单元测试。"""

from __future__ import annotations

from dataclasses import asdict, fields, replace
from unittest.mock import MagicMock

import pytest
from ditto_application.builders import (
    BacktestRuntimeBuilder,
    PublishedStrategyRuntime,
)
from ditto_application.exceptions import AppBuilderError
from ditto_application.processes.execution.backtest_process import (
    BacktestCatalogRequestConfig,
)
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
from ditto_data.catalog.snapshot_reader import SnapshotReadService
from ditto_execution.planner import SimpleExecutionPlanner
from ditto_execution.reality import AShareFeeModel
from ditto_kernel.identity import InstrumentId
from ditto_risk.pre_trade import CompositePreTradeCheck
from ditto_strategy.alpha.node_registry import default_node_registry
from ditto_strategy.alpha.parameters import (
    CandidateParameter,
    ParameterBinder,
    canonical_parameter_hash,
)
from ditto_strategy.alpha.pipeline import StrategyPipeline
from ditto_strategy.alpha.spec_codec import adapt_legacy_strategy_spec
from ditto_strategy.alpha.specs import StrategySpec
from ditto_strategy.models import StrategyArtifactRecord, StrategySpecRecord
from ditto_strategy.storage.sqlite.services.strategy_artifact_service import (
    StrategyArtifactService,
)

from .ordinary_catalog_support import LISTINGS, CatalogProvider, make_metadata


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


def _make_published_strategy_runtime(
    spec: StrategySpec,
    *,
    version: int,
    spec_hash: str | None = None,
) -> PublishedStrategyRuntime:
    binding = ParameterBinder(registry=default_node_registry()).bind(
        adapt_legacy_strategy_spec(spec),
        candidate_parameters=(),
    )
    return PublishedStrategyRuntime(
        record=StrategySpecRecord(
            strategy_id=spec.strategy_id,
            name=spec.name,
            spec_json=asdict(spec),
            version=version,
            tags=spec.tags,
        ),
        spec=spec,
        base_spec=binding.base_spec,
        resolved_spec=binding.resolved_spec,
        pipeline=MagicMock(spec=StrategyPipeline),
        base_spec_hash=binding.base_spec_hash,
        spec_hash=spec_hash or binding.resolved_spec_hash,
        parameter_hash=binding.parameter_hash,
        effective_parameters=binding.effective_parameters,
    )


class TestBacktestRuntimeBuilder:
    """published backtest runtime 装配测试。"""

    @pytest.mark.parametrize("gap", ["member", "warmup", "benchmark", "rule", "exit"])
    def test_catalog_entry_rejects_incomplete_inputs_before_execution(
        self, gap: str
    ) -> None:
        spec = _make_strategy_spec()
        strategy_builder = MagicMock()
        strategy_builder.build_published_runtime.return_value = (
            _make_published_strategy_runtime(spec, version=1)
        )
        metadata = make_metadata()
        provider = CatalogProvider()
        if gap == "member":
            provider.missing.add((2_000_002, "all"))
        elif gap == "warmup":
            provider.missing_before = "2026-01-10"
        elif gap == "benchmark":
            provider.missing.add((3_000_001, "all"))
        else:
            records = {iid: dict(record) for iid, record in LISTINGS.items()}
            if gap == "rule":
                records[2_000_001]["ticker"] = "999999"
            else:
                records[2_000_001]["delist_date"] = "2026-01-12"
            metadata.instrument.get_instrument.side_effect = records.get
        builder = BacktestRuntimeBuilder(
            strategy_runtime_builder=strategy_builder,
            metadata_service=metadata,
            data_provider=provider,
        )
        with pytest.raises(ValueError, match=r"missing|incomplete|exit"):
            builder.build_published_runtime(
                config=BacktestCatalogRequestConfig(
                    strategy_id=spec.strategy_id,
                    start_date="2026-01-10",
                    end_date="2026-01-13",
                ),
                version=1,
            )

    def test_catalog_stock_suspension_reaches_planner_and_fills(self) -> None:
        from datetime import UTC, datetime

        from ditto_execution.brokerage import ProcessInput
        from ditto_execution.orders.ids import ClientOrderId
        from ditto_execution.orders.model import Order
        from ditto_kernel.order import OrderSide, OrderType
        from ditto_strategy.alpha.models import TargetPortfolio

        spec = _make_strategy_spec(asset_class="stock", template="stock_selection")
        strategy_builder = MagicMock()
        strategy_builder.build_published_runtime.return_value = (
            _make_published_strategy_runtime(spec, version=1)
        )
        provider = CatalogProvider()
        provider.suspended = True
        runtime = BacktestRuntimeBuilder(
            strategy_runtime_builder=strategy_builder,
            metadata_service=make_metadata("stock"),
            data_provider=provider,
        ).build_published_runtime(
            config=BacktestCatalogRequestConfig(
                strategy_id=spec.strategy_id,
                start_date="2026-01-12",
                end_date="2026-01-13",
            ),
            version=1,
        )
        iid = InstrumentId(1_000_001)
        bars = runtime.data_feed.get_slice("2026-01-12").bars
        assert bars[iid].is_suspended
        assert runtime.rule_provider is not None
        plan = runtime.planner.plan(
            TargetPortfolio(
                trade_date="2026-01-12",
                strategy_id=spec.strategy_id,
                run_id="suspension",
                positions={iid: 0.5},
            ),
            runtime.brokerage.get_account(),
            "2026-01-12",
            rules=runtime.rule_provider.get_rules("2026-01-12", [iid]),
            market_snapshots=bars,
        )
        assert not plan.orders
        assert plan.blocked_orders[0].reason == "suspended"
        runtime.brokerage.place_order(
            Order(
                client_id=ClientOrderId("suspended"),
                instrument_id=iid,
                direction=OrderSide.BUY,
                order_type=OrderType.MARKET,
                quantity=100,
            )
        )
        assert (
            runtime.brokerage.process_pending(
                ProcessInput(
                    step_time=datetime(2026, 1, 12, 15, tzinfo=UTC),
                    trade_date="2026-01-12",
                    bars=bars,
                )
            )
            == ()
        )

    def test_etf_half_tick_limit_matches_observed_exchange_price(self) -> None:
        import polars as pl
        from ditto_application.builders.ordinary_backtest import (
            build_ordinary_rules,
            ordinary_market_transform,
        )
        from ditto_data.provider import BarQuery

        provider = CatalogProvider()
        frame = provider.get_bars(
            BarQuery(instruments=["510300.SH"], start="2026-10-22", end="2026-10-22")
        ).with_columns(pl.lit(4.185).alias("pre_close"))
        rules = build_ordinary_rules(
            make_metadata(),
            [2_000_001],
            asset_class="etf",
            commission_rate=0.0003,
            period=("2026-10-22", "2026-10-22"),
        )
        result = ordinary_market_transform(rules, start_date="2026-10-22")(frame)
        assert result["limit_up"].item() == 4.604
        assert result["limit_down"].item() == 3.767

    @pytest.mark.parametrize("asset_class", ["stock", "etf"])
    def test_catalog_execution_uses_seed_costs_and_t1(self, asset_class: str) -> None:
        from datetime import UTC, datetime
        from decimal import Decimal

        from ditto_execution.brokerage import ProcessInput
        from ditto_execution.orders.ids import ClientOrderId
        from ditto_execution.orders.model import Order
        from ditto_execution.reality.price import round_to_tick
        from ditto_kernel.order import OrderSide, OrderType
        from ditto_strategy.alpha.specs import CostModelSpec, ExecutionSpec

        spec = replace(
            _make_strategy_spec(asset_class=asset_class),
            execution=ExecutionSpec(
                cost_model=CostModelSpec(commission_rate=0.001, slippage_bps=17)
            ),
        )
        builder = MagicMock()
        builder.build_published_runtime.return_value = _make_published_strategy_runtime(
            spec, version=1
        )
        runtime = BacktestRuntimeBuilder(
            strategy_runtime_builder=builder,
            metadata_service=make_metadata(asset_class),
            data_provider=CatalogProvider(),
        ).build_published_runtime(
            config=BacktestCatalogRequestConfig(
                strategy_id=spec.strategy_id,
                start_date="2026-01-09",
                end_date="2026-01-12",
            ),
            version=1,
        )
        iid = InstrumentId(1_000_001 if asset_class == "stock" else 2_000_001)
        stock = asset_class == "stock"

        def step(day: int) -> ProcessInput:
            date_string = f"2026-01-{day:02}"
            return ProcessInput(
                step_time=datetime(2026, 1, day, 15, tzinfo=UTC),
                trade_date=date_string,
                bars=runtime.data_feed.get_slice(date_string).bars,
            )

        buy = Order(
            client_id=ClientOrderId("buy"),
            instrument_id=iid,
            direction=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=1000,
        )
        runtime.brokerage.place_order(buy)
        fill = runtime.brokerage.process_pending(step(9))[0]
        assert fill.fill_price == round_to_tick(
            Decimal("10.017"), 0.01 if stock else 0.001
        )
        assert fill.fee == pytest.approx(
            fill.fill_price * 1000 * (0.00101 if stock else 0.001)
        )
        assert runtime.brokerage.get_account().positions[iid].available_quantity == 0
        sell = Order(
            client_id=ClientOrderId("sell"),
            instrument_id=iid,
            direction=OrderSide.SELL,
            order_type=OrderType.MARKET,
            quantity=1000,
        )
        runtime.brokerage.place_order(sell)
        assert runtime.brokerage.process_pending(step(9)) == ()
        fill = runtime.brokerage.process_pending(step(12))[0]
        assert fill.fee == pytest.approx(
            fill.fill_price * 1000 * (0.00151 if stock else 0.001)
        )

    def test_ordinary_catalog_cannot_claim_strict_snapshot_qualification(self) -> None:
        from ditto_application.exceptions import AppBuilderError

        builder = BacktestRuntimeBuilder(
            strategy_runtime_builder=MagicMock(),
            metadata_service=make_metadata(),
            data_provider=CatalogProvider(),
        )
        with pytest.raises(AppBuilderError, match="cannot certify"):
            builder.build_published_runtime(
                config=BacktestCatalogRequestConfig(
                    strategy_id="ordinary",
                    start_date="2026-10-08",
                    end_date="2026-11-06",
                    research_snapshot_id="strict-snapshot",
                    research_snapshot_manifest_hash="a" * 64,
                ),
                version=1,
            )

    def test_catalog_resolution_preserves_every_request_field(self) -> None:
        """Resolved config keeps the entire unresolved launch request intact."""
        from ditto_application.builders import service_factory
        from ditto_application.processes.execution import backtest_process

        request_type = getattr(
            backtest_process,
            "BacktestCatalogRequestConfig",
            None,
        )
        resolver = getattr(
            service_factory,
            "_resolve_backtest_catalog_request",
            None,
        )

        # getattr 探针只做存在性检查；调用走静态可解析的真实符号。
        assert request_type is BacktestCatalogRequestConfig
        assert callable(resolver)
        request = BacktestCatalogRequestConfig(
            strategy_id="momentum-etf",
            strategy_version="requested",
            run_id="run-request",
            parent_run_id="run-parent",
            start_date="2026-01-10",
            end_date="2026-01-13",
            initial_cash=2_000_000.0,
            candidate_parameters=(
                CandidateParameter(
                    path="/pipeline/nodes/legacy_factor_set/config/params/lookback",
                    value=20,
                ),
            ),
            random_seed=1729,
            knowledge_lag_days=3,
            data_catalog_identities=("dataset:snapshot",),
            recommendation_status="candidate",
            participation_rate=0.02,
            fill_mode="all_or_nothing",
            resume_from_run_id="resume-source",
        )

        resolved = service_factory._resolve_backtest_catalog_request(
            request,
            strategy_version="7",
            benchmark_id=InstrumentId(3_000_001),
            base_spec_hash="a" * 64,
            spec_hash="b" * 64,
            parameter_hash=canonical_parameter_hash(()),
            effective_parameters=(),
        )

        request_fields = {field.name for field in fields(request)}
        resolved_fields = {field.name for field in fields(resolved)}
        assert resolved_fields == request_fields | {
            "base_spec_hash",
            "spec_hash",
            "parameter_hash",
            "effective_parameters",
            "sample_pool",
        }
        for field_name in request_fields - {"strategy_version", "benchmark_id"}:
            assert getattr(resolved, field_name) == getattr(request, field_name)
        assert resolved.strategy_version == "7"
        assert resolved.benchmark_id == InstrumentId(3_000_001)
        assert resolved.spec_hash == "b" * 64

    def test_build_published_runtime_creates_minimal_backtest_components(self) -> None:
        """builder 应从 published runtime 构造可跑的 backtest 依赖。"""
        canonical_spec_hash = "b" * 64
        spec = _make_strategy_spec()
        strategy_runtime_builder = MagicMock()
        strategy_runtime_builder.build_published_runtime.return_value = (
            _make_published_strategy_runtime(
                spec,
                version=2,
                spec_hash=canonical_spec_hash,
            )
        )
        metadata_service = make_metadata(spec.asset_class)
        metadata_service.resolve_instrument_id.return_value = 3_000_001
        metadata_service.get_universe.return_value = [2_000_001, 2_000_002]
        metadata_service.universe.get_universe_detail.return_value = {
            "universe_id": "cn_etf",
            "name": "Fixed research sample",
            "description": "Selected 2026-01-09; not historical membership",
            "source_ref": "instrument_registry:sha256:" + "c" * 64,
        }
        metadata_service.instrument.get_instrument.return_value = {
            "ticker": "510300",
            "exchange": "XSHG",
        }
        metadata_service.instrument.get_source_ticker.side_effect = (
            "510300.SH",
            "510500.SH",
            "000300.SH",
        )
        data_provider = CatalogProvider()
        builder = BacktestRuntimeBuilder(
            strategy_runtime_builder=strategy_runtime_builder,
            metadata_service=metadata_service,
            data_provider=data_provider,
        )

        runtime = builder.build_published_runtime(
            config=BacktestCatalogRequestConfig(
                strategy_id="momentum-etf",
                start_date="2026-01-10",
                end_date="2026-01-13",
                initial_cash=2_000_000.0,
            ),
            version=2,
        )

        assert runtime.config.strategy_version == "2"
        assert runtime.config.spec_hash == canonical_spec_hash
        assert runtime.config.benchmark_id == 3_000_001
        assert runtime.config.sample_pool is not None
        assert {
            key: value
            for key, value in runtime.config.sample_pool.items()
            if key != "description"
        } == {
            "universe_id": "cn_etf",
            "name": "Fixed research sample",
            "source_ref": "instrument_registry:sha256:" + "c" * 64,
        }
        assert "Selected 2026-01-09" in str(runtime.config.sample_pool["description"])
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
        assert runtime.data_feed._tickers == ("510300.SH", "510500.SH")
        assert [
            item.args
            for item in metadata_service.instrument.get_source_ticker.call_args_list
        ] == [
            (2_000_001, "tushare", "2026-01-10"),
            (2_000_002, "tushare", "2026-01-10"),
            (3_000_001, "tushare", "2026-01-10"),
        ]
        fill_model = runtime.brokerage._model.fill_model
        assert isinstance(fill_model, AShareFillModel)
        assert fill_model.participation_rate == pytest.approx(0.05)
        strategy_runtime_builder.build_published_runtime.assert_called_once_with(
            "momentum-etf",
            2,
            candidate_parameters=(),
        )

    def test_all_or_nothing_fill_mode_disables_participation_cap(self) -> None:
        """fill_mode=all_or_nothing 应保留旧的不限流成交行为。"""
        spec = _make_strategy_spec()
        strategy_runtime_builder = MagicMock()
        strategy_runtime_builder.build_published_runtime.return_value = (
            _make_published_strategy_runtime(spec, version=2, spec_hash="b" * 64)
        )
        metadata_service = make_metadata(spec.asset_class)
        metadata_service.resolve_instrument_id.return_value = 3_000_001
        metadata_service.get_universe.return_value = [2_000_001, 2_000_002]
        metadata_service.instrument.get_instrument.return_value = {
            "ticker": "510300",
            "exchange": "XSHG",
        }
        data_provider = CatalogProvider()
        builder = BacktestRuntimeBuilder(
            strategy_runtime_builder=strategy_runtime_builder,
            metadata_service=metadata_service,
            data_provider=data_provider,
        )

        runtime = builder.build_published_runtime(
            config=BacktestCatalogRequestConfig(
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
            _make_published_strategy_runtime(spec, version=2, spec_hash="b" * 64)
        )
        metadata_service = make_metadata(spec.asset_class)
        metadata_service.resolve_instrument_id.return_value = 3_000_001
        metadata_service.get_universe.return_value = [2_000_001]
        metadata_service.instrument.get_instrument.return_value = {
            "ticker": "510300",
            "exchange": "XSHG",
        }
        data_provider = CatalogProvider()
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
            config=BacktestCatalogRequestConfig(
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

    def test_core_lane_stock_data_available_by_default(self) -> None:
        """核心市场 lane 静态为 initial-focus,默认回测入口可用。"""
        spec = _make_strategy_spec(
            strategy_id="stock-alpha",
            name="Stock Alpha",
            template="stock_selection",
            universe="cn_stock",
            asset_class="stock",
        )
        strategy_runtime_builder = MagicMock()
        strategy_runtime_builder.build_published_runtime.return_value = (
            _make_published_strategy_runtime(spec, version=1, spec_hash="b" * 64)
        )
        metadata_service = make_metadata(spec.asset_class)
        data_provider = CatalogProvider()
        builder = BacktestRuntimeBuilder(
            strategy_runtime_builder=strategy_runtime_builder,
            metadata_service=metadata_service,
            data_provider=data_provider,
        )

        builder.build_published_runtime(
            config=BacktestCatalogRequestConfig(
                strategy_id="stock-alpha",
                start_date="2026-01-10",
                end_date="2026-01-13",
            ),
            version=1,
        )

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
            _make_published_strategy_runtime(spec, version=1, spec_hash="b" * 64)
        )
        metadata_service = make_metadata(spec.asset_class)
        metadata_service.resolve_instrument_id.return_value = 3_000_001
        metadata_service.get_universe.return_value = [1_000_001]
        metadata_service.instrument.get_instrument.return_value = {
            "ticker": "600000",
            "exchange": "XSHG",
        }
        data_provider = CatalogProvider()
        builder = BacktestRuntimeBuilder(
            strategy_runtime_builder=strategy_runtime_builder,
            metadata_service=metadata_service,
            data_provider=data_provider,
        )

        runtime = builder.build_published_runtime(
            config=BacktestCatalogRequestConfig(
                strategy_id="stock-alpha",
                start_date="2026-01-10",
                end_date="2026-01-13",
            ),
            version=1,
            allow_experimental_data=True,
        )

        assert runtime.spec.asset_class == "stock"


def test_missing_benchmark_keeps_original_security_scope_when_pool_changes():
    spec = _make_strategy_spec()
    strategy_builder = MagicMock()
    strategy_builder.build_published_runtime.return_value = (
        _make_published_strategy_runtime(spec, version=1)
    )
    metadata = make_metadata()
    metadata.resolve_instrument_id.return_value = None
    metadata.universe.get_constituent_history.return_value = [
        {"instrument_id": iid, "effective_from": "2014-01-01", "effective_to": None}
        for iid in [2000001, 2000002]
    ]
    saved: dict[str, StrategyArtifactRecord] = {}
    artifacts = MagicMock(spec=StrategyArtifactService)
    artifacts.get_artifact.side_effect = saved.get
    artifacts.save_artifact.side_effect = lambda record: saved.setdefault(
        record.artifact_id, record
    )
    reader = MagicMock(spec=SnapshotReadService)
    reader.list_snapshots.return_value = ()
    builder = BacktestRuntimeBuilder(
        strategy_runtime_builder=strategy_builder,
        metadata_service=metadata,
        data_provider=CatalogProvider(),
        artifact_service=artifacts,
        snapshot_read_service=reader,
    )
    request = BacktestCatalogRequestConfig(
        strategy_id=spec.strategy_id,
        run_id="original",
        start_date="2014-10-13",
        end_date="2014-10-24",
        initial_cash=1000000,
        historical_reconstruction=True,
    )
    with pytest.raises(AppBuilderError, match="declared benchmark cannot be resolved"):
        builder.build_published_runtime(config=request)
    original = saved["original:historical_inputs"]
    assert original.metadata["members"] == ["510300.SH", "510500.SH"]
    assert original.metadata["instrument_ids"] == [2000001, 2000002]
    metadata.resolve_instrument_id.return_value = 3000001
    metadata.get_universe.return_value = [2000001]
    metadata.universe.get_constituent_history.return_value = []
    with pytest.raises(AppBuilderError, match="missing retained calendar"):
        builder.build_published_runtime(
            config=replace(request, run_id="repaired", parent_run_id="original")
        )
    assert (
        saved["repaired:historical_inputs"].metadata["members"]
        == original.metadata["members"]
    )
    assert (
        saved["repaired:historical_inputs"].metadata["instrument_ids"]
        == original.metadata["instrument_ids"]
    )
    assert "benchmark cannot be resolved" in str(original.metadata["reason"])


@pytest.mark.parametrize("missing", ["listing", "provider_identity"])
def test_identity_failure_preserves_all_member_intervals_before_repair(missing):
    spec = _make_strategy_spec()
    strategy_builder = MagicMock()
    strategy_builder.build_published_runtime.return_value = (
        _make_published_strategy_runtime(spec, version=1)
    )
    metadata = make_metadata()
    intervals = [
        {
            "instrument_id": 2000001,
            "effective_from": "2014-01-01",
            "effective_to": None,
        },
        {
            "instrument_id": 2000002,
            "effective_from": "2014-10-20",
            "effective_to": None,
        },
    ]
    metadata.universe.get_constituent_history.return_value = intervals
    if missing == "listing":
        metadata.instrument.get_instrument.side_effect = lambda iid: (
            None if iid == 2000002 else LISTINGS.get(iid)
        )
    else:
        metadata.instrument.get_source_ticker.side_effect = lambda iid, *_: (
            None if iid == 2000002 else "510300.SH"
        )
    saved: dict[str, StrategyArtifactRecord] = {}
    artifacts = MagicMock(spec=StrategyArtifactService)
    artifacts.get_artifact.side_effect = saved.get
    artifacts.save_artifact.side_effect = lambda record: saved.setdefault(
        record.artifact_id, record
    )
    builder = BacktestRuntimeBuilder(
        strategy_runtime_builder=strategy_builder,
        metadata_service=metadata,
        data_provider=CatalogProvider(),
        artifact_service=artifacts,
        snapshot_read_service=MagicMock(spec=SnapshotReadService),
    )
    request = BacktestCatalogRequestConfig(
        strategy_id=spec.strategy_id,
        run_id="identity-failed",
        start_date="2014-10-13",
        end_date="2014-10-24",
        historical_reconstruction=True,
    )
    with pytest.raises(AppBuilderError, match="missing historical"):
        builder.build_published_runtime(config=request)
    original = saved["identity-failed:historical_inputs"]
    assert original.metadata["instrument_ids"] == [2000001, 2000002]
    assert original.metadata["membership_intervals"] == intervals
    metadata.universe.get_constituent_history.return_value = intervals[:1]
    metadata.instrument.get_instrument.side_effect = lambda iid: (
        {**LISTINGS[iid], "list_date": "2030-01-01"}
        if iid == 2000001
        else LISTINGS.get(iid)
    )
    metadata.instrument.get_source_ticker.side_effect = lambda iid, *_: {
        2000001: "510300.SH",
        2000002: "510500.SH",
    }.get(iid)
    metadata.resolve_instrument_id.return_value = None
    with pytest.raises(AppBuilderError, match="benchmark cannot be resolved"):
        builder.build_published_runtime(
            config=replace(
                request, run_id="identity-repaired", parent_run_id=request.run_id
            )
        )
    repaired = saved["identity-repaired:historical_inputs"]
    assert repaired.metadata["instrument_ids"] == original.metadata["instrument_ids"]
    assert repaired.metadata["membership_intervals"] == intervals
    assert repaired.metadata["members"] == ["510300.SH", "510500.SH"]
    repaired_roster = repaired.metadata["roster"]
    original_roster = original.metadata["roster"]
    assert isinstance(repaired_roster, list)
    assert isinstance(original_roster, list)
    assert repaired_roster[0] == original_roster[0]
