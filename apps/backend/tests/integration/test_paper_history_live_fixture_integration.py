"""PAPER history live-fixture acceptance: real DI, session binding, replay."""

from __future__ import annotations

import tempfile
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import polars as pl
import pytest
from ditto_application.commands.paper_account import (
    CreatePaperAccountCommand,
    CreatePaperAccountHandler,
)
from ditto_application.commands.paper_session import (
    CreatePaperSessionCommand,
    PaperSessionCommandHandler,
)
from ditto_application.exceptions import AppQueryError
from ditto_application.processes.execution.reconcile_paper_account import (
    ReconcilePaperAccount,
)
from ditto_application.queries.portfolio_history import (
    GetPaperHistoryQuery,
    PaperHistoryRequest,
)
from ditto_apps.registry.container import make_app_container
from ditto_data.catalog import DataAssetRef
from ditto_data.catalog.provider_payload import FilesystemProviderPayloadStore
from ditto_data.catalog.source_snapshot import ProviderSnapshot, ProviderSnapshotDraft
from ditto_data.catalog.source_snapshot_store import SQLiteProviderSnapshotStore
from ditto_execution.paper.sqlite_store import SqlitePaperSessionStore
from ditto_execution.storage.sqlite.account_journal import SqliteAccountEventJournal
from ditto_kernel.identity import InstrumentId
from ditto_platform.foundation import SQLiteClient, SQLitePool
from ditto_portfolio.account_ledger import (
    AccountEventDraft,
    AccountEventSource,
    AccountEventType,
    FlowPosition,
    create_account_event,
    ledger_hash,
)

ACCOUNT_ID = "live-paper-history"
OTHER_ACCOUNT_ID = "live-paper-history-other"
SESSION_ID = "live-paper-history-session"
OTHER_SESSION_ID = "live-paper-history-session-other"
INSTRUMENT = 600519
NOW = datetime(2026, 3, 1, 1, 0, tzinfo=UTC)
KNOWLEDGE = datetime(2026, 3, 5, 16, 0, tzinfo=UTC)

_BARS = (
    ("2026-03-02", 10.0),
    ("2026-03-03", 9.5),
    ("2026-03-04", 12.1),
)


def _seed(root: Path) -> str:
    """Retain prices, bootstrap both PAPER accounts, and append engine events."""
    metadata = root / "metadata" / "metadata.sqlite"
    metadata.parent.mkdir(parents=True, exist_ok=True)
    client = SQLiteClient(SQLitePool(str(metadata)))
    trading = root / "trading" / "trading.sqlite"
    trading.parent.mkdir(parents=True, exist_ok=True)
    trading_client = SQLiteClient(SQLitePool(str(trading)))
    try:
        payload = pl.DataFrame(
            {
                "instrument_id": [INSTRUMENT] * len(_BARS),
                "trade_date": [day for day, _ in _BARS],
                "open": [close for _, close in _BARS],
                "high": [close for _, close in _BARS],
                "low": [close for _, close in _BARS],
                "close": [close for _, close in _BARS],
                "volume": [1000.0] * len(_BARS),
                "amount": [10000.0] * len(_BARS),
                "published_at": [
                    datetime.fromisoformat(f"{day}T10:00:00+00:00") for day, _ in _BARS
                ],
                "available_at": [
                    datetime.fromisoformat(f"{day}T10:00:00+00:00") for day, _ in _BARS
                ],
            }
        )
        artifact = FilesystemProviderPayloadStore(root).retain_payload(
            dataset_id="stock_daily",
            source="paper_history_fixture",
            payload=payload,
        )
        snapshot = ProviderSnapshot.create(
            ProviderSnapshotDraft(
                dataset_id="stock_daily",
                source="paper_history_fixture",
                request_start="2026-03-02",
                request_end="2026-03-04",
                schema_version="market.stock_daily.v1",
                checksum=artifact.checksum,
                canonical_asset=DataAssetRef(
                    dataset_id="stock_daily",
                    namespace="market",
                    partition_keys=("trade_date=2026-03-02",),
                ),
                request_parameters_hash="sha256:paper-history-request-v1",
                response_metadata=(("fixture", "paper-history-live"),),
                license_record_id="license:paper-history:v1",
                row_count=artifact.row_count,
                payload_uri=artifact.uri,
                payload_retained=True,
                created_at=NOW,
            )
        )
        SQLiteProviderSnapshotStore(client).append_snapshot(snapshot)

        journal = SqliteAccountEventJournal(trading_client)
        store = SqlitePaperSessionStore(trading_client)
        account_handler = CreatePaperAccountHandler(journal=journal, clock=lambda: NOW)
        session_handler = PaperSessionCommandHandler(
            store=store,
            account_journal=journal,
            clock=lambda: NOW,
            reconciler=ReconcilePaperAccount(store=store, account_journal=journal),
        )
        for account_id in (ACCOUNT_ID, OTHER_ACCOUNT_ID):
            account_handler.handle(
                CreatePaperAccountCommand(
                    account_id=account_id,
                    name="模拟账户" if account_id == ACCOUNT_ID else "另一模拟账户",
                    opened_at=NOW,
                    trade_date="2026-03-02",
                    initial_cash=Decimal("100"),
                    idempotency_key=f"{account_id}:opening",
                )
            )
        for session_id, account_id in (
            (SESSION_ID, ACCOUNT_ID),
            (OTHER_SESSION_ID, OTHER_ACCOUNT_ID),
        ):
            session_handler.create(
                CreatePaperSessionCommand(
                    session_id=session_id,
                    account_id=account_id,
                    strategy_id="strategy-1",
                    trade_date="2026-03-02",
                    idempotency_key=f"{session_id}:create",
                )
            )

        account = journal.get_account(ACCOUNT_ID)
        assert account is not None
        journal.append(
            create_account_event(
                account=account,
                draft=AccountEventDraft(
                    event_type=AccountEventType.BUY,
                    event_id="paper-history-buy",
                    trade_date="2026-03-02",
                    settlement_date="2026-03-02",
                    recorded_at=NOW,
                    idempotency_key="paper-ledger:execution-buy",
                    actor=f"paper-session:{SESSION_ID}",
                    source=AccountEventSource.PAPER_ENGINE,
                    instrument_id=InstrumentId(INSTRUMENT),
                    quantity=Decimal("10"),
                    price=Decimal("10"),
                ),
            )
        )
        journal.append(
            create_account_event(
                account=account,
                draft=AccountEventDraft(
                    event_type=AccountEventType.DIVIDEND,
                    event_id="paper-history-dividend",
                    trade_date="2026-03-03",
                    settlement_date="2026-03-03",
                    recorded_at=NOW,
                    idempotency_key="paper-ledger:corporate-action-dividend",
                    actor="paper-engine:corporate-actions",
                    source=AccountEventSource.PAPER_ENGINE,
                    instrument_id=InstrumentId(INSTRUMENT),
                    gross_amount=Decimal("5"),
                ),
            )
        )
        journal.append(
            create_account_event(
                account=account,
                draft=AccountEventDraft(
                    event_type=AccountEventType.FEE,
                    event_id="paper-history-fee",
                    trade_date="2026-03-03",
                    settlement_date="2026-03-03",
                    recorded_at=NOW,
                    idempotency_key="paper-ledger:custody-fee",
                    actor="paper-engine:fees",
                    source=AccountEventSource.PAPER_ENGINE,
                    gross_amount=Decimal("1"),
                ),
            )
        )
        journal.append(
            create_account_event(
                account=account,
                draft=AccountEventDraft(
                    event_type=AccountEventType.DEPOSIT,
                    event_id="paper-history-deposit",
                    trade_date="2026-03-04",
                    settlement_date="2026-03-04",
                    recorded_at=NOW,
                    idempotency_key="paper-ledger:topup",
                    actor="paper-engine:account-topup",
                    source=AccountEventSource.PAPER_ENGINE,
                    gross_amount=Decimal("100"),
                    flow_position=FlowPosition.START_OF_DAY,
                ),
            )
        )
        store.close()
        journal.close()
        return snapshot.snapshot_id
    finally:
        client.close()
        trading_client.close()


def _request(
    snapshot_id: str,
    revision_hash: str,
    *,
    event_count: int = 5,
    session_id: str = SESSION_ID,
) -> PaperHistoryRequest:
    return PaperHistoryRequest(
        account_id=ACCOUNT_ID,
        session_id=session_id,
        start_date="2026-03-02",
        end_date="2026-03-04",
        knowledge_cutoff=KNOWLEDGE,
        publication_cutoff=KNOWLEDGE,
        source_snapshot_ids=(snapshot_id,),
        ledger_event_count=event_count,
        ledger_hash=revision_hash,
    )


def _revision_hash(root: Path) -> str:
    client = SQLiteClient(SQLitePool(str(root / "trading/trading.sqlite")))
    try:
        journal = SqliteAccountEventJournal(client)
        return ledger_hash(journal.list_events(ACCOUNT_ID))
    finally:
        client.close()


def _append_deposit_correction(root: Path) -> None:
    client = SQLiteClient(SQLitePool(str(root / "trading/trading.sqlite")))
    try:
        journal = SqliteAccountEventJournal(client)
        account = journal.get_account(ACCOUNT_ID)
        assert account is not None
        deposit = next(
            event
            for event in journal.list_events(ACCOUNT_ID)
            if event.event_type is AccountEventType.DEPOSIT
        )
        journal.append(
            create_account_event(
                account=account,
                draft=AccountEventDraft(
                    event_type=AccountEventType.CORRECTION,
                    event_id="paper-history-deposit-correction",
                    trade_date="2026-03-04",
                    settlement_date="2026-03-04",
                    recorded_at=NOW,
                    idempotency_key="paper-ledger:topup-correction",
                    actor="paper-engine:account-topup",
                    source=AccountEventSource.PAPER_ENGINE,
                    gross_amount=Decimal("200"),
                    flow_position=FlowPosition.START_OF_DAY,
                    corrects_event_id=deposit.event_id,
                    replacement_event_type=AccountEventType.DEPOSIT,
                ),
            )
        )
        journal.close()
    finally:
        client.close()


@pytest.mark.integration
def test_paper_history_live_fixture_replays_session_bound_series(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with tempfile.TemporaryDirectory(prefix="ditto-paper-history-") as temporary:
        root = Path(temporary)
        snapshot_id = _seed(root)
        for name, path in {
            "DITTO_STATE_ROOT": root,
            "DITTO_CONFIG_ROOT": root / "config",
            "DITTO_CACHE_ROOT": root / "cache",
            "DITTO_LOG_DIR": root / "logs",
            "SQLITE_PATH": root / "metadata/metadata.sqlite",
            "DITTO_TRADING_SQLITE_PATH": root / "trading/trading.sqlite",
        }.items():
            monkeypatch.setenv(name, str(path))
        monkeypatch.setenv("ENVIRONMENT", "testing")

        revision_hash = _revision_hash(root)
        container = make_app_container()
        try:
            query = container.get(GetPaperHistoryQuery)
            view = query.history(_request(snapshot_id, revision_hash))
            replay = query.history(_request(snapshot_id, revision_hash))

            # A session bound to another account must fail closed, not fall
            # back to reading this account's ledger.
            with pytest.raises(AppQueryError) as conflict:
                query.history(
                    _request(
                        snapshot_id,
                        revision_hash,
                        session_id=OTHER_SESSION_ID,
                    )
                )
            assert (
                conflict.value.details["code"]
                == "PAPER_HISTORY_SESSION_ACCOUNT_MISMATCH"
            )
        finally:
            container.close()

        # 03-02: 10 shares @ 10, no cash. 03-03: ex-div 9.5 + 5 dividend cash
        # - 1 fee = 99. 03-04: 10 @ 12.1 + 104 cash = 225.
        assert [point.total_value for point in view.points] == [
            Decimal("100"),
            Decimal("99.00"),
            Decimal("225.00"),
        ]
        assert [point.cash for point in view.points] == [
            Decimal("0"),
            Decimal("4.00"),
            Decimal("104.00"),
        ]
        # Opening cash and the top-up are external flows; the dividend and
        # the fee stay internal to the series.
        assert [point.external_flow for point in view.points] == [
            Decimal("100.00"),
            Decimal("0"),
            Decimal("100.00"),
        ]
        assert view.points[1].period_return == Decimal("-0.01")
        assert view.points[2].period_return == Decimal("225") / Decimal(
            "199"
        ) - Decimal("1")
        assert view.segments[0].linked_return == (
            Decimal("99") / Decimal("100") * (Decimal("225") / Decimal("199"))
            - Decimal("1")
        )
        assert view.method == "twr-linked-v1"
        assert view.result_id.startswith("paper-history:sha256:")
        assert replay.result_id == view.result_id

        # GET-style replays never append; only the explicit correction does.
        _append_deposit_correction(root)
        new_hash = _revision_hash(root)
        assert new_hash != revision_hash

        container = make_app_container()
        try:
            query = container.get(GetPaperHistoryQuery)
            old = query.history(_request(snapshot_id, revision_hash))
            revised = query.history(_request(snapshot_id, new_hash, event_count=6))
        finally:
            container.close()
        assert old.result_id == view.result_id
        assert old.points[2].total_value == Decimal("225.00")
        assert revised.points[2].total_value == Decimal("325.00")
        assert revised.result_id != view.result_id

        # The read-only replay left the ledger untouched at six events.
        assert len(_events_count(root)) == 6


def _events_count(root: Path) -> tuple[object, ...]:
    client = SQLiteClient(SQLitePool(str(root / "trading/trading.sqlite")))
    try:
        journal = SqliteAccountEventJournal(client)
        events = journal.list_events(ACCOUNT_ID)
        journal.close()
        return events
    finally:
        client.close()
