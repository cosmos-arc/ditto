"""MANUAL history live-fixture acceptance: real DI, retained prices, replay."""

from __future__ import annotations

import tempfile
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import polars as pl
import pytest
from ditto_application.commands.account_ledger import (
    CreateAccountCommand,
    CreateAccountHandler,
    ManualAccountCommandHandler,
    ManualEventInput,
    RecordManualEventCommand,
    TradeEventTerms,
)
from ditto_application.queries.portfolio_history import (
    AccountHistoryRequest,
    GetManualHistoryQuery,
)
from ditto_apps.registry.container import make_app_container
from ditto_data.catalog import DataAssetRef
from ditto_data.catalog.provider_payload import FilesystemProviderPayloadStore
from ditto_data.catalog.source_snapshot import ProviderSnapshot, ProviderSnapshotDraft
from ditto_data.catalog.source_snapshot_store import SQLiteProviderSnapshotStore
from ditto_execution.storage.sqlite.account_journal import SqliteAccountEventJournal
from ditto_kernel.identity import InstrumentId
from ditto_platform.foundation import SQLiteClient, SQLitePool
from ditto_portfolio.account_ledger import (
    AccountEventType,
    FlowPosition,
    ledger_hash,
)

ACCOUNT_ID = "live-manual-history"
INSTRUMENT = 600519
RECORDED_AT = datetime(2026, 3, 1, 1, 0, tzinfo=UTC)
KNOWLEDGE = datetime(2026, 3, 5, 16, 0, tzinfo=UTC)

_BARS = (
    ("2026-03-02", 10.0),
    ("2026-03-03", 11.0),
    ("2026-03-04", 12.1),
)


def _seed(root: Path) -> tuple[str, str]:
    """Retain one price snapshot and append the manual ledger stream."""
    database = root / "metadata" / "metadata.sqlite"
    database.parent.mkdir(parents=True, exist_ok=True)
    client = SQLiteClient(SQLitePool(str(database)))
    trading_database = root / "trading" / "trading.sqlite"
    trading_database.parent.mkdir(parents=True, exist_ok=True)
    trading_client = SQLiteClient(SQLitePool(str(trading_database)))
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
            source="manual_history_fixture",
            payload=payload,
        )
        snapshot = ProviderSnapshot.create(
            ProviderSnapshotDraft(
                dataset_id="stock_daily",
                source="manual_history_fixture",
                request_start="2026-03-02",
                request_end="2026-03-04",
                schema_version="market.stock_daily.v1",
                checksum=artifact.checksum,
                canonical_asset=DataAssetRef(
                    dataset_id="stock_daily",
                    namespace="market",
                    partition_keys=("trade_date=2026-03-02",),
                ),
                request_parameters_hash="sha256:manual-history-request-v1",
                response_metadata=(("fixture", "manual-history-live"),),
                license_record_id="license:manual-history:v1",
                row_count=artifact.row_count,
                payload_uri=artifact.uri,
                payload_retained=True,
                created_at=RECORDED_AT,
            )
        )
        SQLiteProviderSnapshotStore(client).append_snapshot(snapshot)

        journal = SqliteAccountEventJournal(trading_client)
        handlers = ManualAccountCommandHandler(
            journal=journal,
            clock=lambda: RECORDED_AT,
        )
        CreateAccountHandler(journal=journal).handle(
            CreateAccountCommand.manual(
                account_id=ACCOUNT_ID,
                name="手工账户",
                opened_at=RECORDED_AT,
            )
        )
        handlers.record(
            RecordManualEventCommand(
                account_id=ACCOUNT_ID,
                event=ManualEventInput.cash(
                    event_type="opening_cash",
                    trade_date="2026-03-02",
                    settlement_date="2026-03-02",
                    idempotency_key="opening",
                    actor="user:chevy",
                    amount=Decimal("100"),
                ),
            )
        )
        handlers.record(
            RecordManualEventCommand(
                account_id=ACCOUNT_ID,
                event=ManualEventInput.buy_or_sell(
                    side="buy",
                    trade_date="2026-03-02",
                    settlement_date="2026-03-02",
                    idempotency_key="buy",
                    actor="user:chevy",
                    instrument_id=InstrumentId(INSTRUMENT),
                    terms=TradeEventTerms(
                        quantity=Decimal("10"),
                        price=Decimal("10"),
                    ),
                ),
            )
        )
        handlers.record(
            RecordManualEventCommand(
                account_id=ACCOUNT_ID,
                event=ManualEventInput.cash(
                    event_type="deposit",
                    trade_date="2026-03-04",
                    settlement_date="2026-03-04",
                    idempotency_key="deposit",
                    actor="user:chevy",
                    amount=Decimal("100"),
                    flow_position=FlowPosition.START_OF_DAY,
                ),
            )
        )
        events = journal.list_events(ACCOUNT_ID)
        journal.close()
        return snapshot.snapshot_id, ledger_hash(events)
    finally:
        client.close()
        trading_client.close()


def _request(
    snapshot_id: str,
    revision_hash: str,
    *,
    event_count: int = 3,
) -> AccountHistoryRequest:
    return AccountHistoryRequest(
        account_id=ACCOUNT_ID,
        start_date="2026-03-02",
        end_date="2026-03-04",
        knowledge_cutoff=KNOWLEDGE,
        publication_cutoff=KNOWLEDGE,
        source_snapshot_ids=(snapshot_id,),
        ledger_event_count=event_count,
        ledger_hash=revision_hash,
    )


@pytest.mark.integration
def test_manual_history_live_fixture_replays_flow_adjusted_returns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with tempfile.TemporaryDirectory(prefix="ditto-manual-history-") as temporary:
        root = Path(temporary)
        snapshot_id, revision_hash = _seed(root)
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

        container = make_app_container()
        try:
            query = container.get(GetManualHistoryQuery)
            view = query.history(_request(snapshot_id, revision_hash))
            replay = query.history(_request(snapshot_id, revision_hash))
        finally:
            container.close()

        assert [point.total_value for point in view.points] == [
            Decimal("100.00"),
            Decimal("110.00"),
            Decimal("221.00"),
        ]
        assert [point.cash for point in view.points] == [
            Decimal("0.00"),
            Decimal("0.00"),
            Decimal("100.00"),
        ]
        assert view.points[1].period_return == Decimal("0.1")
        assert view.points[2].period_return == Decimal("221") / Decimal(
            "210"
        ) - Decimal("1")
        assert view.points[2].external_flow == Decimal("100.00")
        assert view.segments[0].linked_return == (
            Decimal("11") / Decimal("10") * (Decimal("221") / Decimal("210"))
            - Decimal("1")
        )
        assert view.segments[0].closed_reason == "range_end"
        assert view.method == "twr-linked-v1"
        assert replay.result_id == view.result_id

        # A GET-style replay never appends ledger events.
        trading_client = SQLiteClient(SQLitePool(str(root / "trading/trading.sqlite")))
        try:
            journal = SqliteAccountEventJournal(trading_client)
            assert len(journal.list_events(ACCOUNT_ID)) == 3

            # Appending a correction changes only the new revision; the old
            # result replays byte-identically under its frozen identity.
            journal.append(
                _deposit_correction(
                    journal,
                    gross_amount=Decimal("200"),
                )
            )
            assert ledger_hash(journal.list_events(ACCOUNT_ID)) != revision_hash
        finally:
            trading_client.close()

        container = make_app_container()
        try:
            query = container.get(GetManualHistoryQuery)
            old = query.history(_request(snapshot_id, revision_hash))
            new_hash = ledger_hash_from(root)
            revised = query.history(_request(snapshot_id, new_hash, event_count=4))
        finally:
            container.close()
        assert old.result_id == view.result_id
        assert old.points[2].total_value == Decimal("221.00")
        assert revised.points[2].total_value == Decimal("321.00")
        assert revised.result_id != view.result_id


def ledger_hash_from(root: Path) -> str:
    client = SQLiteClient(SQLitePool(str(root / "trading/trading.sqlite")))
    try:
        journal = SqliteAccountEventJournal(client)
        return ledger_hash(journal.list_events(ACCOUNT_ID))
    finally:
        client.close()


def _deposit_correction(
    journal: SqliteAccountEventJournal,
    *,
    gross_amount: Decimal,
):
    from ditto_portfolio.account_ledger import (
        AccountEventDraft,
        AccountEventSource,
        create_account_event,
    )

    account = journal.get_account(ACCOUNT_ID)
    if account is None:
        raise AssertionError("fixture account is missing")
    deposit = next(
        event
        for event in journal.list_events(ACCOUNT_ID)
        if event.event_type is AccountEventType.DEPOSIT
    )
    return create_account_event(
        account=account,
        draft=AccountEventDraft(
            event_type=AccountEventType.CORRECTION,
            event_id="account-event:manual-history-correction",
            trade_date="2026-03-04",
            settlement_date="2026-03-04",
            recorded_at=RECORDED_AT,
            idempotency_key="deposit-correction",
            actor="user:chevy",
            source=AccountEventSource.MANUAL_ENTRY,
            gross_amount=gross_amount,
            flow_position=FlowPosition.START_OF_DAY,
            corrects_event_id=deposit.event_id,
            replacement_event_type=AccountEventType.DEPOSIT,
        ),
    )
