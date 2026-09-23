"""Isolated live fixture for the three-leg history-comparison browser journey.

Seeds one retained price snapshot (with an invalid 510300 close on 2026-03-04),
two PAPER accounts (one exposed to the gap), one MANUAL account, and two saved
signal packages, then returns the exact identities the UI journey compares.
"""

from __future__ import annotations

import argparse
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import orjson
import polars as pl
from ditto_application.commands.paper_account import (
    CreatePaperAccountCommand,
    CreatePaperAccountHandler,
)
from ditto_application.commands.paper_session import (
    CreatePaperSessionCommand,
    PaperSessionCommandHandler,
)
from ditto_application.processes.execution.reconcile_paper_account import (
    ReconcilePaperAccount,
)
from ditto_application.signal_package_contract import compute_signal_package_checksum
from ditto_data.catalog import DataAssetRef
from ditto_data.catalog.provider_payload import FilesystemProviderPayloadStore
from ditto_data.catalog.source_snapshot import ProviderSnapshot, ProviderSnapshotDraft
from ditto_data.catalog.source_snapshot_store import SQLiteProviderSnapshotStore
from ditto_execution.paper.sqlite_store import SqlitePaperSessionStore
from ditto_execution.storage.sqlite.account_journal import SqliteAccountEventJournal
from ditto_kernel.identity import InstrumentId
from ditto_platform.foundation import SQLiteClient, SQLitePool
from ditto_portfolio.account_ledger import (
    AccountDefinition,
    AccountEvent,
    AccountEventDraft,
    AccountEventSource,
    AccountEventType,
    AccountKind,
    create_account_event,
)
from ditto_strategy.models import (
    ArtifactKind,
    StrategyArtifactRecord,
    StrategySpecRecord,
)
from ditto_strategy.storage.sqlite.services.strategy_artifact_service import (
    StrategyArtifactService,
)
from ditto_strategy.storage.sqlite.strategy_artifact_store import (
    SQLiteStrategyArtifactReader,
    SQLiteStrategyArtifactWriter,
)
from ditto_strategy.storage.sqlite.strategy_spec_store import (
    SQLiteStrategySpecWriter,
)

STRATEGY_ID = "live-history-comparison"
PAPER_ACCOUNT = "cmp-live-paper-main"
PAPER_SESSION = "cmp-live-paper-main-session"
GAP_PAPER_ACCOUNT = "cmp-live-paper-gap"
GAP_PAPER_SESSION = "cmp-live-paper-gap-session"
MANUAL_ACCOUNT = "cmp-live-manual"
NOW = datetime(2026, 3, 1, 1, 0, tzinfo=UTC)
KNOWLEDGE = datetime(2026, 3, 5, 16, 0, tzinfo=UTC)

_BARS = (
    ("2026-03-02", 600519, 10.0),
    ("2026-03-03", 600519, 11.0),
    ("2026-03-04", 600519, 12.1),
    ("2026-03-02", 510300, 20.0),
    ("2026-03-03", 510300, 22.0),
    # An invalid close keeps 2026-03-04 a visible gap row for 510300 holders.
    ("2026-03-04", 510300, 0.0),
)


def _package_record(
    artifact_id: str,
    signal_date: str,
    weights: dict[int, float],
    snapshot_id: str,
) -> StrategyArtifactRecord:
    payload: dict[str, object] = {
        "dataset_snapshot_ids": {"stock_daily": snapshot_id},
        "factor_ids": [],
        "factor_values": {},
        "intents": [],
        "risk_flags": [],
        "selection_reasons": {
            str(instrument): {"target_weight": weight}
            for instrument, weight in weights.items()
        },
        "signal_date": signal_date,
        "strategy_id": STRATEGY_ID,
        "strategy_version": "1",
    }
    return StrategyArtifactRecord(
        artifact_id=artifact_id,
        strategy_id=STRATEGY_ID,
        run_id=f"eod-{signal_date}-{STRATEGY_ID}-1",
        artifact_type=ArtifactKind.SIGNAL_PACKAGE,
        file_path=f"evidence/{artifact_id}.json",
        metadata={
            **payload,
            "schema_version": "1.0",
            "business_payload": payload,
            "batch_key": f"eod-{signal_date}-{STRATEGY_ID}-1",
            "checksum": compute_signal_package_checksum(payload),
            "no_rebalance": True,
            "outcome": "no_rebalance",
        },
        status="active",
        created_at=NOW.isoformat(),
    )


@dataclass(frozen=True)
class _LedgerEventSpec:
    """One fixture ledger row bound to one account and its actor."""

    event_id: str
    event_type: AccountEventType
    source: AccountEventSource
    actor: str
    instrument_id: int | None = None
    quantity: str = "0"
    price: str = "0"
    gross_amount: str = "0"


def _ledger_event(account: AccountDefinition, spec: _LedgerEventSpec) -> AccountEvent:
    return create_account_event(
        account=account,
        draft=AccountEventDraft(
            event_type=spec.event_type,
            event_id=spec.event_id,
            trade_date="2026-03-02",
            settlement_date="2026-03-02",
            recorded_at=NOW,
            idempotency_key=f"idem-{spec.event_id}",
            actor=spec.actor,
            source=spec.source,
            instrument_id=(
                InstrumentId(spec.instrument_id)
                if spec.instrument_id is not None
                else None
            ),
            quantity=Decimal(spec.quantity),
            price=Decimal(spec.price),
            gross_amount=Decimal(spec.gross_amount),
        ),
    )


def _fresh_temporary_root(raw: str) -> Path:
    root = Path(raw).resolve()
    root.mkdir(parents=True, exist_ok=True)
    for child in root.iterdir():
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()
    return root


def seed(root: Path) -> dict[str, object]:
    """Write the isolated fixture and return the exact journey identities."""
    metadata = root / "metadata" / "metadata.sqlite"
    metadata.parent.mkdir(parents=True, exist_ok=True)
    pool = SQLitePool(str(metadata))
    client = SQLiteClient(pool)
    trading = root / "trading" / "trading.sqlite"
    trading.parent.mkdir(parents=True, exist_ok=True)
    trading_client = SQLiteClient(SQLitePool(str(trading)))
    try:
        closes = [row[2] for row in _BARS]
        payload = pl.DataFrame(
            {
                "instrument_id": [row[1] for row in _BARS],
                "trade_date": [row[0] for row in _BARS],
                "open": closes,
                "high": closes,
                "low": closes,
                "close": closes,
                "volume": [1000.0] * len(_BARS),
                "amount": [10000.0] * len(_BARS),
                "published_at": [
                    datetime.fromisoformat(f"{row[0]}T10:00:00+00:00") for row in _BARS
                ],
                "available_at": [
                    datetime.fromisoformat(f"{row[0]}T10:00:00+00:00") for row in _BARS
                ],
            }
        )
        artifact = FilesystemProviderPayloadStore(root).retain_payload(
            dataset_id="stock_daily",
            source="history_comparison_fixture",
            payload=payload,
        )
        snapshot = ProviderSnapshot.create(
            ProviderSnapshotDraft(
                dataset_id="stock_daily",
                source="history_comparison_fixture",
                request_start="2026-03-02",
                request_end="2026-03-04",
                schema_version="market.stock_daily.v1",
                checksum=artifact.checksum,
                canonical_asset=DataAssetRef(
                    dataset_id="stock_daily",
                    namespace="market",
                    partition_keys=("trade_date=2026-03-02",),
                ),
                request_parameters_hash="sha256:history-comparison-request-v1",
                response_metadata=(("fixture", "history-comparison-journey"),),
                license_record_id="license:history-comparison:v1",
                row_count=artifact.row_count,
                payload_uri=artifact.uri,
                payload_retained=True,
                created_at=NOW,
            )
        )
        SQLiteProviderSnapshotStore(client).append_snapshot(snapshot)

        writer = SQLiteStrategyArtifactWriter(pool)
        writer.init_schema()
        service = StrategyArtifactService(
            reader=SQLiteStrategyArtifactReader(pool),
            writer=writer,
        )
        service.save_artifact(
            _package_record(
                "cmp-journey-a",
                "2026-03-02",
                {600519: 0.6, 510300: 0.4},
                snapshot.snapshot_id,
            )
        )
        service.save_artifact(
            _package_record(
                "cmp-journey-b", "2026-03-03", {600519: 1.0}, snapshot.snapshot_id
            )
        )

        # The strategies catalog feeds the picker; a bare spec row is enough
        # for the comparison journey (targets come from signal packages).
        spec_writer = SQLiteStrategySpecWriter(pool)
        spec_writer.init_schema()
        spec_writer.save(
            StrategySpecRecord(
                strategy_id=STRATEGY_ID,
                name="共同区间比较策略",
                spec_json={"kind": "history-comparison-fixture"},
                version=1,
                created_at=NOW.isoformat(),
                tags=(),
            )
        )

        journal = SqliteAccountEventJournal(trading_client)
        store = SqlitePaperSessionStore(trading_client)
        account_handler = CreatePaperAccountHandler(journal=journal, clock=lambda: NOW)
        session_handler = PaperSessionCommandHandler(
            store=store,
            account_journal=journal,
            clock=lambda: NOW,
            reconciler=ReconcilePaperAccount(store=store, account_journal=journal),
        )
        for account_id in (PAPER_ACCOUNT, GAP_PAPER_ACCOUNT):
            account_handler.handle(
                CreatePaperAccountCommand(
                    account_id=account_id,
                    name="比较模拟账户"
                    if account_id == PAPER_ACCOUNT
                    else "缺口模拟账户",
                    opened_at=NOW,
                    trade_date="2026-03-02",
                    initial_cash=Decimal("100"),
                    idempotency_key=f"{account_id}:opening",
                )
            )
        for session_id, account_id in (
            (PAPER_SESSION, PAPER_ACCOUNT),
            (GAP_PAPER_SESSION, GAP_PAPER_ACCOUNT),
        ):
            session_handler.create(
                CreatePaperSessionCommand(
                    session_id=session_id,
                    account_id=account_id,
                    strategy_id=STRATEGY_ID,
                    trade_date="2026-03-02",
                    idempotency_key=f"{session_id}:create",
                )
            )

        main_paper = journal.get_account(PAPER_ACCOUNT)
        assert main_paper is not None
        journal.append(
            _ledger_event(
                main_paper,
                _LedgerEventSpec(
                    event_id="cmp-main-buy",
                    event_type=AccountEventType.BUY,
                    source=AccountEventSource.PAPER_ENGINE,
                    actor=f"paper-session:{PAPER_SESSION}",
                    instrument_id=600519,
                    quantity="5",
                    price="10",
                ),
            )
        )
        gap_paper = journal.get_account(GAP_PAPER_ACCOUNT)
        assert gap_paper is not None
        journal.append(
            _ledger_event(
                gap_paper,
                _LedgerEventSpec(
                    event_id="cmp-gap-buy",
                    event_type=AccountEventType.BUY,
                    source=AccountEventSource.PAPER_ENGINE,
                    actor=f"paper-session:{GAP_PAPER_SESSION}",
                    instrument_id=510300,
                    quantity="5",
                    price="20",
                ),
            )
        )
        journal.create_account(
            AccountDefinition(
                account_id=MANUAL_ACCOUNT,
                kind=AccountKind.MANUAL,
                name="比较实盘账户",
                opened_at=NOW,
            )
        )
        manual = journal.get_account(MANUAL_ACCOUNT)
        assert manual is not None
        journal.append(
            _ledger_event(
                manual,
                _LedgerEventSpec(
                    event_id="cmp-manual-opening",
                    event_type=AccountEventType.OPENING_CASH,
                    source=AccountEventSource.MANUAL_ENTRY,
                    actor="user:fixture",
                    gross_amount="100",
                ),
            )
        )
        journal.append(
            _ledger_event(
                manual,
                _LedgerEventSpec(
                    event_id="cmp-manual-buy",
                    event_type=AccountEventType.BUY,
                    source=AccountEventSource.MANUAL_ENTRY,
                    actor="user:fixture",
                    instrument_id=600519,
                    quantity="8",
                    price="10",
                ),
            )
        )
        store.close()
        journal.close()
        return {
            "data_root": str(root),
            "strategy_id": STRATEGY_ID,
            "paper_account_id": PAPER_ACCOUNT,
            "paper_session_id": PAPER_SESSION,
            "gap_paper_account_id": GAP_PAPER_ACCOUNT,
            "gap_paper_session_id": GAP_PAPER_SESSION,
            "manual_account_id": MANUAL_ACCOUNT,
            "snapshot_id": snapshot.snapshot_id,
            "start_date": "2026-03-02",
            "end_date": "2026-03-04",
            "knowledge_cutoff": KNOWLEDGE.isoformat(),
            "model_initial_capital": "100",
            "frontend_path": "/portfolio/?mode=comparison",
            # Model 100→110→121 (+21%); Paper 100→105→110.50 (+10.5%);
            # Manual 100→108→116.80 (+16.8%).
            "expected_window": {
                "start": "2026-03-02",
                "end": "2026-03-04",
                "model_return": "+21.00%",
                "paper_return": "+10.50%",
                "manual_return": "+16.80%",
            },
            # The gap account holds only 510300: its 03-04 invalid close ends
            # the common window at 03-03 with single-digit-percent returns.
            "expected_gap_window": {
                "start": "2026-03-02",
                "end": "2026-03-03",
                "model_return": "+10.00%",
                "paper_return": "+10.00%",
                "manual_return": "+8.00%",
            },
        }
    finally:
        client.close()
        trading_client.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", required=True)
    args = parser.parse_args()
    root = _fresh_temporary_root(args.data_root)
    print(orjson.dumps(seed(root), option=orjson.OPT_SORT_KEYS).decode())


if __name__ == "__main__":
    main()
