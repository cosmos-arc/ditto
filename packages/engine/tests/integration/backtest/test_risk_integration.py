"""PostTrade 风控集成测试 — 端到端风控链路验证.

验证完整风控链路:
  PostTrade scan -> RiskLock -> Pipeline (RiskLockFilter) -> Planner block (S1)

覆盖两个核心场景:
  1. 风控触发 + 锁定 + Pipeline/Planner 联动
  2. 审计日志完整性 (risk_log + pre_trade_log + fills)
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import polars as pl
from ditto_engine.accounting.account import Account
from ditto_engine.accounting.cash import CashBook
from ditto_engine.alpha.templates.etf_rotation import (
    ETFRotationConfig,
    build_etf_rotation_pipeline,
)
from ditto_engine.backtest.engine import (
    EngineConfig,
    EngineLoop,
    EngineMode,
    EngineOptions,
)
from ditto_engine.backtest.statistics import (
    ExecutionAuditCollector,
)
from ditto_engine.execution.brokerage import BacktestBrokerage
from ditto_engine.execution.planner import SimpleExecutionPlanner
from ditto_engine.execution.reality import BrokerageModel, SimpleFeeModel
from ditto_engine.risk.post_trade import (
    CompositePostTradeGuard,
    ConcentrationLimitRule,
    MarketAnomalyRule,
    SingleLossLimitRule,
)
from ditto_engine.risk.pre_trade import (
    BuyingPowerCheck,
    CompositePreTradeCheck,
    LotSizeCheck,
)
from ditto_kernel.clock import SimulatedClock

from .conftest import (
    INITIAL_CASH,
    TRADE_DATES_3,
    TRADE_DATES_5,
    _make_market_df,
    build_test_data_feed,
    write_parquet_data,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_single_loss_data() -> dict[int, pl.DataFrame]:
    """构造触发 SingleLossLimitRule 的价格数据.

    Day 1: 标的 1 = 10.0 (买入价), 标的 2/3 正常
    Day 2: 标的 1 = 7.0 (亏损 30% > 15% 阈值), 触发 REDUCE_POSITION
    Day 3: 标的 1 = 6.5, 标的 2/3 正常

    SingleLossLimitRule 对单个标的生成 action (instrument_id != "*"),
    EngineLoop 会将标的 1 加入 risk_locked。
    """
    return {
        1: _make_market_df(
            TRADE_DATES_3,
            [10.0, 7.0, 6.5],
        ),
        2: _make_market_df(
            TRADE_DATES_3,
            [20.0, 20.5, 21.0],
        ),
        3: _make_market_df(
            TRADE_DATES_3,
            [5.0, 5.1, 5.2],
        ),
    }


def _make_concentration_data() -> dict[int, pl.DataFrame]:
    """构造触发 ConcentrationLimitRule 的价格数据 (5 日).

    使用 top_k=1:
      Day 1: 信号全为 0 (prev_close == close), 管道选标的 1
             大额买单可能被 buying_power reject
      Day 2: 标的 1 信号 > 0, 买单通过 -> 建仓标的 1 (~100%)
      Day 3: ConcentrationLimitRule(max_weight=0.20) 检测到标的 1 ~100%
             -> REDUCE_POSITION -> 标的 1 锁定
             -> RiskLockFilter 过滤标的 1 -> Pipeline 选其他标的
             -> Planner 不为标的 1 生成买单
    """
    return {
        1: _make_market_df(
            TRADE_DATES_5,
            [10.0, 10.5, 10.3, 10.1, 10.0],
        ),
        2: _make_market_df(
            TRADE_DATES_5,
            [20.0, 20.5, 21.0, 21.5, 22.0],
        ),
        3: _make_market_df(
            TRADE_DATES_5,
            [5.0, 5.1, 5.2, 5.3, 5.4],
        ),
    }


def _make_anomaly_data() -> dict[int, pl.DataFrame]:
    """构造触发 MarketAnomalyRule 的价格数据.

    Day 2: 标的 1 日涨跌幅 > 阈值 (close=12.0, prev_close=10.0, +20%)
    MarketAnomalyRule 使用 ALERT 类型, instrument_id != "*",
    但 EngineLoop 只对 REDUCE_POSITION/LIQUIDATE 加锁,
    所以 MarketAnomalyRule 不会触发锁定。

    此数据主要用于验证 audit_log 中有 risk_scan 记录。
    """
    return {
        1: _make_market_df(
            TRADE_DATES_3,
            [10.0, 12.0, 11.5],
        ),
        2: _make_market_df(
            TRADE_DATES_3,
            [20.0, 20.5, 21.0],
        ),
        3: _make_market_df(
            TRADE_DATES_3,
            [5.0, 5.1, 5.2],
        ),
    }


def _build_engine_with_risk_and_audit(
    tmp_path: Path,
    data: dict[int, pl.DataFrame],
    pipeline_config: ETFRotationConfig | None = None,
    post_trade_rules: tuple | None = None,
    start_date: str = "2026-01-05",
    end_date: str = "2026-01-07",
) -> tuple[EngineLoop, ExecutionAuditCollector]:
    """组装带 PostTrade 风控 + Audit 收集器的 EngineLoop.

    Returns:
        (EngineLoop, ExecutionAuditCollector) -- collector 引用独立保存,
        测试可通过 collector.get_risk_log() 等方法访问审计数据。
    """
    data_dir = write_parquet_data(tmp_path, data)

    data_feed = build_test_data_feed(
        parquet_dir=data_dir,
        start_date=start_date,
        end_date=end_date,
    )

    config = EngineConfig(
        start_date=start_date,
        end_date=end_date,
        initial_cash=INITIAL_CASH,
        mode=EngineMode.BACKTEST,
        strategy_id="test-risk-integration",
        strategy_run_id="run-risk",
    )

    pipeline_config = pipeline_config or ETFRotationConfig(top_k=3, cash_target=0.0)
    pipeline = build_etf_rotation_pipeline(pipeline_config)

    account = Account(
        cash=CashBook(
            available=INITIAL_CASH,
            settled=INITIAL_CASH,
            frozen=0.0,
        ),
    )

    brokerage = BacktestBrokerage(
        account=account,
        model=BrokerageModel(fee_model=SimpleFeeModel()),
    )

    pre_trade_check = CompositePreTradeCheck(
        checks=(LotSizeCheck(), BuyingPowerCheck()),
    )

    fee_model = SimpleFeeModel()

    audit_collector = ExecutionAuditCollector()

    # 构建 PostTrade 风控
    post_trade_guard: CompositePostTradeGuard | None = None
    if post_trade_rules:
        post_trade_guard = CompositePostTradeGuard(rules=post_trade_rules)

    planner = SimpleExecutionPlanner()

    engine = EngineLoop(
        config=config,
        pipeline=pipeline,
        planner=planner,
        brokerage=brokerage,
        pre_trade_check=pre_trade_check,
        data_feed=data_feed,
        options=EngineOptions(
            clock=SimulatedClock(initial=datetime(2026, 1, 5, tzinfo=UTC)),
            fee_model=fee_model,
            post_trade_guard=post_trade_guard,
            audit_collector=audit_collector,
        ),
    )

    return engine, audit_collector


# ---------------------------------------------------------------------------
# Task 3B.1: PostTrade 触发 + RiskLock 集成测试
# ---------------------------------------------------------------------------


class TestPostTradeRiskLockIntegration:
    """PostTrade 触发 + RiskLock -> Pipeline + Planner 集成。"""

    def test_single_loss_triggers_lock_and_prevents_buy(self, tmp_path: Path) -> None:
        """单标的亏损超限 -> REDUCE_POSITION -> 锁定 -> 不选入 -> Planner 不买单。

        场景:
          Day 1: 正常买入 3 个 ETF
          Day 2: ETF-001 亏损 30% > SingleLossLimitRule(0.15) 阈值
                -> ETF-001 被 lock_instrument
                -> RiskLockFilter 过滤 ETF-001
                -> Planner 不为 ETF-001 生成买单
                -> ETF-002/003 正常交易
        """
        data = _make_single_loss_data()
        post_trade_rules = (SingleLossLimitRule(threshold=0.15),)
        engine, audit_collector = _build_engine_with_risk_and_audit(
            tmp_path,
            data,
            post_trade_rules=post_trade_rules,
        )

        result = engine.run()

        # 验证回测完成
        assert result.total_trades > 0
        fills = result.fills

        # Day 1: 3 个 ETF 均买入
        day1_date = "2026-01-05"
        day1_fills = [
            f for f in fills if f.event_time.strftime("%Y-%m-%d") == day1_date
        ]
        day1_instruments = {f.instrument_id for f in day1_fills}
        assert 1 in day1_instruments

        # Day 2: 标的 1 不应有新的买入单
        day2_date = "2026-01-06"
        day2_fills = [
            f for f in fills if f.event_time.strftime("%Y-%m-%d") == day2_date
        ]
        day2_buy_fills = [
            f for f in day2_fills if f.direction.value == "buy" and f.instrument_id == 1
        ]
        assert len(day2_buy_fills) == 0, "标的 1 应被锁定, 不应在 Day 2 产生新的买单"

        # 审计日志: Day 2 应有 SingleLossLimitRule 的记录
        risk_log = audit_collector.get_risk_log()
        loss_records = [
            r
            for r in risk_log
            if r.rule_id == "single_loss_limit" and r.instrument_id == 1
        ]
        assert len(loss_records) > 0, "审计日志应包含标的 1 的 single_loss_limit 记录"
        assert loss_records[0].action_taken == "reduce_position"

    def test_concentration_limit_triggers_reduce(self, tmp_path: Path) -> None:
        """集中度超限 -> REDUCE_POSITION -> 标的锁定 -> Pipeline 过滤。

        场景: top_k=1, Day 1 信号全为 0, Day 2 建仓 ETF-001 (~100%),
        Day 3 ConcentrationLimitRule(max_weight=0.20) 触发,
        ETF-001 被锁定, Day 3 无 ETF-001 买单。
        """
        data = _make_concentration_data()
        post_trade_rules = (ConcentrationLimitRule(max_weight=0.20),)
        pipeline_config = ETFRotationConfig(top_k=1, cash_target=0.0)
        engine, audit_collector = _build_engine_with_risk_and_audit(
            tmp_path,
            data,
            pipeline_config=pipeline_config,
            post_trade_rules=post_trade_rules,
            start_date="2026-01-05",
            end_date="2026-01-09",
        )

        result = engine.run()

        # 审计日志: 应有 ConcentrationLimitRule 的记录
        risk_log = audit_collector.get_risk_log()
        conc_records = [r for r in risk_log if r.rule_id == "concentration_limit"]
        assert len(conc_records) > 0, "审计日志应包含 concentration_limit 记录"

        # ConcentrationLimitRule 触发后, 标的 1 被锁定
        # 后续不应有标的 1 的买单 (锁定后 Pipeline 过滤)
        fills = result.fills
        # 找到 concentration rule 触发的日期
        trigger_date = conc_records[0].trade_date
        post_lock_buys = [
            f
            for f in fills
            if f.event_time.strftime("%Y-%m-%d") >= trigger_date
            and f.direction.value == "buy"
            and f.instrument_id == 1
        ]
        assert len(post_lock_buys) == 0, (
            f"标的 1 在 {trigger_date} 被锁定后, 不应有新买单"
        )

    def test_market_anomaly_creates_audit_records(self, tmp_path: Path) -> None:
        """市场异常波动 -> MarketAnomalyRule 生成 risk_log 记录。

        注意: MarketAnomalyRule 使用 ALERT 类型 (非 REDUCE_POSITION/LIQUIDATE),
        EngineLoop 不会对 ALERT action 加锁,
        此测试验证的是审计日志的记录完整性。
        """
        data = _make_anomaly_data()
        post_trade_rules = (MarketAnomalyRule(threshold=0.05),)
        engine, audit_collector = _build_engine_with_risk_and_audit(
            tmp_path,
            data,
            post_trade_rules=post_trade_rules,
        )

        result = engine.run()

        # 审计日志: Day 2 应有 market_anomaly 记录 (标的 1 涨幅 20% > 5%)
        risk_log = audit_collector.get_risk_log()
        anomaly_records = [r for r in risk_log if r.rule_id == "market_anomaly"]
        assert len(anomaly_records) > 0, "审计日志应包含 market_anomaly 记录"

        # 应包含标的 1 的记录
        etf001_records = [r for r in anomaly_records if r.instrument_id == 1]
        assert len(etf001_records) > 0, "审计日志应包含标的 1 的 market_anomaly 记录"
        assert etf001_records[0].action_taken == "alert"
        assert etf001_records[0].severity == "warning"

        # 回测正常完成 (ALERT 不锁定标的)
        assert result.total_trades > 0


# ---------------------------------------------------------------------------
# Task 3B.2: 审计日志完整性测试
# ---------------------------------------------------------------------------


class TestAuditLogCompleteness:
    """审计日志完整性 -- risk_log + pre_trade_log + fill_log 一致性。"""

    def test_risk_scan_records_in_audit_log(self, tmp_path: Path) -> None:
        """每个 PostTrade risk action 有对应 risk_log 记录。"""
        data = _make_single_loss_data()
        post_trade_rules = (
            SingleLossLimitRule(threshold=0.15),
            ConcentrationLimitRule(max_weight=0.20),
        )
        engine, audit_collector = _build_engine_with_risk_and_audit(
            tmp_path,
            data,
            post_trade_rules=post_trade_rules,
        )

        engine.run()

        # 收集所有触发的风控规则
        risk_log = audit_collector.get_risk_log()
        triggered_rule_ids = {r.rule_id for r in risk_log}

        # 至少有一个规则被触发 (SingleLossLimitRule 在 Day 2 应触发)
        assert len(triggered_rule_ids) > 0

        # 每条 risk_log 的 trade_date 应在回测区间内
        backtest_dates = set(TRADE_DATES_3)
        for record in risk_log:
            assert record.trade_date in backtest_dates, (
                f"risk_log trade_date {record.trade_date} 不在回测区间内"
            )

        # risk_log 中的 severity 和 action_taken 应为有效值
        valid_severities = {"warning", "critical", "emergency"}
        valid_actions = {"reduce_position", "liquidate", "alert"}
        for record in risk_log:
            assert record.severity in valid_severities
            assert record.action_taken in valid_actions

    def test_pre_trade_decisions_recorded(self, tmp_path: Path) -> None:
        """每个通过 PreTrade 校验的订单有对应 pre_trade_decision 记录。"""
        data = _make_single_loss_data()
        post_trade_rules = (SingleLossLimitRule(threshold=0.15),)
        engine, audit_collector = _build_engine_with_risk_and_audit(
            tmp_path,
            data,
            post_trade_rules=post_trade_rules,
        )

        result = engine.run()

        fills = result.fills
        pre_trade_log = audit_collector.get_pre_trade_log()

        # accepted/resized 的决策数量应与 fills 数量一致
        # (每个 fill 对应一个通过的 pre_trade decision)
        accepted_decisions = [
            d for d in pre_trade_log if d.decision in ("accepted", "resized")
        ]
        assert len(accepted_decisions) == len(fills), (
            f"accepted/resized decisions ({len(accepted_decisions)}) "
            f"应等于 fills 数量 ({len(fills)})"
        )

        # 每个 accepted decision 应有 final_quantity > 0
        for d in accepted_decisions:
            assert d.final_quantity > 0, (
                f"decision={d.decision} 的 final_quantity 应 > 0, "
                f"实际: {d.final_quantity}"
            )

        # 每个 decision 的 trade_date 应在回测区间内
        backtest_dates = set(TRADE_DATES_3)
        for d in pre_trade_log:
            assert d.trade_date in backtest_dates

    def test_audit_log_consistency(self, tmp_path: Path) -> None:
        """risk_log + pre_trade_log 与 fills 时间线一致。"""
        data = _make_single_loss_data()
        post_trade_rules = (
            SingleLossLimitRule(threshold=0.15),
            ConcentrationLimitRule(max_weight=0.20),
        )
        engine, audit_collector = _build_engine_with_risk_and_audit(
            tmp_path,
            data,
            post_trade_rules=post_trade_rules,
        )

        result = engine.run()

        risk_log = audit_collector.get_risk_log()
        pre_trade_log = audit_collector.get_pre_trade_log()
        fills = result.fills

        backtest_dates = set(TRADE_DATES_3)

        # 1. 所有 risk_log 日期在回测区间内
        for r in risk_log:
            assert r.trade_date in backtest_dates

        # 2. 所有 pre_trade_log 日期在回测区间内
        for d in pre_trade_log:
            assert d.trade_date in backtest_dates

        # 3. accepted/resized 的 decision 有 final_quantity > 0
        for d in pre_trade_log:
            if d.decision in ("accepted", "resized"):
                assert d.final_quantity > 0, (
                    "accepted/resized decision 的 final_quantity 应 > 0"
                )

        # 4. rejected 的 decision 有 final_quantity == 0
        rejected = [d for d in pre_trade_log if d.decision == "rejected"]
        for d in rejected:
            assert d.final_quantity == 0, "rejected decision 的 final_quantity 应 == 0"

        # 5. 每个 fill 的 event_time 日期在回测区间内
        for fill in fills:
            fill_date = fill.event_time.strftime("%Y-%m-%d")
            assert fill_date in backtest_dates

        # 6. risk_log 中触发的日期不应晚于最后的 fill 日期
        if risk_log and fills:
            last_risk_date = max(r.trade_date for r in risk_log)
            last_fill_date = max(f.event_time.strftime("%Y-%m-%d") for f in fills)
            assert last_risk_date <= last_fill_date, (
                "risk_log 最后触发日期不应晚于最后 fill 日期"
            )
