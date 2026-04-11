"""
SignalQueryFacade — 信号查询门面.

通过 TradeService 查询已保存的交易意图（intents），
支持按策略、信号日期查询，以及获取最新信号日期的 intents。
"""

from __future__ import annotations

from ditto_data.services.trade_service import TradeService

from ditto_app.types import TradeIntent, record_to_intent

__all__ = ["SignalQueryFacade"]


class SignalQueryFacade:
    """
    信号查询门面.

    封装 TradeService 的意图查询操作，
    提供按最新信号日期和指定日期查询 intents 的能力。
    """

    def __init__(self, trade_service: TradeService) -> None:
        self._service = trade_service

    def get_latest_intents(self, strategy_id: str) -> list[TradeIntent]:
        """
        获取最新信号日期的交易意图.

        查询该策略所有 intents，按 signal_date 降序排列，
        返回最新日期的全部 intents。

        Args:
            strategy_id: 策略 ID.

        Returns:
            最新信号日期的 TradeIntent DTO 列表.

        """
        records = self._service.list_intents(
            strategy_id=strategy_id,
            signal_date=None,
            status=None,
        )
        if not records:
            return []

        latest_date = max(r.signal_date for r in records)
        return [record_to_intent(r) for r in records if r.signal_date == latest_date]

    def get_intents_by_date(
        self,
        strategy_id: str,
        signal_date: str,
    ) -> list[TradeIntent]:
        """
        获取指定信号日期的交易意图.

        Args:
            strategy_id: 策略 ID.
            signal_date: 信号日期 (YYYY-MM-DD).

        Returns:
            指定日期的 TradeIntent DTO 列表.

        """
        records = self._service.list_intents(
            strategy_id=strategy_id,
            signal_date=signal_date,
            status=None,
        )
        return [record_to_intent(r) for r in records]
