"""回测确定性重放测试 — 验证同配置运行结果一致、版本变更可 diff.

Layer 1: 同 config + 同代码 → 两次运行结果完全一致
Layer 2: 不同策略参数 → diff report 精确指出差异
P5 证明型测试: manifest 序列化稳定性、rule_refs 排序、pre_trade 审计链路
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import orjson
import polars as pl
import pytest
from ditto_core.accounting.account import Account
from ditto_core.accounting.cash import CashBook
from ditto_core.backtest.data_feed import ParquetDataFeed
from ditto_core.backtest.engine import (
    EngineConfig,
    EngineLoop,
    EngineMode,
    EngineOptions,
)
from ditto_core.backtest.manifest import (
    RuleRef,
    RunManifest,
    RunMode,
    serialize_manifest,
)
from ditto_core.backtest.risk.pre_trade import (
    BuyingPowerCheck,
    CompositePreTradeCheck,
    LotSizeCheck,
)
from ditto_core.backtest.statistics import (
    ExecutionAuditCollector,
    PreTradeDecisionRecord,
)
from ditto_core.execution.brokerage import BacktestBrokerage
from ditto_core.execution.fills import FillEvent
from ditto_core.execution.planner import SimpleExecutionPlanner
from ditto_core.execution.reality import (
    AShareFeeModel,
    BrokerageModel,
    SimpleFeeModel,
)
from ditto_core.execution.rules import (
    FeeSchedule,
    InstrumentDefinition,
    InstrumentRules,
    RulesGetter,
    TradingRuleSet,
)
from ditto_core.strategy.templates.etf_rotation import (
    ETFRotationConfig,
    build_etf_rotation_pipeline,
)

from .conftest import (
    INITIAL_CASH,
    INSTRUMENT_IDS,
    generate_3day_data,
    write_parquet_data,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _default_rules_getter(
    instrument_id: str,
    trade_date: str,
) -> InstrumentRules:
    """默认规则 — 与 BacktestBrokerage._default_rules_getter 一致。"""
    return (
        InstrumentDefinition(
            instrument_id=instrument_id,
            asset_class="etf",
            exchange="XSHE",
            currency="CNY",
            tick_size=0.001,
            lot_size=100,
            multiplier=1.0,
            board_segment="main",
            lifecycle_state="normal",
        ),
        TradingRuleSet(
            instrument_id=instrument_id,
            as_of_date=trade_date,
            settlement_cycle=0,
            fund_settlement_cycle=0,
            price_limit_pct=None,
            order_types_supported=("market", "limit"),
            call_auction_sessions=(),
        ),
        FeeSchedule(
            instrument_id=instrument_id,
            as_of_date=trade_date,
            commission_rate=0.0003,
            min_commission=5.0,
            stamp_duty_rate=0.0,
            transfer_fee_rate=0.0,
        ),
    )


def _ashare_rules_getter(
    instrument_id: str,
    trade_date: str,
) -> InstrumentRules:
    """A 股规则 — 包含印花税 (仅卖出) + 过户费。"""
    return (
        InstrumentDefinition(
            instrument_id=instrument_id,
            asset_class="etf",
            exchange="XSHE",
            currency="CNY",
            tick_size=0.001,
            lot_size=100,
            multiplier=1.0,
            board_segment="main",
            lifecycle_state="normal",
        ),
        TradingRuleSet(
            instrument_id=instrument_id,
            as_of_date=trade_date,
            settlement_cycle=1,
            fund_settlement_cycle=0,
            price_limit_pct=0.10,
            order_types_supported=("market", "limit"),
            call_auction_sessions=(),
        ),
        FeeSchedule(
            instrument_id=instrument_id,
            as_of_date=trade_date,
            commission_rate=0.0003,
            min_commission=5.0,
            stamp_duty_rate=0.001,
            transfer_fee_rate=0.00001,
        ),
    )


def _build_engine_loop(
    tmp_path: Path,
    data: dict[str, pl.DataFrame],
    config: EngineConfig,
    pipeline: Any,
    fee_model: SimpleFeeModel | AShareFeeModel,
    pre_trade_check: CompositePreTradeCheck,
    instance_id: int = 0,
    rules_getter: RulesGetter | None = None,
) -> EngineLoop:
    """从测试数据构建完整 EngineLoop 实例。"""
    instance_dir = tmp_path / f"engine_{instance_id}"
    instance_dir.mkdir(parents=True)
    data_dir = write_parquet_data(instance_dir, data)
    data_feed = ParquetDataFeed(
        data_dir=data_dir,
        instrument_ids=INSTRUMENT_IDS,
        start_date=config.start_date,
        end_date=config.end_date,
    )
    account = Account(
        cash=CashBook(
            available=INITIAL_CASH,
            settled=INITIAL_CASH,
            frozen=0.0,
        ),
    )
    brokerage = BacktestBrokerage(
        account=account,
        model=BrokerageModel(fee_model=fee_model),
        rules_getter=rules_getter,
    )
    planner = SimpleExecutionPlanner()

    return EngineLoop(
        config=config,
        pipeline=pipeline,
        planner=planner,
        brokerage=brokerage,
        pre_trade_check=pre_trade_check,
        data_feed=data_feed,
        options=EngineOptions(fee_model=fee_model),
    )


def _fill_key(fill: FillEvent) -> tuple[str, str, int, float, float]:
    """提取 FillEvent 的业务关键字段（排除 UUID）。"""
    return (
        fill.instrument_id,
        fill.direction.value,
        fill.filled_quantity,
        fill.fill_price,
        fill.fee,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def three_day_config() -> EngineConfig:
    """3 日回测配置。"""
    return EngineConfig(
        start_date="2026-01-05",
        end_date="2026-01-07",
        initial_cash=INITIAL_CASH,
        mode=EngineMode.BACKTEST,
        strategy_id="test-etf-rotation",
        strategy_run_id="run-repro",
    )


@pytest.fixture
def etf_pipeline() -> Any:
    """etf_rotation 策略 Pipeline。"""
    config = ETFRotationConfig(top_k=3, cash_target=0.0)
    return build_etf_rotation_pipeline(config)


@pytest.fixture
def composite_pre_trade_check() -> CompositePreTradeCheck:
    """组合 PreTrade 校验。"""
    return CompositePreTradeCheck(
        checks=(LotSizeCheck(), BuyingPowerCheck()),
    )


@pytest.fixture
def three_day_test_data() -> dict[str, pl.DataFrame]:
    """3 日测试数据。"""
    return generate_3day_data()


@pytest.fixture
def two_identical_engine_loops(
    tmp_path: Path,
    three_day_config: EngineConfig,
    etf_pipeline: Any,
    composite_pre_trade_check: CompositePreTradeCheck,
    three_day_test_data: dict[str, pl.DataFrame],
) -> tuple[EngineLoop, EngineLoop]:
    """构建两个独立但配置完全相同的 EngineLoop 实例。"""
    data = three_day_test_data
    kwargs = {
        "config": three_day_config,
        "pipeline": etf_pipeline,
        "pre_trade_check": composite_pre_trade_check,
    }
    loop1 = _build_engine_loop(
        tmp_path,
        data,
        fee_model=SimpleFeeModel(),
        instance_id=0,
        **kwargs,
    )
    loop2 = _build_engine_loop(
        tmp_path,
        data,
        fee_model=SimpleFeeModel(),
        instance_id=1,
        **kwargs,
    )
    return loop1, loop2


# ---------------------------------------------------------------------------
# Task 3A.1: Layer 1 — 同 manifest 结果一致
# ---------------------------------------------------------------------------


class TestReproducibilityLayer1:
    """同 config + 同代码 → 两次运行结果完全一致。"""

    def test_reproducible_with_same_manifest(
        self,
        two_identical_engine_loops: tuple[EngineLoop, EngineLoop],
    ) -> None:
        """同 config 运行两次 → final_nav / fills / orders 完全一致。"""
        loop1, loop2 = two_identical_engine_loops

        result1 = loop1.run()
        result2 = loop2.run()

        assert result1.final_nav == result2.final_nav
        assert result1.total_trades == result2.total_trades

        fills1 = sorted([_fill_key(f) for f in result1.fills])
        fills2 = sorted([_fill_key(f) for f in result2.fills])
        assert fills1 == fills2

        orders1 = sorted(
            [(o.instrument_id, o.direction.value, o.quantity) for o in result1.orders]
        )
        orders2 = sorted(
            [(o.instrument_id, o.direction.value, o.quantity) for o in result2.orders]
        )
        assert orders1 == orders2

        assert result1.manifest is not None
        assert result2.manifest is not None
        assert result1.manifest.rule_refs == result2.manifest.rule_refs

    def test_reproducible_manifest_serialization(
        self,
        two_identical_engine_loops: tuple[EngineLoop, EngineLoop],
    ) -> None:
        """两次运行的 manifest 序列化 JSON 字节级一致（排除 created_at）。"""
        loop1, loop2 = two_identical_engine_loops
        result1 = loop1.run()
        result2 = loop2.run()

        assert result1.manifest is not None
        assert result2.manifest is not None

        json1 = serialize_manifest(result1.manifest)
        json2 = serialize_manifest(result2.manifest)

        parsed1 = orjson.loads(json1)
        parsed2 = orjson.loads(json2)

        for key in parsed1:
            if key == "created_at":
                continue
            assert parsed1[key] == parsed2[key], f"manifest field '{key}' differs"

    def test_reproducible_account_nav(
        self,
        two_identical_engine_loops: tuple[EngineLoop, EngineLoop],
    ) -> None:
        """两次运行的 AccountView.nav 完全一致。"""
        loop1, loop2 = two_identical_engine_loops
        result1 = loop1.run()
        result2 = loop2.run()

        assert result1.account_view is not None
        assert result2.account_view is not None
        assert result1.account_view.nav == result2.account_view.nav
        assert result1.account_view.cash.total == result2.account_view.cash.total


# ---------------------------------------------------------------------------
# Task 3A.2: Layer 2 — 版本变更 diff report
# ---------------------------------------------------------------------------


class TestReproducibilityLayer2:
    """不同策略参数 → diff report 精确指出差异。"""

    def test_version_change_diff_report(
        self,
        tmp_path: Path,
        three_day_config: EngineConfig,
        etf_pipeline: Any,
        composite_pre_trade_check: CompositePreTradeCheck,
        three_day_test_data: dict[str, pl.DataFrame],
    ) -> None:
        """不同 fee model + fee_schedule → fills 中的 fee 字段不同。"""
        data = three_day_test_data

        loop_simple = _build_engine_loop(
            tmp_path,
            data,
            three_day_config,
            etf_pipeline,
            SimpleFeeModel(),
            composite_pre_trade_check,
            instance_id=0,
        )
        result_simple = loop_simple.run()

        loop_ashare = _build_engine_loop(
            tmp_path,
            data,
            three_day_config,
            etf_pipeline,
            AShareFeeModel(),
            composite_pre_trade_check,
            instance_id=1,
            rules_getter=_ashare_rules_getter,
        )
        result_ashare = loop_ashare.run()

        assert result_simple.manifest is not None
        assert result_ashare.manifest is not None

        assert result_simple.manifest.strategy_id == result_ashare.manifest.strategy_id

        simple_fees = {(f.instrument_id, f.fee) for f in result_simple.fills}
        ashare_fees = {(f.instrument_id, f.fee) for f in result_ashare.fills}

        assert len(simple_fees) > 0, "SimpleFeeModel run should produce fills"
        assert simple_fees != ashare_fees, (
            "Different fee models should produce different fees"
        )

        simple_instruments = {iid for iid, _ in simple_fees}
        ashare_instruments = {iid for iid, _ in ashare_fees}
        common_instruments = simple_instruments & ashare_instruments
        assert len(common_instruments) > 0, (
            "Both runs should trade at least one common instrument"
        )

    def test_different_fee_model_nav_differs(
        self,
        tmp_path: Path,
        three_day_config: EngineConfig,
        etf_pipeline: Any,
        composite_pre_trade_check: CompositePreTradeCheck,
        three_day_test_data: dict[str, pl.DataFrame],
    ) -> None:
        """不同 fee model → final_nav 不同（费用差异影响 NAV）。"""
        data = three_day_test_data

        loop_simple = _build_engine_loop(
            tmp_path,
            data,
            three_day_config,
            etf_pipeline,
            SimpleFeeModel(),
            composite_pre_trade_check,
            instance_id=0,
        )
        result_simple = loop_simple.run()

        loop_ashare = _build_engine_loop(
            tmp_path,
            data,
            three_day_config,
            etf_pipeline,
            AShareFeeModel(),
            composite_pre_trade_check,
            instance_id=1,
            rules_getter=_ashare_rules_getter,
        )
        result_ashare = loop_ashare.run()

        simple_total_fee = sum(f.fee for f in result_simple.fills)
        ashare_total_fee = sum(f.fee for f in result_ashare.fills)
        assert simple_total_fee != ashare_total_fee, (
            f"Total fees differ: simple={simple_total_fee:.2f} "
            f"vs ashare={ashare_total_fee:.2f}"
        )

        assert result_simple.final_nav != result_ashare.final_nav


# ---------------------------------------------------------------------------
# Task 3A.3: P5 证明型测试
# ---------------------------------------------------------------------------


class TestProofTests:
    """P5 证明型测试。"""

    def test_manifest_canonical_json_stable(self) -> None:
        """同 manifest 二次序列化 → 字节级一致。"""
        manifest = RunManifest(
            run_id="test-run-001",
            strategy_id="etf-rotation",
            strategy_version="1.0.0",
            mode=RunMode.BACKTEST,
            created_at="2026-01-07T12:00:00Z",
            input_refs=("market://parquet/ETF-001", "market://parquet/ETF-002"),
            parameter_overrides=("top_k=3",),
            rule_refs=(
                RuleRef(
                    instrument_id="ETF-001",
                    definition_version="a1b2c3d4",
                    trading_rule_as_of="2026-01-01",
                    fee_schedule_as_of="2026-01-01",
                ),
                RuleRef(
                    instrument_id="ETF-002",
                    definition_version="e5f6g7h8",
                    trading_rule_as_of="2026-01-01",
                    fee_schedule_as_of="2026-01-01",
                ),
            ),
            config_hash="deadbeef",
            engine_version="0.1.0",
        )

        json1 = serialize_manifest(manifest)
        json2 = serialize_manifest(manifest)
        assert json1 == json2, "Same manifest should produce byte-identical JSON"

    def test_rule_refs_sorted_and_diffable(self) -> None:
        """rule_refs 稳定排序 → diff 可定位变更。"""
        rule_a = RuleRef(
            instrument_id="ETF-002",
            definition_version="e5f6g7h8",
            trading_rule_as_of="2026-01-01",
            fee_schedule_as_of="2026-01-01",
        )
        rule_b = RuleRef(
            instrument_id="ETF-001",
            definition_version="a1b2c3d4",
            trading_rule_as_of="2026-01-01",
            fee_schedule_as_of="2026-01-01",
        )
        rule_c = RuleRef(
            instrument_id="ETF-003",
            definition_version="11223344",
            trading_rule_as_of="2026-01-01",
            fee_schedule_as_of="2026-01-01",
        )

        manifest_v1 = RunManifest(
            run_id="test-diff-v1",
            strategy_id="etf-rotation",
            strategy_version="1.0.0",
            mode=RunMode.BACKTEST,
            created_at="2026-01-07T12:00:00Z",
            rule_refs=(rule_a, rule_b),
        )

        json_v1 = serialize_manifest(manifest_v1)
        parsed_v1 = orjson.loads(json_v1)
        ref_ids_v1 = [r["instrument_id"] for r in parsed_v1["rule_refs"]]
        assert ref_ids_v1 == ["ETF-001", "ETF-002"], (
            "rule_refs should be sorted by instrument_id"
        )

        manifest_v2 = RunManifest(
            run_id="test-diff-v2",
            strategy_id="etf-rotation",
            strategy_version="1.0.0",
            mode=RunMode.BACKTEST,
            created_at="2026-01-07T12:00:00Z",
            rule_refs=(rule_a, rule_b, rule_c),
        )

        json_v2 = serialize_manifest(manifest_v2)
        parsed_v2 = orjson.loads(json_v2)
        ref_ids_v2 = [r["instrument_id"] for r in parsed_v2["rule_refs"]]
        assert ref_ids_v2 == ["ETF-001", "ETF-002", "ETF-003"]

        assert ref_ids_v1 != ref_ids_v2, "Added rule_ref should be detectable"
        assert ref_ids_v1 == ref_ids_v2[:2], "Existing refs should remain unchanged"

    def test_order_log_resize_check_chain(self) -> None:
        """pre_trade_decision.check_sequence 还原 resize 链路。"""
        collector = ExecutionAuditCollector()

        decision = PreTradeDecisionRecord(
            trade_date="2026-01-05",
            order_id="order-001",
            instrument_id="ETF-001",
            direction="buy",
            original_quantity=1500,
            final_quantity=1400,
            decision="resized",
            reason="lot_size adjusted",
            check_sequence=("lot_size", "buying_power"),
        )
        collector.record_pre_trade_decisions("2026-01-05", (decision,))

        log = collector.get_pre_trade_log()
        assert len(log) == 1

        recorded = log[0]
        assert recorded.check_sequence == ("lot_size", "buying_power")
        assert recorded.instrument_id == "ETF-001"
        assert recorded.original_quantity == 1500
        assert recorded.final_quantity == 1400
        assert recorded.decision == "resized"

    def test_manifest_with_no_rule_refs(self) -> None:
        """空 rule_refs 的 manifest 也能稳定序列化。"""
        manifest = RunManifest(
            run_id="empty-rules",
            strategy_id="test",
            strategy_version="",
            mode=RunMode.RESEARCH,
            created_at="2026-01-01T00:00:00Z",
        )

        json1 = serialize_manifest(manifest)
        json2 = serialize_manifest(manifest)
        assert json1 == json2

        parsed = orjson.loads(json1)
        assert parsed["rule_refs"] == []
