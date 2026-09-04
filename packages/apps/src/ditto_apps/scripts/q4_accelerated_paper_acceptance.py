"""Build, execute, or verify accelerated real-provider Paper acceptance."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from typing import cast

import orjson
from ditto_application.queries.source import SourceDataPort

from ditto_apps.operations.q4_accelerated_paper_acceptance import (
    approved_accelerated_acceptance_request,
    build_accelerated_acceptance_proposal,
)
from ditto_apps.operations.q4_live_account_acceptance import (
    INSTRUMENT_CODE,
    SHANGHAI,
    AcceptanceMarketSource,
    atomic_write_json,
    calendar_dates,
    canonical_bar,
    canonical_hash,
    load_json,
)
from ditto_apps.registry.container import make_app_container
from ditto_apps.registry.infra.config import preload_runtime_secrets
from ditto_apps.registry.live.q4_accelerated_paper_acceptance_runtime import (
    run_accelerated_paper_acceptance,
    verify_accelerated_acceptance,
)

__all__ = [
    "approved_accelerated_acceptance_request",
    "build_accelerated_acceptance_proposal",
    "run_accelerated_paper_acceptance",
    "verify_accelerated_acceptance",
]

_TARGET_DAYS = 20


def _live_proposal(
    *,
    data_root: Path,
    evidence_root: Path,
    live_day_evidence: Path,
    now: datetime,
) -> dict[str, object]:
    live_day = load_json(live_day_evidence.resolve(strict=True), field="live day")
    live_approval_hash = cast("str", live_day.get("request_hash"))
    preload_runtime_secrets()
    container = make_app_container()
    try:
        source = cast("AcceptanceMarketSource", container.get(SourceDataPort))
        local = now.astimezone(SHANGHAI)
        closed_through = (
            local.date()
            if local.timetz().replace(tzinfo=None) >= time(15, 0)
            else local.date() - timedelta(days=1)
        )
        calendar = source.fetch_calendar(
            (closed_through - timedelta(days=60)).isoformat(),
            (closed_through + timedelta(days=14)).isoformat(),
        )
        all_open = calendar_dates(calendar)
        closed = tuple(item for item in all_open if item <= closed_through.isoformat())
        if len(closed) < _TARGET_DAYS:
            raise ValueError("provider calendar lacks twenty closed trading days")
        trade_dates = closed[-_TARGET_DAYS:]
        later = tuple(item for item in all_open if item > trade_dates[-1])
        if not later:
            raise ValueError("provider calendar lacks the final settlement day")
        sequence = (*trade_dates, later[0])
        frame = source.fetch_etf_daily(
            source_ticker=INSTRUMENT_CODE,
            start_date=trade_dates[0],
            end_date=trade_dates[-1],
        )
        by_date = {
            str(row.get("trade_date")): canonical_bar(cast("Mapping[str, object]", row))
            for row in frame.to_dicts()
            if str(row.get("source_ticker")) == INSTRUMENT_CODE
        }
        bars = tuple(by_date[item] for item in trade_dates)
        return build_accelerated_acceptance_proposal(
            data_root=data_root,
            evidence_root=evidence_root,
            generated_at=now,
            open_dates=sequence,
            provider_bars=bars,
            live_day_approval_hash=live_approval_hash,
            live_day_evidence_hash=canonical_hash(live_day),
        )
    finally:
        container.close()


def _write(payload: Mapping[str, object], output: Path | None) -> None:
    if output is None:
        sys.stdout.write(orjson.dumps(payload, option=orjson.OPT_SORT_KEYS).decode())
        sys.stdout.write("\n")
    else:
        atomic_write_json(output.resolve(), payload)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    proposal = subparsers.add_parser("proposal")
    proposal.add_argument("--data-root", type=Path, required=True)
    proposal.add_argument("--evidence-root", type=Path, required=True)
    proposal.add_argument("--live-day-evidence", type=Path, required=True)
    proposal.add_argument("--output", type=Path)
    run = subparsers.add_parser("run")
    run.add_argument("--proposal", type=Path, required=True)
    run.add_argument("--approved-request-hash", required=True)
    run.add_argument("--operator-id", required=True)
    run.add_argument("--output", type=Path)
    status = subparsers.add_parser("status")
    status.add_argument("--proposal", type=Path, required=True)
    status.add_argument("--approved-request-hash", required=True)
    status.add_argument("--output", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run one read-only proposal or one exactly approved replay/status action."""
    args = _parser().parse_args(argv)
    now = datetime.now(UTC)
    if args.command == "proposal":
        payload = _live_proposal(
            data_root=args.data_root,
            evidence_root=args.evidence_root,
            live_day_evidence=args.live_day_evidence,
            now=now,
        )
    else:
        proposal = load_json(Path(args.proposal).resolve(strict=True), field="proposal")
        approved = approved_accelerated_acceptance_request(
            proposal, approved_request_hash=str(args.approved_request_hash)
        )
        if args.command == "run":
            preload_runtime_secrets()
            container = make_app_container()
            try:
                source = cast("AcceptanceMarketSource", container.get(SourceDataPort))
                payload = run_accelerated_paper_acceptance(
                    proposal,
                    approved_request_hash=approved.request_hash,
                    operator_id=str(args.operator_id),
                    source=source,
                    approved_at=now,
                )
            finally:
                container.close()
        else:
            payload = verify_accelerated_acceptance(
                data_root=approved.data_root,
                evidence_root=approved.evidence_root,
                expected_approval_hash=approved.request_hash,
            )
    _write(payload, args.output)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
