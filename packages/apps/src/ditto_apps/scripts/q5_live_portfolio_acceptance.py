"""Build or execute the exactly approved live portfolio closure."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

import orjson

from ditto_apps.operations.q4_live_account_acceptance import (
    atomic_write_json,
    load_json,
)
from ditto_apps.operations.q5_live_portfolio_acceptance import (
    approved_live_portfolio_acceptance_request,
    build_live_portfolio_acceptance_proposal,
)
from ditto_apps.registry.live.q5_live_portfolio_acceptance_runtime import (
    run_live_portfolio_acceptance,
)
from ditto_apps.registry.live.q5_live_portfolio_proposal import (
    LivePortfolioProposalRequest,
    build_live_portfolio_proposal,
)

__all__ = [
    "approved_live_portfolio_acceptance_request",
    "build_live_portfolio_acceptance_proposal",
]


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
    proposal.add_argument("--trading-database", type=Path, required=True)
    proposal.add_argument("--evidence-root", type=Path, required=True)
    proposal.add_argument("--q3-evidence", type=Path, required=True)
    proposal.add_argument("--account-evidence", type=Path, required=True)
    proposal.add_argument("--output", type=Path)
    run = subparsers.add_parser("run")
    run.add_argument("--proposal", type=Path, required=True)
    run.add_argument("--approved-request-hash", required=True)
    run.add_argument("--operator-id", required=True)
    run.add_argument("--output", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Build a read-only proposal or execute its exact approved writes."""
    args = _parser().parse_args(argv)
    if args.command == "proposal":
        payload = build_live_portfolio_proposal(
            LivePortfolioProposalRequest(
                data_root=args.data_root,
                trading_database=args.trading_database,
                evidence_root=args.evidence_root,
                q3_evidence=args.q3_evidence,
                account_evidence=args.account_evidence,
                observed_at=datetime.now(UTC),
            )
        )
    else:
        proposal = load_json(args.proposal.resolve(strict=True), field="proposal")
        payload = run_live_portfolio_acceptance(
            proposal,
            approved_request_hash=str(args.approved_request_hash),
            operator_id=str(args.operator_id),
            executed_at=datetime.now(UTC),
        )
    _write(payload, args.output)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
