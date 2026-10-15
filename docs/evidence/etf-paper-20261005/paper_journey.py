"""
#408 real journey: provider ingestion → authorization → handoff → execution.

Runs against a brand-new isolated root with the configured Tushare source and
the maintainer-confirmed config declaration. Never places broker orders and
never reuses an existing root (the script refuses to overwrite; --resume is
the explicit opt-in for idempotent recovery).
"""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import subprocess
import sys
import time
from contextlib import closing
from dataclasses import asdict
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from ditto_application.commands.paper_account import (
    CreatePaperAccountCommand,
    CreatePaperAccountHandler,
)
from ditto_application.etf_paper_contracts import (
    ETFPaperExecutionRequest,
    ETFPaperHandoffRequest,
)
from ditto_application.etf_paper_execution import ETFPaperExecution
from ditto_application.etf_paper_handoff import ETFPaperHandoff
from ditto_application.processes.portfolio.etf_allocation import (
    ETFAllocationCommand,
    ETFAllocationRequest,
    ETFAllocationReviewRequest,
    ETFPaperAuthorizationRequest,
)
from ditto_application.queries.account_ledger import AccountLedgerQuery
from ditto_application.queries.etf_allocation_review import (
    ETFAllocationReviewRequest as ETFReviewQueryRequest,
)
from ditto_application.queries.etf_allocation_review import GetETFAllocationReviewQuery
from ditto_application.queries.etf_paper_handoff_facts import LiveETFPaperHandoffFacts
from ditto_application.queries.metadata import MetadataQueryFacade
from ditto_application.queries.snapshot_readiness import SnapshotReadinessQuery
from ditto_apps.registry.container import make_app_container
from ditto_apps.registry.contexts.ingestion import create_ingestion_bundle
from ditto_apps.registry.infra.init_providers import MetadataDbInitProvider
from ditto_data.catalog.provider_payload import ProviderPayloadReader
from ditto_data.catalog.source_snapshot import ProviderSnapshotReader

SIGNAL_DATE = "2026-09-30"
TRADE_DATE = "2026-10-08"
ACCOUNT_ID = "issue-408-journey-paper"
SESSION_ID = "issue-408-journey-session"
ALLOCATION_ID = "issue-408-journey"
ACTOR = "chevy"


def wait_for_cutoff_boundary() -> None:
    """Wait for the next whole-second visibility boundary."""
    boundary = math.ceil(time.time())
    while (remaining := boundary - time.time()) > 0:
        time.sleep(remaining)


def canonical_now() -> str:
    """Serialize the current instant in the canonical UTC Z form."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def main() -> None:
    """Run the isolated full ETF Paper acceptance journey (signal or execute phase)."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--config-root", type=Path, required=True)
    parser.add_argument(
        "--phase",
        choices=("signal", "execute"),
        default="signal",
        help="signal=signal-evening full chain; execute=next-evening fill leg",
    )
    parser.add_argument(
        "--signal-date",
        default=None,
        help="override signal day (default: today in Asia/Shanghai)",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="reuse an existing root: skip init/ingest and re-run the "
        "idempotent journey chain to (re)write report.json",
    )
    args = parser.parse_args()
    root = args.root.resolve()
    global SIGNAL_DATE  # noqa: PLW0603
    if args.signal_date:
        SIGNAL_DATE = args.signal_date
    elif args.resume and (root / "report.json").is_file():
        SIGNAL_DATE = str(json.loads((root / "report.json").read_text())["signal_date"])
    else:
        SIGNAL_DATE = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    if not args.resume and (root / "report.json").is_file():
        raise RuntimeError(f"root already has a report; use --resume: {root}")
    os.environ.update(
        DITTO_CONFIG_ROOT=str(args.config_root.resolve()),
        DITTO_STATE_ROOT=str(root / "state"),
        DITTO_CACHE_ROOT=str(root / "cache"),
    )
    git = shutil.which("git")
    if git is None:
        raise RuntimeError("git is required to bind the code identity")
    if args.phase == "execute":
        if not (root / "report.json").is_file():
            raise RuntimeError(f"execute phase needs a prior signal-phase root: {root}")
        report = json.loads((root / "report.json").read_text())
        report["execute_sha"] = _git_sha(git)
        _execute_phase(root, report)
        report["finished_at"] = datetime.now(UTC).isoformat()
        _write_report(root, report)
        sys.stdout.write(str(root / "report.json") + "\n")
        return
    if args.resume:
        if not root.is_dir():
            raise RuntimeError(f"--resume needs an existing root: {root}")
        report: dict[str, object] = {
            "sha": _git_sha(git),
            "root": str(root),
            "resumed_at": datetime.now(UTC).isoformat(),
            "signal_date": SIGNAL_DATE,
        }
        _journey_phase(root, report)
        report["finished_at"] = datetime.now(UTC).isoformat()
        _write_report(root, report)
        sys.stdout.write(str(root / "report.json") + "\n")
        return
    root.mkdir(parents=True, exist_ok=False)
    (root / "state").mkdir()
    if not MetadataDbInitProvider().initialize(root / "state").success:
        raise RuntimeError("metadata initialization failed")
    report = {
        "sha": _git_sha(git),
        "root": str(root),
        "started_at": datetime.now(UTC).isoformat(),
        "scope": (
            "isolated PAPER only; real provider ingestion, maintainer-confirmed "
            "config rules, authorized handoff and simulated execution"
        ),
        "signal_date": SIGNAL_DATE,
    }
    _ingest_phase(root, report)
    _journey_phase(root, report)
    report["finished_at"] = datetime.now(UTC).isoformat()
    _write_report(root, report)
    sys.stdout.write(str(root / "report.json") + "\n")


def _git_sha(git: str) -> str:
    return subprocess.check_output(  # noqa: S603 - resolved git, fixed read-only arguments
        [git, "rev-parse", "HEAD"], text=True
    ).strip()


def _execute_phase(root: Path, report: dict[str, object]) -> None:
    """Fill the handed-off session after the trade-day close (live cadence)."""
    global SIGNAL_DATE, TRADE_DATE  # noqa: PLW0603
    SIGNAL_DATE = str(report["signal_date"])
    TRADE_DATE = str(report["intended_trade_date"])
    report.update(
        phase="execute",
        executed_at=datetime.now(UTC).isoformat(),
    )
    with create_ingestion_bundle("tushare") as bundle:
        result = bundle.coordinator.ingest_date("etf_daily", TRADE_DATE)
        report["execution_day_ingestion"] = asdict(result)
        if result.status != "success":
            _write_report(root, report)
            raise RuntimeError(f"etf_daily@{TRADE_DATE}: {result.status}")
    with closing(make_app_container()) as container:
        snapshots = container.get(ProviderSnapshotReader)
        execution_daily = next(
            item
            for item in snapshots.list_snapshots()
            if item.dataset_id == "etf_daily" and item.request_end == TRADE_DATE
        )
        prior_snapshots = report["snapshots"]
        if not isinstance(prior_snapshots, dict):
            raise RuntimeError("prior report has no snapshots section")
        version = report["allocation_version"]
        if not isinstance(version, dict):
            raise RuntimeError("prior report has no allocation version")
        outcomes, replay_equal = _run_execution(
            container,
            dict(prior_snapshots),
            execution_daily,
            str(version["version_id"]),
            str(report["authorization_id"]),
        )
        report["snapshots"] = {
            **prior_snapshots,
            "etf_daily_execution": execution_daily.snapshot_id,
        }
        report["execution_outcomes"] = [asdict(outcome) for outcome in outcomes]
        report["execution_replay_equal"] = replay_equal
        # 估值在 T+1 晚跑：此刻 trade-day bar(knowledge_date=T+1)已可见。
        report["valuation"] = asdict(
            _run_valuation(
                container,
                str(version["version_id"]),
                execution_daily.snapshot_id,
            )
        )
        wait_for_cutoff_boundary()
        statement = container.get(AccountLedgerQuery).get_paper(
            account_id=ACCOUNT_ID,
            as_of=TRADE_DATE,
            valuation_prices={},
            recorded_through=datetime.now(UTC),
        )
        report["ledger_after_execution"] = {
            "events": [asdict(event) for event in statement.events],
            "valuation_complete": statement.snapshot.valuation_complete,
        }
        report["journey_status"] = (
            "EXECUTED"
            if outcomes and all(outcome.status == "filled" for outcome in outcomes)
            else "PARTIAL"
        )


def _ingest_phase(root: Path, report: dict[str, object]) -> None:
    """Ingest real provider inputs plus the config declaration into the root."""
    with create_ingestion_bundle("tushare") as bundle:
        ingestion: dict[str, object] = {}
        for dataset in ("calendar", "etf_basic", "etf_daily"):
            result = bundle.coordinator.ingest_date(dataset, SIGNAL_DATE)
            ingestion[f"{dataset}@{SIGNAL_DATE}"] = asdict(result)
            if result.status != "success":
                report["ingestion"] = ingestion
                _write_report(root, report)
                raise RuntimeError(f"{dataset}@{SIGNAL_DATE}: {result.status}")
        report["ingestion"] = ingestion
    with create_ingestion_bundle("config") as bundle:
        declared = bundle.coordinator.ingest_date("etf_reference", SIGNAL_DATE)
        repeat = bundle.coordinator.ingest_date("etf_reference", SIGNAL_DATE)
        report["etf_reference_ingestion"] = asdict(declared)
        report["etf_reference_repeat"] = asdict(repeat)
        if declared.status != "success" or repeat.status != "skipped":
            _write_report(root, report)
            raise RuntimeError(f"etf_reference: {declared.status}/{repeat.status}")


def _journey_phase(root: Path, report: dict[str, object]) -> None:
    """Drive allocation → review → authorization → handoff → valuation."""
    with closing(make_app_container()) as container:
        snapshots = container.get(ProviderSnapshotReader)
        by_dataset = {item.dataset_id: item for item in snapshots.list_snapshots()}
        daily_snapshots = [
            item
            for item in snapshots.list_snapshots()
            if item.dataset_id == "etf_daily"
        ]
        signal_daily = daily_snapshots[0]
        report["snapshots"] = {
            "etf_basic": by_dataset["etf_basic"].snapshot_id,
            "etf_daily_signal": signal_daily.snapshot_id,
            "etf_reference": by_dataset["etf_reference"].snapshot_id,
        }
        report["declaration_source"] = by_dataset["etf_reference"].source
        report["account_receipt"] = asdict(_fund_account(container))
        preview = _preview_handoff_facts(container, snapshots, by_dataset, signal_daily)
        report["handoff_preview"] = preview
        global TRADE_DATE  # noqa: PLW0603
        TRADE_DATE = str(preview["next_trading_day"])
        report["intended_trade_date"] = TRADE_DATE
        instrument_id = next(iter(preview["investable_instrument_ids"]))
        version, authorization_id = _approval_chain(
            container, by_dataset, instrument_id
        )
        report["allocation_version"] = asdict(version)
        report["authorization_id"] = authorization_id
        handoff = _run_handoff(
            container, by_dataset, signal_daily, version.version_id, authorization_id
        )
        report["handoff_receipt"] = asdict(handoff)
        # 估值不在信号晚跑：日线生产者按 knowledge_date=T+1 盖章，当日 bar
        # 对当晚 cutoff 不可见；估值随 execute 相位在 T+1 晚执行。
        wait_for_cutoff_boundary()
        statement = container.get(AccountLedgerQuery).get_paper(
            account_id=ACCOUNT_ID,
            as_of=SIGNAL_DATE,
            valuation_prices={},
            recorded_through=datetime.now(UTC),
        )
        report["ledger_after_handoff"] = {
            "events": [asdict(event) for event in statement.events],
            "valuation_complete": statement.snapshot.valuation_complete,
        }
        report["journey_status"] = "COMPLETED"
        report["execution_leg"] = (
            "Same-evening live cadence: this version was saved on the signal day "
            "after its close, so it stays executable. The daily-bar producer "
            "stamps knowledge_date = trade_date + 1, so run the fill leg one "
            f"calendar day after the trade day ({TRADE_DATE}): "
            f"paper_journey.py --phase execute --root {root}"
        )


def _fund_account(container: object) -> object:
    """Create the PAPER account through the real account command path."""
    return container.get(CreatePaperAccountHandler).handle(  # type: ignore[attr-defined]
        CreatePaperAccountCommand(
            account_id=ACCOUNT_ID,
            name="issue #408 acceptance journey",
            opened_at=datetime(2026, 9, 1, tzinfo=UTC),
            trade_date=SIGNAL_DATE,
            initial_cash=Decimal("10000"),
            idempotency_key="journey-opening",
        )
    )


def _preview_handoff_facts(
    container: object,
    snapshots: ProviderSnapshotReader,
    by_dataset: dict[str, object],
    signal_daily: object,
) -> dict[str, object]:
    """Resolve handoff facts to prove restriction/currency/rules are visible."""
    wait_for_cutoff_boundary()
    reference = by_dataset["etf_reference"].snapshot_id  # type: ignore[attr-defined]
    facts = LiveETFPaperHandoffFacts(
        metadata=container.get(MetadataQueryFacade),  # type: ignore[attr-defined]
        readiness=container.get(SnapshotReadinessQuery),  # type: ignore[attr-defined]
        snapshots=snapshots,
        payloads=container.get(ProviderPayloadReader),  # type: ignore[attr-defined]
        ledger=container.get(AccountLedgerQuery),  # type: ignore[attr-defined]
    ).resolve(
        ETFPaperHandoffRequest(
            allocation_id=ALLOCATION_ID,
            version_id="preview",
            authorization_id="preview",
            account_id=ACCOUNT_ID,
            session_id="preview",
            idempotency_key="preview",
            signal_date=SIGNAL_DATE,
            decision_date=datetime.now(UTC).date().isoformat(),
            intended_trade_date=TRADE_DATE,
            knowledge_cutoff=datetime.now(UTC),
            source_snapshot_id=by_dataset["etf_basic"].snapshot_id,  # type: ignore[attr-defined]
            input_snapshot_ids={
                "etf_daily": signal_daily.snapshot_id,  # type: ignore[attr-defined]
                "etf_reference": reference,
            },
        )
    )
    return {
        "investable_instrument_ids": sorted(facts.investable_instrument_ids),
        "next_trading_day": facts.next_trading_day,
        "unavailable_reasons": {
            str(key): value for key, value in facts.unavailable_reasons.items()
        },
    }


def _approval_chain(
    container: object, by_dataset: dict[str, object], instrument_id: int
) -> tuple[object, str]:
    """Save, submit, approve and authorize the fixed target version."""
    allocations = container.get(ETFAllocationCommand)  # type: ignore[attr-defined]
    version = allocations.save(
        ETFAllocationRequest(
            allocation_id=ALLOCATION_ID,
            idempotency_key="save-1",
            parent_version_id=None,
            asof=SIGNAL_DATE,
            knowledge_cutoff=canonical_now(),
            source_snapshot_id=by_dataset["etf_basic"].snapshot_id,  # type: ignore[attr-defined]
            instrument_ids=(instrument_id,),
            mode="equal",
            cash_weight=Decimal("0.5"),
            max_position_weight=Decimal("0.5"),
            manual_weights={},
            reason="issue #408 real journey acceptance target",
        )
    )
    for action, reason in (
        ("submit", "journey review submission"),
        ("approve", "journey review approval"),
    ):
        version = allocations.review(
            ETFAllocationReviewRequest(
                allocation_id=ALLOCATION_ID,
                version_id=version.version_id,
                action=action,
                actor=ACTOR,
                reason=reason,
                idempotency_key=f"review-{action}",
            )
        )
    authorization = allocations.authorize_paper(
        ETFPaperAuthorizationRequest(
            allocation_id=ALLOCATION_ID,
            version_id=version.version_id,
            account_id=ACCOUNT_ID,
            session_id=SESSION_ID,
            intended_trade_date=TRADE_DATE,
            actor=ACTOR,
            reason="journey Paper authorization for #408 acceptance",
            idempotency_key="authorize-1",
        )
    )
    return version, authorization.artifact_id


def _run_handoff(
    container: object,
    by_dataset: dict[str, object],
    signal_daily: object,
    version_id: str,
    authorization_id: str,
) -> object:
    """Start the Paper session from the composed, authorized inputs."""
    wait_for_cutoff_boundary()
    return container.get(ETFPaperHandoff).handoff(  # type: ignore[attr-defined]
        ETFPaperHandoffRequest(
            allocation_id=ALLOCATION_ID,
            version_id=version_id,
            authorization_id=authorization_id,
            account_id=ACCOUNT_ID,
            session_id=SESSION_ID,
            idempotency_key="handoff-1",
            signal_date=SIGNAL_DATE,
            decision_date=datetime.now(UTC).date().isoformat(),
            intended_trade_date=TRADE_DATE,
            knowledge_cutoff=datetime.now(UTC),
            source_snapshot_id=by_dataset["etf_basic"].snapshot_id,  # type: ignore[attr-defined]
            input_snapshot_ids={
                "etf_daily": signal_daily.snapshot_id,  # type: ignore[attr-defined]
                "etf_reference": by_dataset["etf_reference"].snapshot_id,  # type: ignore[attr-defined]
            },
        )
    )


def _run_valuation(
    container: object,
    version_id: str,
    market_snapshot_id: str,
) -> object:
    """Value the authorized target against the real account at the current day."""
    wait_for_cutoff_boundary()
    as_of = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    return container.get(GetETFAllocationReviewQuery).get(  # type: ignore[attr-defined]
        ETFReviewQueryRequest(
            allocation_id=ALLOCATION_ID,
            version_id=version_id,
            account_kind="paper",
            account_id=ACCOUNT_ID,
            as_of=as_of,
            knowledge_cutoff=datetime.now(UTC),
            source_snapshot_ids=(market_snapshot_id,),
        )
    )


def _run_execution(
    container: object,
    by_dataset: dict[str, object],
    execution_daily: object,
    version_id: str,
    authorization_id: str,
) -> tuple[tuple[object, ...], bool]:
    """Evaluate the approved target with execution-day evidence and replay it."""
    executor = container.get(ETFPaperExecution)  # type: ignore[attr-defined]
    request = ETFPaperExecutionRequest(
        allocation_id=ALLOCATION_ID,
        version_id=version_id,
        authorization_id=authorization_id,
        account_id=ACCOUNT_ID,
        session_id=SESSION_ID,
        signal_date=SIGNAL_DATE,
        intended_trade_date=TRADE_DATE,
        execution_cutoff=datetime.now(UTC),
        reference_snapshot_id=by_dataset["etf_basic"].snapshot_id,  # type: ignore[attr-defined]
        market_snapshot_id=execution_daily.snapshot_id,  # type: ignore[attr-defined]
        input_snapshot_ids={
            "etf_daily": execution_daily.snapshot_id,  # type: ignore[attr-defined]
            "etf_reference": by_dataset["etf_reference"].snapshot_id,  # type: ignore[attr-defined]
        },
        idempotency_key="execute-1",
    )
    outcomes = executor.execute(request)
    replayed = executor.execute(request)
    return outcomes, replayed == outcomes


def _write_report(root: Path, report: dict[str, object]) -> None:
    """Persist the journey report inside the isolated root."""
    (root / "report.json").write_text(
        json.dumps(report, default=str, ensure_ascii=False, indent=2)
    )


if __name__ == "__main__":
    main()
