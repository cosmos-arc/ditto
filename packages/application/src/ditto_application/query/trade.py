"""
TradeQueryFacade — 交易意图查询门面.

通过 TradeService 间接访问交易意图数据，
将 Record 映射为 App 层 DTO 后返回。
"""

from __future__ import annotations

from ditto_data.services.trade import TradeService

from ditto_application.execution_dto import TradeIntent, record_to_intent

__all__ = ["TradeQueryFacade"]


class TradeQueryFacade:
    """
    交易意图查询门面.

    封装 TradeService 的意图查询操作，对外暴露 DTO。
    """

    def __init__(self, trade_service: TradeService) -> None:
        self._service = trade_service

    def list_intents(
        self,
        strategy_id: str,
        signal_date: str | None = None,
        status: str | None = None,
    ) -> list[TradeIntent]:
        """
        列出交易意图.

        Args:
            strategy_id: 策略 ID.
            signal_date: 信号日期过滤 (可选).
            status: 状态过滤 (可选).

        Returns:
            TradeIntent DTO 列表.

        """
        records = self._service.list_intents(
            strategy_id=strategy_id,
            signal_date=signal_date,
            status=status,
        )
        return [record_to_intent(r) for r in records]

    def get_intent(self, intent_id: str) -> TradeIntent | None:
        """
        获取交易意图.

        Args:
            intent_id: 意图唯一标识.

        Returns:
            TradeIntent DTO 或 None.

        """
        record = self._service.get_intent(intent_id)
        return record_to_intent(record) if record else None
