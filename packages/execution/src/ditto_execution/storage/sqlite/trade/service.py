"""
TradeService — 交易信号/成交/持仓 CRUD 服务.

使用 SQLite 持久化交易闭环的本地数据记录（SignalRecord、
FillRecord、PositionRecord、AccountSnapshotRecord），
提供按条件查询、状态更新等操作。

注意：本服务仅操作 *Record 数据类，不依赖 app/engine 包。
"""

from __future__ import annotations

import sqlite3
from collections.abc import Generator
from contextlib import contextmanager

from ditto_platform.foundation import SQLiteClient

from ditto_execution.audit.execution_audit_service import ExecutionAuditService
from ditto_execution.audit.models import AccountBaselineAuditPayload
from ditto_execution.errors import (
    FillConflictError,
    FillNotFoundError,
    FillProcessingError,
)
from ditto_execution.fills.validation import (
    validate_fill_adjustment_record,
    validate_fill_record,
)
from ditto_execution.models import (
    AccountSnapshotRecord,
    BrokerEventRecord,
    FillAdjustmentRecord,
    FillRecord,
    PositionRecord,
    SignalRecord,
)
from ditto_execution.storage.deps import ExecutionReaders, ExecutionWriters

__all__ = [
    "TradeService",
]


def _same_intent_payload(existing: SignalRecord, candidate: SignalRecord) -> bool:
    """Compare immutable intent facts, excluding lifecycle and generated time."""
    return (
        existing.intent_id == candidate.intent_id
        and existing.strategy_id == candidate.strategy_id
        and existing.signal_date == candidate.signal_date
        and existing.instrument_id == candidate.instrument_id
        and existing.direction == candidate.direction
        and existing.target_weight == candidate.target_weight
        and existing.current_weight == candidate.current_weight
        and existing.delta_weight == candidate.delta_weight
        and existing.quantity == candidate.quantity
    )


def _same_fill_payload(existing: FillRecord, candidate: FillRecord) -> bool:
    """Compare immutable fill facts while ignoring generated write time."""
    return (
        existing.fill_id == candidate.fill_id
        and existing.intent_id == candidate.intent_id
        and existing.strategy_id == candidate.strategy_id
        and existing.trade_date == candidate.trade_date
        and existing.instrument_id == candidate.instrument_id
        and existing.direction == candidate.direction
        and existing.quantity == candidate.quantity
        and existing.fill_price == candidate.fill_price
        and existing.fee == candidate.fee
        and existing.slippage == candidate.slippage
        and existing.notes == candidate.notes
        and existing.settlement_date == candidate.settlement_date
    )


def _same_adjustment_payload(
    existing: FillAdjustmentRecord,
    candidate: FillAdjustmentRecord,
) -> bool:
    """Compare request facts while ignoring the generated evidence timestamp."""
    return (
        existing.adjustment_id == candidate.adjustment_id
        and existing.fill_id == candidate.fill_id
        and existing.adjustment_type == candidate.adjustment_type
        and existing.replacement_fill_id == candidate.replacement_fill_id
        and existing.reason == candidate.reason
    )


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
        sqlite_client: SQLiteClient | None = None,
        audit_service: ExecutionAuditService | None = None,
    ) -> None:
        self._readers = readers
        self._writers = writers
        self._sqlite_client = sqlite_client
        self._audit_service = audit_service

    @contextmanager
    def ledger_transaction(self) -> Generator[None]:
        """Own one nested-safe SQLite transaction for a ledger/projection update."""
        if self._sqlite_client is None:
            msg = "Trade ledger transaction client is not configured"
            raise FillProcessingError(msg)
        connection = self._sqlite_client.conn
        owns_transaction = not connection.in_transaction
        if owns_transaction:
            connection.execute("BEGIN IMMEDIATE")
        try:
            yield
        except Exception:
            if owns_transaction:
                self._sqlite_client.rollback()
            raise
        else:
            if owns_transaction:
                self._sqlite_client.commit()

    # ------------------------------------------------------------------
    # Intent CRUD
    # ------------------------------------------------------------------

    def save_intent(self, record: SignalRecord) -> None:
        """按 stable intent ID 幂等保存；不同 payload 拒绝覆盖。"""
        existing = self._readers.intent.get(record.intent_id)
        if existing is not None:
            if _same_intent_payload(existing, record):
                return
            raise ValueError(f"Intent ID conflict: {record.intent_id}")
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
        with self.ledger_transaction():
            return self._writers.intent.update_status_uncommitted(
                intent_id,
                status,
                expected_current=expected_current,
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

    def save_fill(self, record: FillRecord) -> bool:
        """Persist by fill ID and report whether this call created the row."""
        try:
            with self.ledger_transaction():
                validate_fill_record(record)
                existing = self._readers.fill.get(record.fill_id)
                if existing is not None:
                    if _same_fill_payload(existing, record):
                        return False
                    msg = f"Fill ID conflict: {record.fill_id}"
                    raise FillConflictError(msg)
                self._writers.fill.save_strict_uncommitted(record)
                return True
        except sqlite3.IntegrityError as exc:
            msg = f"Fill ID conflict: {record.fill_id}"
            raise FillConflictError(msg) from exc

    def get_fill(self, fill_id: str) -> FillRecord | None:
        """按 fill_id 查询单条成交记录."""
        return self._readers.fill.get(fill_id)

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

    def list_effective_fills(
        self,
        strategy_id: str,
        trade_date: str | None = None,
        intent_id: str | None = None,
        end_date: str | None = None,
    ) -> list[FillRecord]:
        """List fills that remain effective after append-only corrections."""
        return self._readers.fill.list_effective(
            strategy_id,
            trade_date=trade_date,
            intent_id=intent_id,
            end_date=end_date,
        )

    def get_fill_adjustment(
        self,
        adjustment_id: str,
    ) -> FillAdjustmentRecord | None:
        """Return one append-only correction event by idempotency key."""
        return self._readers.fill_adjustment.get(adjustment_id)

    def list_fill_adjustments(
        self,
        strategy_id: str,
        *,
        fill_id: str | None = None,
        intent_id: str | None = None,
    ) -> list[FillAdjustmentRecord]:
        """List immutable correction evidence for a strategy ledger."""
        return self._readers.fill_adjustment.list(
            strategy_id,
            fill_id=fill_id,
            intent_id=intent_id,
        )

    def apply_fill_adjustment(
        self,
        record: FillAdjustmentRecord,
        *,
        replacement_fill: FillRecord | None = None,
    ) -> bool:
        """Atomically append an adjustment and report whether it was created."""
        self._validate_adjustment_request(record, replacement_fill)
        reader = self._readers.fill_adjustment
        writer = self._writers.fill_adjustment
        try:
            with self.ledger_transaction():
                if replacement_fill is not None:
                    validate_fill_record(replacement_fill)
                existing = reader.get(record.adjustment_id)
                if existing is not None:
                    if _same_adjustment_payload(existing, record):
                        self._validate_adjustment_replay(
                            existing,
                            replacement_fill=replacement_fill,
                        )
                        return False
                    msg = f"Fill adjustment ID conflict: {record.adjustment_id}"
                    raise FillConflictError(msg)

                existing_for_fill = reader.get_for_fill(record.fill_id)
                if existing_for_fill is not None:
                    msg = f"Fill already adjusted: {record.fill_id}"
                    raise FillConflictError(msg)

                source_fill = self._readers.fill.get(record.fill_id)
                if source_fill is None:
                    msg = f"Fill not found: {record.fill_id}"
                    raise FillNotFoundError(msg)

                if replacement_fill is not None:
                    self._validate_replacement_identity(source_fill, replacement_fill)
                    if self._readers.fill.get(replacement_fill.fill_id) is not None:
                        msg = (
                            "Replacement fill already exists: "
                            f"{replacement_fill.fill_id}"
                        )
                        raise FillConflictError(msg)
                    self._writers.fill.save_strict_uncommitted(replacement_fill)

                writer.save_uncommitted(record)
                return True
        except sqlite3.IntegrityError as exc:
            msg = f"Fill adjustment conflict: {record.adjustment_id}"
            raise FillConflictError(msg) from exc

    def _validate_adjustment_replay(
        self,
        existing: FillAdjustmentRecord,
        *,
        replacement_fill: FillRecord | None,
    ) -> None:
        """Exact replay also requires the persisted replacement facts to match."""
        if existing.adjustment_type == "void":
            return
        if replacement_fill is None or existing.replacement_fill_id is None:
            msg = f"Replacement fill payload conflict: {existing.replacement_fill_id}"
            raise FillConflictError(msg)
        persisted = self._readers.fill.get(existing.replacement_fill_id)
        if persisted is None or not _same_fill_payload(persisted, replacement_fill):
            msg = f"Replacement fill payload conflict: {existing.replacement_fill_id}"
            raise FillConflictError(msg)

    @staticmethod
    def _validate_adjustment_request(
        record: FillAdjustmentRecord,
        replacement_fill: FillRecord | None,
    ) -> None:
        validate_fill_adjustment_record(record)
        if record.adjustment_type == "void":
            TradeService._validate_void_adjustment_request(record, replacement_fill)
            return
        if record.adjustment_type == "replace":
            TradeService._validate_replace_adjustment_request(
                record,
                replacement_fill,
            )
            return
        msg = f"Unsupported fill adjustment type: {record.adjustment_type}"
        raise FillProcessingError(msg)

    @staticmethod
    def _validate_void_adjustment_request(
        record: FillAdjustmentRecord,
        replacement_fill: FillRecord | None,
    ) -> None:
        if record.replacement_fill_id is not None or replacement_fill is not None:
            raise FillProcessingError("Void adjustment cannot include replacement fill")

    @staticmethod
    def _validate_replace_adjustment_request(
        record: FillAdjustmentRecord,
        replacement_fill: FillRecord | None,
    ) -> None:
        if not record.replacement_fill_id:
            raise FillProcessingError("Replace adjustment requires replacement_fill_id")
        if replacement_fill is None:
            raise FillProcessingError("Replace adjustment requires replacement fill")
        if replacement_fill.fill_id != record.replacement_fill_id:
            raise FillProcessingError("Replacement fill ID does not match adjustment")
        if replacement_fill.fill_id == record.fill_id:
            raise FillProcessingError("Replacement fill must use a new fill_id")

    @staticmethod
    def _validate_replacement_identity(
        source: FillRecord,
        replacement: FillRecord,
    ) -> None:
        if (
            source.intent_id != replacement.intent_id
            or source.strategy_id != replacement.strategy_id
            or source.instrument_id != replacement.instrument_id
            or source.direction != replacement.direction
        ):
            msg = (
                "Replacement fill must preserve intent, strategy, instrument, "
                + "and direction"
            )
            raise FillProcessingError(msg)

    # ------------------------------------------------------------------
    # Position CRUD
    # ------------------------------------------------------------------

    def save_position(self, record: PositionRecord) -> None:
        """保存持仓快照."""
        self._writers.position.save(record)

    def replace_position_snapshot(
        self,
        *,
        strategy_id: str,
        snapshot_date: str,
        positions: tuple[PositionRecord, ...],
    ) -> None:
        """Atomically replace one derived manual-position snapshot as a group."""
        if self._sqlite_client is None:
            msg = "Trade ledger transaction client is not configured"
            raise FillProcessingError(msg)
        for position in positions:
            if (
                position.run_id != ""
                or position.strategy_id != strategy_id
                or position.snapshot_date != snapshot_date
            ):
                raise FillProcessingError(
                    "Manual position projection identity does not match replacement"
                )
        with self.ledger_transaction():
            delete_sql = (
                "DELETE FROM actual_positions "  # noqa: S608 - constant SQL
                + "WHERE run_id = '' AND strategy_id = ? AND snapshot_date = ?"
            )
            self._sqlite_client.execute(
                delete_sql,
                (strategy_id, snapshot_date),
            )
            for position in positions:
                self._writers.position.save_uncommitted(position)

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

    def save_account_baseline(
        self,
        *,
        account: AccountSnapshotRecord,
        positions: tuple[PositionRecord, ...],
        audit_payload: AccountBaselineAuditPayload | None = None,
    ) -> None:
        """Atomically persist one account baseline and its positions."""
        if self._sqlite_client is None:
            raise RuntimeError(
                "TradeService baseline transaction client is not configured"
            )
        try:
            self._sqlite_client.execute(
                """DELETE FROM actual_positions
                WHERE run_id = ? AND strategy_id = ? AND snapshot_date = ?""",
                (account.run_id, account.strategy_id, account.snapshot_date),
            )
            self._sqlite_client.execute(
                """DELETE FROM account_snapshots
                WHERE run_id = ? AND strategy_id = ? AND account_id = ?
                AND snapshot_date = ?""",
                (
                    account.run_id,
                    account.strategy_id,
                    account.account_id,
                    account.snapshot_date,
                ),
            )
            self._writers.account.save_uncommitted(account)
            for position in positions:
                self._writers.position.save_uncommitted(position)
            if audit_payload is not None:
                if self._audit_service is None:
                    raise RuntimeError(
                        "TradeService baseline audit service is not configured"
                    )
                self._audit_service.save_account_baseline_log(
                    account.run_id,
                    audit_payload,
                    commit=False,
                )
            self._sqlite_client.commit()
        except Exception:
            self._sqlite_client.rollback()
            raise

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
