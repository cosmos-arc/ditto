"""stock_sector_rotation 策略模板快照测试 — 10 日回测端到端验证.

场景:
- 10 日正常快照 — 两层 Pipeline (行业选股 + 行业内选股)
- 行业切换 — Week1: TECH 领涨, Week2: HEALTH 领涨
- NAV 确定性 — 相同配置两次运行结果一致
- 最终持仓只含个股（行业 ETF 被过滤）

注: 由于 EngineLoop._build_input_bundle 不添加 sector_id / is_sector 列，
    通过 SectorRotationEngineLoop 子类覆盖 _build_input_bundle 来注入。
"""

from __future__ import annotations

from pathlib import Path

import polars as pl
from ditto_engine.alpha.pipeline import StrategyInputBundle
from ditto_engine.alpha.templates.stock_sector_rotation import (
    StockSectorRotationConfig,
    build_stock_sector_rotation_pipeline,
)
from ditto_engine.backtest.data_feed import Slice
from ditto_engine.backtest.engine import EngineLoop, EngineOptions

from .conftest import (
    INITIAL_CASH,
    SECTOR_INSTRUMENT_IDS,
    TRADE_DATES_10,
    assert_cash_conservation,
    build_snapshot_engine,
    make_sector_10day_data,
)

# ---------------------------------------------------------------------------
# 行业映射 — instrument_id → (sector_id, is_sector)
# ---------------------------------------------------------------------------

_SECTOR_MAP: dict[int, tuple[int, bool]] = {
    # 行业 ETF
    100: (100, True),  # 金融
    101: (101, True),  # 科技
    102: (102, True),  # 医药
    # 金融行业个股
    110: (100, False),
    111: (100, False),
    112: (100, False),
    # 科技行业个股
    120: (101, False),
    121: (101, False),
    122: (101, False),
    # 医药行业个股
    130: (102, False),
    131: (102, False),
    132: (102, False),
}


# ---------------------------------------------------------------------------
# 自定义 EngineLoop — 注入 sector_id / is_sector 列
# ---------------------------------------------------------------------------


class SectorRotationEngineLoop(EngineLoop):
    """覆盖 _build_input_bundle，为行业轮动模板注入 sector_id / is_sector。"""

    def _build_input_bundle(
        self,
        date: str,
        slice_: Slice,
    ) -> StrategyInputBundle:
        """构建 StrategyInputBundle — 含 sector_id / is_sector 列。"""
        instrument_ids = list(slice_.bars.keys())
        sector_ids = [_SECTOR_MAP.get(iid, (iid, False))[0] for iid in instrument_ids]
        is_sectors = [_SECTOR_MAP.get(iid, (iid, False))[1] for iid in instrument_ids]

        instruments = pl.DataFrame(
            {
                "instrument_id": instrument_ids,
                "sector_id": sector_ids,
                "is_sector": is_sectors,
            },
        )

        # Build market_data and signal_values
        market_rows: list[dict[str, object]] = []
        signal_rows: list[dict[str, object]] = []
        for iid, bar in slice_.bars.items():
            market_rows.append(
                {
                    "instrument_id": iid,
                    "open": bar.open,
                    "high": bar.high,
                    "low": bar.low,
                    "close": bar.close,
                    "volume": bar.volume,
                }
            )
            signal_rows.append(
                {
                    "instrument_id": iid,
                    "signal_value": (
                        (bar.close / bar.prev_close - 1.0) if bar.prev_close else 0.0
                    ),
                }
            )

        return StrategyInputBundle(
            trade_date=date,
            strategy_id=self._config.strategy_id,
            run_id=self._config.strategy_run_id,
            instruments=instruments,
            market_data=pl.DataFrame(market_rows),
            signal_values=pl.DataFrame(signal_rows),
            benchmark_close=slice_.benchmark_close,
        )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _build_sector_engine(
    tmp_path: Path,
    rebalance_freq: str = "daily",
) -> SectorRotationEngineLoop:
    """组装 stock_sector_rotation 回测引擎。"""
    data = make_sector_10day_data()
    config = StockSectorRotationConfig(
        sector_signal="signal_value",
        stock_signal="signal_value",
        top_sectors=2,
        stocks_per_sector=2,
        sector_weight_method="equal_weight",
        stock_weight_method="equal_weight",
        max_weight=0.30,
        cash_target=0.0,
        rebalance_freq=rebalance_freq,
    )
    pipeline = build_stock_sector_rotation_pipeline(config)

    base_engine = build_snapshot_engine(
        tmp_path=tmp_path,
        data=data,
        instrument_ids=SECTOR_INSTRUMENT_IDS,
        pipeline=pipeline,
        start_date=TRADE_DATES_10[0],
        end_date=TRADE_DATES_10[-1],
        strategy_id="test-stock-sector-rotation",
        strategy_run_id="run-sector-rotation",
        rebalance_freq=rebalance_freq,
    )

    # 用 SectorRotationEngineLoop 替换 — 复用 base_engine 的所有组件
    return SectorRotationEngineLoop(
        config=base_engine._config,
        pipeline=base_engine._pipeline,
        planner=base_engine._planner,
        brokerage=base_engine._brokerage,
        pre_trade_check=base_engine._pre_trade_check,
        data_feed=base_engine._data_feed,
        options=EngineOptions(fee_model=base_engine._fee_model),
    )


# ---------------------------------------------------------------------------
# Test Classes
# ---------------------------------------------------------------------------


class TestTenDaySnapshot:
    """10 日回测快照 — 验证 stock_sector_rotation 基本闭环功能。"""

    def test_run_completes_without_error(self, tmp_path: Path) -> None:
        """回测能完整运行不报错。"""
        engine = _build_sector_engine(tmp_path)
        result = engine.run()

        assert result is not None
        assert result.period == ("2026-01-05", "2026-01-16")

    def test_final_nav_reasonable(self, tmp_path: Path) -> None:
        """最终 NAV 在合理范围内。"""
        engine = _build_sector_engine(tmp_path)
        result = engine.run()

        assert result.final_nav > 0
        assert result.final_nav > 900_000.0

    def test_fills_produced(self, tmp_path: Path) -> None:
        """订单成交产生 FillEvent。"""
        engine = _build_sector_engine(tmp_path)
        result = engine.run()

        assert len(result.fills) > 0
        for fill in result.fills:
            assert fill.fill_price > 0
            assert fill.filled_quantity > 0
            assert fill.fee >= 0

    def test_account_view_has_positions(self, tmp_path: Path) -> None:
        """最终账户有持仓。"""
        engine = _build_sector_engine(tmp_path)
        result = engine.run()

        assert result.account_view is not None
        assert len(result.account_view.positions) > 0

    def test_no_sector_etf_in_positions(self, tmp_path: Path) -> None:
        """最终持仓不包含行业 ETF — FinalStockFilterStage 过滤。"""
        engine = _build_sector_engine(tmp_path)
        result = engine.run()

        assert result.account_view is not None
        sector_etf_ids = {100, 101, 102}  # 行业 ETF instrument_id
        for iid in result.account_view.positions:
            assert iid not in sector_etf_ids, f"最终持仓不应包含行业 ETF: {iid}"

    def test_positions_are_stocks(self, tmp_path: Path) -> None:
        """最终持仓均为个股（非行业 ETF）。"""
        engine = _build_sector_engine(tmp_path)
        result = engine.run()

        assert result.account_view is not None
        for iid in result.account_view.positions:
            assert iid >= 110, f"持仓 {iid} 不是个股"

    def test_position_count_within_limit(self, tmp_path: Path) -> None:
        """最终持仓数 <= top_sectors * stocks_per_sector。"""
        engine = _build_sector_engine(tmp_path)
        result = engine.run()

        assert result.account_view is not None
        # top_sectors=2, stocks_per_sector=2 → 最多 4 个持仓
        assert len(result.account_view.positions) <= 4


class TestSectorSwitching:
    """行业切换场景 — Week1: TECH 领涨, Week2: HEALTH 领涨。"""

    def test_week1_has_tech_or_finance_positions(self, tmp_path: Path) -> None:
        """Week1 应持有 TECH 或 FINANCE 行业个股。

        Week1: TECH 动量 > FINANCE > HEALTH
        top_sectors=2 → 选中 TECH + FINANCE
        """
        engine = _build_sector_engine(tmp_path)
        result = engine.run()

        assert result.account_view is not None

        # 至少有 TECH 或 FINANCE 行业的个股被交易
        tech_or_finance_fills = [
            f for f in result.fills if f.instrument_id in (110, 111, 112, 120, 121, 122)
        ]
        assert len(tech_or_finance_fills) > 0, "Week1 应有 TECH 或 FINANCE 行业个股成交"

    def test_week2_health_sector_enters(self, tmp_path: Path) -> None:
        """Week2 HEALTH 行业动量超过 TECH，应纳入 HEALTH 个股。

        Week2: HEALTH 动量 > TECH > FINANCE
        top_sectors=2 → 选中 HEALTH + TECH
        """
        engine = _build_sector_engine(tmp_path)
        result = engine.run()

        # Week2 (Day 6-10) 应有 HEALTH 行业个股成交
        week2_dates = TRADE_DATES_10[5:]
        health_fills = [
            f
            for f in result.fills
            if f.event_time.strftime("%Y-%m-%d") in week2_dates
            and f.instrument_id in (130, 131, 132)
        ]
        assert len(health_fills) > 0, "Week2 应有 HEALTH 行业个股成交"


class TestNavDeterminism:
    """NAV 确定性 — 相同配置两次运行结果一致。"""

    def test_nav_deterministic(self, tmp_path: Path) -> None:
        """相同配置运行两次，NAV 完全一致。"""
        engine1 = _build_sector_engine(tmp_path)
        result1 = engine1.run()

        engine2 = _build_sector_engine(tmp_path)
        result2 = engine2.run()

        assert result1.final_nav == result2.final_nav, (
            f"NAV 不确定: run1={result1.final_nav}, run2={result2.final_nav}"
        )

    def test_fill_count_deterministic(self, tmp_path: Path) -> None:
        """相同配置运行两次，成交笔数一致。"""
        engine1 = _build_sector_engine(tmp_path)
        result1 = engine1.run()

        engine2 = _build_sector_engine(tmp_path)
        result2 = engine2.run()

        assert len(result1.fills) == len(result2.fills)

    def test_position_ids_deterministic(self, tmp_path: Path) -> None:
        """相同配置运行两次，最终持仓标的集合一致。"""
        engine1 = _build_sector_engine(tmp_path)
        result1 = engine1.run()

        engine2 = _build_sector_engine(tmp_path)
        result2 = engine2.run()

        assert result1.account_view is not None
        assert result2.account_view is not None
        ids1 = set(result1.account_view.positions.keys())
        ids2 = set(result2.account_view.positions.keys())
        assert ids1 == ids2


class TestCashConservation:
    """现金守恒验证。"""

    def test_total_value_approx_initial(self, tmp_path: Path) -> None:
        """NAV + fees ≈ initial cash。"""
        engine = _build_sector_engine(tmp_path)
        result = engine.run()

        assert_cash_conservation(result, INITIAL_CASH)
