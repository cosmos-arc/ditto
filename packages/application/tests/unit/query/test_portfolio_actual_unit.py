"""
PortfolioActualQueryFacade 单元测试 — 实际组合查询门面.

覆盖：get_latest_positions、get_position_history、get_fills、compute_pnl。
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from ditto_execution.models import (
    FillRecord,
    PositionRecord,
)

# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------


def _make_position_record(
    *,
    snapshot_id: str = "snap-1",
    strategy_id: str = "strat-1",
    snapshot_date: str = "2026-04-10",
    instrument_id: int = 1,
    quantity: int = 1000,
    available_quantity: int = 1000,
    average_cost: float = 1.5,
    market_value: float = 1500.0,
    unrealized_pnl: float = 100.0,
    realized_pnl: float = 50.0,
    total_fees: float = 5.0,
) -> PositionRecord:
    """构建 PositionRecord 测试 fixture."""
    return PositionRecord(
        snapshot_id=snapshot_id,
        strategy_id=strategy_id,
        snapshot_date=snapshot_date,
        instrument_id=instrument_id,
        quantity=quantity,
        available_quantity=available_quantity,
        average_cost=average_cost,
        market_value=market_value,
        unrealized_pnl=unrealized_pnl,
        realized_pnl=realized_pnl,
        total_fees=total_fees,
    )


def _make_fill_record(
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
    settlement_date: str = "2026-04-11",
) -> FillRecord:
    """构建 FillRecord 测试 fixture."""
    return FillRecord(
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
        settlement_date=settlement_date,
    )


# ---------------------------------------------------------------------------
# get_latest_positions 测试
# ---------------------------------------------------------------------------


class TestGetLatestPositions:
    """PortfolioActualQueryFacade.get_latest_positions — 最新持仓查询."""

    def test_delegates_to_trade_service(self) -> None:
        """委托到 TradeService.list_positions 并映射为 DTO."""
        from ditto_application.queries.portfolio_actual import (
            PortfolioActualQueryFacade,
        )

        mock_trade_service = MagicMock()
        record = _make_position_record(instrument_id=1)
        mock_trade_service.list_positions.return_value = [record]

        facade = PortfolioActualQueryFacade(trade_service=mock_trade_service)
        result = facade.get_latest_positions("strat-1")

        assert len(result) == 1
        assert result[0].instrument_id == 1
        assert result[0].strategy_id == "strat-1"
        mock_trade_service.list_positions.assert_called_once_with("strat-1")

    def test_empty_positions(self) -> None:
        """无持仓时返回空列表."""
        from ditto_application.queries.portfolio_actual import (
            PortfolioActualQueryFacade,
        )

        mock_trade_service = MagicMock()
        mock_trade_service.list_positions.return_value = []

        facade = PortfolioActualQueryFacade(trade_service=mock_trade_service)
        result = facade.get_latest_positions("strat-1")

        assert result == []

    def test_multiple_positions(self) -> None:
        """多个持仓全部映射."""
        from ditto_application.queries.portfolio_actual import (
            PortfolioActualQueryFacade,
        )

        mock_trade_service = MagicMock()
        records = [
            _make_position_record(instrument_id=1, quantity=1000),
            _make_position_record(instrument_id=2, quantity=500),
        ]
        mock_trade_service.list_positions.return_value = records

        facade = PortfolioActualQueryFacade(trade_service=mock_trade_service)
        result = facade.get_latest_positions("strat-1")

        assert len(result) == 2
        instruments = [r.instrument_id for r in result]
        assert instruments == [1, 2]


# ---------------------------------------------------------------------------
# get_position_history 测试
# ---------------------------------------------------------------------------


class TestGetPositionHistory:
    """PortfolioActualQueryFacade.get_position_history — 持仓历史查询."""

    def test_delegates_with_snapshot_date(self) -> None:
        """传递 snapshot_date 参数."""
        from ditto_application.queries.portfolio_actual import (
            PortfolioActualQueryFacade,
        )

        mock_trade_service = MagicMock()
        record = _make_position_record(snapshot_date="2026-04-09")
        mock_trade_service.list_positions.return_value = [record]

        facade = PortfolioActualQueryFacade(trade_service=mock_trade_service)
        result = facade.get_position_history("strat-1", snapshot_date="2026-04-09")

        assert len(result) == 1
        mock_trade_service.list_positions.assert_called_once_with(
            "strat-1",
            snapshot_date="2026-04-09",
        )

    def test_delegates_without_snapshot_date(self) -> None:
        """不传 snapshot_date 时默认 None."""
        from ditto_application.queries.portfolio_actual import (
            PortfolioActualQueryFacade,
        )

        mock_trade_service = MagicMock()
        mock_trade_service.list_positions.return_value = []

        facade = PortfolioActualQueryFacade(trade_service=mock_trade_service)
        facade.get_position_history("strat-1")

        mock_trade_service.list_positions.assert_called_once_with(
            "strat-1",
            snapshot_date=None,
        )


# ---------------------------------------------------------------------------
# get_fills 测试
# ---------------------------------------------------------------------------


class TestGetFills:
    """PortfolioActualQueryFacade.get_fills — 成交记录查询."""

    def test_delegates_to_trade_service(self) -> None:
        """委托到 TradeService.list_fills 并映射为 DTO."""
        from ditto_application.queries.portfolio_actual import (
            PortfolioActualQueryFacade,
        )

        mock_trade_service = MagicMock()
        record = _make_fill_record()
        mock_trade_service.list_fills.return_value = [record]

        facade = PortfolioActualQueryFacade(trade_service=mock_trade_service)
        result = facade.get_fills("strat-1")

        assert len(result) == 1
        assert result[0].fill_id == "fill-1"
        assert result[0].instrument_id == 1
        mock_trade_service.list_fills.assert_called_once_with(
            "strat-1",
            trade_date=None,
            end_date=None,
        )

    def test_fills_with_date_range(self) -> None:
        """传递日期范围参数."""
        from ditto_application.queries.portfolio_actual import (
            PortfolioActualQueryFacade,
        )

        mock_trade_service = MagicMock()
        mock_trade_service.list_fills.return_value = []

        facade = PortfolioActualQueryFacade(trade_service=mock_trade_service)
        facade.get_fills(
            "strat-1",
            start_date="2026-01-01",
            end_date="2026-03-31",
        )

        mock_trade_service.list_fills.assert_called_once_with(
            "strat-1",
            trade_date="2026-01-01",
            end_date="2026-03-31",
        )

    def test_fills_empty(self) -> None:
        """无成交时返回空列表."""
        from ditto_application.queries.portfolio_actual import (
            PortfolioActualQueryFacade,
        )

        mock_trade_service = MagicMock()
        mock_trade_service.list_fills.return_value = []

        facade = PortfolioActualQueryFacade(trade_service=mock_trade_service)
        result = facade.get_fills("strat-1")

        assert result == []


# ---------------------------------------------------------------------------
# compute_pnl 测试
# ---------------------------------------------------------------------------


class TestComputePnl:
    """PortfolioActualQueryFacade.compute_pnl — P&L 汇总计算."""

    def test_empty_positions_returns_zero(self) -> None:
        """无持仓时返回全零 PnlSummary."""
        from ditto_application.queries.portfolio_actual import (
            PnlSummary,
            PortfolioActualQueryFacade,
        )

        mock_trade_service = MagicMock()
        mock_trade_service.list_positions.return_value = []

        facade = PortfolioActualQueryFacade(trade_service=mock_trade_service)
        result = facade.compute_pnl("strat-1", "2026-04-10")

        assert result == PnlSummary(
            total_realized_pnl=0.0,
            total_unrealized_pnl=0.0,
            total_fees=0.0,
            net_pnl=0.0,
        )

    def test_single_position_pnl(self) -> None:
        """单标的 P&L: net = realized + unrealized - fees."""
        from ditto_application.queries.portfolio_actual import (
            PortfolioActualQueryFacade,
        )

        mock_trade_service = MagicMock()
        record = _make_position_record(
            realized_pnl=500.0,
            unrealized_pnl=200.0,
            total_fees=30.0,
        )
        mock_trade_service.list_positions.return_value = [record]

        facade = PortfolioActualQueryFacade(trade_service=mock_trade_service)
        result = facade.compute_pnl("strat-1", "2026-04-10")

        assert result.total_realized_pnl == pytest.approx(500.0)
        assert result.total_unrealized_pnl == pytest.approx(200.0)
        assert result.total_fees == pytest.approx(30.0)
        # net = 500 + 200 - 30 = 670
        assert result.net_pnl == pytest.approx(670.0)

    def test_multiple_positions_aggregation(self) -> None:
        """多标的 P&L 聚合."""
        from ditto_application.queries.portfolio_actual import (
            PortfolioActualQueryFacade,
        )

        mock_trade_service = MagicMock()
        records = [
            _make_position_record(
                instrument_id=1,
                realized_pnl=300.0,
                unrealized_pnl=100.0,
                total_fees=10.0,
            ),
            _make_position_record(
                instrument_id=2,
                realized_pnl=200.0,
                unrealized_pnl=-50.0,
                total_fees=15.0,
            ),
        ]
        mock_trade_service.list_positions.return_value = records

        facade = PortfolioActualQueryFacade(trade_service=mock_trade_service)
        result = facade.compute_pnl("strat-1", "2026-04-10")

        assert result.total_realized_pnl == pytest.approx(500.0)  # 300 + 200
        assert result.total_unrealized_pnl == pytest.approx(50.0)  # 100 + (-50)
        assert result.total_fees == pytest.approx(25.0)  # 10 + 15
        # net = 500 + 50 - 25 = 525
        assert result.net_pnl == pytest.approx(525.0)

    def test_negative_net_pnl(self) -> None:
        """净亏损场景."""
        from ditto_application.queries.portfolio_actual import (
            PortfolioActualQueryFacade,
        )

        mock_trade_service = MagicMock()
        record = _make_position_record(
            realized_pnl=-100.0,
            unrealized_pnl=-200.0,
            total_fees=50.0,
        )
        mock_trade_service.list_positions.return_value = [record]

        facade = PortfolioActualQueryFacade(trade_service=mock_trade_service)
        result = facade.compute_pnl("strat-1", "2026-04-10")

        # net = -100 + (-200) - 50 = -350
        assert result.net_pnl == pytest.approx(-350.0)

    def test_compute_pnl_passes_snapshot_date(self) -> None:
        """snapshot_date 正确传递给 TradeService."""
        from ditto_application.queries.portfolio_actual import (
            PortfolioActualQueryFacade,
        )

        mock_trade_service = MagicMock()
        mock_trade_service.list_positions.return_value = []

        facade = PortfolioActualQueryFacade(trade_service=mock_trade_service)
        facade.compute_pnl("strat-1", "2026-04-09")

        mock_trade_service.list_positions.assert_called_once_with(
            "strat-1",
            snapshot_date="2026-04-09",
        )


# ---------------------------------------------------------------------------
# PnlSummary 不可变性测试
# ---------------------------------------------------------------------------


class TestPnlSummaryFrozen:
    """PnlSummary — frozen dataclass 验证."""

    def test_frozen(self) -> None:
        from ditto_application.queries.portfolio_actual import PnlSummary

        summary = PnlSummary(
            total_realized_pnl=100.0,
            total_unrealized_pnl=50.0,
            total_fees=10.0,
            net_pnl=140.0,
        )

        with pytest.raises(AttributeError):
            summary.net_pnl = 999.0  # type: ignore[misc]
