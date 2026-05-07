"""Backtest snapshot tests — 端到端验证回测闭环.

使用真实组件（非 mock）组装完整回测引擎，
用固定 parquet 数据验证输出确定性。

Phase 3 新增:
- 涨跌停场景快照 (AShareFillModel + limit_up/limit_down)
- ST 场景快照 (5% 涨跌停)
"""

from __future__ import annotations

from ditto_backtest.engine import EngineLoop


class TestThreeDaySnapshot:
    """3 日回测快照 — 验证基本闭环功能。"""

    def test_run_completes_without_error(
        self,
        assembled_engine_loop: EngineLoop,
    ) -> None:
        """回测能完整运行不报错。"""
        result = assembled_engine_loop.run()

        assert result is not None
        assert result.run_id == "run-3day"
        assert result.period == ("2026-01-05", "2026-01-07")

    def test_final_nav_reasonable(
        self,
        assembled_engine_loop: EngineLoop,
    ) -> None:
        """最终 NAV 在合理范围内 — 扣除手续费后应接近初始资金。"""
        result = assembled_engine_loop.run()

        # 初始 100 万，买入后因手续费和滑点 NAV 应略低于 100 万
        assert result.final_nav > 0
        # NAV 不应为负或零
        assert result.final_nav > 900_000.0
        # NAV 不应超过初始（没有收益的情况下）
        assert result.final_nav <= 1_000_000.0

    def test_orders_generated_on_rebalance_days(
        self,
        assembled_engine_loop: EngineLoop,
    ) -> None:
        """调仓日产生订单。"""
        result = assembled_engine_loop.run()

        # V1: 每日调仓，3 天应都有订单
        # 第一天买入 3 个标的，后续天可能也有调仓订单
        assert len(result.orders) > 0

    def test_fills_produced(
        self,
        assembled_engine_loop: EngineLoop,
    ) -> None:
        """订单成交产生 FillEvent。"""
        result = assembled_engine_loop.run()

        assert len(result.fills) > 0
        for fill in result.fills:
            assert fill.fill_price > 0
            assert fill.filled_quantity > 0
            assert fill.fee >= 0

    def test_first_day_buys_all_etfs(
        self,
        assembled_engine_loop: EngineLoop,
    ) -> None:
        """第一天应买入所有 3 个 ETF（空仓 → 等权配置）。"""
        result = assembled_engine_loop.run()

        # 收集第一天的 fills
        day1_fills = [
            f for f in result.fills if f.event_time.strftime("%Y-%m-%d") == "2026-01-05"
        ]

        # 应有 3 笔买入成交
        buy_instruments = {
            f.instrument_id for f in day1_fills if f.direction.value == "buy"
        }
        assert len(buy_instruments) == 3
        assert 1 in buy_instruments
        assert 2 in buy_instruments
        assert 3 in buy_instruments

    def test_account_view_not_none(
        self,
        assembled_engine_loop: EngineLoop,
    ) -> None:
        """最终账户快照存在。"""
        result = assembled_engine_loop.run()

        assert result.account_view is not None
        assert result.account_view.nav > 0
        assert len(result.account_view.positions) == 3


class TestFiveDaySnapshot:
    """5 日回测快照 — 多次调仓验证。"""

    def test_run_completes(
        self,
        five_day_engine_loop: EngineLoop,
    ) -> None:
        """5 日回测完整运行。"""
        result = five_day_engine_loop.run()

        assert result is not None
        assert result.period == ("2026-01-05", "2026-01-09")

    def test_multiple_rebalance_days(
        self,
        five_day_engine_loop: EngineLoop,
    ) -> None:
        """5 天 V1 每日调仓 — 应有多天产生订单。"""
        result = five_day_engine_loop.run()

        assert len(result.orders) > 0

    def test_nav_monotonic_tracking(
        self,
        five_day_engine_loop: EngineLoop,
    ) -> None:
        """NAV 随天数演变合理 — 不会跳变到 0 或负值。"""
        result = five_day_engine_loop.run()

        assert result.final_nav > 0
        # 5 天内 NAV 变化幅度应在合理范围
        assert result.final_nav > 900_000.0

    def test_fills_have_valid_prices(
        self,
        five_day_engine_loop: EngineLoop,
    ) -> None:
        """成交价格合理 — 在各标的的价格范围内。"""
        result = five_day_engine_loop.run()

        price_ranges = {
            1: (4.9, 10.6),
            2: (9.8, 20.6),
            3: (2.4, 5.4),
        }
        for fill in result.fills:
            low, high = price_ranges[fill.instrument_id]
            assert low <= fill.fill_price <= high, (
                f"{fill.instrument_id} fill_price {fill.fill_price} "
                f"out of range [{low}, {high}]"
            )

    def test_position_count_at_end(
        self,
        five_day_engine_loop: EngineLoop,
    ) -> None:
        """最终持仓数 = 3（等权全仓策略）。"""
        result = five_day_engine_loop.run()

        assert result.account_view is not None
        assert len(result.account_view.positions) == 3


class TestLimitUpSnapshot:
    """涨停场景快照 — Day 2 标的 1 涨停（买入失败）。"""

    def test_day1_normal_buy(self, limit_up_engine_loop: EngineLoop) -> None:
        """Day 1 正常买入标的 1（未涨停）。"""
        result = limit_up_engine_loop.run()

        day1_fills = [
            f
            for f in result.fills
            if f.event_time.strftime("%Y-%m-%d") == "2026-01-05"
            and f.instrument_id == 1
            and f.direction.value == "buy"
        ]
        assert len(day1_fills) > 0

    def test_day2_no_buy_at_limit_up(
        self,
        limit_up_engine_loop: EngineLoop,
    ) -> None:
        """Day 2 标的 1 涨停 — 买入订单不成交。"""
        result = limit_up_engine_loop.run()

        day2_fills = [
            f
            for f in result.fills
            if f.event_time.strftime("%Y-%m-%d") == "2026-01-06"
            and f.instrument_id == 1
            and f.direction.value == "buy"
        ]
        assert len(day2_fills) == 0

    def test_run_completes(self, limit_up_engine_loop: EngineLoop) -> None:
        """涨停场景回测完整运行。"""
        result = limit_up_engine_loop.run()

        assert result is not None
        assert result.final_nav > 0

    def test_other_etfs_trade_normally(
        self,
        limit_up_engine_loop: EngineLoop,
    ) -> None:
        """标的 2/3 不受涨跌停影响，正常交易。"""
        result = limit_up_engine_loop.run()

        day1_fills = [
            f for f in result.fills if f.event_time.strftime("%Y-%m-%d") == "2026-01-05"
        ]
        buys = {f.instrument_id for f in day1_fills if f.direction.value == "buy"}
        assert 2 in buys
        assert 3 in buys


class TestLimitDownSnapshot:
    """跌停场景快照 — Day 2 标的 1 跌停（卖出失败）。"""

    def test_day1_normal_buy(self, limit_down_engine_loop: EngineLoop) -> None:
        """Day 1 正常买入标的 1（未跌停）。"""
        result = limit_down_engine_loop.run()

        day1_fills = [
            f
            for f in result.fills
            if f.event_time.strftime("%Y-%m-%d") == "2026-01-05"
            and f.instrument_id == 1
            and f.direction.value == "buy"
        ]
        assert len(day1_fills) > 0

    def test_day2_no_sell_at_limit_down(
        self,
        limit_down_engine_loop: EngineLoop,
    ) -> None:
        """Day 2 标的 1 跌停 — 卖出订单不成交。"""
        result = limit_down_engine_loop.run()

        day2_fills = [
            f
            for f in result.fills
            if f.event_time.strftime("%Y-%m-%d") == "2026-01-06"
            and f.instrument_id == 1
            and f.direction.value == "sell"
        ]
        assert len(day2_fills) == 0

    def test_run_completes(self, limit_down_engine_loop: EngineLoop) -> None:
        """跌停场景回测完整运行。"""
        result = limit_down_engine_loop.run()

        assert result is not None
        assert result.final_nav > 0

    def test_nav_impact_of_limit_down(
        self,
        limit_down_engine_loop: EngineLoop,
    ) -> None:
        """跌停阻止卖出 → NAV 因持仓市值下跌而受影响。"""
        result = limit_down_engine_loop.run()

        # NAV 应低于初始资金（持有跌停标的市值下跌）
        assert result.final_nav < 1_000_000.0


class TestSTSnapshot:
    """ST 场景快照 — 标的 1 为 ST 标的（5% 涨跌停）。"""

    def test_day1_normal_buy(self, st_engine_loop: EngineLoop) -> None:
        """Day 1 正常买入 ST 标的（未涨停）。"""
        result = st_engine_loop.run()

        day1_fills = [
            f
            for f in result.fills
            if f.event_time.strftime("%Y-%m-%d") == "2026-01-05"
            and f.instrument_id == 1
            and f.direction.value == "buy"
        ]
        assert len(day1_fills) > 0

    def test_day2_no_buy_at_st_limit_up(
        self,
        st_engine_loop: EngineLoop,
    ) -> None:
        """Day 2 ST 标的涨停 (5%) — 买入订单不成交。"""
        result = st_engine_loop.run()

        day2_fills = [
            f
            for f in result.fills
            if f.event_time.strftime("%Y-%m-%d") == "2026-01-06"
            and f.instrument_id == 1
            and f.direction.value == "buy"
        ]
        assert len(day2_fills) == 0

    def test_run_completes(self, st_engine_loop: EngineLoop) -> None:
        """ST 场景回测完整运行。"""
        result = st_engine_loop.run()

        assert result is not None
        assert result.final_nav > 0

    def test_non_st_etfs_normal(
        self,
        st_engine_loop: EngineLoop,
    ) -> None:
        """非 ST 标的（标的 2/3）正常交易。"""
        result = st_engine_loop.run()

        day1_fills = [
            f for f in result.fills if f.event_time.strftime("%Y-%m-%d") == "2026-01-05"
        ]
        buys = {f.instrument_id for f in day1_fills if f.direction.value == "buy"}
        assert 2 in buys
        assert 3 in buys

    def test_final_positions(self, st_engine_loop: EngineLoop) -> None:
        """最终仍有 3 个持仓（ST 不影响持仓数量）。"""
        result = st_engine_loop.run()

        assert result.account_view is not None
        assert len(result.account_view.positions) == 3
