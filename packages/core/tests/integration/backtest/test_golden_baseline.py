"""Golden test baseline — 回测关键指标回归基线.

使用确定性回测数据验证引擎输出的一致性，作为后续 Phase 迁移的回归安全网。
任何破坏回测结果一致性的代码变更都会导致断言失败。

基线值通过 3 日 / 5 日固定 parquet 数据 + etf_rotation 策略建立。
如需更新基线，需确认行为变更的合理性后修改对应的期望值。

运行方式:
  pixi run -e dev pytest packages/core/tests/integration/ \\
    backtest/test_golden_baseline.py -v
"""

from __future__ import annotations

import pytest
from ditto_engine.accounting.account import Account
from ditto_engine.accounting.cash import CashBook
from ditto_engine.backtest.audit import ExecutionAuditCollector
from ditto_engine.backtest.engine import (
    EngineConfig,
    EngineLoop,
    EngineMode,
    EngineOptions,
)
from ditto_engine.backtest.statistics import build_report
from ditto_engine.execution.brokerage import BacktestBrokerage
from ditto_engine.execution.planner import SimpleExecutionPlanner
from ditto_engine.execution.reality import BrokerageModel

from .conftest import INITIAL_CASH, build_test_data_feed, write_parquet_data


def _build_engine_with_audit(
    data_dir,
    pipeline,
    pre_trade_check,
    fee_model,
    start_date: str,
    end_date: str,
) -> tuple[EngineLoop, ExecutionAuditCollector]:
    """组装带审计收集器的回测引擎。"""
    audit = ExecutionAuditCollector()
    data_feed = build_test_data_feed(data_dir, start_date, end_date)
    account = Account(
        cash=CashBook(
            available=INITIAL_CASH,
            settled=INITIAL_CASH,
            frozen=0.0,
        ),
    )
    config = EngineConfig(
        start_date=start_date,
        end_date=end_date,
        initial_cash=INITIAL_CASH,
        mode=EngineMode.BACKTEST,
        strategy_id="golden-baseline",
        strategy_run_id="golden-baseline",
    )
    engine = EngineLoop(
        config=config,
        pipeline=pipeline,
        planner=SimpleExecutionPlanner(),
        brokerage=BacktestBrokerage(
            account=account,
            model=BrokerageModel(fee_model=fee_model),
        ),
        pre_trade_check=pre_trade_check,
        data_feed=data_feed,
        options=EngineOptions(fee_model=fee_model, audit_collector=audit),
    )
    return engine, audit


class TestGoldenBaseline:
    """Golden test — 回测关键指标必须与基线一致。"""

    def test_3day_etf_rotation_baseline(
        self,
        tmp_path,
        three_day_data,
        etf_rotation_pipeline,
        pre_trade_check,
        fee_model,
    ) -> None:
        """3 日 ETF 轮动回测 — 验证关键指标与基线一致。"""
        data_dir = write_parquet_data(tmp_path, three_day_data)
        engine, audit = _build_engine_with_audit(
            data_dir,
            etf_rotation_pipeline,
            pre_trade_check,
            fee_model,
            start_date="2026-01-05",
            end_date="2026-01-07",
        )

        result = engine.run()
        report = build_report(audit, run_id=result.run_id)

        # EngineResult 层级指标
        assert result.final_nav == 999954.2841199999
        assert result.total_trades == 7

        # AlphaStatistics 层级指标
        assert report.alpha_stats.annualized_return == pytest.approx(3.249402928305334)
        assert report.alpha_stats.max_drawdown == pytest.approx(-8.0203602269124e-05)
        assert report.alpha_stats.sharpe_ratio == pytest.approx(11.333292780046666)

        # AggregatedTradeStatistics 层级指标
        assert report.aggregated_trade_stats.total_trades == 3
        assert report.aggregated_trade_stats.win_rate == 100.0

    def test_5day_etf_rotation_baseline(
        self,
        tmp_path,
        five_day_data,
        etf_rotation_pipeline,
        pre_trade_check,
        fee_model,
    ) -> None:
        """5 日 ETF 轮动回测 — 验证关键指标与基线一致。"""
        data_dir = write_parquet_data(tmp_path, five_day_data)
        engine, audit = _build_engine_with_audit(
            data_dir,
            etf_rotation_pipeline,
            pre_trade_check,
            fee_model,
            start_date="2026-01-05",
            end_date="2026-01-09",
        )

        result = engine.run()
        report = build_report(audit, run_id=result.run_id)

        # EngineResult 层级指标
        assert result.final_nav == pytest.approx(1001160.0580472726)
        assert result.total_trades == 13

        # AlphaStatistics 层级指标
        assert report.alpha_stats.annualized_return == pytest.approx(9.626625991102312)
        assert report.alpha_stats.max_drawdown == pytest.approx(-8.0203602269124e-05)
        assert report.alpha_stats.sharpe_ratio == pytest.approx(20.634343104906)

        # AggregatedTradeStatistics 层级指标
        assert report.aggregated_trade_stats.total_trades == 8
        assert report.aggregated_trade_stats.win_rate == 100.0
