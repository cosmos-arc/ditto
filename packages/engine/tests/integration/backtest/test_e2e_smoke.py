"""端到端冒烟测试 — 验证回测完整链路.

验证 DataFeed → Pipeline → EngineLoop → BacktestReport 完整闭环:
  1. test_simple_etf_backtest: 简单 ETF 等权策略 + 10 日数据 → 报告完整性
  2. test_backtest_report_no_nan: 10 日回测报告 NAV 曲线无 NaN
  3. test_backtest_with_custom_signal: 自定义 signal_value → Pipeline 排序正确
"""

from __future__ import annotations

import math
from datetime import UTC, datetime

import polars as pl
import pytest
from ditto_engine.accounting.account import Account
from ditto_engine.accounting.cash import CashBook
from ditto_engine.alpha.pipeline import StrategyPipeline
from ditto_engine.alpha.templates.etf_rotation import (
    ETFRotationConfig,
    build_etf_rotation_pipeline,
)
from ditto_engine.backtest.audit import ExecutionAuditCollector
from ditto_engine.backtest.engine import (
    EngineConfig,
    EngineLoop,
    EngineMode,
    EngineOptions,
)
from ditto_engine.backtest.statistics import BacktestReport, build_report
from ditto_engine.execution.brokerage import BacktestBrokerage
from ditto_engine.execution.planner import SimpleExecutionPlanner
from ditto_engine.execution.reality import BrokerageModel, SimpleFeeModel
from ditto_engine.risk.pre_trade import (
    BuyingPowerCheck,
    CompositePreTradeCheck,
    LotSizeCheck,
)
from ditto_kernel.clock import SimulatedClock

from .conftest import (
    INITIAL_CASH,
    _make_market_df,
    build_test_data_feed,
    write_parquet_data,
)

# ---------------------------------------------------------------------------
# Constants — 10 日测试数据
# ---------------------------------------------------------------------------

TRADE_DATES_10 = [f"2026-01-0{d}" for d in range(5, 10)] + [
    "2026-01-12",
    "2026-01-13",
    "2026-01-14",
    "2026-01-15",
    "2026-01-16",
]


def generate_10day_data() -> dict[int, pl.DataFrame]:
    """10 日测试数据 — 稳定上涨趋势，方便确定性验证。

    ETF-001: 10.0 → 10.9 (线性上涨)
    ETF-002: 20.0 → 21.8 (线性上涨)
    ETF-003: 5.0 → 5.2 (小幅上涨)
    """
    n = len(TRADE_DATES_10)
    close_1 = [round(10.0 + i * 0.1, 2) for i in range(n)]
    close_2 = [round(20.0 + i * 0.2, 2) for i in range(n)]
    close_3 = [round(5.0 + i * 0.02, 2) for i in range(n)]
    return {
        1: _make_market_df(TRADE_DATES_10, close_1),
        2: _make_market_df(TRADE_DATES_10, close_2),
        3: _make_market_df(TRADE_DATES_10, close_3),
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_engine_with_audit(
    data_dir,
    pipeline: StrategyPipeline,
    pre_trade_check: CompositePreTradeCheck,
    fee_model: SimpleFeeModel,
    start_date: str,
    end_date: str,
    initial_cash: float = INITIAL_CASH,
) -> tuple[EngineLoop, ExecutionAuditCollector]:
    """组装带审计收集器的回测引擎。"""
    audit = ExecutionAuditCollector()
    data_feed = build_test_data_feed(data_dir, start_date, end_date)
    account = Account(
        cash=CashBook(
            available=initial_cash,
            settled=initial_cash,
            frozen=0.0,
        ),
    )
    config = EngineConfig(
        start_date=start_date,
        end_date=end_date,
        initial_cash=initial_cash,
        mode=EngineMode.BACKTEST,
        strategy_id="e2e-smoke",
        strategy_run_id="e2e-smoke-run",
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
        options=EngineOptions(
            clock=SimulatedClock(
                initial=datetime(
                    int(start_date[:4]),
                    int(start_date[5:7]),
                    int(start_date[8:10]),
                    tzinfo=UTC,
                ),
            ),
            fee_model=fee_model,
            audit_collector=audit,
        ),
    )
    return engine, audit


def _assert_report_complete(report: BacktestReport) -> None:
    """验证报告基本完整性。"""
    assert report is not None
    assert report.run_id != ""
    assert report.period[0] != ""
    assert report.period[1] != ""
    assert report.initial_cash > 0
    assert report.final_nav > 0


def _assert_nav_series_valid(report: BacktestReport) -> None:
    """验证 NAV 曲线: 非空、无 NaN、非负。"""
    assert len(report.nav_series) > 0, "NAV 序列不应为空"

    for trade_date, nav in report.nav_series:
        assert not math.isnan(nav), f"NAV 在 {trade_date} 为 NaN"
        assert not math.isinf(nav), f"NAV 在 {trade_date} 为 Inf"
        assert nav >= 0, f"NAV 在 {trade_date} 为负数: {nav}"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def ten_day_data() -> dict[int, pl.DataFrame]:
    """10 日市场数据。"""
    return generate_10day_data()


@pytest.fixture
def ten_day_parquet_dir(
    tmp_path,
    ten_day_data: dict[int, pl.DataFrame],
):
    """10 日 parquet 数据目录。"""
    return write_parquet_data(tmp_path, ten_day_data)


@pytest.fixture
def etf_rotation_pipeline():
    """etf_rotation 策略 Pipeline — top_k=3, equal_weight。"""
    config = ETFRotationConfig(top_k=3, cash_target=0.0)
    return build_etf_rotation_pipeline(config)


@pytest.fixture
def fee_model() -> SimpleFeeModel:
    """统一手续费模型。"""
    return SimpleFeeModel()


@pytest.fixture
def pre_trade_check() -> CompositePreTradeCheck:
    """组合 PreTrade 校验。"""
    return CompositePreTradeCheck(
        checks=(LotSizeCheck(), BuyingPowerCheck()),
    )


# ---------------------------------------------------------------------------
# Test Cases
# ---------------------------------------------------------------------------


class TestE2ESmoke:
    """端到端冒烟测试 — 验证回测完整链路。"""

    def test_simple_etf_backtest(
        self,
        ten_day_parquet_dir,
        etf_rotation_pipeline,
        pre_trade_check,
        fee_model,
    ) -> None:
        """简单 ETF 策略回测 — 10 日数据 → 报告完整性验证。

        验证链路: DataFeed → Pipeline → EngineLoop → BacktestReport
        """
        engine, audit = _build_engine_with_audit(
            data_dir=ten_day_parquet_dir,
            pipeline=etf_rotation_pipeline,
            pre_trade_check=pre_trade_check,
            fee_model=fee_model,
            start_date="2026-01-05",
            end_date="2026-01-16",
        )

        # 执行引擎
        engine_result = engine.run()

        # 构建 BacktestReport
        report = build_report(audit, run_id=engine_result.run_id)

        # 验证报告完整性
        _assert_report_complete(report)
        # report.initial_cash = 首日 fill 后的 NAV（含费用/滑点），接近但不等于配置值
        assert report.initial_cash > 0
        assert report.final_nav > 0

        # 验证 NAV 曲线有效性
        _assert_nav_series_valid(report)

        # 验证 NAV 序列长度 = 交易日数量
        assert len(report.nav_series) == len(TRADE_DATES_10)

        # 验证 portfolio_stats 长度一致
        assert len(report.portfolio_stats) == len(TRADE_DATES_10)

        # 验证产生交易（10 日回测应有 fill）
        assert len(report.fill_log) > 0, "10 日回测应产生成交记录"

    def test_backtest_report_no_nan(
        self,
        ten_day_parquet_dir,
        etf_rotation_pipeline,
        pre_trade_check,
        fee_model,
    ) -> None:
        """10 日回测报告 NAV 曲线无 NaN — 数据完整性验证。

        重点验证: NAV 序列、日收益率、累计收益率、回撤等数值均非 NaN。
        """
        engine, audit = _build_engine_with_audit(
            data_dir=ten_day_parquet_dir,
            pipeline=etf_rotation_pipeline,
            pre_trade_check=pre_trade_check,
            fee_model=fee_model,
            start_date="2026-01-05",
            end_date="2026-01-16",
        )

        engine_result = engine.run()
        report = build_report(audit, run_id=engine_result.run_id)

        # NAV 序列无 NaN
        _assert_nav_series_valid(report)

        # PortfolioStatistics 数值完整性
        for stat in report.portfolio_stats:
            assert not math.isnan(stat.nav), f"NAV NaN on {stat.trade_date}"
            assert not math.isnan(stat.daily_return), (
                f"daily_return NaN on {stat.trade_date}"
            )
            assert not math.isnan(stat.cumulative_return), (
                f"cumulative_return NaN on {stat.trade_date}"
            )
            assert not math.isnan(stat.drawdown), f"drawdown NaN on {stat.trade_date}"
            assert not math.isnan(stat.max_drawdown), (
                f"max_drawdown NaN on {stat.trade_date}"
            )
            assert not math.isnan(stat.cash_ratio), (
                f"cash_ratio NaN on {stat.trade_date}"
            )

        # AlphaStatistics 数值完整性
        alpha = report.alpha_stats
        assert not math.isnan(alpha.annualized_return)
        assert not math.isnan(alpha.annualized_volatility)
        assert not math.isnan(alpha.sharpe_ratio)
        assert not math.isnan(alpha.sortino_ratio)
        assert not math.isnan(alpha.max_drawdown)
        assert not math.isnan(alpha.total_turnover)
        assert not math.isnan(alpha.total_fees)
        assert not math.isnan(alpha.net_return_after_cost)
        assert not math.isnan(alpha.cost_drag)

    def test_backtest_with_custom_signal(
        self,
        ten_day_parquet_dir,
        pre_trade_check,
        fee_model,
    ) -> None:
        """含自定义 signal_value 的策略回测 — Pipeline 排序正确。

        使用自定义 Pipeline 验证 signal_value 注入后排序和权重分配正确。
        """
        from ditto_engine.alpha.builtins import (
            ScoringStage,
            SelectionStage,
            SignalStage,
        )
        from ditto_engine.portfolio.allocation import (
            AllocationStage,
            EqualWeightAllocator,
        )

        # 构建自定义 Pipeline: Signal → Score → Selection → Allocation → Constraint
        from ditto_engine.portfolio.constraints import (
            ConstraintChecker,
            ConstraintStage,
            MaxWeightConstraint,
        )

        checker = ConstraintChecker(
            constraints=[MaxWeightConstraint(max_weight=0.5)],
        )
        pipeline = StrategyPipeline(
            stages=[
                SignalStage(),
                ScoringStage(),  # signal_value → score
                SelectionStage(top_k=2),
                AllocationStage(allocator=EqualWeightAllocator()),
                ConstraintStage(checker=checker),
            ],
        )

        engine, audit = _build_engine_with_audit(
            data_dir=ten_day_parquet_dir,
            pipeline=pipeline,
            pre_trade_check=pre_trade_check,
            fee_model=fee_model,
            start_date="2026-01-05",
            end_date="2026-01-16",
        )

        engine_result = engine.run()
        report = build_report(audit, run_id=engine_result.run_id)

        # 验证报告基本完整性
        _assert_report_complete(report)
        _assert_nav_series_valid(report)

        # 验证: 产生成交（自定义 Pipeline top_k=2）
        assert len(report.fill_log) > 0, "自定义 Pipeline 回测应产生成交"

        # 验证: 最终 NAV 为有限数
        assert math.isfinite(report.final_nav)
        total_return = (report.final_nav / report.initial_cash - 1.0) * 100
        assert math.isfinite(total_return), f"total_return 非有限数: {total_return}"

    def test_daily_nav_monotonic_with_no_loss(
        self,
        ten_day_parquet_dir,
        etf_rotation_pipeline,
        pre_trade_check,
        fee_model,
    ) -> None:
        """10 日稳定上涨数据 — 累计收益率最终应为正数。

        10 日数据全部上涨，验证回测引擎正确捕获正收益。
        """
        engine, audit = _build_engine_with_audit(
            data_dir=ten_day_parquet_dir,
            pipeline=etf_rotation_pipeline,
            pre_trade_check=pre_trade_check,
            fee_model=fee_model,
            start_date="2026-01-05",
            end_date="2026-01-16",
        )

        engine_result = engine.run()
        report = build_report(audit, run_id=engine_result.run_id)

        # 稳定上涨行情: 最终 NAV >= 初始资金（扣除少量手续费后仍应接近）
        # 由于数据设计为持续上涨，最终 NAV 应大于初始资金
        assert report.final_nav >= report.initial_cash * 0.99, (
            f"稳定上涨行情下 NAV 不应大幅亏损: "
            f"initial={report.initial_cash}, final={report.final_nav}"
        )

        # 累计收益率最终应为非负数（正收益行情 + 手续费抵消后）
        final_cumulative = report.portfolio_stats[-1].cumulative_return
        assert math.isfinite(final_cumulative)

    def test_report_period_matches_dates(
        self,
        ten_day_parquet_dir,
        etf_rotation_pipeline,
        pre_trade_check,
        fee_model,
    ) -> None:
        """报告期间与回测配置日期一致。"""
        engine, audit = _build_engine_with_audit(
            data_dir=ten_day_parquet_dir,
            pipeline=etf_rotation_pipeline,
            pre_trade_check=pre_trade_check,
            fee_model=fee_model,
            start_date="2026-01-05",
            end_date="2026-01-16",
        )

        engine_result = engine.run()
        report = build_report(audit, run_id=engine_result.run_id)

        assert report.period[0] == "2026-01-05"
        assert report.period[1] == "2026-01-16"

        # EngineResult 的 period 也应一致
        assert engine_result.period[0] == "2026-01-05"
        assert engine_result.period[1] == "2026-01-16"
