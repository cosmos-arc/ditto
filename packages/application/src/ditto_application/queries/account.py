"""Account baseline query contract."""

from __future__ import annotations

from dataclasses import dataclass

from ditto_execution.contracts import AccountDataPort, PositionDataPort
from ditto_execution.models import AccountSnapshotRecord, PositionRecord

__all__ = ["AccountBaselineQuery", "AccountBaselineReadModel"]


@dataclass(frozen=True)
class AccountBaselineReadModel:
    """账户快照及与其日期、运行标识严格一致的持仓。"""

    account: AccountSnapshotRecord
    positions: tuple[PositionRecord, ...]


class AccountBaselineQuery:
    """按信号日读取最新可用账户基线。"""

    def __init__(
        self,
        *,
        account_port: AccountDataPort,
        position_port: PositionDataPort,
    ) -> None:
        self._account_port = account_port
        self._position_port = position_port

    def get_latest(
        self,
        *,
        account_id: str,
        strategy_id: str,
        signal_date: str,
    ) -> AccountBaselineReadModel | None:
        """返回快照日不晚于信号日的最新基线。"""
        sleeve_id = f"manual-{account_id}-{strategy_id}"
        candidates = self._account_port.list_account_snapshots(
            sleeve_id,
            strategy_id=strategy_id,
            account_id=account_id,
        )
        eligible = [
            account for account in candidates if account.snapshot_date <= signal_date
        ]
        if not eligible:
            return None
        account = max(
            eligible,
            key=lambda item: (item.snapshot_date, item.created_at, item.snapshot_id),
        )
        positions = self._position_port.list_positions(
            strategy_id=strategy_id,
            snapshot_date=account.snapshot_date,
            run_id=sleeve_id,
        )
        return AccountBaselineReadModel(account=account, positions=tuple(positions))
