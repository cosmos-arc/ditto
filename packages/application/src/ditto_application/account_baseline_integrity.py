"""Integrity rules shared by account-baseline commands and queries."""

from __future__ import annotations

from collections.abc import Iterable
from math import fsum, isclose, isfinite

from ditto_execution.models import AccountSnapshotRecord, PositionRecord

__all__ = ["resolve_complete_baseline_positions"]

_EXPOSURE_ABS_TOLERANCE = 1e-6


def resolve_complete_baseline_positions(
    account: AccountSnapshotRecord,
    candidates: Iterable[PositionRecord],
) -> tuple[PositionRecord, ...] | None:
    """Return exactly owned positions when the persisted aggregate is complete."""
    if not isfinite(account.exposure) or account.exposure < 0:
        return None

    owned: list[PositionRecord] = []
    instrument_ids: set[int] = set()
    for position in candidates:
        if not _belongs_to_account(account, position):
            continue
        if position.instrument_id in instrument_ids:
            return None
        if not isfinite(position.market_value) or position.market_value < 0:
            return None
        instrument_ids.add(position.instrument_id)
        owned.append(position)

    if account.exposure > 0 and not owned:
        return None
    exposure = fsum(position.market_value for position in owned)
    if not isclose(
        exposure,
        account.exposure,
        rel_tol=0.0,
        abs_tol=_EXPOSURE_ABS_TOLERANCE,
    ):
        return None
    return tuple(sorted(owned, key=lambda position: position.instrument_id))


def _belongs_to_account(
    account: AccountSnapshotRecord,
    position: PositionRecord,
) -> bool:
    """Match the exact aggregate identity encoded by the R1 baseline command."""
    return (
        position.run_id == account.run_id
        and position.strategy_id == account.strategy_id
        and position.snapshot_date == account.snapshot_date
        and position.snapshot_id == f"{account.snapshot_id}-{position.instrument_id}"
    )
