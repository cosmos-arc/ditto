"""
TradeService — 交易信号/成交/持仓 CRUD 服务.

使用 SQLite 持久化交易闭环的本地数据记录（SignalRecord、
FillRecord、PositionRecord），
提供按条件查询、状态更新等操作。

注意：本服务仅操作 *Record 数据类，不依赖 app/engine 包。
"""

from __future__ import annotations

from ditto_execution.models import FillRecord, PositionRecord, SignalRecord
from ditto_execution.storage.deps import ExecutionReaders, ExecutionWriters

__all__ = [
    "TradeService",
]


class TradeService:
    """
    交易信号/成交/持仓 CRUD 服务.

    负责三类交易闭环记录的 SQLite 持久化：
    - SignalRecord: 交易信号
    - FillRecord: 成交记录
    - PositionRecord: 持仓快照
    """

    def __init__(
        self,
        readers: ExecutionReaders,
        writers: ExecutionWriters,
    ) -> None:
        self._readers = readers
        self._writers = writers

    # ------------------------------------------------------------------
    # Signal CRUD
    # ------------------------------------------------------------------

    def save_intent(self, record: SignalRecord) -> None:
        """保存交易信号记录."""
        self._writers.signal.save(record)

    def get_intent(self, intent_id: str) -> SignalRecord | None:
        """按 intent_id 查询单条交易信号."""
        return self._readers.signal.get(intent_id)

    def list_intents(
        self,
        strategy_id: str,
        signal_date: str | None = None,
        status: str | None = None,
    ) -> list[SignalRecord]:
        """按条件查询交易信号列表."""
        return self._readers.signal.list(
            strategy_id, signal_date=signal_date, status=status
        )

    def update_intent_status(
        self,
        intent_id: str,
        status: str,
        *,
        expected_current: tuple[str, ...],
    ) -> bool:
        """更新交易信号状态（expected_current 用于 TOCTOU 防护）。"""
        return self._writers.signal.update_status(
            intent_id, status, expected_current=expected_current
        )

    # ------------------------------------------------------------------
    # Fill CRUD
    # ------------------------------------------------------------------

    def save_fill(self, record: FillRecord) -> None:
        """保存成交记录."""
        self._writers.fill.save(record)

    def get_fill(self, fill_id: str) -> FillRecord | None:
        """按 fill_id 查询单条成交记录."""
        return self._readers.fill.get(fill_id)

    def find_fill(self, intent_id: str, trade_date: str) -> FillRecord | None:
        """按 intent_id + trade_date 查找成交记录（幂等去重用）。"""
        return self._readers.fill.find(intent_id, trade_date)

    def list_fills(
        self,
        strategy_id: str,
        trade_date: str | None = None,
        intent_id: str | None = None,
        end_date: str | None = None,
    ) -> list[FillRecord]:
        """按条件查询成交记录列表."""
        return self._readers.fill.list(
            strategy_id, trade_date=trade_date, intent_id=intent_id, end_date=end_date
        )

    # ------------------------------------------------------------------
    # Position CRUD
    # ------------------------------------------------------------------

    def save_position(self, record: PositionRecord) -> None:
        """保存持仓快照."""
        self._writers.position.save(record)

    def get_latest_position(
        self, strategy_id: str, instrument_id: int
    ) -> PositionRecord | None:
        """查询指定策略/标的的最新持仓快照."""
        return self._readers.position.get_latest(strategy_id, instrument_id)

    def list_positions(
        self,
        strategy_id: str,
        snapshot_date: str | None = None,
    ) -> list[PositionRecord]:
        """按条件查询持仓快照列表."""
        return self._readers.position.list(strategy_id, snapshot_date=snapshot_date)
