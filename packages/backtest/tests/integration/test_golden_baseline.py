"""Golden test baseline — 回测关键指标回归基线 (inline-snapshot).

使用确定性回测数据验证引擎输出的一致性，作为后续 Phase 迁移的回归安全网。
任何破坏回测结果一致性的代码变更都会导致断言失败。

快照值通过 inline-snapshot 自动管理，更新方式:
  pixi run -e dev pytest packages/backtest/tests/integration/ \\
    test_golden_baseline.py --snapshot-update -v

基线值通过 3 日 / 5 日固定 parquet 数据 + etf_rotation 策略建立。
"""

from __future__ import annotations

import importlib.util
from datetime import UTC, datetime
from pathlib import Path

import pytest
from ditto_backtest.audit import ExecutionAuditCollector
from ditto_backtest.brokerage import BacktestBrokerage
from ditto_backtest.engine import (
    EngineConfig,
    EngineLoop,
    EngineMode,
    EngineOptions,
)
from ditto_backtest.simulation import BrokerageModel
from ditto_backtest.statistics import build_report
from ditto_backtest.synchronizer import BacktestSynchronizer
from ditto_execution.orders.book import OrderBook
from ditto_execution.orders.journal import InMemoryOrderEventJournal
from ditto_execution.planner import SimpleExecutionPlanner
from ditto_kernel.clock import SimulatedClock
from ditto_portfolio.accounting import Account, CashBook
from inline_snapshot import snapshot

_conftest_path = Path(__file__).parent / "conftest.py"
_spec = importlib.util.spec_from_file_location("_conftest", _conftest_path)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]

INITIAL_CASH = _mod.INITIAL_CASH
build_test_data_feed = _mod.build_test_data_feed
write_parquet_data = _mod.write_parquet_data


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
        spec_hash="e" * 64,
        base_spec_hash="e" * 64,
        parameter_hash="4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945",
        effective_parameters=(),
        research_snapshot_id=None,
        research_snapshot_manifest_hash=None,
        mode=EngineMode.BACKTEST,
        strategy_id="golden-baseline",
        strategy_run_id="golden-baseline",
    )
    clock = SimulatedClock(
        initial=datetime(
            int(start_date[:4]),
            int(start_date[5:7]),
            int(start_date[8:10]),
            tzinfo=UTC,
        ),
    )
    synchronizer = BacktestSynchronizer(
        data_feed=data_feed,
        clock=clock,
        start_date=start_date,
    )
    engine = EngineLoop(
        config=config,
        pipeline=pipeline,
        planner=SimpleExecutionPlanner(),
        brokerage=BacktestBrokerage(
            account=account,
            order_book=OrderBook(journal=InMemoryOrderEventJournal()),
            model=BrokerageModel(fee_model=fee_model),
        ),
        pre_trade_check=pre_trade_check,
        data_feed=data_feed,
        synchronizer=synchronizer,
        options=EngineOptions(
            fee_model=fee_model,
            audit_collector=audit,
        ),
    )
    return engine, audit


@pytest.mark.snapshot
class TestGoldenBaseline:
    """Golden test — 回测关键指标通过 inline-snapshot 锁定。"""

    def test_3day_etf_rotation_baseline(
        self,
        tmp_path,
        three_day_data,
        etf_rotation_pipeline,
        pre_trade_check,
        fee_model,
    ) -> None:
        """3 日 ETF 轮动回测 — 验证关键指标与快照一致。"""
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

        assert result.final_nav == snapshot(998115.2271599998)
        assert result.total_trades == snapshot(9)
        assert report.alpha_stats.annualized_return == snapshot(-16.038197082756867)
        assert report.alpha_stats.max_drawdown == snapshot(-1.1256421793995597)
        assert report.alpha_stats.sharpe_ratio == snapshot(-0.6727290829013094)
        assert report.aggregated_trade_stats.total_trades == snapshot(4)
        assert report.aggregated_trade_stats.win_rate == snapshot(100.0)

    def test_5day_etf_rotation_baseline(
        self,
        tmp_path,
        five_day_data,
        etf_rotation_pipeline,
        pre_trade_check,
        fee_model,
    ) -> None:
        """5 日 ETF 轮动回测 — 验证关键指标与快照一致。"""
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

        assert result.final_nav == snapshot(1040603.2855399998)
        assert result.total_trades == snapshot(18)
        assert report.alpha_stats.annualized_return == snapshot(1166.5580727754098)
        assert report.alpha_stats.max_drawdown == snapshot(-1.1256421793995597)
        assert report.alpha_stats.sharpe_ratio == snapshot(40.67721350648211)
        assert report.aggregated_trade_stats.total_trades == snapshot(10)
        assert report.aggregated_trade_stats.win_rate == snapshot(100.0)

    def test_3day_etf_trend_swing_baseline(
        self,
        tmp_path,
        three_day_data,
        etf_trend_swing_pipeline,
        pre_trade_check,
        fee_model,
    ) -> None:
        """3 日 ETF 趋势追踪回测 — 验证关键指标与快照一致。"""
        data_dir = write_parquet_data(tmp_path, three_day_data)
        engine, audit = _build_engine_with_audit(
            data_dir,
            etf_trend_swing_pipeline,
            pre_trade_check,
            fee_model,
            start_date="2026-01-05",
            end_date="2026-01-07",
        )

        result = engine.run()
        report = build_report(audit, run_id=result.run_id)

        assert result.final_nav == snapshot(992355.3246009998)
        assert result.total_trades == snapshot(6)
        assert report.alpha_stats.annualized_return == snapshot(-59.50665387311345)
        assert report.alpha_stats.max_drawdown == snapshot(-1.682421395002831)
        assert report.alpha_stats.sharpe_ratio == snapshot(-1.9881165936696805)
        assert report.aggregated_trade_stats.total_trades == snapshot(3)
        assert report.aggregated_trade_stats.win_rate == snapshot(33.33333333333333)
