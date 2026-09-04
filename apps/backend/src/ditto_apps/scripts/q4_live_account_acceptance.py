"""Exactly approved Manual acceptance and real-provider Paper soak CLI."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

import orjson
from ditto_application.queries.source import SourceDataPort

from ditto_apps.operations.q4_live_account_acceptance import (
    INSTRUMENT_CODE,
    SHANGHAI,
    AcceptanceMarketSource,
    approved_acceptance_request,
    atomic_write_json,
    build_acceptance_proposal,
    calendar_dates,
    load_json,
    verify_soak_progress,
)
from ditto_apps.registry.container import make_app_container
from ditto_apps.registry.infra.config import preload_runtime_secrets
from ditto_apps.registry.live.q4_live_account_acceptance_runtime import (
    bootstrap_approved_acceptance,
    record_next_paper_day,
)

__all__ = [
    "approved_acceptance_request",
    "bootstrap_approved_acceptance",
    "build_acceptance_proposal",
    "record_next_paper_day",
    "select_next_eligible_trade_date",
    "verify_soak_progress",
]

from ditto_apps.operations.q4_live_account_acceptance import (
    select_next_eligible_trade_date,
)


def _live_proposal(
    *, data_root: Path, evidence_root: Path, now: datetime
) -> dict[str, object]:
    preload_runtime_secrets()
    container = make_app_container()
    try:
        source = cast("AcceptanceMarketSource", container.get(SourceDataPort))
        local_day = now.astimezone(SHANGHAI).date()
        calendar = source.fetch_calendar(
            (local_day - timedelta(days=14)).isoformat(),
            (local_day + timedelta(days=60)).isoformat(),
        )
        open_dates = calendar_dates(calendar)
        forecast = tuple(item for item in open_dates if item > local_day.isoformat())
        bars = source.fetch_etf_daily(
            source_ticker=INSTRUMENT_CODE,
            start_date=(local_day - timedelta(days=14)).isoformat(),
            end_date=local_day.isoformat(),
        )
        eligible = [
            row
            for row in bars.to_dicts()
            if str(row.get("trade_date")) < local_day.isoformat()
        ]
        if not eligible:
            raise ValueError("no prior published 518880.SH bar is available")
        latest = max(eligible, key=lambda row: str(row["trade_date"]))
        return build_acceptance_proposal(
            data_root=data_root,
            evidence_root=evidence_root,
            generated_at=now,
            latest_published_bar=cast("Mapping[str, object]", latest),
            forecast_open_dates=forecast,
        )
    finally:
        container.close()


def _write_or_print(payload: Mapping[str, object], output: Path | None) -> None:
    if output is None:
        sys.stdout.write(orjson.dumps(payload, option=orjson.OPT_SORT_KEYS).decode())
        sys.stdout.write("\n")
    else:
        atomic_write_json(output.resolve(), payload)


def main() -> int:
    """Run proposal, bootstrap, one-day record, or status verification."""
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    proposal_parser = subparsers.add_parser("proposal")
    proposal_parser.add_argument("--data-root", type=Path, required=True)
    proposal_parser.add_argument("--evidence-root", type=Path, required=True)
    proposal_parser.add_argument("--output", type=Path)
    bootstrap_parser = subparsers.add_parser("bootstrap")
    bootstrap_parser.add_argument("--proposal", type=Path, required=True)
    bootstrap_parser.add_argument("--approved-request-hash", required=True)
    bootstrap_parser.add_argument("--operator-id", required=True)
    bootstrap_parser.add_argument("--output", type=Path)
    record_parser = subparsers.add_parser("record-day")
    record_parser.add_argument("--proposal", type=Path, required=True)
    record_parser.add_argument("--approved-request-hash", required=True)
    record_parser.add_argument("--operator-id", required=True)
    record_parser.add_argument("--closed-day-authorization")
    record_parser.add_argument("--output", type=Path)
    status_parser = subparsers.add_parser("status")
    status_parser.add_argument("--proposal", type=Path, required=True)
    status_parser.add_argument("--approved-request-hash", required=True)
    status_parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    now = datetime.now(UTC)
    if args.command == "proposal":
        payload = _live_proposal(
            data_root=args.data_root,
            evidence_root=args.evidence_root,
            now=now,
        )
    else:
        proposal = load_json(args.proposal.resolve(strict=True), field="proposal")
        if args.command == "bootstrap":
            payload = bootstrap_approved_acceptance(
                proposal,
                approved_request_hash=args.approved_request_hash,
                approved_at=now,
                operator_id=args.operator_id,
            )
        elif args.command == "record-day":
            preload_runtime_secrets()
            container = make_app_container()
            try:
                source = cast("AcceptanceMarketSource", container.get(SourceDataPort))
                payload = record_next_paper_day(
                    proposal,
                    approved_request_hash=args.approved_request_hash,
                    operator_id=args.operator_id,
                    source=source,
                    now=now,
                    closed_day_authorization=args.closed_day_authorization,
                )
            finally:
                container.close()
        else:
            approved = approved_acceptance_request(
                proposal,
                approved_request_hash=args.approved_request_hash,
            )
            payload = verify_soak_progress(
                data_root=approved.data_root,
                evidence_root=approved.evidence_root,
                expected_approval_hash=approved.request_hash,
            )
    _write_or_print(payload, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
