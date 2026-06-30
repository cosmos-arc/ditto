"""
TradeService — 交易信号/成交/持仓 CRUD 服务.

使用 SQLite 持久化交易闭环的本地数据记录（SignalRecord、
FillRecord、PositionRecord、AccountSnapshotRecord），
提供按条件查询、状态更新等操作。

注意：本服务仅操作 *Record 数据类，不依赖 app/engine 包。
"""

from __future__ import annotations

from ditto_execution.models import (
    AccountSnapshotRecord,
    BrokerEventRecord,
    FillRecord,
    PositionRecord,
    SignalRecord,
)
from ditto_execution.storage.deps import ExecutionReaders, ExecutionWriters

__all__ = [
    "TradeService",
]


class TradeService:
    """
    交易信号/成交/持仓 CRUD 服务.

    负责交易闭环记录的 SQLite 持久化：
    - SignalRecord: 交易信号
    - FillRecord: 成交记录
    - PositionRecord: 持仓快照
    - AccountSnapshotRecord: 账户快照
    - BrokerEventRecord: 标准化券商网关事件
    """

    def __init__(
        self,
        readers: ExecutionReaders,
        writers: ExecutionWriters,
    ) -> None:
        self._readers = readers
        self._writers = writers

    # ------------------------------------------------------------------
    # Intent CRUD
    # ------------------------------------------------------------------

    def save_intent(self, record: SignalRecord) -> None:
        """保存交易信号记录."""
        self._writers.intent.save(record)

    def get_intent(self, intent_id: str) -> SignalRecord | None:
        """按 intent_id 查询单条交易信号."""
        return self._readers.intent.get(intent_id)

    def list_intents(
        self,
        strategy_id: str,
        signal_date: str | None = None,
        status: str | None = None,
    ) -> list[SignalRecord]:
        """按条件查询交易信号列表."""
        return self._readers.intent.list(
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
        return self._writers.intent.update_status(
            intent_id, status, expected_current=expected_current
        )

    def get_order_status(self, order_id: str) -> str | None:
        """按 order_id 查询本地订单状态；当前由 intent status 承载。"""
        record = self.get_intent(order_id)
        if record is None:
            return None
        return record.status

    def update_order_status(
        self,
        order_id: str,
        status: str,
        *,
        expected_current: tuple[str, ...],
    ) -> bool:
        """更新本地订单状态；当前落到 intent status 并保留并发保护。"""
        return self.update_intent_status(
            order_id,
            status,
            expected_current=expected_current,
        )

    # ------------------------------------------------------------------
    # Fill CRUD
    # ------------------------------------------------------------------

    def save_fill(self, record: FillRecord) -> None:
        """保存成交记录."""
        self._writers.fill.save(record)

    def replace_fill(self, record: FillRecord) -> bool:
        """按 fill_id 替换已有成交记录；不存在时返回 False."""
        return self._writers.fill.replace(record)

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
        self,
        strategy_id: str,
        instrument_id: int,
        run_id: str | None = None,
    ) -> PositionRecord | None:
        """查询指定策略/标的的最新持仓快照."""
        return self._readers.position.get_latest(
            strategy_id, instrument_id, run_id=run_id
        )

    def list_positions(
        self,
        strategy_id: str,
        snapshot_date: str | None = None,
        run_id: str | None = None,
    ) -> list[PositionRecord]:
        """按条件查询持仓快照列表."""
        return self._readers.position.list(
            strategy_id, snapshot_date=snapshot_date, run_id=run_id
        )

    # ------------------------------------------------------------------
    # Account Snapshot CRUD
    # ------------------------------------------------------------------

    def save_account_snapshot(self, record: AccountSnapshotRecord) -> None:
        """保存账户快照."""
        self._writers.account.save(record)

    def get_latest_account_snapshot(
        self,
        run_id: str,
        account_id: str,
    ) -> AccountSnapshotRecord | None:
        """查询指定运行/账户的最新账户快照."""
        return self._readers.account.get_latest(run_id, account_id)

    def list_account_snapshots(
        self,
        run_id: str,
        *,
        strategy_id: str | None = None,
        account_id: str | None = None,
        snapshot_date: str | None = None,
    ) -> list[AccountSnapshotRecord]:
        """按条件查询账户快照列表."""
        return self._readers.account.list(
            run_id,
            strategy_id=strategy_id,
            account_id=account_id,
            snapshot_date=snapshot_date,
        )

    # ------------------------------------------------------------------
    # Broker Event CRUD
    # ------------------------------------------------------------------

    def save_broker_event(self, record: BrokerEventRecord) -> None:
        """保存标准化券商事件."""
        self._writers.broker_event.save(record)

    def get_broker_event(self, event_id: str) -> BrokerEventRecord | None:
        """按 event_id 查询单条券商事件."""
        return self._readers.broker_event.get(event_id)

    def list_broker_events(
        self,
        run_id: str,
        *,
        event_type: str | None = None,
        order_id: str | None = None,
        broker_order_id: str | None = None,
        fill_id: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[BrokerEventRecord]:
        """按运行、事件类型、关联键和日期查询标准化券商事件."""
        return self._readers.broker_event.list(
            run_id,
            event_type=event_type,
            order_id=order_id,
            broker_order_id=broker_order_id,
            fill_id=fill_id,
            start_date=start_date,
            end_date=end_date,
        )
