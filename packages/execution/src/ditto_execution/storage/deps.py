"""Execution domain dependency groups for DI assembly."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ditto_execution.models import (
    AccountSnapshotRecord,
    BrokerEventRecord,
    FillRecord,
    PositionRecord,
    SignalRecord,
)


class _IntentReaderPort(Protocol):
    """Read-side dependency for trade intents."""

    def get(self, intent_id: str) -> SignalRecord | None: ...

    def list(
        self,
        strategy_id: str,
        signal_date: str | None = None,
        status: str | None = None,
    ) -> list[SignalRecord]: ...


class _IntentWriterPort(Protocol):
    """Write-side dependency for trade intents."""

    def save(self, record: SignalRecord) -> None: ...

    def update_status(
        self,
        intent_id: str,
        status: str,
        *,
        expected_current: tuple[str, ...],
    ) -> bool: ...


class _FillReaderPort(Protocol):
    """Read-side dependency for fills."""

    def get(self, fill_id: str) -> FillRecord | None: ...

    def find(self, intent_id: str, trade_date: str) -> FillRecord | None: ...

    def list(
        self,
        strategy_id: str,
        trade_date: str | None = None,
        intent_id: str | None = None,
        end_date: str | None = None,
    ) -> list[FillRecord]: ...


class _FillWriterPort(Protocol):
    """Write-side dependency for fills."""

    def save(self, record: FillRecord) -> None: ...

    def replace(self, record: FillRecord) -> bool: ...


class _PositionReaderPort(Protocol):
    """Read-side dependency for position snapshots."""

    def get_latest(
        self,
        strategy_id: str,
        instrument_id: int,
        run_id: str | None = None,
    ) -> PositionRecord | None: ...

    def list(
        self,
        strategy_id: str,
        snapshot_date: str | None = None,
        run_id: str | None = None,
    ) -> list[PositionRecord]: ...


class _PositionWriterPort(Protocol):
    """Write-side dependency for position snapshots."""

    def save(self, record: PositionRecord) -> None: ...

    def save_uncommitted(self, record: PositionRecord) -> None: ...


class _AccountSnapshotReaderPort(Protocol):
    """Read-side dependency for account snapshots."""

    def get_latest(
        self,
        run_id: str,
        account_id: str,
    ) -> AccountSnapshotRecord | None: ...

    def list(
        self,
        run_id: str,
        *,
        strategy_id: str | None = None,
        account_id: str | None = None,
        snapshot_date: str | None = None,
    ) -> list[AccountSnapshotRecord]: ...


class _AccountSnapshotWriterPort(Protocol):
    """Write-side dependency for account snapshots."""

    def save(self, record: AccountSnapshotRecord) -> None: ...

    def save_uncommitted(self, record: AccountSnapshotRecord) -> None: ...


class _BrokerEventReaderPort(Protocol):
    """Read-side dependency for normalized broker gateway events."""

    def get(self, event_id: str) -> BrokerEventRecord | None: ...

    def list(
        self,
        run_id: str,
        *,
        event_type: str | None = None,
        order_id: str | None = None,
        broker_order_id: str | None = None,
        fill_id: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[BrokerEventRecord]: ...


class _BrokerEventWriterPort(Protocol):
    """Write-side dependency for normalized broker gateway events."""

    def save(self, record: BrokerEventRecord) -> None: ...


@dataclass(frozen=True)
class ExecutionReaders:
    """Execution domain read dependencies."""

    intent: _IntentReaderPort
    fill: _FillReaderPort
    position: _PositionReaderPort
    account: _AccountSnapshotReaderPort
    broker_event: _BrokerEventReaderPort


@dataclass(frozen=True)
class ExecutionWriters:
    """Execution domain write dependencies."""

    intent: _IntentWriterPort
    fill: _FillWriterPort
    position: _PositionWriterPort
    account: _AccountSnapshotWriterPort
    broker_event: _BrokerEventWriterPort


__all__ = ["ExecutionReaders", "ExecutionWriters"]
