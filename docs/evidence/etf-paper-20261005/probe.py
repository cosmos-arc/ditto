"""Reproduce #408 in a new isolated root; never place orders or reuse a ledger."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import asdict
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from ditto_application.etf_paper_contracts import ETFPaperHandoffRequest
from ditto_application.queries.account_ledger import AccountLedgerQuery
from ditto_application.queries.etf_paper_handoff_facts import LiveETFPaperHandoffFacts
from ditto_application.queries.etf_paper_reference import (
    ETFPaperReferenceQuery,
    paper_reference_candidates,
)
from ditto_application.queries.metadata import MetadataQueryFacade
from ditto_application.queries.snapshot_readiness import SnapshotReadinessQuery
from ditto_apps.registry.container import make_app_container
from ditto_apps.registry.contexts.ingestion import create_ingestion_bundle
from ditto_apps.registry.infra.init_providers import MetadataDbInitProvider
from ditto_data.catalog.provider_payload import ProviderPayloadReader
from ditto_data.catalog.source_snapshot import ProviderSnapshotReader
from ditto_execution.storage.sqlite.account_journal import SqliteAccountEventJournal
from ditto_kernel.identity import InstrumentId
from ditto_portfolio.account_ledger import (
    AccountDefinition,
    AccountEventDraft,
    AccountEventSource,
    AccountEventType,
    AccountKind,
    create_account_event,
)


def main() -> None:
    """Run the isolated provider and Paper-input probe."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--config-root", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    root.mkdir(parents=True, exist_ok=False)
    os.environ.update(
        DITTO_CONFIG_ROOT=str(args.config_root.resolve()),
        DITTO_STATE_ROOT=str(root / "state"),
        DITTO_CACHE_ROOT=str(root / "cache"),
    )
    (root / "state").mkdir()
    if not MetadataDbInitProvider().initialize(root / "state").success:
        raise RuntimeError("metadata initialization failed")
    git = shutil.which("git")
    if git is None:
        raise RuntimeError("git is required to bind the code identity")
    report: dict[str, object] = {
        "sha": subprocess.check_output(  # noqa: S603 - resolved git, fixed read-only arguments
            [git, "rev-parse", "HEAD"], text=True
        ).strip(),
        "root": str(root),
        "started_at": datetime.now(UTC).isoformat(),
        "scope": "isolated PAPER only; simulated opening cash 10000 and 100 ETF units",
    }
    with create_ingestion_bundle("tushare") as bundle:
        results = {}
        for dataset in ("calendar", "etf_basic", "etf_daily"):
            result = bundle.coordinator.ingest_date(dataset, "2026-09-30")
            results[dataset] = asdict(result)
            if result.status != "success":
                report["ingestion"] = results
                (root / "report.json").write_text(
                    json.dumps(report, default=str, ensure_ascii=False, indent=2)
                )
                raise RuntimeError(f"{dataset}: {result.status}")
        report["ingestion"] = results
        report["repeat_etf_daily"] = asdict(
            bundle.coordinator.ingest_date("etf_daily", "2026-09-30")
        )
    with (
        make_app_container() as container,
        SqliteAccountEventJournal(str(root / "paper.sqlite")) as journal,
    ):
        snapshots = container.get(ProviderSnapshotReader)
        inputs = {item.dataset_id: item for item in snapshots.list_snapshots()}
        report["snapshots"] = {key: asdict(value) for key, value in inputs.items()}
        metadata = container.get(MetadataQueryFacade)
        readiness = container.get(SnapshotReadinessQuery)
        payloads = container.get(ProviderPayloadReader)
        time.sleep(1)  # Canonical query cutoffs have second resolution.
        query = ETFPaperReferenceQuery(
            asof="2026-09-30",
            cutoff=datetime.now(UTC),
            snapshot_id=inputs["etf_basic"].snapshot_id,
            input_snapshot_ids={"etf_daily": inputs["etf_daily"].snapshot_id},
        )
        candidates = paper_reference_candidates(
            metadata=metadata,
            readiness=readiness,
            snapshots=snapshots,
            payloads=payloads,
            query=query,
        )
        candidate = next(
            item
            for item in candidates.values()
            if item.ticker == "510300" and item.exchange == "SSE"
        )
        report["candidate"] = asdict(candidate)
        price = Decimal(str(candidate.fields["price_close"].value))
        account = journal.create_account(
            AccountDefinition(
                account_id="issue-408-isolated-paper",
                kind=AccountKind.PAPER,
                name="explicit simulated capital",
                opened_at=datetime(2026, 9, 1, tzinfo=UTC),
            )
        )
        for event_type, quantity, amount in (
            (AccountEventType.OPENING_CASH, Decimal(0), Decimal(10000)),
            (AccountEventType.OPENING_POSITION, Decimal(100), price * 100),
        ):
            journal.append(
                create_account_event(
                    account=account,
                    draft=AccountEventDraft(
                        event_id=event_type.value,
                        event_type=event_type,
                        trade_date="2026-09-30",
                        settlement_date="2026-09-30",
                        recorded_at=datetime.now(UTC),
                        idempotency_key=event_type.value,
                        actor="issue-408-isolated-probe",
                        source=AccountEventSource.PAPER_ENGINE,
                        instrument_id=InstrumentId(candidate.instrument_id)
                        if quantity
                        else None,
                        quantity=quantity,
                        price=price if quantity else Decimal(0),
                        gross_amount=amount,
                    ),
                )
            )
        time.sleep(1)
        ledger = AccountLedgerQuery(journal=journal)
        facts = LiveETFPaperHandoffFacts(
            metadata=metadata,
            readiness=readiness,
            snapshots=snapshots,
            payloads=payloads,
            ledger=ledger,
        ).resolve(
            ETFPaperHandoffRequest(
                allocation_id="not-authorized",
                version_id="not-authorized",
                authorization_id="not-authorized",
                account_id=account.account_id,
                session_id="not-started",
                idempotency_key="probe",
                signal_date="2026-09-30",
                decision_date=datetime.now(UTC).date().isoformat(),
                intended_trade_date="2026-10-08",
                knowledge_cutoff=datetime.now(UTC),
                source_snapshot_id=query.snapshot_id,
                input_snapshot_ids=query.input_snapshot_ids,
            )
        )
        report["handoff_facts"] = asdict(facts)
        report["valuation"] = asdict(
            ledger.get_paper(
                account_id=account.account_id,
                as_of="2026-09-30",
                valuation_prices={InstrumentId(candidate.instrument_id): price},
                recorded_through=datetime.now(UTC),
            ).snapshot
        )
        report["journey_status"] = (
            "BLOCKED: no authorized handoff or execution; "
            + "required rules/currency/restriction absent"
        )
    report["finished_at"] = datetime.now(UTC).isoformat()
    (root / "report.json").write_text(
        json.dumps(report, default=str, ensure_ascii=False, indent=2)
    )
    sys.stdout.write(str(root / "report.json") + "\n")


if __name__ == "__main__":
    main()
