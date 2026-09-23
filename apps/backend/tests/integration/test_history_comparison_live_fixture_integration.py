"""History comparison live-fixture acceptance: real DI over three legs."""

from __future__ import annotations

import sqlite3
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
from ditto_application.processes.execution.reconcile_paper_account import (
    ReconcilePaperAccount,
)
from ditto_application.queries.history_comparison import (
    GetHistoryComparisonQuery,
    HistoryComparisonRequest,
)
from ditto_application.signal_package_contract import compute_signal_package_checksum
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
    AccountDefinition,
    AccountEvent,
    AccountEventDraft,
    AccountEventSource,
    AccountEventType,
    AccountKind,
    create_account_event,
    ledger_hash,
)
from ditto_strategy.models import ArtifactKind, StrategyArtifactRecord
from ditto_strategy.storage.sqlite.services.strategy_artifact_service import (
    StrategyArtifactService,
)
from ditto_strategy.storage.sqlite.strategy_artifact_store import (
    SQLiteStrategyArtifactReader,
    SQLiteStrategyArtifactWriter,
)

STRATEGY_ID = "live-history-comparison"
PAPER_ACCOUNT = "live-cmp-paper"
PAPER_SESSION = "live-cmp-paper-session"
MANUAL_ACCOUNT = "live-cmp-manual"
NOW = datetime(2026, 3, 1, 1, 0, tzinfo=UTC)
KNOWLEDGE = datetime(2026, 3, 5, 16, 0, tzinfo=UTC)
_D = Decimal

_BARS = (
    ("2026-03-02", 600519, 10.0),
    ("2026-03-03", 600519, 11.0),
    ("2026-03-04", 600519, 12.1),
    ("2026-03-02", 510300, 20.0),
    ("2026-03-03", 510300, 22.0),
    ("2026-03-04", 510300, 20.0),
)


def _closes(gap: bool) -> list[float]:
    """510300's 03-04 close degrades to an invalid row in the gap variant."""
    return [
        0.0 if gap and row[1] == 510300 and row[0] == "2026-03-04" else row[2]
        for row in _BARS
    ]


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


def _event(
    account: AccountDefinition,
    event_id: str,
    event_type: AccountEventType,
    *,
    trade_date: str = "2026-03-02",
    instrument_id: int | None = None,
    quantity: str = "0",
    price: str = "0",
    gross_amount: str = "0",
    source: AccountEventSource,
    actor: str,
) -> AccountEvent:
    return create_account_event(
        account=account,
        draft=AccountEventDraft(
            event_type=event_type,
            event_id=event_id,
            trade_date=trade_date,
            settlement_date=trade_date,
            recorded_at=NOW,
            idempotency_key=f"idem-{event_id}",
            actor=actor,
            source=source,
            instrument_id=(
                InstrumentId(instrument_id) if instrument_id is not None else None
            ),
            quantity=_D(quantity),
            price=_D(price),
            gross_amount=_D(gross_amount),
        ),
    )


def _seed(root: Path, *, gap: bool = False, manual_start: str = "2026-03-02") -> str:
    """Retain prices and persist every leg's real inputs."""
    metadata = root / "metadata" / "metadata.sqlite"
    metadata.parent.mkdir(parents=True, exist_ok=True)
    pool = SQLitePool(str(metadata))
    client = SQLiteClient(pool)
    trading = root / "trading" / "trading.sqlite"
    trading.parent.mkdir(parents=True, exist_ok=True)
    trading_client = SQLiteClient(SQLitePool(str(trading)))
    try:
        closes = _closes(gap)
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
                response_metadata=(("fixture", "history-comparison-live"),),
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
                "cmp-live-a",
                "2026-03-02",
                {600519: 0.6, 510300: 0.4},
                snapshot.snapshot_id,
            )
        )
        service.save_artifact(
            _package_record(
                "cmp-live-b", "2026-03-03", {600519: 1.0}, snapshot.snapshot_id
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
        account_handler.handle(
            CreatePaperAccountCommand(
                account_id=PAPER_ACCOUNT,
                name="比较模拟账户",
                opened_at=NOW,
                trade_date="2026-03-02",
                initial_cash=_D("100"),
                idempotency_key=f"{PAPER_ACCOUNT}:opening",
            )
        )
        session_handler.create(
            CreatePaperSessionCommand(
                session_id=PAPER_SESSION,
                account_id=PAPER_ACCOUNT,
                strategy_id=STRATEGY_ID,
                trade_date="2026-03-02",
                idempotency_key=f"{PAPER_SESSION}:create",
            )
        )
        paper = journal.get_account(PAPER_ACCOUNT)
        assert paper is not None
        for event_id, instrument, quantity, price in (
            ("cmp-paper-buy-600519", 600519, "5", "10"),
            ("cmp-paper-buy-510300", 510300, "2", "20"),
        ):
            journal.append(
                _event(
                    paper,
                    event_id,
                    AccountEventType.BUY,
                    instrument_id=instrument,
                    quantity=quantity,
                    price=price,
                    source=AccountEventSource.PAPER_ENGINE,
                    actor=f"paper-session:{PAPER_SESSION}",
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
            _event(
                manual,
                "cmp-manual-opening",
                AccountEventType.OPENING_CASH,
                trade_date=manual_start,
                gross_amount="100",
                source=AccountEventSource.MANUAL_ENTRY,
                actor="user:fixture",
            )
        )
        journal.append(
            _event(
                manual,
                "cmp-manual-buy",
                AccountEventType.BUY,
                trade_date=manual_start,
                instrument_id=600519,
                quantity="8",
                price="10",
                source=AccountEventSource.MANUAL_ENTRY,
                actor="user:fixture",
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
    *,
    paper_ledger_event_count: int | None = None,
    paper_ledger_hash: str | None = None,
    manual_ledger_event_count: int | None = None,
    manual_ledger_hash: str | None = None,
    benchmark_symbol: str | None = None,
    benchmark_type: str | None = None,
) -> HistoryComparisonRequest:
    return HistoryComparisonRequest(
        strategy_id=STRATEGY_ID,
        paper_account_id=PAPER_ACCOUNT,
        paper_session_id=PAPER_SESSION,
        manual_account_id=MANUAL_ACCOUNT,
        start_date="2026-03-02",
        end_date="2026-03-04",
        model_initial_capital=_D("100"),
        knowledge_cutoff=KNOWLEDGE,
        publication_cutoff=KNOWLEDGE,
        source_snapshot_ids=(snapshot_id,),
        paper_ledger_event_count=paper_ledger_event_count,
        paper_ledger_hash=paper_ledger_hash,
        manual_ledger_event_count=manual_ledger_event_count,
        manual_ledger_hash=manual_ledger_hash,
        benchmark_symbol=benchmark_symbol,
        benchmark_type=benchmark_type,
    )


def _store_state(root: Path) -> tuple[tuple[str, ...], ...]:
    """Account/session rows plus retained payloads plus artifact statuses."""

    def table_rows(database: Path, query: str) -> tuple[str, ...]:
        connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
        try:
            return tuple(sorted(str(row) for row in connection.execute(query)))
        finally:
            connection.close()

    def payload_files(directory: Path) -> tuple[str, ...]:
        return (
            tuple(sorted(path.name for path in directory.rglob("*") if path.is_file()))
            if directory.exists()
            else ()
        )

    trading = (
        table_rows(root / "trading/trading.sqlite", "SELECT * FROM paper_sessions"),
        table_rows(
            root / "trading/trading.sqlite",
            "SELECT event_id FROM account_journal_events",
        ),
        table_rows(
            root / "trading/trading.sqlite",
            "SELECT account_id FROM account_journal_accounts",
        ),
    )
    metadata = table_rows(
        root / "metadata/metadata.sqlite",
        "SELECT artifact_id, status FROM strategy_artifact",
    )
    return (*trading, metadata, payload_files(root / "payloads"))


def _container_env(monkeypatch: pytest.MonkeyPatch, root: Path) -> None:
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


def _revisions(root: Path) -> dict[str, tuple[int, str]]:
    client = SQLiteClient(SQLitePool(str(root / "trading/trading.sqlite")))
    try:
        journal = SqliteAccountEventJournal(client)
        return {
            account_id: (
                len(journal.list_events(account_id)),
                ledger_hash(journal.list_events(account_id)),
            )
            for account_id in (PAPER_ACCOUNT, MANUAL_ACCOUNT)
        }
    finally:
        client.close()


@pytest.mark.integration
def test_history_comparison_live_fixture_composes_three_legs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with tempfile.TemporaryDirectory(prefix="ditto-history-comparison-") as temporary:
        root = Path(temporary)
        snapshot_id = _seed(root)
        _container_env(monkeypatch, root)

        state_before = _store_state(root)
        revisions = _revisions(root)
        container = make_app_container()
        try:
            query = container.get(GetHistoryComparisonQuery)
            view = query.history(_request(snapshot_id))
            replay = query.history(_request(snapshot_id))
        finally:
            container.close()
        assert _store_state(root) == state_before

        # Model 100→110→121; Paper 100→109→110.50; Manual 100→108→116.80.
        assert view.status == "comparable"
        assert view.result_id.startswith("history-comparison:sha256:")
        assert view.method == "twr-linked-v1"
        assert view.currency == "CNY"
        assert view.comparison_policy_version == "common-window-twr-v1"
        assert [(run.start_date, run.end_date) for run in view.runs] == [
            ("2026-03-02", "2026-03-04")
        ]
        run = view.runs[0]
        assert [point.on_date for point in run.points] == [
            "2026-03-02",
            "2026-03-03",
            "2026-03-04",
        ]
        assert run.points[2].growth["model"] == _D("1.21")
        assert run.points[2].growth["paper"] == _D("1.09") * (_D("110.5") / _D("109"))
        assert run.points[2].growth["manual"] == _D("1.08") * (_D("116.8") / _D("108"))
        assert run.points[2].assets == {
            "model": _D("121.00"),
            "paper": _D("110.50"),
            "manual": _D("116.80"),
        }
        assert run.window_returns == {
            "model": _D("1.21") - _D("1"),
            "paper": _D("1.09") * (_D("110.5") / _D("109")) - _D("1"),
            "manual": _D("1.08") * (_D("116.8") / _D("108")) - _D("1"),
        }
        legs = {leg.kind: leg for leg in view.legs}
        assert legs["paper"].ledger_revision is not None
        assert (
            legs["paper"].ledger_revision.event_count,
            legs["paper"].ledger_revision.ledger_hash,
        ) == revisions[PAPER_ACCOUNT]
        assert legs["manual"].ledger_revision is not None
        assert (
            legs["manual"].ledger_revision.event_count,
            legs["manual"].ledger_revision.ledger_hash,
        ) == revisions[MANUAL_ACCOUNT]
        assert legs["model"].target_count == 2
        assert replay.result_id == view.result_id


@pytest.mark.integration
def test_history_comparison_live_fixture_pinned_revisions_replay_after_correction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with tempfile.TemporaryDirectory(
        prefix="ditto-history-comparison-pin-"
    ) as temporary:
        root = Path(temporary)
        snapshot_id = _seed(root)
        _container_env(monkeypatch, root)
        revisions = _revisions(root)

        container = make_app_container()
        try:
            query = container.get(GetHistoryComparisonQuery)
            first = query.history(_request(snapshot_id))
        finally:
            container.close()

        # A future correction lands on both ledgers after the compared range.
        client = SQLiteClient(SQLitePool(str(root / "trading/trading.sqlite")))
        try:
            journal = SqliteAccountEventJournal(client)
            for account_id, source in (
                (PAPER_ACCOUNT, AccountEventSource.PAPER_ENGINE),
                (MANUAL_ACCOUNT, AccountEventSource.MANUAL_ENTRY),
            ):
                account = journal.get_account(account_id)
                assert account is not None
                journal.append(
                    _event(
                        account,
                        f"cmp-{account_id}-deposit-late",
                        AccountEventType.DEPOSIT,
                        trade_date="2026-03-09",
                        gross_amount="500",
                        source=source,
                        actor="user:fixture",
                    )
                )
            journal.close()
        finally:
            client.close()

        container = make_app_container()
        try:
            query = container.get(GetHistoryComparisonQuery)
            pinned = query.history(
                _request(
                    snapshot_id,
                    paper_ledger_event_count=revisions[PAPER_ACCOUNT][0],
                    paper_ledger_hash=revisions[PAPER_ACCOUNT][1],
                    manual_ledger_event_count=revisions[MANUAL_ACCOUNT][0],
                    manual_ledger_hash=revisions[MANUAL_ACCOUNT][1],
                )
            )
            unpinned = query.history(_request(snapshot_id))
        finally:
            container.close()

        assert pinned.result_id == first.result_id
        assert pinned.runs == first.runs
        assert pinned.legs == first.legs
        assert unpinned.result_id != first.result_id
        pinned_legs = {leg.kind: leg for leg in pinned.legs}
        assert pinned_legs["paper"].ledger_revision is not None
        assert (
            pinned_legs["paper"].ledger_revision.event_count,
            pinned_legs["paper"].ledger_revision.ledger_hash,
        ) == revisions[PAPER_ACCOUNT]
        assert pinned_legs["manual"].ledger_revision is not None
        assert (
            pinned_legs["manual"].ledger_revision.event_count,
            pinned_legs["manual"].ledger_revision.ledger_hash,
        ) == revisions[MANUAL_ACCOUNT]


@pytest.mark.integration
def test_history_comparison_live_fixture_overlays_declared_benchmark(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with tempfile.TemporaryDirectory(
        prefix="ditto-history-comparison-benchmark-"
    ) as temporary:
        root = Path(temporary)
        snapshot_id = _seed(root)
        _container_env(monkeypatch, root)

        container = make_app_container()
        try:
            query = container.get(GetHistoryComparisonQuery)
            plain = query.history(_request(snapshot_id))
            benchmarked = query.history(
                _request(
                    snapshot_id,
                    benchmark_symbol="510300",
                    benchmark_type="price",
                )
            )
            replay = query.history(
                _request(
                    snapshot_id,
                    benchmark_symbol="510300",
                    benchmark_type="price",
                )
            )
        finally:
            container.close()

        assert plain.benchmark is None
        # The retained snapshot prices 510300 at 20.0/22.0/20.0.
        assert benchmarked.benchmark is not None
        benchmark = benchmarked.benchmark
        assert benchmark.symbol == "510300"
        assert benchmark.type == "price"
        assert benchmark.currency == "CNY"
        assert benchmark.empty_reason is None
        assert benchmarked.runs == plain.runs
        assert benchmarked.status == plain.status
        assert benchmarked.result_id != plain.result_id
        assert replay.result_id == benchmarked.result_id
        overlay_run = benchmark.runs[0]
        assert (overlay_run.start_date, overlay_run.end_date) == (
            "2026-03-02",
            "2026-03-04",
        )
        assert [point.growth for point in overlay_run.points] == [
            _D("1"),
            _D("22") / _D("20"),
            _D("1"),
        ]
        assert overlay_run.window_return == _D("0")


@pytest.mark.integration
def test_history_comparison_live_fixture_invisible_benchmark_is_explicit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with tempfile.TemporaryDirectory(
        prefix="ditto-history-comparison-benchmark-empty-"
    ) as temporary:
        root = Path(temporary)
        snapshot_id = _seed(root)
        _container_env(monkeypatch, root)

        container = make_app_container()
        try:
            query = container.get(GetHistoryComparisonQuery)
            view = query.history(
                _request(snapshot_id, benchmark_symbol="999999", benchmark_type="price")
            )
        finally:
            container.close()

        assert view.status == "comparable"
        assert view.benchmark is not None
        assert view.benchmark.empty_reason == "benchmark_price_not_visible"
        assert all(
            point.growth is None for run in view.benchmark.runs for point in run.points
        )


@pytest.mark.integration
def test_history_comparison_live_fixture_gap_limits_the_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with tempfile.TemporaryDirectory(
        prefix="ditto-history-comparison-gap-"
    ) as temporary:
        root = Path(temporary)
        snapshot_id = _seed(root, gap=True)
        _container_env(monkeypatch, root)

        container = make_app_container()
        try:
            query = container.get(GetHistoryComparisonQuery)
            view = query.history(_request(snapshot_id))
        finally:
            container.close()

        # 510300's invalid 03-04 close gaps the PAPER leg (it still holds the
        # ETF), so the common window stops at 03-03 and never links the gap.
        assert view.status == "comparable"
        assert [(run.start_date, run.end_date) for run in view.runs] == [
            ("2026-03-02", "2026-03-03")
        ]
        assert view.runs[0].window_returns["model"] == _D("0.1")
        assert view.runs[0].window_returns["paper"] == _D("0.09")
        assert view.runs[0].window_returns["manual"] == _D("0.08")
        paper_leg = next(leg for leg in view.legs if leg.kind == "paper")
        assert paper_leg.gap_count == 1


@pytest.mark.integration
def test_history_comparison_live_fixture_no_overlap_is_incomparable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with tempfile.TemporaryDirectory(
        prefix="ditto-history-comparison-empty-"
    ) as temporary:
        root = Path(temporary)
        snapshot_id = _seed(root, manual_start="2026-03-10")
        _container_env(monkeypatch, root)

        container = make_app_container()
        try:
            query = container.get(GetHistoryComparisonQuery)
            view = query.history(_request(snapshot_id))
        finally:
            container.close()

        assert view.status == "incomparable"
        assert view.empty_reason == "no_common_valuation_dates"
        assert view.runs == ()
        manual_leg = next(leg for leg in view.legs if leg.kind == "manual")
        assert manual_leg.point_count == 0
