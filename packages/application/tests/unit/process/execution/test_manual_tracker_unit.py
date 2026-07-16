"""ManualTracker 单元测试 — Fill 聚合 → 实际持仓/P&L (含 T+1 交收)."""

from __future__ import annotations

import pytest
from ditto_application.exceptions import AppProcessError
from ditto_application.execution_dto import ManualExecutionFill
from ditto_application.processes.execution.manual_tracker import ManualTracker

# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------


def _make_fill(
    *,
    fill_id: str = "fill-1",
    intent_id: str = "intent-1",
    strategy_id: str = "strat-1",
    trade_date: str = "2026-04-10",
    instrument_id: int = 1,
    direction: str = "buy",
    quantity: int = 1000,
    fill_price: float = 1.5,
    fee: float = 5.0,
    slippage: float = 0.0,
    notes: str = "",
) -> ManualExecutionFill:
    """构建 ManualExecutionFill 测试 fixture."""
    return ManualExecutionFill(
        fill_id=fill_id,
        intent_id=intent_id,
        strategy_id=strategy_id,
        trade_date=trade_date,
        instrument_id=instrument_id,
        direction=direction,
        quantity=quantity,
        fill_price=fill_price,
        fee=fee,
        slippage=slippage,
        notes=notes,
    )


# 标准交易日历（2026-04-06 ~ 2026-04-17，跳过周末）
_STANDARD_CALENDAR: tuple[str, ...] = (
    "2026-04-06",  # 周一
    "2026-04-07",  # 周二
    "2026-04-08",  # 周三
    "2026-04-09",  # 周四
    "2026-04-10",  # 周五
    "2026-04-13",  # 周一
    "2026-04-14",  # 周二
    "2026-04-15",  # 周三
    "2026-04-16",  # 周四
    "2026-04-17",  # 周五
)


# ---------------------------------------------------------------------------
# compute_settlement_date 测试
# ---------------------------------------------------------------------------


class TestComputeSettlementDate:
    """ManualTracker.compute_settlement_date — T+N 交收日期计算."""

    def test_t_plus_1_standard(self) -> None:
        """T+1 标准场景: 周四买入 → 周五交收."""

        tracker = ManualTracker(trading_calendar=_STANDARD_CALENDAR)
        result = tracker.compute_settlement_date("2026-04-09", cycle=1)
        assert result == "2026-04-10"

    def test_t_plus_1_cross_weekend(self) -> None:
        """T+1 跨周末: 周五买入 → 周一交收."""

        tracker = ManualTracker(trading_calendar=_STANDARD_CALENDAR)
        result = tracker.compute_settlement_date("2026-04-10", cycle=1)
        assert result == "2026-04-13"

    def test_t_plus_2(self) -> None:
        """T+2 场景: 周四买入 → 下周一交收."""

        tracker = ManualTracker(trading_calendar=_STANDARD_CALENDAR)
        result = tracker.compute_settlement_date("2026-04-09", cycle=2)
        assert result == "2026-04-13"

    def test_empty_calendar_returns_same_date(self) -> None:
        """空日历时返回原交易日期."""

        tracker = ManualTracker(trading_calendar=())
        result = tracker.compute_settlement_date("2026-04-10", cycle=1)
        assert result == "2026-04-10"


# ---------------------------------------------------------------------------
# compute_positions 测试
# ---------------------------------------------------------------------------


class TestComputePositionsEmpty:
    """ManualTracker.compute_positions — 空输入."""

    def test_empty_fills_returns_empty_list(self) -> None:
        """无 fill 记录时返回空列表."""

        tracker = ManualTracker(trading_calendar=_STANDARD_CALENDAR)
        result = tracker.compute_positions(
            fills=[],
            strategy_id="strat-1",
            snapshot_date="2026-04-11",
        )
        assert result == []


class TestComputePositionsSingleBuy:
    """ManualTracker.compute_positions — 单笔买入."""

    def test_single_buy_quantity_and_cost(self) -> None:
        """单笔买入: quantity=1000, avg_cost=1.5, total_fees=5.0."""

        tracker = ManualTracker(trading_calendar=_STANDARD_CALENDAR)
        fills = [
            _make_fill(
                fill_id="fill-1",
                trade_date="2026-04-10",
                instrument_id=1,
                direction="buy",
                quantity=1000,
                fill_price=1.5,
                fee=5.0,
            ),
        ]
        result = tracker.compute_positions(
            fills=fills,
            strategy_id="strat-1",
            snapshot_date="2026-04-10",
        )

        assert len(result) == 1
        pos = result[0]
        assert pos.instrument_id == 1
        assert pos.quantity == 1000
        assert pos.average_cost == pytest.approx(1.5)
        assert pos.total_fees == pytest.approx(5.0)
        assert pos.realized_pnl == pytest.approx(0.0)
        assert pos.unrealized_pnl == pytest.approx(0.0)
        assert pos.market_value == pytest.approx(0.0)
        assert pos.strategy_id == "strat-1"
        assert pos.snapshot_date == "2026-04-10"

    def test_single_buy_t_plus_1_available_quantity_zero(self) -> None:
        """买入当天 T+1 交收: available_quantity=0."""

        tracker = ManualTracker(trading_calendar=_STANDARD_CALENDAR)
        fills = [
            _make_fill(
                trade_date="2026-04-10",
                instrument_id=1,
                direction="buy",
                quantity=1000,
                fill_price=1.5,
                fee=5.0,
            ),
        ]
        result = tracker.compute_positions(
            fills=fills,
            strategy_id="strat-1",
            snapshot_date="2026-04-10",  # 同一天
        )

        assert result[0].available_quantity == 0

    def test_single_buy_next_day_available_quantity(self) -> None:
        """买入次日: available_quantity=1000 (T+1 交收完成)."""

        tracker = ManualTracker(trading_calendar=_STANDARD_CALENDAR)
        fills = [
            _make_fill(
                trade_date="2026-04-10",
                instrument_id=1,
                direction="buy",
                quantity=1000,
                fill_price=1.5,
                fee=5.0,
            ),
        ]
        result = tracker.compute_positions(
            fills=fills,
            strategy_id="strat-1",
            snapshot_date="2026-04-13",  # 下一个交易日
        )

        assert result[0].available_quantity == 1000


class TestComputePositionsBuyAndSell:
    """ManualTracker.compute_positions — 买入后卖出."""

    def test_buy_then_sell_reduces_quantity(self) -> None:
        """买入 1000 后卖出 500: quantity=500."""

        tracker = ManualTracker(trading_calendar=_STANDARD_CALENDAR)
        fills = [
            _make_fill(
                fill_id="fill-1",
                trade_date="2026-04-08",
                instrument_id=1,
                direction="buy",
                quantity=1000,
                fill_price=1.5,
                fee=5.0,
            ),
            _make_fill(
                fill_id="fill-2",
                trade_date="2026-04-09",
                instrument_id=1,
                direction="sell",
                quantity=500,
                fill_price=2.0,
                fee=3.0,
            ),
        ]
        result = tracker.compute_positions(
            fills=fills,
            strategy_id="strat-1",
            snapshot_date="2026-04-09",
        )

        assert len(result) == 1
        pos = result[0]
        assert pos.quantity == 500
        assert pos.average_cost == pytest.approx(1.5)
        assert pos.total_fees == pytest.approx(8.0)

    def test_buy_then_sell_realized_pnl(self) -> None:
        """卖出时计算已实现盈亏: (2.0 - 1.5) * 500 = 250.0."""

        tracker = ManualTracker(trading_calendar=_STANDARD_CALENDAR)
        fills = [
            _make_fill(
                fill_id="fill-1",
                trade_date="2026-04-08",
                instrument_id=1,
                direction="buy",
                quantity=1000,
                fill_price=1.5,
                fee=5.0,
            ),
            _make_fill(
                fill_id="fill-2",
                trade_date="2026-04-09",
                instrument_id=1,
                direction="sell",
                quantity=500,
                fill_price=2.0,
                fee=3.0,
            ),
        ]
        result = tracker.compute_positions(
            fills=fills,
            strategy_id="strat-1",
            snapshot_date="2026-04-09",
        )

        # realized_pnl = (sell_price - avg_cost) * sell_qty = (2.0 - 1.5) * 500 = 250.0
        assert result[0].realized_pnl == pytest.approx(250.0)

    def test_sell_more_than_held_raises_error(self) -> None:
        """卖出数量超过持仓时抛出 AppProcessError."""

        tracker = ManualTracker(trading_calendar=_STANDARD_CALENDAR)
        fills = [
            _make_fill(
                trade_date="2026-04-08",
                instrument_id=1,
                direction="buy",
                quantity=100,
                fill_price=1.5,
                fee=5.0,
            ),
            _make_fill(
                trade_date="2026-04-09",
                instrument_id=1,
                direction="sell",
                quantity=200,
                fill_price=2.0,
                fee=3.0,
            ),
        ]
        with pytest.raises(AppProcessError, match="oversold"):
            tracker.compute_positions(
                fills=fills,
                strategy_id="strat-1",
                snapshot_date="2026-04-09",
            )

    def test_fully_closed_position_retains_realized_pnl_and_fees(self) -> None:
        """全部平仓后保留零数量经济快照，供 P&L 汇总读取。"""

        tracker = ManualTracker(trading_calendar=_STANDARD_CALENDAR)
        fills = [
            _make_fill(
                fill_id="fill-1",
                trade_date="2026-04-08",
                instrument_id=1,
                direction="buy",
                quantity=1000,
                fill_price=1.5,
                fee=5.0,
            ),
            _make_fill(
                fill_id="fill-2",
                trade_date="2026-04-09",
                instrument_id=1,
                direction="sell",
                quantity=1000,
                fill_price=2.0,
                fee=3.0,
            ),
        ]
        result = tracker.compute_positions(
            fills=fills,
            strategy_id="strat-1",
            snapshot_date="2026-04-09",
        )

        assert len(result) == 1
        assert result[0].quantity == 0
        assert result[0].available_quantity == 0
        assert result[0].realized_pnl == pytest.approx(500.0)
        assert result[0].total_fees == pytest.approx(8.0)


class TestComputePositionsMultipleBuys:
    """ManualTracker.compute_positions — 多笔买入 (部分成交)."""

    def test_weighted_average_cost(self) -> None:
        """两笔买入: 加权平均成本 = (1.5*1000 + 2.0*500) / 1500 = 1.6667."""

        tracker = ManualTracker(trading_calendar=_STANDARD_CALENDAR)
        fills = [
            _make_fill(
                fill_id="fill-1",
                trade_date="2026-04-08",
                instrument_id=1,
                direction="buy",
                quantity=1000,
                fill_price=1.5,
                fee=5.0,
            ),
            _make_fill(
                fill_id="fill-2",
                trade_date="2026-04-09",
                instrument_id=1,
                direction="buy",
                quantity=500,
                fill_price=2.0,
                fee=3.0,
            ),
        ]
        result = tracker.compute_positions(
            fills=fills,
            strategy_id="strat-1",
            snapshot_date="2026-04-09",
        )

        pos = result[0]
        assert pos.quantity == 1500
        # avg_cost = (1.5 * 1000 + 2.0 * 500) / 1500 = 2500 / 1500 ≈ 1.6667
        assert pos.average_cost == pytest.approx(2500.0 / 1500.0, rel=1e-4)
        assert pos.total_fees == pytest.approx(8.0)

    def test_three_buys_weighted_average(self) -> None:
        """三笔买入的加权平均成本."""

        tracker = ManualTracker(trading_calendar=_STANDARD_CALENDAR)
        fills = [
            _make_fill(
                fill_id="fill-1",
                trade_date="2026-04-08",
                instrument_id=1,
                direction="buy",
                quantity=200,
                fill_price=10.0,
                fee=2.0,
            ),
            _make_fill(
                fill_id="fill-2",
                trade_date="2026-04-09",
                instrument_id=1,
                direction="buy",
                quantity=300,
                fill_price=12.0,
                fee=3.0,
            ),
            _make_fill(
                fill_id="fill-3",
                trade_date="2026-04-10",
                instrument_id=1,
                direction="buy",
                quantity=500,
                fill_price=11.0,
                fee=4.0,
            ),
        ]
        result = tracker.compute_positions(
            fills=fills,
            strategy_id="strat-1",
            snapshot_date="2026-04-10",
        )

        pos = result[0]
        assert pos.quantity == 1000
        # avg = (10*200 + 12*300 + 11*500) / 1000 = (2000+3600+5500)/1000 = 11.1
        assert pos.average_cost == pytest.approx(11.1, rel=1e-4)
        assert pos.total_fees == pytest.approx(9.0)


class TestComputePositionsTPlusOne:
    """ManualTracker.compute_positions — T+1 交收规则."""

    def test_buy_same_day_frozen(self) -> None:
        """买入当天 available=0（冻结）."""

        tracker = ManualTracker(trading_calendar=_STANDARD_CALENDAR)
        fills = [
            _make_fill(
                trade_date="2026-04-10",
                instrument_id=1,
                direction="buy",
                quantity=1000,
                fill_price=1.5,
                fee=5.0,
            ),
        ]
        result = tracker.compute_positions(
            fills=fills,
            strategy_id="strat-1",
            snapshot_date="2026-04-10",
        )
        assert result[0].available_quantity == 0

    def test_buy_previous_day_settled(self) -> None:
        """T-1 日买入, T 日已交收: available=quantity."""

        tracker = ManualTracker(trading_calendar=_STANDARD_CALENDAR)
        fills = [
            _make_fill(
                trade_date="2026-04-09",
                instrument_id=1,
                direction="buy",
                quantity=1000,
                fill_price=1.5,
                fee=5.0,
            ),
        ]
        result = tracker.compute_positions(
            fills=fills,
            strategy_id="strat-1",
            snapshot_date="2026-04-10",
        )
        assert result[0].available_quantity == 1000

    def test_mixed_buy_dates_partial_available(self) -> None:
        """T-1 买入 500 + T 日买入 500: available=500 (T-1 已交收, T 日冻结)."""

        tracker = ManualTracker(trading_calendar=_STANDARD_CALENDAR)
        fills = [
            _make_fill(
                fill_id="fill-1",
                trade_date="2026-04-09",
                instrument_id=1,
                direction="buy",
                quantity=500,
                fill_price=1.5,
                fee=2.0,
            ),
            _make_fill(
                fill_id="fill-2",
                trade_date="2026-04-10",
                instrument_id=1,
                direction="buy",
                quantity=500,
                fill_price=1.6,
                fee=2.0,
            ),
        ]
        result = tracker.compute_positions(
            fills=fills,
            strategy_id="strat-1",
            snapshot_date="2026-04-10",
        )

        pos = result[0]
        assert pos.quantity == 1000
        assert pos.available_quantity == 500  # T-1 买入的 500 已交收

    def test_sell_does_not_affect_available_for_remaining(self) -> None:
        """卖出后剩余持仓的 available 不受卖出影响."""

        tracker = ManualTracker(trading_calendar=_STANDARD_CALENDAR)
        fills = [
            _make_fill(
                fill_id="fill-1",
                trade_date="2026-04-08",
                instrument_id=1,
                direction="buy",
                quantity=1000,
                fill_price=1.5,
                fee=5.0,
            ),
            _make_fill(
                fill_id="fill-2",
                trade_date="2026-04-09",
                instrument_id=1,
                direction="sell",
                quantity=300,
                fill_price=2.0,
                fee=3.0,
            ),
        ]
        result = tracker.compute_positions(
            fills=fills,
            strategy_id="strat-1",
            snapshot_date="2026-04-10",
        )

        pos = result[0]
        assert pos.quantity == 700
        # 4/8 买入的 1000 在 4/9 已交收, 但 4/9 卖了 300
        # available = 已交收买入量 - 已交收卖出量 = 1000 - 300 = 700
        assert pos.available_quantity == 700

    def test_buy_cross_weekend_settlement(self) -> None:
        """周五买入, 下周一交收: 周五 available=0, 周一 available=qty."""

        tracker = ManualTracker(trading_calendar=_STANDARD_CALENDAR)
        fills = [
            _make_fill(
                trade_date="2026-04-10",  # 周五
                instrument_id=1,
                direction="buy",
                quantity=1000,
                fill_price=1.5,
                fee=5.0,
            ),
        ]

        # 周五快照: 买入当天, available=0
        result_fri = tracker.compute_positions(
            fills=fills,
            strategy_id="strat-1",
            snapshot_date="2026-04-10",
        )
        assert result_fri[0].available_quantity == 0

        # 下周一快照: T+1 交收完成 (跳过周末)
        result_mon = tracker.compute_positions(
            fills=fills,
            strategy_id="strat-1",
            snapshot_date="2026-04-13",
        )
        assert result_mon[0].available_quantity == 1000


class TestComputePositionsMultiInstrument:
    """ManualTracker.compute_positions — 多标的分组."""

    def test_two_instruments_independent(self) -> None:
        """两个标的各自独立计算持仓."""

        tracker = ManualTracker(trading_calendar=_STANDARD_CALENDAR)
        fills = [
            _make_fill(
                fill_id="fill-1",
                trade_date="2026-04-08",
                instrument_id=1,
                direction="buy",
                quantity=1000,
                fill_price=1.5,
                fee=5.0,
            ),
            _make_fill(
                fill_id="fill-2",
                trade_date="2026-04-08",
                instrument_id=2,
                direction="buy",
                quantity=500,
                fill_price=3.0,
                fee=4.0,
            ),
        ]
        result = tracker.compute_positions(
            fills=fills,
            strategy_id="strat-1",
            snapshot_date="2026-04-09",
        )

        assert len(result) == 2
        positions_by_inst = {p.instrument_id: p for p in result}

        pos1 = positions_by_inst[1]
        assert pos1.quantity == 1000
        assert pos1.average_cost == pytest.approx(1.5)
        assert pos1.total_fees == pytest.approx(5.0)

        pos2 = positions_by_inst[2]
        assert pos2.quantity == 500
        assert pos2.average_cost == pytest.approx(3.0)
        assert pos2.total_fees == pytest.approx(4.0)

    def test_fills_filtered_by_strategy_id(self) -> None:
        """只聚合指定 strategy_id 的 fills."""

        tracker = ManualTracker(trading_calendar=_STANDARD_CALENDAR)
        fills = [
            _make_fill(
                fill_id="fill-1",
                strategy_id="strat-1",
                trade_date="2026-04-08",
                instrument_id=1,
                direction="buy",
                quantity=1000,
                fill_price=1.5,
                fee=5.0,
            ),
            _make_fill(
                fill_id="fill-2",
                strategy_id="strat-2",  # 不同策略
                trade_date="2026-04-08",
                instrument_id=1,
                direction="buy",
                quantity=2000,
                fill_price=1.5,
                fee=8.0,
            ),
        ]
        result = tracker.compute_positions(
            fills=fills,
            strategy_id="strat-1",
            snapshot_date="2026-04-09",
        )

        assert len(result) == 1
        assert result[0].quantity == 1000  # 只计入 strat-1 的 fill


class TestComputePositionsUnrealizedPnl:
    """ManualTracker.compute_positions — 未实现盈亏."""

    def test_unrealized_pnl_with_market_price(self) -> None:
        """有 market_price 时计算 unrealized_pnl."""

        tracker = ManualTracker(trading_calendar=_STANDARD_CALENDAR)
        fills = [
            _make_fill(
                trade_date="2026-04-08",
                instrument_id=1,
                direction="buy",
                quantity=1000,
                fill_price=1.5,
                fee=5.0,
            ),
        ]
        result = tracker.compute_positions(
            fills=fills,
            strategy_id="strat-1",
            snapshot_date="2026-04-09",
            market_prices={1: 2.0},
        )

        pos = result[0]
        # unrealized_pnl = (market_price - avg_cost) * qty
        #                 = (2.0 - 1.5) * 1000 = 500.0
        assert pos.unrealized_pnl == pytest.approx(500.0)
        # market_value = market_price * quantity = 2.0 * 1000 = 2000.0
        assert pos.market_value == pytest.approx(2000.0)

    def test_unrealized_pnl_without_market_price(self) -> None:
        """无 market_price 时 unrealized_pnl=0, market_value=0."""

        tracker = ManualTracker(trading_calendar=_STANDARD_CALENDAR)
        fills = [
            _make_fill(
                trade_date="2026-04-08",
                instrument_id=1,
                direction="buy",
                quantity=1000,
                fill_price=1.5,
                fee=5.0,
            ),
        ]
        result = tracker.compute_positions(
            fills=fills,
            strategy_id="strat-1",
            snapshot_date="2026-04-09",
            market_prices=None,
        )

        pos = result[0]
        assert pos.unrealized_pnl == pytest.approx(0.0)
        assert pos.market_value == pytest.approx(0.0)

    def test_unrealized_pnl_partial_market_price(self) -> None:
        """market_prices 只包含部分标的."""

        tracker = ManualTracker(trading_calendar=_STANDARD_CALENDAR)
        fills = [
            _make_fill(
                fill_id="fill-1",
                trade_date="2026-04-08",
                instrument_id=1,
                direction="buy",
                quantity=1000,
                fill_price=1.5,
                fee=5.0,
            ),
            _make_fill(
                fill_id="fill-2",
                trade_date="2026-04-08",
                instrument_id=2,
                direction="buy",
                quantity=500,
                fill_price=3.0,
                fee=4.0,
            ),
        ]
        result = tracker.compute_positions(
            fills=fills,
            strategy_id="strat-1",
            snapshot_date="2026-04-09",
            market_prices={1: 2.0},  # 只有 instrument_id=1 的价格
        )

        positions_by_inst = {p.instrument_id: p for p in result}

        # instrument_id=1: 有市价
        pos1 = positions_by_inst[1]
        assert pos1.unrealized_pnl == pytest.approx(500.0)
        assert pos1.market_value == pytest.approx(2000.0)

        # instrument_id=2: 无市价
        pos2 = positions_by_inst[2]
        assert pos2.unrealized_pnl == pytest.approx(0.0)
        assert pos2.market_value == pytest.approx(0.0)

    def test_unrealized_pnl_negative(self) -> None:
        """市价低于成本时 unrealized_pnl 为负."""

        tracker = ManualTracker(trading_calendar=_STANDARD_CALENDAR)
        fills = [
            _make_fill(
                trade_date="2026-04-08",
                instrument_id=1,
                direction="buy",
                quantity=1000,
                fill_price=2.0,
                fee=5.0,
            ),
        ]
        result = tracker.compute_positions(
            fills=fills,
            strategy_id="strat-1",
            snapshot_date="2026-04-09",
            market_prices={1: 1.5},  # 低于成本
        )

        pos = result[0]
        # unrealized_pnl = (1.5 - 2.0) * 1000 = -500.0
        assert pos.unrealized_pnl == pytest.approx(-500.0)


class TestComputePositionsComplexScenario:
    """ManualTracker.compute_positions — 复合场景."""

    def test_full_trading_scenario(self) -> None:
        """完整交易场景: 多笔买卖 + T+1 + 市价."""

        tracker = ManualTracker(trading_calendar=_STANDARD_CALENDAR)
        fills = [
            # T-2: 买入 1000 @ 10.0
            _make_fill(
                fill_id="fill-1",
                trade_date="2026-04-08",
                instrument_id=1,
                direction="buy",
                quantity=1000,
                fill_price=10.0,
                fee=10.0,
            ),
            # T-1: 买入 500 @ 12.0
            _make_fill(
                fill_id="fill-2",
                trade_date="2026-04-09",
                instrument_id=1,
                direction="buy",
                quantity=500,
                fill_price=12.0,
                fee=6.0,
            ),
            # T: 卖出 800 @ 13.0
            _make_fill(
                fill_id="fill-3",
                trade_date="2026-04-10",
                instrument_id=1,
                direction="sell",
                quantity=800,
                fill_price=13.0,
                fee=8.0,
            ),
        ]
        result = tracker.compute_positions(
            fills=fills,
            strategy_id="strat-1",
            snapshot_date="2026-04-10",
            market_prices={1: 11.0},
        )

        assert len(result) == 1
        pos = result[0]

        # avg_cost = (10*1000 + 12*500) / 1500 = 16000/1500 ≈ 10.6667
        expected_avg = 16000.0 / 1500.0
        assert pos.average_cost == pytest.approx(expected_avg, rel=1e-4)
        assert pos.quantity == 700  # 1500 - 800

        # realized_pnl = (13.0 - 10.6667) * 800 ≈ 1866.67
        expected_realized = (13.0 - expected_avg) * 800
        assert pos.realized_pnl == pytest.approx(expected_realized, rel=1e-2)

        # unrealized_pnl = (11.0 - 10.6667) * 700 ≈ 233.33
        expected_unrealized = (11.0 - expected_avg) * 700
        assert pos.unrealized_pnl == pytest.approx(expected_unrealized, rel=1e-2)

        # market_value = 11.0 * 700 = 7700.0
        assert pos.market_value == pytest.approx(7700.0)

        # total_fees = 10 + 6 + 8 = 24.0
        assert pos.total_fees == pytest.approx(24.0)

        # T+1: 4/8 买入已交收, 4/9 买入已交收, 4/10 卖出冻结?
        # 买入交收: 4/8 买 1000 (4/9 交收), 4/9 买 500 (4/10 交收)
        # 卖出冻结: 4/10 卖 800 (T 日卖出, 已扣除)
        # available = 已交收买入量 - 已交收卖出量
        # 4/10 卖出 800 -> settlement = 4/13
        # snapshot_date = 4/10, 卖出的 settlement 还没到
        # 但卖出是直接扣减, available 应反映实际可卖数量
        # available = quantity(700) - 当天冻结的买入量
        # 4/10 没有新买入, 所以 available = 700 - 0 = 700? 不对
        # 重新考虑: available 是基于 T+1 规则, 买入的股票在交收后才可卖
        # 已交收买入量: 4/8 买 1000 (4/9 交收✓), 4/9 买 500 (4/10 交收✓)
        # 总买入已交收 = 1500
        # 已交收卖出量: 4/10 卖 800, settlement = 4/13, 未交收
        # 但卖出是直接扣减持仓, 不需要 T+1 等待
        # 所以 available = 已交收买入量 - 已交收卖出量 = 1500 - 0 = 1500?
        # 不对, available 应该 <= quantity (700)
        # available = min(quantity, 已交收买入量 - 卖出量)
        # 实际上 available 应该是: 当前持仓中已经完成 T+1 交收的部分
        # 简化模型: available = quantity - 当天买入未交收量
        # 4/10 没有买入, 所以 available = 700
        assert pos.available_quantity == 700

    def test_snapshot_id_is_deterministic(self) -> None:
        """相同输入生成一致的 snapshot_id (确定性 UUID)."""

        tracker = ManualTracker(trading_calendar=_STANDARD_CALENDAR)
        fills = [
            _make_fill(
                trade_date="2026-04-08",
                instrument_id=1,
                direction="buy",
                quantity=1000,
                fill_price=1.5,
                fee=5.0,
            ),
        ]
        result1 = tracker.compute_positions(
            fills=fills,
            strategy_id="strat-1",
            snapshot_date="2026-04-09",
        )
        result2 = tracker.compute_positions(
            fills=fills,
            strategy_id="strat-1",
            snapshot_date="2026-04-09",
        )

        assert result1[0].snapshot_id == result2[0].snapshot_id


class TestComputePositionsPITCutoff:
    """ManualTracker.compute_positions — PIT 截断 (未来 fills 不计入)."""

    def test_future_fills_excluded_from_snapshot(self) -> None:
        """snapshot_date 之后的 fills 被截断, 不影响历史快照."""

        tracker = ManualTracker(trading_calendar=_STANDARD_CALENDAR)
        fills = [
            # 4/8 买入 1000
            _make_fill(
                fill_id="fill-1",
                trade_date="2026-04-08",
                instrument_id=1,
                direction="buy",
                quantity=1000,
                fill_price=1.5,
                fee=5.0,
            ),
            # 4/10 卖出 500 (未来成交)
            _make_fill(
                fill_id="fill-2",
                trade_date="2026-04-10",
                instrument_id=1,
                direction="sell",
                quantity=500,
                fill_price=2.0,
                fee=3.0,
            ),
        ]
        # 以 4/8 为快照日期 → 只有 fill-1 计入
        result = tracker.compute_positions(
            fills=fills,
            strategy_id="strat-1",
            snapshot_date="2026-04-08",
        )

        assert len(result) == 1
        pos = result[0]
        assert pos.quantity == 1000
        assert pos.realized_pnl == pytest.approx(0.0)
        assert pos.total_fees == pytest.approx(5.0)

    def test_future_fills_excluded_same_instrument_multiple_days(self) -> None:
        """多日 fills 场景: snapshot_date 正好截断中间某日."""

        tracker = ManualTracker(trading_calendar=_STANDARD_CALENDAR)
        fills = [
            _make_fill(
                fill_id="fill-1",
                trade_date="2026-04-08",
                instrument_id=1,
                direction="buy",
                quantity=1000,
                fill_price=1.5,
                fee=5.0,
            ),
            _make_fill(
                fill_id="fill-2",
                trade_date="2026-04-09",
                instrument_id=1,
                direction="buy",
                quantity=500,
                fill_price=2.0,
                fee=3.0,
            ),
            _make_fill(
                fill_id="fill-3",
                trade_date="2026-04-10",
                instrument_id=1,
                direction="sell",
                quantity=200,
                fill_price=2.5,
                fee=2.0,
            ),
        ]
        # 以 4/9 为快照日期 → fill-1 + fill-2 计入, fill-3 被截断
        result = tracker.compute_positions(
            fills=fills,
            strategy_id="strat-1",
            snapshot_date="2026-04-09",
        )

        assert len(result) == 1
        pos = result[0]
        assert pos.quantity == 1500
        assert pos.realized_pnl == pytest.approx(0.0)
        assert pos.total_fees == pytest.approx(8.0)

    def test_all_fills_future_returns_empty(self) -> None:
        """所有 fills 都在 snapshot_date 之后 → 返回空列表."""

        tracker = ManualTracker(trading_calendar=_STANDARD_CALENDAR)
        fills = [
            _make_fill(
                fill_id="fill-1",
                trade_date="2026-04-10",
                instrument_id=1,
                direction="buy",
                quantity=1000,
                fill_price=1.5,
                fee=5.0,
            ),
        ]
        result = tracker.compute_positions(
            fills=fills,
            strategy_id="strat-1",
            snapshot_date="2026-04-08",
        )

        assert result == []


class TestComputePositionsPITEdgeCases:
    """ManualTracker.compute_positions — PIT 截断边界场景."""

    def test_snapshot_date_equals_trade_date_included(self) -> None:
        """snapshot_date == trade_date 的 fill 被计入（<= 截断）."""

        tracker = ManualTracker(trading_calendar=_STANDARD_CALENDAR)
        fills = [
            _make_fill(
                fill_id="fill-1",
                trade_date="2026-04-10",
                instrument_id=1,
                direction="buy",
                quantity=1000,
                fill_price=1.5,
                fee=5.0,
            ),
            _make_fill(
                fill_id="fill-2",
                trade_date="2026-04-11",
                instrument_id=1,
                direction="buy",
                quantity=500,
                fill_price=1.6,
                fee=3.0,
            ),
        ]
        # snapshot_date = fill-1 的日期 → fill-1 计入, fill-2 被截断
        result = tracker.compute_positions(
            fills=fills,
            strategy_id="strat-1",
            snapshot_date="2026-04-10",
        )

        assert len(result) == 1
        pos = result[0]
        assert pos.quantity == 1000
        assert pos.total_fees == pytest.approx(5.0)

    def test_future_sell_not_reflected_in_earlier_snapshot(self) -> None:
        """未来卖出不影响更早快照的持仓量和已实现盈亏."""

        tracker = ManualTracker(trading_calendar=_STANDARD_CALENDAR)
        fills = [
            # 买入 1000 @ 1.5
            _make_fill(
                fill_id="fill-1",
                trade_date="2026-04-08",
                instrument_id=1,
                direction="buy",
                quantity=1000,
                fill_price=1.5,
                fee=5.0,
            ),
            # 4/10 卖出 500 @ 2.0 (未来)
            _make_fill(
                fill_id="fill-2",
                trade_date="2026-04-10",
                instrument_id=1,
                direction="sell",
                quantity=500,
                fill_price=2.0,
                fee=3.0,
            ),
        ]
        # 以 4/9 快照 → 卖出被截断, 持仓=1000, 已实现盈亏=0
        result = tracker.compute_positions(
            fills=fills,
            strategy_id="strat-1",
            snapshot_date="2026-04-09",
        )

        assert len(result) == 1
        pos = result[0]
        assert pos.quantity == 1000
        assert pos.realized_pnl == pytest.approx(0.0)

    def test_future_buy_not_reflected_in_earlier_snapshot(self) -> None:
        """未来买入不影响更早快照的持仓量."""

        tracker = ManualTracker(trading_calendar=_STANDARD_CALENDAR)
        fills = [
            # 买入 500 @ 1.5
            _make_fill(
                fill_id="fill-1",
                trade_date="2026-04-08",
                instrument_id=1,
                direction="buy",
                quantity=500,
                fill_price=1.5,
                fee=5.0,
            ),
            # 4/10 买入 500 @ 2.0 (未来)
            _make_fill(
                fill_id="fill-2",
                trade_date="2026-04-10",
                instrument_id=1,
                direction="buy",
                quantity=500,
                fill_price=2.0,
                fee=3.0,
            ),
        ]
        # 以 4/9 快照 → 第二笔买入被截断, 持仓=500
        result = tracker.compute_positions(
            fills=fills,
            strategy_id="strat-1",
            snapshot_date="2026-04-09",
        )

        assert len(result) == 1
        pos = result[0]
        assert pos.quantity == 500
        assert pos.average_cost == pytest.approx(1.5)
        assert pos.total_fees == pytest.approx(5.0)

    def test_pit_truncation_across_strategies(self) -> None:
        """PIT 截断不受其他策略影响：不同策略的未来 fills 不参与."""

        tracker = ManualTracker(trading_calendar=_STANDARD_CALENDAR)
        fills = [
            _make_fill(
                fill_id="fill-1",
                strategy_id="strat-1",
                trade_date="2026-04-08",
                instrument_id=1,
                direction="buy",
                quantity=1000,
                fill_price=1.5,
                fee=5.0,
            ),
            # 同策略未来 fill
            _make_fill(
                fill_id="fill-2",
                strategy_id="strat-1",
                trade_date="2026-04-10",
                instrument_id=1,
                direction="sell",
                quantity=500,
                fill_price=2.0,
                fee=3.0,
            ),
            # 不同策略的同期 fill (不影响 strat-1)
            _make_fill(
                fill_id="fill-3",
                strategy_id="strat-2",
                trade_date="2026-04-09",
                instrument_id=1,
                direction="buy",
                quantity=300,
                fill_price=1.8,
                fee=2.0,
            ),
        ]
        # strat-1 以 4/9 快照
        result = tracker.compute_positions(
            fills=fills,
            strategy_id="strat-1",
            snapshot_date="2026-04-09",
        )

        assert len(result) == 1
        pos = result[0]
        assert pos.quantity == 1000
        assert pos.strategy_id == "strat-1"
        assert pos.realized_pnl == pytest.approx(0.0)

    def test_pit_with_empty_fills_returns_empty(self) -> None:
        """空 fills 列表在任何 snapshot_date 都返回空."""

        tracker = ManualTracker(trading_calendar=_STANDARD_CALENDAR)
        result = tracker.compute_positions(
            fills=[],
            strategy_id="strat-1",
            snapshot_date="2026-04-10",
        )

        assert result == []
