"""回测确定性重放测试 — 验证同配置运行结果一致、版本变更可 diff.

Layer 1: 同 config + 同代码 → 两次运行结果完全一致
Layer 2: 不同策略参数 → diff report 精确指出差异
P5 证明型测试: manifest 序列化稳定性、rule_refs 排序、pre_trade 审计链路
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import orjson
import polars as pl
import pytest
from ditto_engine.backtest.engine import (
    EngineConfig,
    EngineLoop,
    EngineMode,
    EngineOptions,
    EngineResult,
)
from ditto_engine.backtest.manifest import (
    RuleRef,
    RunManifest,
    RunMode,
    serialize_manifest,
)
from ditto_engine.backtest.statistics import (
    ExecutionAuditCollector,
    PreTradeDecisionRecord,
    build_report,
)
from ditto_engine.execution.brokerage import BacktestBrokerage
from ditto_engine.execution.planner import SimpleExecutionPlanner
from ditto_engine.execution.reality import (
    AShareFeeModel,
    BrokerageModel,
    SimpleFeeModel,
)
from ditto_engine.execution.rules import (
    FeeSchedule,
    InstrumentDefinition,
    InstrumentRules,
    RulesGetter,
    TradingRuleSet,
)
from ditto_kernel.clock import SimulatedClock
from ditto_portfolio.accounting.account import Account
from ditto_portfolio.accounting.cash import CashBook
from ditto_portfolio.accounting.fills import FillEvent
from ditto_risk.pre_trade import (
    BuyingPowerCheck,
    CompositePreTradeCheck,
    LotSizeCheck,
)
from ditto_strategy.alpha.templates.etf_rotation import (
    ETFRotationConfig,
    build_etf_rotation_pipeline,
)

from .conftest import (
    INITIAL_CASH,
    INSTRUMENT_IDS,
    build_test_data_feed,
    generate_3day_data,
    write_parquet_data,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _default_rules_getter(
    instrument_id: int,
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
    instrument_id: int,
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
    data: dict[int, pl.DataFrame],
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
    data_feed = build_test_data_feed(
        parquet_dir=data_dir,
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
        options=EngineOptions(
            clock=SimulatedClock(initial=datetime(2026, 1, 5, tzinfo=UTC)),
            fee_model=fee_model,
        ),
    )


def _build_audited_engine_loop(
    tmp_path: Path,
    data: dict[int, pl.DataFrame],
    config: EngineConfig,
    pipeline: Any,
    fee_model: SimpleFeeModel | AShareFeeModel,
    pre_trade_check: CompositePreTradeCheck,
    collector: ExecutionAuditCollector,
    instance_id: int = 0,
    rules_getter: RulesGetter | None = None,
) -> _AuditedEngineLoop:
    """构建带审计收集器的 EngineLoop — 自动记录每日快照和成交。"""
    instance_dir = tmp_path / f"audited_{instance_id}"
    instance_dir.mkdir(parents=True)
    data_dir = write_parquet_data(instance_dir, data)
    data_feed = build_test_data_feed(
        parquet_dir=data_dir,
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

    return _AuditedEngineLoop(
        config=config,
        pipeline=pipeline,
        planner=planner,
        brokerage=brokerage,
        pre_trade_check=pre_trade_check,
        data_feed=data_feed,
        options=EngineOptions(
            clock=SimulatedClock(initial=datetime(2026, 1, 5, tzinfo=UTC)),
            fee_model=fee_model,
            audit_collector=collector,
        ),
        collector=collector,
    )


class _AuditedEngineLoop(EngineLoop):
    """EngineLoop 子类 — 在每步后自动记录 account_view 和 fills 到审计收集器。"""

    def __init__(
        self,
        collector: ExecutionAuditCollector,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._audit_collector = collector

    def _step(self, date: str) -> bool:
        """执行单日步骤并记录审计数据。"""
        # 记录步骤前账户快照
        account_view_before = self._brokerage.get_account()
        self._audit_collector.record_account_view(
            f"{date}-before",
            account_view_before,
        )

        # 执行原始步骤
        result = super()._step(date)

        # 记录步骤后账户快照
        account_view_after = self._brokerage.get_account()
        self._audit_collector.record_account_view(date, account_view_after)

        return result


def _fill_key(fill: FillEvent) -> tuple[int, str, int, float, float]:
    """提取 FillEvent 的业务关键字段（排除 UUID）。"""
    return (
        fill.instrument_id,
        fill.direction.value,
        fill.filled_quantity,
        fill.fill_price,
        fill.fee,
    )


def _fill_identity_key(fill: FillEvent) -> str:
    """FillEvent 的归一化标识 — 用于 diff 比对 (instrument, direction, date)。"""
    return f"{fill.instrument_id}|{fill.direction.value}|{fill.event_time:%Y-%m-%d}"


# ---------------------------------------------------------------------------
# RunDiff — 两次引擎运行定量差异
# ---------------------------------------------------------------------------


@dataclass
class RunDiff:
    """两次引擎运行的定量差异。"""

    nav_delta: float
    nav_delta_pct: float
    total_fee_delta: float
    affected_instruments: set[int]
    affected_dates: set[str]
    fill_count_diff: int
    extra_fills_in_a: set[str]
    extra_fills_in_b: set[str]


def compute_run_diff(
    result_a: EngineResult,
    result_b: EngineResult,
    label_a: str = "A",
    label_b: str = "B",
) -> RunDiff:
    """计算两次引擎运行的定量差异。

    Args:
        result_a: 第一次运行结果。
        result_b: 第二次运行结果。
        label_a: 第一次运行标签 (用于 extra_fills 标识)。
        label_b: 第二次运行标签。

    Returns:
        RunDiff 实例，包含 NAV 差异、费用差异、影响标的/日期等。
    """
    nav_delta = result_a.final_nav - result_b.final_nav
    nav_delta_pct = (
        (nav_delta / result_b.final_nav * 100) if result_b.final_nav != 0 else 0.0
    )

    total_fee_a = sum(f.fee for f in result_a.fills)
    total_fee_b = sum(f.fee for f in result_b.fills)
    total_fee_delta = total_fee_a - total_fee_b

    # 归一化 fill 标识
    keys_a = {_fill_identity_key(f) for f in result_a.fills}
    keys_b = {_fill_identity_key(f) for f in result_b.fills}

    extra_in_a = keys_a - keys_b
    extra_in_b = keys_b - keys_a

    # 影响标的 — 两个运行中 fill 标识不同的 instrument
    affected_instruments: set[int] = set()
    affected_dates: set[str] = set()

    all_diff_keys = extra_in_a | extra_in_b
    for key in all_diff_keys:
        parts = key.split("|")
        if len(parts) == 3:
            affected_instruments.add(int(parts[0]))
            affected_dates.add(parts[2])

    # 额外添加费用不同但标识相同的标的
    fee_map_a: dict[str, float] = {}
    fee_map_b: dict[str, float] = {}
    for f in result_a.fills:
        k = _fill_identity_key(f)
        fee_map_a[k] = fee_map_a.get(k, 0.0) + f.fee
    for f in result_b.fills:
        k = _fill_identity_key(f)
        fee_map_b[k] = fee_map_b.get(k, 0.0) + f.fee

    for k in keys_a & keys_b:
        if abs(fee_map_a.get(k, 0.0) - fee_map_b.get(k, 0.0)) > 1e-10:
            parts = k.split("|")
            if len(parts) == 3:
                affected_instruments.add(int(parts[0]))
                affected_dates.add(parts[2])

    return RunDiff(
        nav_delta=nav_delta,
        nav_delta_pct=nav_delta_pct,
        total_fee_delta=total_fee_delta,
        affected_instruments=affected_instruments,
        affected_dates=affected_dates,
        fill_count_diff=abs(len(result_a.fills) - len(result_b.fills)),
        extra_fills_in_a=extra_in_a,
        extra_fills_in_b=extra_in_b,
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
def three_day_test_data() -> dict[int, pl.DataFrame]:
    """3 日测试数据。"""
    return generate_3day_data()


@pytest.fixture
def two_identical_engine_loops(
    tmp_path: Path,
    three_day_config: EngineConfig,
    etf_pipeline: Any,
    composite_pre_trade_check: CompositePreTradeCheck,
    three_day_test_data: dict[int, pl.DataFrame],
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

    def test_reproducible_nav_series(
        self,
        tmp_path: Path,
        three_day_config: EngineConfig,
        etf_pipeline: Any,
        composite_pre_trade_check: CompositePreTradeCheck,
        three_day_test_data: dict[int, pl.DataFrame],
    ) -> None:
        """两次运行的 nav_series 逐日完全一致 — 验证整个 NAV 轨迹的确定性。"""
        data = three_day_test_data
        collector1 = ExecutionAuditCollector()
        collector2 = ExecutionAuditCollector()

        loop1 = _build_audited_engine_loop(
            tmp_path,
            data,
            three_day_config,
            etf_pipeline,
            SimpleFeeModel(),
            composite_pre_trade_check,
            collector=collector1,
            instance_id=0,
        )
        loop2 = _build_audited_engine_loop(
            tmp_path,
            data,
            three_day_config,
            etf_pipeline,
            SimpleFeeModel(),
            composite_pre_trade_check,
            collector=collector2,
            instance_id=1,
        )

        result1 = loop1.run()
        result2 = loop2.run()

        report1 = build_report(collector1, run_id=result1.run_id)
        report2 = build_report(collector2, run_id=result2.run_id)

        assert len(report1.nav_series) > 0, "nav_series should not be empty"
        assert len(report1.nav_series) == len(report2.nav_series), (
            f"nav_series length differs: {len(report1.nav_series)} vs "
            f"{len(report2.nav_series)}"
        )

        for i, ((date1, nav1), (date2, nav2)) in enumerate(
            zip(report1.nav_series, report2.nav_series, strict=True),
        ):
            assert date1 == date2, f"Day {i}: date differs ({date1} vs {date2})"
            assert nav1 == nav2, f"Day {i} ({date1}): nav differs ({nav1} vs {nav2})"

    def test_reproducible_nav_series_with_engine_version(
        self,
        tmp_path: Path,
        three_day_config: EngineConfig,
        etf_pipeline: Any,
        composite_pre_trade_check: CompositePreTradeCheck,
        three_day_test_data: dict[int, pl.DataFrame],
    ) -> None:
        """同 engine_version 两次运行 → nav_series 一致。"""
        data = three_day_test_data
        config = EngineConfig(
            start_date="2026-01-05",
            end_date="2026-01-07",
            initial_cash=INITIAL_CASH,
            mode=EngineMode.BACKTEST,
            strategy_id="test-etf-rotation",
            strategy_run_id="run-version",
            engine_version="0.1.0",
        )
        collector1 = ExecutionAuditCollector()
        collector2 = ExecutionAuditCollector()

        loop1 = _build_audited_engine_loop(
            tmp_path,
            data,
            config,
            etf_pipeline,
            SimpleFeeModel(),
            composite_pre_trade_check,
            collector=collector1,
            instance_id=0,
        )
        loop2 = _build_audited_engine_loop(
            tmp_path,
            data,
            config,
            etf_pipeline,
            SimpleFeeModel(),
            composite_pre_trade_check,
            collector=collector2,
            instance_id=1,
        )

        result1 = loop1.run()
        result2 = loop2.run()

        report1 = build_report(collector1, run_id=result1.run_id)
        report2 = build_report(collector2, run_id=result2.run_id)

        assert report1.nav_series == report2.nav_series

    def test_manifest_captures_strategy_metadata_and_inputs(
        self,
        tmp_path: Path,
        etf_pipeline: Any,
        composite_pre_trade_check: CompositePreTradeCheck,
        three_day_test_data: dict[int, pl.DataFrame],
    ) -> None:
        """manifest 应冻结策略版本、参数覆盖、输入引用与配置哈希。"""
        config = EngineConfig(
            start_date="2026-01-05",
            end_date="2026-01-07",
            initial_cash=INITIAL_CASH,
            mode=EngineMode.BACKTEST,
            strategy_id="test-etf-rotation",
            strategy_version="2026.03",
            strategy_run_id="run-manifest-meta",
            parameter_overrides=("top_k=3", "cash_target=0.0"),
            engine_version="0.2.0",
        )
        loop = _build_engine_loop(
            tmp_path,
            three_day_test_data,
            config,
            etf_pipeline,
            SimpleFeeModel(),
            composite_pre_trade_check,
            instance_id=0,
        )

        result = loop.run()

        assert result.manifest is not None
        assert result.manifest.strategy_version == "2026.03"
        assert result.manifest.parameter_overrides == (
            "top_k=3",
            "cash_target=0.0",
        )
        assert result.manifest.rule_resolution_policy == "as_of_date"
        assert result.manifest.engine_version == "0.2.0"
        assert result.manifest.config_hash != ""
        assert result.manifest.input_refs == tuple(sorted(INSTRUMENT_IDS))


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
        three_day_test_data: dict[int, pl.DataFrame],
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
        three_day_test_data: dict[int, pl.DataFrame],
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

    def test_compute_run_diff_identical_runs(
        self,
        two_identical_engine_loops: tuple[EngineLoop, EngineLoop],
    ) -> None:
        """同 config 两次运行 → compute_run_diff 输出全零差异。"""
        loop1, loop2 = two_identical_engine_loops
        result1 = loop1.run()
        result2 = loop2.run()

        diff = compute_run_diff(result1, result2, "run-1", "run-2")

        assert diff.nav_delta == 0.0
        assert diff.nav_delta_pct == 0.0
        assert diff.total_fee_delta == 0.0
        assert diff.fill_count_diff == 0
        assert len(diff.affected_instruments) == 0
        assert len(diff.affected_dates) == 0
        assert len(diff.extra_fills_in_a) == 0
        assert len(diff.extra_fills_in_b) == 0

    def test_compute_run_diff_different_fee_models(
        self,
        tmp_path: Path,
        three_day_config: EngineConfig,
        etf_pipeline: Any,
        composite_pre_trade_check: CompositePreTradeCheck,
        three_day_test_data: dict[int, pl.DataFrame],
    ) -> None:
        """不同 fee model → compute_run_diff 精确量化差异。"""
        data = three_day_test_data

        config_simple = EngineConfig(
            start_date="2026-01-05",
            end_date="2026-01-07",
            initial_cash=INITIAL_CASH,
            mode=EngineMode.BACKTEST,
            strategy_id="test-etf-rotation",
            strategy_run_id="v0.1.0-simple",
            engine_version="0.1.0",
        )
        config_ashare = EngineConfig(
            start_date="2026-01-05",
            end_date="2026-01-07",
            initial_cash=INITIAL_CASH,
            mode=EngineMode.BACKTEST,
            strategy_id="test-etf-rotation",
            strategy_run_id="v0.1.0-ashare",
            engine_version="0.1.0",
        )

        loop_simple = _build_engine_loop(
            tmp_path,
            data,
            config_simple,
            etf_pipeline,
            SimpleFeeModel(),
            composite_pre_trade_check,
            instance_id=0,
        )
        result_simple = loop_simple.run()

        loop_ashare = _build_engine_loop(
            tmp_path,
            data,
            config_ashare,
            etf_pipeline,
            AShareFeeModel(),
            composite_pre_trade_check,
            instance_id=1,
            rules_getter=_ashare_rules_getter,
        )
        result_ashare = loop_ashare.run()

        diff = compute_run_diff(
            result_simple,
            result_ashare,
            label_a="v0.1.0-simple",
            label_b="v0.1.0-ashare",
        )

        # NAV 应该不同
        assert diff.nav_delta != 0.0, (
            f"NAV delta should be non-zero, got {diff.nav_delta}"
        )

        # 费用总额不同
        assert diff.total_fee_delta != 0.0, (
            f"Fee delta should be non-zero, got {diff.total_fee_delta}"
        )

        # 应至少有一个受影响标的
        assert len(diff.affected_instruments) > 0, (
            "Should have at least one affected instrument"
        )

        # 应至少有一个受影响日期
        assert len(diff.affected_dates) > 0, "Should have at least one affected date"


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
            input_refs=(1, 2),
            parameter_overrides=("top_k=3",),
            rule_refs=(
                RuleRef(
                    instrument_id=1,
                    definition_version="a1b2c3d4",
                    trading_rule_as_of="2026-01-01",
                    fee_schedule_as_of="2026-01-01",
                ),
                RuleRef(
                    instrument_id=2,
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
            instrument_id=2,
            definition_version="e5f6g7h8",
            trading_rule_as_of="2026-01-01",
            fee_schedule_as_of="2026-01-01",
        )
        rule_b = RuleRef(
            instrument_id=1,
            definition_version="a1b2c3d4",
            trading_rule_as_of="2026-01-01",
            fee_schedule_as_of="2026-01-01",
        )
        rule_c = RuleRef(
            instrument_id=3,
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
        assert ref_ids_v1 == [1, 2], "rule_refs should be sorted by instrument_id"

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
        assert ref_ids_v2 == [1, 2, 3]

        assert ref_ids_v1 != ref_ids_v2, "Added rule_ref should be detectable"
        assert ref_ids_v1 == ref_ids_v2[:2], "Existing refs should remain unchanged"

    def test_order_log_resize_check_chain(self) -> None:
        """pre_trade_decision.check_sequence 还原 resize 链路。"""
        collector = ExecutionAuditCollector()

        decision = PreTradeDecisionRecord(
            trade_date="2026-01-05",
            order_id="order-001",
            instrument_id=1,
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
        assert recorded.instrument_id == 1
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
