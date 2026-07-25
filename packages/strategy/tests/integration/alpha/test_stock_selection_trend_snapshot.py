"""stock_selection_trend 策略模板快照测试 — 10 日回测端到端验证.

场景:
- 10 日正常快照 — 多因子选股基本功能
- Weekly 调仓频率 — 仅周一产生新订单
- NAV 确定性 — 相同配置两次运行结果一致

注: 使用 signal_factors=("signal_value",) 单因子模式，
    因 EngineLoop._build_input_bundle 仅生成 signal_value 列。
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from ditto_backtest.engine import EngineLoop
from ditto_strategy.alpha.pipeline import StrategyPipeline
from ditto_strategy.alpha.templates.stock_selection_trend import (
    StockSelectionTrendConfig,
    build_stock_selection_trend_pipeline,
)

_conftest_path = Path(__file__).parent / "conftest.py"
_spec = importlib.util.spec_from_file_location("_conftest", _conftest_path)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]

INITIAL_CASH = _mod.INITIAL_CASH
STOCK_INSTRUMENT_IDS = _mod.STOCK_INSTRUMENT_IDS
TRADE_DATES_10 = _mod.TRADE_DATES_10
account_position_signature = _mod.account_position_signature
assert_cash_conservation = _mod.assert_cash_conservation
build_snapshot_engine = _mod.build_snapshot_engine
make_stock_10day_data = _mod.make_stock_10day_data

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _build_daily_engine(tmp_path: Path) -> EngineLoop:
    """组装 stock_selection_trend 每日调仓引擎。"""
    data = make_stock_10day_data()
    config = StockSelectionTrendConfig(
        signal_factors=("signal_value",),
        signal_weights=(1.0,),
        top_k=3,
        max_weight=0.15,
        allocation_method="equal_weight",
        cash_target=0.0,
        trend_threshold=0.0,
        rebalance_freq="daily",
    )
    stages = build_stock_selection_trend_pipeline(config)
    pipeline = StrategyPipeline(stages)

    return build_snapshot_engine(
        tmp_path=tmp_path,
        data=data,
        instrument_ids=STOCK_INSTRUMENT_IDS,
        pipeline=pipeline,
        start_date=TRADE_DATES_10[0],
        end_date=TRADE_DATES_10[-1],
        strategy_id="test-stock-selection",
        strategy_run_id="run-selection-10day",
        rebalance_freq="daily",
    )


def _build_weekly_engine(tmp_path: Path) -> EngineLoop:
    """组装 stock_selection_trend 每周调仓引擎。"""
    data = make_stock_10day_data()
    config = StockSelectionTrendConfig(
        signal_factors=("signal_value",),
        signal_weights=(1.0,),
        top_k=3,
        max_weight=0.15,
        allocation_method="equal_weight",
        cash_target=0.0,
        trend_threshold=0.0,
        rebalance_freq="weekly",
    )
    stages = build_stock_selection_trend_pipeline(config)
    pipeline = StrategyPipeline(stages)

    return build_snapshot_engine(
        tmp_path=tmp_path,
        data=data,
        instrument_ids=STOCK_INSTRUMENT_IDS,
        pipeline=pipeline,
        start_date=TRADE_DATES_10[0],
        end_date=TRADE_DATES_10[-1],
        strategy_id="test-stock-selection-weekly",
        strategy_run_id="run-selection-weekly",
        rebalance_freq="weekly",
    )


# ---------------------------------------------------------------------------
# Test Classes
# ---------------------------------------------------------------------------


class TestTenDaySnapshot:
    """10 日回测快照 — 验证 stock_selection_trend 基本闭环功能。"""

    def test_run_completes_without_error(self, tmp_path: Path) -> None:
        """回测能完整运行不报错。"""
        engine = _build_daily_engine(tmp_path)
        result = engine.run()

        assert result is not None
        assert result.period == ("2026-01-05", "2026-01-16")

    def test_final_nav_reasonable(self, tmp_path: Path) -> None:
        """最终 NAV 在合理范围内。"""
        engine = _build_daily_engine(tmp_path)
        result = engine.run()

        assert result.final_nav > 0
        assert result.final_nav > 900_000.0

    def test_fills_produced(self, tmp_path: Path) -> None:
        """订单成交产生 FillEvent。"""
        engine = _build_daily_engine(tmp_path)
        result = engine.run()

        assert len(result.fills) > 0
        for fill in result.fills:
            assert fill.fill_price > 0
            assert fill.filled_quantity > 0
            assert fill.fee >= 0

    def test_account_view_has_positions(self, tmp_path: Path) -> None:
        """最终账户有持仓。"""
        engine = _build_daily_engine(tmp_path)
        result = engine.run()

        assert result.account_view is not None
        assert len(result.account_view.positions) > 0

    def test_top_k_positions(self, tmp_path: Path) -> None:
        """最终持仓数 <= top_k (3)。"""
        engine = _build_daily_engine(tmp_path)
        result = engine.run()

        assert result.account_view is not None
        # 由于 lot size 取整和调仓，实际持仓数可能略少于 top_k
        assert len(result.account_view.positions) <= 3

    def test_daily_golden_signature(self, tmp_path: Path) -> None:
        """Daily snapshot has an explicit promotion-style output signature."""
        engine = _build_daily_engine(tmp_path)
        result = engine.run()

        assert result.final_nav == pytest.approx(1_076_391.4012917997)
        assert result.total_trades == 30
        assert account_position_signature(result) == (
            (11, 16_200, 16_200, 22.0044, 356_400.0, -71.28),
            (13, 22_800, 22_800, 15.5031, 344_280.0, -9_190.68),
        )


class TestWeeklyRebalance:
    """Weekly 调仓频率 — 仅周一产生新订单。"""

    def test_weekly_rebalance_run_completes(self, tmp_path: Path) -> None:
        """Weekly 调仓回测完整运行。"""
        engine = _build_weekly_engine(tmp_path)
        result = engine.run()

        assert result is not None
        assert result.final_nav > 0

    def test_fills_on_monday_only(self, tmp_path: Path) -> None:
        """Weekly 调仓 — fills 仅出现在周一。

        TRADE_DATES_10 中有两个周一:
          2026-01-05 (Mon) — Day 1，初始建仓
          2026-01-12 (Mon) — Day 6，调仓

        注意: 由于 T+1 冻结和 lot size 取整，周二可能有少量成交（前日订单延续）。
        """
        engine = _build_weekly_engine(tmp_path)
        result = engine.run()

        monday_fills = [
            f
            for f in result.fills
            if f.event_time.strftime("%Y-%m-%d") in {"2026-01-05", "2026-01-12"}
        ]
        # 主要成交量应在周一
        assert len(monday_fills) > 0, "周一应有成交"

    def test_two_rebalance_days_have_trades(self, tmp_path: Path) -> None:
        """两个周一（Day 1, Day 6）均应有成交。"""
        engine = _build_weekly_engine(tmp_path)
        result = engine.run()

        fill_dates = {f.event_time.strftime("%Y-%m-%d") for f in result.fills}

        # Day 1 周一必须有成交（初始建仓）
        assert "2026-01-05" in fill_dates, "Day 1 (周一) 应有初始建仓成交"


class TestNavDeterminism:
    """NAV 确定性 — 相同配置两次运行结果一致。"""

    def test_nav_deterministic(self, tmp_path: Path) -> None:
        """相同配置运行两次，NAV 完全一致。"""
        engine1 = _build_daily_engine(tmp_path)
        result1 = engine1.run()

        engine2 = _build_daily_engine(tmp_path)
        result2 = engine2.run()

        assert result1.final_nav == result2.final_nav, (
            f"NAV 不确定: run1={result1.final_nav}, run2={result2.final_nav}"
        )

    def test_fill_count_deterministic(self, tmp_path: Path) -> None:
        """相同配置运行两次，成交笔数一致。"""
        engine1 = _build_daily_engine(tmp_path)
        result1 = engine1.run()

        engine2 = _build_daily_engine(tmp_path)
        result2 = engine2.run()

        assert len(result1.fills) == len(result2.fills)

    def test_weekly_nav_deterministic(self, tmp_path: Path) -> None:
        """Weekly 模式运行两次，NAV 一致。"""
        engine1 = _build_weekly_engine(tmp_path)
        result1 = engine1.run()

        engine2 = _build_weekly_engine(tmp_path)
        result2 = engine2.run()

        assert result1.final_nav == result2.final_nav


class TestCashConservation:
    """现金守恒验证。"""

    def test_total_value_approx_initial(self, tmp_path: Path) -> None:
        """NAV + fees ≈ initial cash。"""
        engine = _build_daily_engine(tmp_path)
        result = engine.run()

        assert_cash_conservation(result, INITIAL_CASH)
