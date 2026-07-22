"""Durable holdout-consumption authority checks."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import date

from ditto_analysis.errors import ExperimentIntegrityError
from ditto_analysis.experiments.persistence import HoldoutClaimRecord
from ditto_analysis.experiments.preflight_authority import (
    DecodedPreflightAuthority,
)
from ditto_analysis.storage.sqlite.experiments._holdout_preflight import (
    validate_holdout_preflight,
)


def _integrity(message: str, reason_code: str) -> ExperimentIntegrityError:
    return ExperimentIntegrityError(message, details={"reason_code": reason_code})


def find_holdout_consumption_conflict(
    connection: sqlite3.Connection,
    current: DecodedPreflightAuthority,
    decode_claim: Callable[[sqlite3.Row], HoldoutClaimRecord],
) -> HoldoutClaimRecord | None:
    """Rebuild every historical authority and find the newest family cutoff."""
    rows = connection.execute(
        "SELECT * FROM holdout_claim ORDER BY claimed_at_epoch_us, claim_id"
    ).fetchall()
    family_history: list[tuple[date, HoldoutClaimRecord]] = []
    for row in rows:
        record = decode_claim(row)
        prior = validate_holdout_preflight(connection, record.fold_key.experiment_id)
        fold = connection.execute(
            """
            SELECT * FROM experiment_fold
            WHERE experiment_id=? AND candidate_id=? AND fold_id=?
            """,
            (
                str(record.fold_key.experiment_id),
                str(record.fold_key.candidate_id),
                str(record.fold_key.fold_id),
            ),
        ).fetchone()
        if (
            record.cycle.cycle_id != prior.research_cycle_id
            or record.cycle.cycle_hash != prior.research_cycle_hash
            or str(record.snapshot_id) != prior.snapshot_id
            or record.window != prior.consumption.oos_window
            or fold is None
            or fold["fold_role"] != "holdout"
            or fold["test_start"] != record.window.start.isoformat()
            or fold["test_end"] != record.window.end.isoformat()
        ):
            raise _integrity(
                "historical holdout consumption authority drifted",
                "holdout_consumption_authority_invalid",
            )
        if prior.strategy_family_id == current.strategy_family_id:
            family_history.append((prior.consumption.certified_data_cutoff, record))
    if not family_history:
        return None
    latest_cutoff, latest_record = max(
        family_history,
        key=lambda item: (item[0], item[1].claimed_at, item[1].claim_id),
    )
    if (
        current.consumption.certified_data_cutoff <= latest_cutoff
        or current.consumption.oos_window.start <= latest_cutoff
    ):
        return latest_record
    return None
