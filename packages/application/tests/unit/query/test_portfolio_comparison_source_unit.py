"""Live comparison source joins only checksum-bound and PIT-visible facts."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from ditto_application.exceptions import AppQueryError
from ditto_application.queries.account_ledger import AccountLedgerQuery
from ditto_application.queries.portfolio_comparison import PortfolioComparisonRequest
from ditto_application.queries.portfolio_comparison_source import (
    LivePortfolioComparisonSource,
)
from ditto_application.signal_package_contract import compute_signal_package_checksum
from ditto_data.catalog import DataAssetRef
from ditto_data.catalog.source_snapshot import (
    ProviderSnapshot,
    ProviderSnapshotDraft,
)
from ditto_data.query.contracts import PITQueryContext
from ditto_execution.paper.session import (
    InMemoryPaperSessionStore,
    PaperSession,
    PaperSessionStatus,
)
from ditto_features.technical_analysis.contracts import TechnicalBar
from ditto_kernel.identity import InstrumentId
from ditto_portfolio.account_ledger import (
    AccountDefinition,
    AccountEvent,
    AccountEventDraft,
    AccountEventSource,
    AccountEventType,
    AccountKind,
    create_account_event,
)
from ditto_strategy.models import ArtifactKind, StrategyArtifactRecord

_AS_OF = "2026-08-31"
_NOW = datetime(2026, 8, 31, 8, 0, tzinfo=UTC)
_CUTOFF = datetime(2026, 8, 31, 9, 0, tzinfo=UTC)


class _ArtifactReader:
    def __init__(self, artifact: StrategyArtifactRecord) -> None:
        self._artifact = artifact

    def list_by_strategy(self, strategy_id: str) -> list[StrategyArtifactRecord]:
        return [self._artifact] if strategy_id == self._artifact.strategy_id else []


class _AccountJournal:
    def __init__(
        self,
        accounts: tuple[AccountDefinition, ...],
        events: tuple[AccountEvent, ...],
    ) -> None:
        self._accounts = {account.account_id: account for account in accounts}
        self._events = events

    def create_account(self, account: AccountDefinition) -> AccountDefinition:
        raise AssertionError("comparison query must not create accounts")

    def get_account(self, account_id: str) -> AccountDefinition | None:
        return self._accounts.get(account_id)

    def append(self, event: AccountEvent) -> AccountEvent:
        raise AssertionError("comparison query must not append ledger events")

    def get_event(self, account_id: str, event_id: str) -> AccountEvent | None:
        return next(
            (
                event
                for event in self._events
                if event.account_id == account_id and event.event_id == event_id
            ),
            None,
        )

    def find_by_idempotency_key(
        self,
        account_id: str,
        idempotency_key: str,
    ) -> AccountEvent | None:
        return next(
            (
                event
                for event in self._events
                if event.account_id == account_id
                and event.idempotency_key == idempotency_key
            ),
            None,
        )

    def list_events(self, account_id: str) -> tuple[AccountEvent, ...]:
        return tuple(event for event in self._events if event.account_id == account_id)


class _SnapshotReader:
    def __init__(self, snapshot: ProviderSnapshot) -> None:
        self._snapshot = snapshot

    def get_snapshot(self, snapshot_id: str) -> ProviderSnapshot | None:
        return self._snapshot if snapshot_id == self._snapshot.snapshot_id else None


class _ValuationSource:
    def __init__(self, snapshot_id: str) -> None:
        self._snapshot_id = snapshot_id
        self.contexts: list[PITQueryContext] = []

    def load(
        self,
        context: PITQueryContext,
        *,
        instrument_id: InstrumentId,
        instrument_code: str,
    ) -> tuple[TechnicalBar, ...]:
        self.contexts.append(context)
        assert instrument_code == str(instrument_id)
        price = {1: 12.0, 2: 20.0}[int(instrument_id)]
        return (
            TechnicalBar(
                occurred_at=datetime(2026, 8, 31, 7, 0, tzinfo=UTC),
                knowledge_at=_NOW,
                publication_at=_NOW,
                source_snapshot_id=self._snapshot_id,
                open=price,
                high=price,
                low=price,
                close=price,
                volume=1000.0,
                turnover=10000.0,
                adjustment_factor=1.0,
                suspended=False,
            ),
        )


def _snapshot() -> ProviderSnapshot:
    return ProviderSnapshot.create(
        ProviderSnapshotDraft(
            dataset_id="stock_daily",
            source="fixture",
            request_start=_AS_OF,
            request_end=_AS_OF,
            schema_version="market.stock_daily.v1",
            checksum="sha256:retained-bars",
            canonical_asset=DataAssetRef(
                dataset_id="stock_daily",
                namespace="market",
                partition_keys=(f"trade_date={_AS_OF}",),
            ),
            request_parameters_hash="sha256:request",
            response_metadata=(("fixture", "portfolio-comparison"),),
            license_record_id="license:fixture",
            row_count=2,
            payload_uri="fixtures/stock-daily.parquet",
            payload_retained=True,
            created_at=_NOW,
        )
    )


def _artifact(
    snapshot_id: str,
    *,
    target_weight: object = 0.6,
) -> StrategyArtifactRecord:
    payload: dict[str, object] = {
        "dataset_snapshot_ids": {"stock_daily": snapshot_id},
        "factor_ids": [],
        "factor_values": {},
        "intents": [],
        "risk_flags": [],
        "selection_reasons": {
            "1": {"target_weight": target_weight},
            "2": {"target_weight": 0.3},
        },
        "signal_date": _AS_OF,
        "strategy_id": "strategy-a",
        "strategy_version": "1",
    }
    checksum = compute_signal_package_checksum(payload)
    return StrategyArtifactRecord(
        artifact_id="model-a",
        strategy_id="strategy-a",
        run_id="run-a",
        artifact_type=ArtifactKind.SIGNAL_PACKAGE,
        file_path="signal-package.json",
        metadata={
            **payload,
            "schema_version": "1.0",
            "business_payload": payload,
            "batch_key": f"eod-{_AS_OF}-strategy-a-1",
            "checksum": checksum,
            "no_rebalance": True,
            "outcome": "no_rebalance",
        },
        status="active",
        created_at=_NOW.isoformat(),
    )


def _account_fixture() -> tuple[
    tuple[AccountDefinition, ...], tuple[AccountEvent, ...]
]:
    paper = AccountDefinition(
        account_id="paper-a",
        kind=AccountKind.PAPER,
        name="Paper A",
        opened_at=_NOW,
    )
    manual = AccountDefinition(
        account_id="manual-a",
        kind=AccountKind.MANUAL,
        name="Manual A",
        opened_at=_NOW,
    )
    events: list[AccountEvent] = []
    for account, source, quantity in (
        (paper, AccountEventSource.PAPER_ENGINE, Decimal("100")),
        (manual, AccountEventSource.MANUAL_ENTRY, Decimal("50")),
    ):
        events.append(
            create_account_event(
                account=account,
                draft=AccountEventDraft(
                    event_type=AccountEventType.OPENING_CASH,
                    event_id=f"{account.account_id}-cash",
                    trade_date=_AS_OF,
                    settlement_date=_AS_OF,
                    recorded_at=_NOW,
                    idempotency_key=f"{account.account_id}-cash",
                    actor="fixture",
                    source=source,
                    gross_amount=Decimal("100000"),
                ),
            )
        )
        events.append(
            create_account_event(
                account=account,
                draft=AccountEventDraft(
                    event_type=AccountEventType.BUY,
                    event_id=f"{account.account_id}-buy",
                    trade_date=_AS_OF,
                    settlement_date="2026-09-01",
                    recorded_at=_NOW,
                    idempotency_key=f"{account.account_id}-buy",
                    actor="fixture",
                    source=source,
                    instrument_id=InstrumentId(1),
                    quantity=quantity,
                    price=Decimal("10"),
                ),
            )
        )
    return (paper, manual), tuple(events)


def _request(
    snapshot_id: str, *, cutoff: datetime = _CUTOFF
) -> PortfolioComparisonRequest:
    return PortfolioComparisonRequest(
        strategy_id="strategy-a",
        model_portfolio_id="model-a",
        paper_account_id="paper-a",
        manual_account_id="manual-a",
        paper_session_id="session-a",
        as_of=_AS_OF,
        knowledge_cutoff=cutoff,
        publication_cutoff=cutoff,
        source_snapshot_ids=(snapshot_id,),
    )


def _source(
    snapshot: ProviderSnapshot,
    *,
    target_weight: object = 0.6,
) -> tuple[LivePortfolioComparisonSource, _ValuationSource]:
    accounts, events = _account_fixture()
    paper_store = InMemoryPaperSessionStore()
    paper_store.create_session(
        PaperSession(
            session_id="session-a",
            account_id="paper-a",
            strategy_id="strategy-a",
            trade_date=_AS_OF,
            status=PaperSessionStatus.RUNNING,
            revision=1,
            created_at=_NOW,
            updated_at=_NOW,
        )
    )
    valuation_source = _ValuationSource(snapshot.snapshot_id)
    return (
        LivePortfolioComparisonSource(
            artifact_reader=_ArtifactReader(
                _artifact(snapshot.snapshot_id, target_weight=target_weight)
            ),
            account_query=AccountLedgerQuery(journal=_AccountJournal(accounts, events)),
            paper_store=paper_store,
            snapshot_reader=_SnapshotReader(snapshot),
            valuation_source=valuation_source,
        ),
        valuation_source,
    )


def test_live_source_joins_package_ledgers_session_and_exact_pit_prices() -> None:
    snapshot = _snapshot()
    source, valuation_source = _source(snapshot)

    result = source.load(_request(snapshot.snapshot_id))

    assert result.model.total_value == Decimal("100200.00")
    assert result.paper.total_value == Decimal("100200.00")
    assert result.manual.total_value == Decimal("100100.00")
    assert tuple(position.market_value for position in result.model.positions) == (
        Decimal("60120.00"),
        Decimal("30060.00"),
    )
    assert result.model.cash == Decimal("10020.00")
    assert result.model.valuation_snapshot_id.startswith("portfolio-valuation:sha256:")
    assert result.paper.valuation_snapshot_id == result.model.valuation_snapshot_id
    assert result.manual.valuation_snapshot_id == result.model.valuation_snapshot_id
    assert result.paper_attribution.unfilled_bps == Decimal("9000.0")
    assert len(valuation_source.contexts) == 2
    assert all(
        context.source_snapshots[0].source_snapshot_ids == (snapshot.snapshot_id,)
        for context in valuation_source.contexts
    )


def test_live_source_rejects_future_snapshot_before_reading_payload() -> None:
    snapshot = _snapshot()
    source, valuation_source = _source(snapshot)

    with pytest.raises(AppQueryError, match="after knowledge cutoff"):
        source.load(
            _request(
                snapshot.snapshot_id,
                cutoff=datetime(2026, 8, 31, 7, 59, tzinfo=UTC),
            )
        )

    assert valuation_source.contexts == []


def test_live_source_maps_malformed_target_weight_to_fail_closed_query_error() -> None:
    snapshot = _snapshot()
    source, valuation_source = _source(snapshot, target_weight="not-a-decimal")

    with pytest.raises(AppQueryError, match="target weight is malformed"):
        source.load(_request(snapshot.snapshot_id))

    assert valuation_source.contexts == []
