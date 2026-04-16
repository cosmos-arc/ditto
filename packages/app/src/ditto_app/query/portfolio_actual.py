"""
PortfolioActualQueryFacade — 实际组合查询门面.

通过 TradeService 间接访问交易数据，提供持仓查询、
成交查询和 P&L 汇总计算。
"""

from __future__ import annotations

from dataclasses import dataclass

from ditto_data.services.trade import TradeService

from ditto_app.execution_dto import (
    ActualPositionSnapshot,
    ManualExecutionFill,
    record_to_fill,
    record_to_snapshot,
)

__all__ = ["PnlSummary", "PortfolioActualQueryFacade"]


@dataclass(frozen=True)
class PnlSummary:
    """
    P&L 汇总.

    Attributes:
        total_realized_pnl: 总已实现盈亏
        total_unrealized_pnl: 总未实现盈亏
        total_fees: 总手续费
        net_pnl: 净盈亏 = realized + unrealized - fees

    """

    total_realized_pnl: float
    total_unrealized_pnl: float
    total_fees: float
    net_pnl: float


class PortfolioActualQueryFacade:
    """
    实际组合查询门面.

    通过 TradeService 间接访问数据，不直接操作 SQLite。
    将 Record 映射为 App 层 DTO 后返回。
    """

    def __init__(self, trade_service: TradeService) -> None:
        self._trade_service = trade_service

    def get_latest_positions(
        self,
        strategy_id: str,
    ) -> list[ActualPositionSnapshot]:
        """
        获取策略的最新实际持仓.

        从 TradeService 获取全部持仓快照并映射为 DTO。

        Args:
            strategy_id: 策略 ID.

        Returns:
            ActualPositionSnapshot 列表.

        """
        records = self._trade_service.list_positions(strategy_id)
        return [record_to_snapshot(r) for r in records]

    def get_position_history(
        self,
        strategy_id: str,
        snapshot_date: str | None = None,
    ) -> list[ActualPositionSnapshot]:
        """
        获取持仓历史.

        Args:
            strategy_id: 策略 ID.
            snapshot_date: 快照日期过滤 (可选).

        Returns:
            ActualPositionSnapshot 列表.

        """
        records = self._trade_service.list_positions(
            strategy_id,
            snapshot_date=snapshot_date,
        )
        return [record_to_snapshot(r) for r in records]

    def get_fills(
        self,
        strategy_id: str,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[ManualExecutionFill]:
        """
        获取成交记录.

        Args:
            strategy_id: 策略 ID.
            start_date: 起始日期 (映射为 trade_date 过滤).
            end_date: 结束日期 (映射为 end_date 范围过滤).

        Returns:
            ManualExecutionFill 列表.

        """
        records = self._trade_service.list_fills(
            strategy_id,
            trade_date=start_date,
            end_date=end_date,
        )
        return [record_to_fill(r) for r in records]

    def compute_pnl(
        self,
        strategy_id: str,
        snapshot_date: str,
    ) -> PnlSummary:
        """
        计算指定日期的 P&L 汇总.

        从该日期的持仓快照聚合 realized_pnl、unrealized_pnl 和 total_fees。

        Args:
            strategy_id: 策略 ID.
            snapshot_date: 快照日期.

        Returns:
            PnlSummary 实例.

        """
        records = self._trade_service.list_positions(
            strategy_id,
            snapshot_date=snapshot_date,
        )
        snapshots = [record_to_snapshot(r) for r in records]

        if not snapshots:
            return PnlSummary(
                total_realized_pnl=0.0,
                total_unrealized_pnl=0.0,
                total_fees=0.0,
                net_pnl=0.0,
            )

        total_realized_pnl = sum(s.realized_pnl for s in snapshots)
        total_unrealized_pnl = sum(s.unrealized_pnl for s in snapshots)
        total_fees = sum(s.total_fees for s in snapshots)
        net_pnl = total_realized_pnl + total_unrealized_pnl - total_fees

        return PnlSummary(
            total_realized_pnl=total_realized_pnl,
            total_unrealized_pnl=total_unrealized_pnl,
            total_fees=total_fees,
            net_pnl=net_pnl,
        )
