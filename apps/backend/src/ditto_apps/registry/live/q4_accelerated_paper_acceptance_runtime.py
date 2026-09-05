"""Paper runtime for exact, accelerated real-provider acceptance."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import cast

from ditto_application.commands.paper_account import (
    CreatePaperAccountCommand,
    CreatePaperAccountHandler,
)
from ditto_execution.storage.sqlite.account_journal import SqliteAccountEventJournal

from ditto_apps.operations.q4_accelerated_paper_acceptance import (
    ACCELERATED_DAY_SCHEMA,
    ACCELERATED_PROGRESS_SCHEMA,
    ApprovedAcceleratedAcceptance,
    approved_accelerated_acceptance_request,
)
from ditto_apps.operations.q4_live_account_acceptance import (
    AcceptanceDayRequest,
    AcceptanceMarketSource,
    atomic_write_json,
    canonical_bar,
    canonical_hash,
    canonical_text,
    load_json,
    load_signing_key,
    parse_iso_date,
    parse_timestamp,
    rfc3339,
    sign_payload,
    verify_signed_payload,
)
from ditto_apps.registry.live.q4_live_account_acceptance_runtime import (
    exclusive_acceptance_state_lock,
    record_acceptance_day,
)
from ditto_apps.registry.live.q4_live_account_acceptance_state import frame_bar

__all__ = ["run_accelerated_paper_acceptance", "verify_accelerated_acceptance"]

_BOOTSTRAP_SCHEMA = "ditto.pap09-accelerated-provider-replay-bootstrap.v1"
_SESSION_PREFIX = "pap09-accelerated-session"
_TARGET_DAYS = 20
_Q4_DAYS = 5


def _paths(approved: ApprovedAcceleratedAcceptance) -> tuple[Path, Path, Path]:
    state = approved.data_root / "state"
    return (
        state / "q4-account-acceptance.sqlite3",
        state / "evidence-signing.key",
        approved.data_root / "evidence" / "bootstrap.json",
    )


def _assert_scoped_roots(approved: ApprovedAcceleratedAcceptance) -> None:
    database, key_path, receipt_path = _paths(approved)
    allowed_private = {
        approved.data_root / "state" / "acceptance.lock",
        database,
        Path(f"{database}-journal"),
        Path(f"{database}-shm"),
        Path(f"{database}-wal"),
        key_path,
        receipt_path,
        *(
            approved.data_root / "evidence" / "days" / f"{trade_date}.json"
            for trade_date in approved.trade_dates
        ),
    }
    allowed_public = {
        approved.evidence_root / "bootstrap.json",
        approved.evidence_root / "accelerated-progress.json",
        *(
            approved.evidence_root / "days" / f"{trade_date}.json"
            for trade_date in approved.trade_dates
        ),
    }
    for root, allowed, label in (
        (approved.data_root, allowed_private, "fresh data root"),
        (approved.evidence_root, allowed_public, "evidence root"),
    ):
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.is_symlink() or (path.is_file() and path not in allowed):
                raise ValueError(f"accelerated {label} contains an unapproved path")


def _bootstrap(
    approved: ApprovedAcceleratedAcceptance,
    *,
    approved_at: datetime,
    operator_id: str,
) -> tuple[bytes, str]:
    database, key_path, receipt_path = _paths(approved)
    approved.data_root.mkdir(parents=True, exist_ok=True)
    approved.evidence_root.mkdir(parents=True, exist_ok=True)
    key = load_signing_key(key_path, create=True)
    if receipt_path.exists():
        receipt = load_json(receipt_path, field="accelerated bootstrap")
        if receipt.get("schema") != _BOOTSTRAP_SCHEMA:
            raise ValueError("accelerated bootstrap schema drifted")
        signature = verify_signed_payload(
            receipt,
            key=key,
            approval_hash=approved.request_hash,
            previous_signature=None,
        )
        public = approved.evidence_root / "bootstrap.json"
        atomic_write_json(public, receipt)
        return key, signature
    paper = approved.paper_scope()
    with SqliteAccountEventJournal(str(database)) as journal:
        account = CreatePaperAccountHandler(
            journal=journal,
            clock=lambda: approved_at,
        ).handle(
            CreatePaperAccountCommand(
                account_id=paper.paper_account_id,
                name="PAP-09 Accelerated Real Provider Acceptance",
                opened_at=approved_at,
                trade_date=approved.trade_dates[0],
                initial_cash=Decimal(paper.paper_opening_cash),
                idempotency_key="pap09-accelerated-account-bootstrap-v1",
            )
        )
    unsigned: dict[str, object] = {
        "schema": _BOOTSTRAP_SCHEMA,
        "status": "passed",
        "request_hash": approved.request_hash,
        "approved_at": rfc3339(approved_at),
        "operator_id": operator_id,
        "acceptance_mode": "accelerated_real_provider_replay",
        "qualifies_as_wall_clock_soak": False,
        "qualifies_as_release_acceptance": True,
        "paper": {
            "account_id": paper.paper_account_id,
            "account_status": account.status,
            "opening_event_id": account.opening_event_id,
            "opening_trade_date": approved.trade_dates[0],
            "opening_cash": paper.paper_opening_cash,
        },
        "live_day_anchor": {
            "approval_hash": approved.live_day_approval_hash,
            "day_evidence_hash": approved.live_day_evidence_hash,
        },
        "safety": {"paper_only": True, "broker_connections": 0, "real_orders": 0},
    }
    receipt = sign_payload(
        unsigned,
        key=key,
        approval_hash=approved.request_hash,
        previous_signature=None,
    )
    atomic_write_json(receipt_path, receipt)
    atomic_write_json(approved.evidence_root / "bootstrap.json", receipt)
    return key, cast("str", cast("Mapping[str, object]", receipt["signature"])["value"])


def _preflight_provider(
    approved: ApprovedAcceleratedAcceptance, source: AcceptanceMarketSource
) -> None:
    calendar = source.fetch_calendar(
        approved.trade_dates[0], approved.settlement_dates[-1]
    )
    rows = calendar.to_dicts()
    open_dates = tuple(
        sorted(
            {
                parse_iso_date(row.get("trade_date"), field="calendar.trade_date")
                for row in rows
                if bool(row.get("is_open"))
            }
        )
    )
    expected = (*approved.trade_dates, approved.settlement_dates[-1])
    visible = tuple(item for item in open_dates if expected[0] <= item <= expected[-1])
    if visible != expected:
        raise ValueError("provider calendar drifted from the approved replay prefix")
    for trade_date, frozen in zip(
        approved.trade_dates, approved.provider_bars, strict=True
    ):
        current = frame_bar(
            source.fetch_etf_daily(
                source_ticker=approved.paper_scope().instrument_code,
                start_date=trade_date,
                end_date=trade_date,
            ),
            trade_date=trade_date,
        )
        if canonical_hash(current) != canonical_hash(canonical_bar(frozen)):
            raise ValueError(f"provider bar drifted for {trade_date}")


def verify_accelerated_acceptance(
    *,
    data_root: Path,
    evidence_root: Path,
    expected_approval_hash: str,
) -> dict[str, object]:
    """Verify the private signature chain and public accelerated mirrors."""
    root = data_root.expanduser().resolve()
    public_root = evidence_root.expanduser().resolve()
    key = load_signing_key(root / "state" / "evidence-signing.key", create=False)
    bootstrap_path = root / "evidence" / "bootstrap.json"
    bootstrap = load_json(bootstrap_path, field="accelerated bootstrap")
    if bootstrap.get("schema") != _BOOTSTRAP_SCHEMA:
        raise ValueError("accelerated bootstrap schema is invalid")
    signature = verify_signed_payload(
        bootstrap,
        key=key,
        approval_hash=expected_approval_hash,
        previous_signature=None,
    )
    public_bootstrap = public_root / "bootstrap.json"
    if (
        not public_bootstrap.exists()
        or public_bootstrap.read_bytes() != bootstrap_path.read_bytes()
    ):
        raise ValueError("accelerated bootstrap public mirror drifted")
    day_paths = sorted((root / "evidence" / "days").glob("*.json"))
    dates: list[str] = []
    hashes: list[str] = []
    balanced: list[bool] = []
    for path in day_paths:
        payload = load_json(path, field=f"accelerated day {path.name}")
        trade_date = parse_iso_date(payload.get("trade_date"), field="trade_date")
        execution = cast("Mapping[str, object]", payload.get("execution"))
        pit = cast("Mapping[str, object]", payload.get("pit"))
        decision_at = parse_timestamp(pit.get("decision_at"), field="pit.decision_at")
        observed_at = parse_timestamp(
            pit.get("bar_observed_at"), field="pit.bar_observed_at"
        )
        execution_at = parse_timestamp(
            pit.get("execution_at"), field="pit.execution_at"
        )
        if (
            payload.get("schema") != ACCELERATED_DAY_SCHEMA
            or payload.get("acceptance_mode") != "accelerated_real_provider_replay"
            or payload.get("qualifies_as_wall_clock_soak") is not False
            or payload.get("qualifies_as_release_acceptance") is not True
            or path.stem != trade_date
            or execution.get("balanced") is not True
            or execution.get("execution_count") != 1
            or execution.get("fill_count") != 1
            or execution.get("ledger_fill_count") != 1
            or pit.get("decision_uses_same_day_close") is not False
            or pit.get("fill_uses_bar_after_observation") is not True
            or pit.get("historical_replay_explicit") is not True
            or pit.get("future_bar_used") is not False
            or not decision_at < observed_at <= execution_at
        ):
            raise ValueError("accelerated day evidence is invalid")
        signature = verify_signed_payload(
            payload,
            key=key,
            approval_hash=expected_approval_hash,
            previous_signature=signature,
        )
        public = public_root / "days" / path.name
        if not public.exists() or public.read_bytes() != path.read_bytes():
            raise ValueError("accelerated day public mirror drifted")
        dates.append(trade_date)
        hashes.append(canonical_hash(payload))
        balanced.append(True)
    if dates != sorted(set(dates)):
        raise ValueError("accelerated day dates are not unique and ordered")
    count = len(dates)
    return {
        "schema": ACCELERATED_PROGRESS_SCHEMA,
        "status": "passed" if count == _TARGET_DAYS else "partial",
        "approval_hash": expected_approval_hash,
        "acceptance_mode": "accelerated_real_provider_replay",
        "qualifies_as_wall_clock_soak": False,
        "qualifies_as_release_acceptance": True,
        "accelerated_trading_day_count": count,
        "trade_dates": dates,
        "day_evidence_hashes": hashes,
        "daily_reconciliations_balanced": balanced,
        "signature_chain_valid": True,
        "signature_chain_head": signature,
        "q4_five_day_ready": count >= _Q4_DAYS,
        "pap09_twenty_day_release_ready": count >= _TARGET_DAYS,
        "remaining_accelerated_trading_days": max(0, _TARGET_DAYS - count),
        "safety": {"paper_only": True, "broker_connections": 0, "real_orders": 0},
    }


def _existing_complete(
    approved: ApprovedAcceleratedAcceptance,
) -> dict[str, object] | None:
    progress_path = approved.evidence_root / "accelerated-progress.json"
    if not progress_path.exists():
        return None
    progress = verify_accelerated_acceptance(
        data_root=approved.data_root,
        evidence_root=approved.evidence_root,
        expected_approval_hash=approved.request_hash,
    )
    return (
        progress if progress["accelerated_trading_day_count"] == _TARGET_DAYS else None
    )


def run_accelerated_paper_acceptance(
    proposal: Mapping[str, object],
    *,
    approved_request_hash: str,
    operator_id: str,
    source: AcceptanceMarketSource,
    approved_at: datetime,
) -> dict[str, object]:
    """Replay twenty frozen provider sessions through the production Paper runtime."""
    approved = approved_accelerated_acceptance_request(
        proposal, approved_request_hash=approved_request_hash
    )
    timestamp = parse_timestamp(rfc3339(approved_at), field="approved_at")
    if timestamp < approved.generated_at:
        raise ValueError("approval cannot predate accelerated proposal")
    operator = canonical_text(operator_id, field="operator_id")
    with exclusive_acceptance_state_lock(approved.data_root):
        _assert_scoped_roots(approved)
        existing = _existing_complete(approved)
        if existing is not None:
            return existing
        _preflight_provider(approved, source)
        key, signature = _bootstrap(
            approved, approved_at=timestamp, operator_id=operator
        )
        paper = approved.paper_scope()
        database, _key_path, _bootstrap_path = _paths(approved)
        for ordinal, (trade_date, settlement_date, frozen_bar) in enumerate(
            zip(
                approved.trade_dates,
                approved.settlement_dates,
                approved.provider_bars,
                strict=True,
            ),
            start=1,
        ):
            durable = approved.data_root / "evidence" / "days" / f"{trade_date}.json"
            public = approved.evidence_root / "days" / f"{trade_date}.json"
            if durable.exists():
                payload = load_json(durable, field=f"accelerated day {trade_date}")
                signature = verify_signed_payload(
                    payload,
                    key=key,
                    approval_hash=approved.request_hash,
                    previous_signature=signature,
                )
                atomic_write_json(public, payload)
                continue
            execution_time = timestamp + timedelta(seconds=ordinal)
            execution = record_acceptance_day(
                AcceptanceDayRequest(
                    approved=paper,
                    database=database,
                    source=source,
                    trade_date=trade_date,
                    settlement_date=settlement_date,
                    now=execution_time,
                    operator_id=operator,
                    session_prefix=_SESSION_PREFIX,
                    pause_reason="PAP-09 accelerated provider replay EOD complete",
                )
            )
            current_bar = cast("Mapping[str, object]", execution.pop("bar"))
            if canonical_hash(current_bar) != canonical_hash(dict(frozen_bar)):
                raise ValueError(f"provider bar drifted during replay for {trade_date}")
            unsigned: dict[str, object] = {
                "schema": ACCELERATED_DAY_SCHEMA,
                "status": "recorded",
                "work_package": "PAP-09",
                "acceptance_mode": "accelerated_real_provider_replay",
                "qualifies_as_wall_clock_soak": False,
                "qualifies_as_release_acceptance": True,
                "accelerated_trading_day_ordinal": ordinal,
                "trade_date": trade_date,
                "recorded_at": rfc3339(execution_time),
                "request_hash": approved.request_hash,
                "provider": {
                    "name": "tushare",
                    "calendar_confirmed_open": True,
                    "market_dataset": "etf_daily",
                    "source_snapshot_id": execution["source_snapshot_id"],
                    "bar": current_bar,
                    "approved_bar_hash": canonical_hash(dict(frozen_bar)),
                    "frozen_at": rfc3339(approved.generated_at),
                },
                "pit": {
                    "decision_at": execution["decision_at"],
                    "bar_observed_at": execution["observed_at"],
                    "execution_at": execution["execution_at"],
                    "publication_cutoff": execution["publication_cutoff"],
                    "decision_precedes_execution": cast("str", execution["decision_at"])
                    < cast("str", execution["execution_at"]),
                    "decision_uses_same_day_close": False,
                    "fill_uses_bar_after_observation": (
                        cast("str", execution["observed_at"])
                        <= cast("str", execution["execution_at"])
                    ),
                    "historical_replay_explicit": True,
                    "future_bar_used": False,
                },
                "execution": {
                    key_: value
                    for key_, value in execution.items()
                    if key_
                    not in {
                        "source_snapshot_id",
                        "observed_at",
                        "publication_cutoff",
                        "decision_at",
                        "execution_at",
                    }
                },
                "live_day_anchor": {
                    "approval_hash": approved.live_day_approval_hash,
                    "day_evidence_hash": approved.live_day_evidence_hash,
                },
                "safety": {
                    "paper_only": True,
                    "broker_connections": 0,
                    "real_orders": 0,
                    "daily_execution_count": 1,
                },
            }
            payload = sign_payload(
                unsigned,
                key=key,
                approval_hash=approved.request_hash,
                previous_signature=signature,
            )
            signature = cast(
                "str", cast("Mapping[str, object]", payload["signature"])["value"]
            )
            atomic_write_json(durable, payload)
            atomic_write_json(public, payload)
        progress = verify_accelerated_acceptance(
            data_root=approved.data_root,
            evidence_root=approved.evidence_root,
            expected_approval_hash=approved.request_hash,
        )
        atomic_write_json(
            approved.evidence_root / "accelerated-progress.json", progress
        )
        return progress
