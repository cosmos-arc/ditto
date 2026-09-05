"""Signed-state and Paper-prefix helpers for Q4/PAP-09 acceptance."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime, time, timedelta
from typing import cast

import polars as pl

from ditto_apps.operations.q4_live_account_acceptance import (
    BOOTSTRAP_SCHEMA,
    SHANGHAI,
    AcceptanceMarketSource,
    ApprovedAcceptance,
    acceptance_state_paths,
    calendar_dates,
    canonical_bar,
    canonical_text,
    load_json,
    parse_timestamp,
    verify_signed_payload,
)

__all__ = [
    "bootstrap_receipt",
    "eligibility_calendar_context",
    "frame_bar",
    "previous_day_signature",
]


def bootstrap_receipt(
    approved: ApprovedAcceptance, *, key: bytes
) -> tuple[dict[str, object], datetime, str]:
    """Load and verify the approval-bound bootstrap receipt."""
    _database, _key_path, path = acceptance_state_paths(approved)
    receipt = load_json(path, field="bootstrap receipt")
    if receipt.get("schema") != BOOTSTRAP_SCHEMA or receipt.get("status") != "passed":
        raise ValueError("bootstrap receipt is not passing")
    signature = verify_signed_payload(
        receipt,
        key=key,
        approval_hash=approved.request_hash,
        previous_signature=None,
    )
    return (
        receipt,
        parse_timestamp(receipt.get("approved_at"), field="approved_at"),
        signature,
    )


def frame_bar(frame: pl.DataFrame, *, trade_date: str) -> dict[str, object]:
    """Require one canonical provider bar for the exact trade date."""
    if frame.height != 1:
        raise ValueError(f"exactly one published ETF bar is required for {trade_date}")
    bar = canonical_bar(cast("Mapping[str, object]", frame.to_dicts()[0]))
    if bar["trade_date"] != trade_date:
        raise ValueError("published ETF bar trade_date drifted")
    return bar


def eligibility_calendar_context(
    *,
    source: AcceptanceMarketSource,
    approved_at: datetime,
    timestamp: datetime,
    progress: Mapping[str, object],
    closed_day_authorization: str | None,
) -> tuple[str | None, date, date, tuple[str, ...]]:
    """Resolve the provider calendar and narrow same-day authorization scope."""
    authorization = (
        canonical_text(
            closed_day_authorization,
            field="closed_day_authorization",
        )
        if closed_day_authorization is not None
        else None
    )
    approval_day = approved_at.astimezone(SHANGHAI).date()
    local_day = timestamp.astimezone(SHANGHAI).date()
    if authorization is not None and local_day != approval_day:
        raise ValueError(
            "closed-day authorization only applies on the approval local date"
        )
    progress_dates = cast("list[object]", progress.get("trade_dates", []))
    approval_day_already_recorded = bool(progress_dates) and (
        progress_dates[0] == approval_day.isoformat()
    )
    include_approval_day = authorization is not None or approval_day_already_recorded
    start = approval_day if include_approval_day else approval_day + timedelta(days=1)
    market_close = datetime.combine(local_day, time(15, 0), tzinfo=SHANGHAI).astimezone(
        UTC
    )
    end = local_day if timestamp >= market_close else local_day - timedelta(days=1)
    calendar = source.fetch_calendar(
        start.isoformat(),
        (local_day + timedelta(days=14)).isoformat(),
    )
    open_dates = tuple(
        item for item in calendar_dates(calendar) if item >= start.isoformat()
    )
    return authorization, local_day, end, open_dates


def previous_day_signature(
    *, approved: ApprovedAcceptance, key: bytes, completed_dates: Sequence[str]
) -> str:
    """Verify the durable chain and return its current signature head."""
    _receipt, _approved_at, signature = bootstrap_receipt(approved, key=key)
    for trade_date in completed_dates:
        payload = load_json(
            approved.data_root / "evidence" / "days" / f"{trade_date}.json",
            field=f"day evidence {trade_date}",
        )
        signature = verify_signed_payload(
            payload,
            key=key,
            approval_hash=approved.request_hash,
            previous_signature=signature,
        )
    return signature
