"""History comparison composes three leg replays into common-window runs."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest
from ditto_application.exceptions import AppQueryError
from ditto_application.queries.account_ledger import LedgerRevision
from ditto_application.queries.history_comparison import (
    GetHistoryComparisonQuery,
    HistoryComparisonRequest,
)
from ditto_application.queries.model_history import GetModelHistoryQuery
from ditto_application.queries.portfolio_history import (
    GetManualHistoryQuery,
    GetPaperHistoryQuery,
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
    FlowPosition,
    create_account_event,
    ledger_hash,
)
from ditto_strategy.models import ArtifactKind, StrategyArtifactRecord

_D = Decimal
_STRATEGY_ID = "strategy-compare"
_PAPER_ACCOUNT = "compare-paper-1"
_MANUAL_ACCOUNT = "compare-manual-1"
_PAPER_SESSION = "compare-paper-session-1"
_OPENED_AT = datetime(2026, 3, 1, 1, 0, tzinfo=UTC)
_RECORDED_AT = datetime(2026, 3, 1, 2, 0, tzinfo=UTC)
_KNOWLEDGE = datetime(2026, 3, 5, 16, 0, tzinfo=UTC)
_CREATED_AT = datetime(2026, 3, 2, 2, 0, tzinfo=UTC)

_FIRST_TARGET = {"1": 0.6, "2": 0.4}
_SECOND_TARGET = {"1": 1.0}


def _account(account_id: str, kind: AccountKind) -> AccountDefinition:
    return AccountDefinition(
        account_id=account_id,
        kind=kind,
        name=f"comparison fixture {account_id}",
        opened_at=_OPENED_AT,
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
    flow_position: FlowPosition | None = None,
    source: AccountEventSource,
) -> AccountEvent:
    return create_account_event(
        account=account,
        draft=AccountEventDraft(
            event_type=event_type,
            event_id=event_id,
            trade_date=trade_date,
            settlement_date=trade_date,
            recorded_at=_RECORDED_AT,
            idempotency_key=f"idem-{event_id}",
            actor=(
                f"paper-session:{_PAPER_SESSION}"
                if source is AccountEventSource.PAPER_ENGINE
                else "user:fixture"
            ),
            source=source,
            instrument_id=(
                InstrumentId(instrument_id) if instrument_id is not None else None
            ),
            quantity=_D(quantity),
            price=_D(price),
            gross_amount=_D(gross_amount),
            flow_position=flow_position,
        ),
    )


class _Journal:
    """Multi-account in-memory journal shared by all legs."""

    def __init__(
        self,
        accounts: dict[str, AccountDefinition],
        events: list[AccountEvent],
    ):
        self._accounts = accounts
        self.events = events

    def create_account(self, account: AccountDefinition) -> AccountDefinition:
        raise AssertionError("history comparison must not create accounts")

    def get_account(self, account_id: str) -> AccountDefinition | None:
        return self._accounts.get(account_id)

    def list_accounts(self) -> tuple[AccountDefinition, ...]:
        return tuple(
            sorted(self._accounts.values(), key=lambda account: account.account_id)
        )

    def append(self, event: AccountEvent) -> AccountEvent:
        self.events.append(event)
        return event

    def get_event(self, account_id: str, event_id: str) -> AccountEvent | None:
        return next(
            (
                event
                for event in self.events
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
                for event in self.events
                if event.account_id == account_id
                and event.idempotency_key == idempotency_key
            ),
            None,
        )

    def list_events(self, account_id: str) -> tuple[AccountEvent, ...]:
        return tuple(event for event in self.events if event.account_id == account_id)


class _SnapshotReader:
    def __init__(self, snapshot: ProviderSnapshot):
        self._snapshot = snapshot

    def get_snapshot(self, snapshot_id: str) -> ProviderSnapshot | None:
        return self._snapshot if snapshot_id == self._snapshot.snapshot_id else None

    def get_observed_at(self, snapshot_id: str) -> datetime | None:
        del snapshot_id
        return None

    def get_predecessor(self, snapshot_id: str) -> str | None:
        del snapshot_id
        return None

    def list_snapshots(
        self,
        *,
        dataset_id: str | None = None,
        source: str | None = None,
        canonical_asset: DataAssetRef | None = None,
    ) -> tuple[ProviderSnapshot, ...]:
        del dataset_id, source, canonical_asset
        return ()


class _ValuationSource:
    def __init__(self, bars: dict[int, tuple[TechnicalBar, ...]]):
        self._bars = bars
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
        return self._bars.get(int(instrument_id), ())


class _ArtifactReader:
    def __init__(self, records: list[StrategyArtifactRecord]):
        self.records = records

    def list_by_strategy(self, strategy_id: str) -> tuple[StrategyArtifactRecord, ...]:
        return tuple(
            record for record in self.records if record.strategy_id == strategy_id
        )


def _bar(day: str, close: float) -> TechnicalBar:
    occurred = datetime.fromisoformat(f"{day}T07:00:00+00:00")
    published = datetime.fromisoformat(f"{day}T10:00:00+00:00")
    return TechnicalBar(
        occurred_at=occurred,
        knowledge_at=published,
        publication_at=published,
        source_snapshot_id=_SNAPSHOT_ID,
        open=close,
        high=close,
        low=close,
        close=close,
        volume=1000.0,
        turnover=close * 1000.0,
        adjustment_factor=1.0,
        suspended=False,
    )


def _snapshot() -> ProviderSnapshot:
    return ProviderSnapshot.create(
        ProviderSnapshotDraft(
            dataset_id="stock_daily",
            source="comparison-fixture",
            request_start="2026-03-02",
            request_end="2026-03-05",
            schema_version="market.stock_daily.v1",
            checksum="sha256:comparison-bars",
            canonical_asset=DataAssetRef("stock_daily", "market"),
            request_parameters_hash="sha256:params",
            response_metadata=(("rows", "6"),),
            license_record_id="license:fixture",
            row_count=6,
            payload_uri="file:///tmp/comparison-bars.parquet",
            payload_retained=True,
            created_at=_CREATED_AT,
        )
    )


_SNAPSHOT = _snapshot()
_SNAPSHOT_ID = _SNAPSHOT.snapshot_id


def _artifact(
    artifact_id: str,
    signal_date: str,
    weights: dict[str, float],
) -> StrategyArtifactRecord:
    payload: dict[str, object] = {
        "dataset_snapshot_ids": {"stock_daily": _SNAPSHOT_ID},
        "factor_ids": [],
        "factor_values": {},
        "intents": [],
        "risk_flags": [],
        "selection_reasons": {
            key: {"target_weight": weight} for key, weight in weights.items()
        },
        "signal_date": signal_date,
        "strategy_id": _STRATEGY_ID,
        "strategy_version": "1",
    }
    return StrategyArtifactRecord(
        artifact_id=artifact_id,
        strategy_id=_STRATEGY_ID,
        run_id=f"eod-{signal_date}-{_STRATEGY_ID}-1",
        artifact_type=ArtifactKind.SIGNAL_PACKAGE,
        file_path=f"evidence/{artifact_id}.json",
        metadata={
            **payload,
            "schema_version": "1.0",
            "business_payload": payload,
            "batch_key": f"eod-{signal_date}-{_STRATEGY_ID}-1",
            "checksum": compute_signal_package_checksum(payload),
            "no_rebalance": True,
            "outcome": "no_rebalance",
        },
        status="active",
        created_at=_CREATED_AT.isoformat(),
    )


def _paper_events(
    *,
    second_instrument_only: bool = False,
) -> list[AccountEvent]:
    account = _account(_PAPER_ACCOUNT, AccountKind.PAPER)
    events = [
        _event(
            account,
            "paper-opening",
            AccountEventType.OPENING_CASH,
            gross_amount="100",
            source=AccountEventSource.PAPER_ENGINE,
        ),
    ]
    if second_instrument_only:
        events.append(
            _event(
                account,
                "paper-buy-2",
                AccountEventType.BUY,
                instrument_id=2,
                quantity="5",
                price="20",
                source=AccountEventSource.PAPER_ENGINE,
            )
        )
    else:
        events.extend(
            (
                _event(
                    account,
                    "paper-buy-1",
                    AccountEventType.BUY,
                    instrument_id=1,
                    quantity="5",
                    price="10",
                    source=AccountEventSource.PAPER_ENGINE,
                ),
                _event(
                    account,
                    "paper-buy-2",
                    AccountEventType.BUY,
                    instrument_id=2,
                    quantity="2",
                    price="20",
                    source=AccountEventSource.PAPER_ENGINE,
                ),
            )
        )
    return events


def _manual_events(*, opening_date: str = "2026-03-02") -> list[AccountEvent]:
    account = _account(_MANUAL_ACCOUNT, AccountKind.MANUAL)
    return [
        _event(
            account,
            "manual-opening",
            AccountEventType.OPENING_CASH,
            trade_date=opening_date,
            gross_amount="100",
            source=AccountEventSource.MANUAL_ENTRY,
        ),
        # 8 × 10 + 20 cash: the manual leg holds positions so bar dates stay
        # visible (an all-cash account only values on its own event dates).
        _event(
            account,
            "manual-buy-1",
            AccountEventType.BUY,
            trade_date=opening_date,
            instrument_id=1,
            quantity="8",
            price="10",
            source=AccountEventSource.MANUAL_ENTRY,
        ),
    ]


def _base_bars() -> dict[int, tuple[TechnicalBar, ...]]:
    return {
        1: (
            _bar("2026-03-02", 10.0),
            _bar("2026-03-03", 11.0),
            _bar("2026-03-04", 12.1),
        ),
        2: (
            _bar("2026-03-02", 20.0),
            _bar("2026-03-03", 22.0),
            _bar("2026-03-04", 20.0),
        ),
    }


def _records() -> list[StrategyArtifactRecord]:
    return [
        _artifact("compare-model-a", "2026-03-02", _FIRST_TARGET),
        _artifact("compare-model-b", "2026-03-03", _SECOND_TARGET),
    ]


def _query(
    *,
    events: list[AccountEvent] | None = None,
    bars: dict[int, tuple[TechnicalBar, ...]] | None = None,
    records: list[StrategyArtifactRecord] | None = None,
) -> tuple[GetHistoryComparisonQuery, _Journal]:
    paper = _account(_PAPER_ACCOUNT, AccountKind.PAPER)
    manual = _account(_MANUAL_ACCOUNT, AccountKind.MANUAL)
    journal = _Journal(
        {paper.account_id: paper, manual.account_id: manual},
        events if events is not None else [*_paper_events(), *_manual_events()],
    )
    sessions = InMemoryPaperSessionStore()
    sessions.create_session(
        PaperSession(
            session_id=_PAPER_SESSION,
            account_id=_PAPER_ACCOUNT,
            strategy_id=_STRATEGY_ID,
            trade_date="2026-03-02",
            status=PaperSessionStatus.RUNNING,
            revision=1,
            created_at=_OPENED_AT,
            updated_at=_RECORDED_AT,
        )
    )
    snapshot_reader = _SnapshotReader(_SNAPSHOT)
    valuation_source = _ValuationSource(bars or _base_bars())
    query = GetHistoryComparisonQuery(
        manual_query=GetManualHistoryQuery(
            journal=journal,
            snapshot_reader=snapshot_reader,
            valuation_source=valuation_source,
        ),
        paper_query=GetPaperHistoryQuery(
            journal=journal,
            session_store=sessions,
            snapshot_reader=snapshot_reader,
            valuation_source=valuation_source,
        ),
        model_query=GetModelHistoryQuery(
            artifact_reader=_ArtifactReader(records or _records()),
            snapshot_reader=snapshot_reader,
            valuation_source=valuation_source,
        ),
        journal=journal,
    )
    return query, journal


def _revision_of(journal: _Journal, account_id: str) -> LedgerRevision:
    events = journal.list_events(account_id)
    return LedgerRevision(
        event_count=len(events),
        ledger_hash=ledger_hash(events),
    )


def _request(**overrides: Any) -> HistoryComparisonRequest:
    base = HistoryComparisonRequest(
        strategy_id=_STRATEGY_ID,
        paper_account_id=_PAPER_ACCOUNT,
        paper_session_id=_PAPER_SESSION,
        manual_account_id=_MANUAL_ACCOUNT,
        start_date="2026-03-02",
        end_date="2026-03-04",
        model_initial_capital=_D("100"),
        knowledge_cutoff=_KNOWLEDGE,
        publication_cutoff=_KNOWLEDGE,
        source_snapshot_ids=(_SNAPSHOT_ID,),
    )
    return replace(base, **overrides)


def test_composes_three_legs_into_hand_computed_common_window() -> None:
    query, journal = _query()

    view = query.history(_request())

    # Model: 100→110→121; Paper: 100→109→110.50; Manual: 100→108→116.80.
    assert view.status == "comparable"
    assert view.empty_reason is None
    assert view.currency == "CNY"
    assert view.method == "twr-linked-v1"
    assert view.valuation_policy_version == "account-valuation-stale-evidence-v1"
    assert view.comparison_policy_version == "common-window-twr-v1"
    assert view.result_id.startswith("history-comparison:sha256:")
    assert len(view.runs) == 1
    run = view.runs[0]
    assert (run.start_date, run.end_date) == ("2026-03-02", "2026-03-04")
    assert run.point_count == 3
    assert [point.on_date for point in run.points] == [
        "2026-03-02",
        "2026-03-03",
        "2026-03-04",
    ]
    for kind in ("model", "paper", "manual"):
        assert run.points[0].growth[kind] == _D("1")
    assert run.points[1].growth["model"] == _D("1.1")
    assert run.points[1].growth["paper"] == _D("1.09")
    assert run.points[1].growth["manual"] == _D("1.08")
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
    assert legs["model"].target_count == 2
    assert legs["model"].ledger_revision is None
    assert legs["paper"].ledger_revision == _revision_of(journal, _PAPER_ACCOUNT)
    assert legs["manual"].ledger_revision == _revision_of(journal, _MANUAL_ACCOUNT)
    for leg in view.legs:
        assert leg.gap_count == 0
        assert leg.point_count == 3
        assert leg.currency == "CNY"
        assert leg.result_id.startswith(f"{leg.kind}-history:sha256:")


def test_server_resolved_ledger_revisions_bind_the_result_identity() -> None:
    query, journal = _query()
    first = query.history(_request())
    first_paper = next(leg for leg in first.legs if leg.kind == "paper")
    assert first_paper.ledger_revision is not None

    # A future correction outside the range changes the resolved revision and
    # therefore the comparison identity, while the in-range series stays put.
    journal.append(
        _event(
            _account(_PAPER_ACCOUNT, AccountKind.PAPER),
            "paper-deposit-late",
            AccountEventType.DEPOSIT,
            trade_date="2026-03-09",
            gross_amount="500",
            flow_position=FlowPosition.START_OF_DAY,
            source=AccountEventSource.PAPER_ENGINE,
        )
    )
    second = query.history(_request())

    assert second.result_id != first.result_id
    paper_leg = next(leg for leg in second.legs if leg.kind == "paper")
    assert paper_leg.ledger_revision is not None
    assert (
        paper_leg.ledger_revision.event_count
        == first_paper.ledger_revision.event_count + 1
    )
    assert [run.start_date for run in second.runs] == [
        run.start_date for run in first.runs
    ]
    assert (
        second.runs[0].points[2].growth["model"]
        == first.runs[0].points[2].growth["model"]
    )


def _late_deposit(account_id: str, event_id: str, *, kind: AccountKind) -> AccountEvent:
    """A future correction appended after the compared range ends."""
    return _event(
        _account(account_id, kind),
        event_id,
        AccountEventType.DEPOSIT,
        trade_date="2026-03-09",
        gross_amount="500",
        flow_position=FlowPosition.START_OF_DAY,
        source=(
            AccountEventSource.PAPER_ENGINE
            if kind is AccountKind.PAPER
            else AccountEventSource.MANUAL_ENTRY
        ),
    )


def test_pinned_revisions_replay_the_original_identity_after_future_correction() -> (
    None
):
    query, journal = _query()
    first = query.history(_request())
    paper_revision = _revision_of(journal, _PAPER_ACCOUNT)
    manual_revision = _revision_of(journal, _MANUAL_ACCOUNT)

    journal.append(
        _late_deposit(_PAPER_ACCOUNT, "paper-deposit-late", kind=AccountKind.PAPER)
    )
    journal.append(
        _late_deposit(_MANUAL_ACCOUNT, "manual-deposit-late", kind=AccountKind.MANUAL)
    )

    # Both changed ledgers pinned: the comparison replays byte-identically.
    pinned = query.history(
        _request(
            paper_ledger_event_count=paper_revision.event_count,
            paper_ledger_hash=paper_revision.ledger_hash,
            manual_ledger_event_count=manual_revision.event_count,
            manual_ledger_hash=manual_revision.ledger_hash,
        )
    )
    assert pinned.result_id == first.result_id
    assert pinned.runs == first.runs
    assert pinned.legs == first.legs

    # Mixed pinning keeps the unpinned leg on the current stream: the manual
    # revision advances, so the comparison identity moves with it while the
    # in-range runs stay unchanged.
    partially_pinned = query.history(
        _request(
            paper_ledger_event_count=paper_revision.event_count,
            paper_ledger_hash=paper_revision.ledger_hash,
        )
    )
    assert partially_pinned.result_id != first.result_id
    partially_paper = next(leg for leg in partially_pinned.legs if leg.kind == "paper")
    assert partially_paper.ledger_revision == paper_revision
    partially_manual = next(
        leg for leg in partially_pinned.legs if leg.kind == "manual"
    )
    assert partially_manual.ledger_revision is not None
    assert partially_manual.ledger_revision.event_count == (
        manual_revision.event_count + 1
    )
    assert [run.start_date for run in partially_pinned.runs] == [
        run.start_date for run in first.runs
    ]


def test_pinning_the_current_revisions_matches_the_unpinned_result() -> None:
    query, journal = _query()
    unpinned = query.history(_request())
    paper_revision = _revision_of(journal, _PAPER_ACCOUNT)
    manual_revision = _revision_of(journal, _MANUAL_ACCOUNT)

    pinned = query.history(
        _request(
            paper_ledger_event_count=paper_revision.event_count,
            paper_ledger_hash=paper_revision.ledger_hash,
            manual_ledger_event_count=manual_revision.event_count,
            manual_ledger_hash=manual_revision.ledger_hash,
        )
    )

    assert pinned == unpinned


def test_partial_revision_pins_fail_closed() -> None:
    query, _ = _query()
    partial: tuple[tuple[str, dict[str, object]], ...] = (
        ("paper count only", {"paper_ledger_event_count": 3}),
        ("paper hash only", {"paper_ledger_hash": "account-ledger:sha256:x"}),
        ("manual count only", {"manual_ledger_event_count": 2}),
        ("manual hash only", {"manual_ledger_hash": "account-ledger:sha256:x"}),
    )
    for label, overrides in partial:
        with pytest.raises(AppQueryError, match="failed closed") as raised:
            query.history(_request(**overrides))
        assert raised.value.details["code"] == "HISTORY_COMPARISON_REQUEST_INVALID", (
            label
        )


def test_pinned_revision_stream_mismatch_fails_closed() -> None:
    query, journal = _query()
    manual_revision = _revision_of(journal, _MANUAL_ACCOUNT)
    paper_revision = _revision_of(journal, _PAPER_ACCOUNT)

    with pytest.raises(AppQueryError) as raised:
        query.history(
            _request(
                manual_ledger_event_count=manual_revision.event_count + 10,
                manual_ledger_hash=manual_revision.ledger_hash,
            )
        )
    assert (
        raised.value.details["code"] == "MANUAL_HISTORY_LEDGER_REVISION_COUNT_INVALID"
    )

    with pytest.raises(AppQueryError) as raised:
        query.history(
            _request(
                manual_ledger_event_count=manual_revision.event_count,
                manual_ledger_hash="account-ledger:sha256:not-the-stream",
            )
        )
    assert raised.value.details["code"] == "MANUAL_HISTORY_LEDGER_REVISION_MISMATCH"

    with pytest.raises(AppQueryError) as raised:
        query.history(
            _request(
                paper_ledger_event_count=paper_revision.event_count,
                paper_ledger_hash="account-ledger:sha256:not-the-stream",
            )
        )
    assert raised.value.details["code"] == "PAPER_HISTORY_LEDGER_REVISION_MISMATCH"


def test_pinned_account_gates_keep_comparison_error_codes() -> None:
    query, _ = _query()

    # The same precondition fails with the same code whether or not a pin is
    # supplied; only stream-vs-pin validation delegates to the leg level.
    with pytest.raises(AppQueryError) as raised:
        query.history(
            _request(
                paper_ledger_event_count=3,
                paper_ledger_hash="account-ledger:sha256:x",
                paper_account_id="missing-account",
            )
        )
    assert raised.value.details["code"] == "HISTORY_COMPARISON_ACCOUNT_NOT_FOUND"

    with pytest.raises(AppQueryError) as raised:
        query.history(
            _request(
                manual_ledger_event_count=2,
                manual_ledger_hash="account-ledger:sha256:x",
                manual_account_id=_PAPER_ACCOUNT,
            )
        )
    assert raised.value.details["code"] == "HISTORY_COMPARISON_ACCOUNT_KIND_MISMATCH"

    query, journal = _query()
    journal.events.clear()
    with pytest.raises(AppQueryError) as raised:
        query.history(
            _request(
                paper_ledger_event_count=3,
                paper_ledger_hash="account-ledger:sha256:x",
            )
        )
    assert raised.value.details["code"] == "HISTORY_COMPARISON_LEDGER_EMPTY"


def test_missing_or_mismatched_accounts_fail_closed() -> None:
    query, _ = _query()

    with pytest.raises(AppQueryError) as raised:
        query.history(_request(manual_account_id="missing-account"))
    assert raised.value.details["code"] == "HISTORY_COMPARISON_ACCOUNT_NOT_FOUND"

    # The MANUAL account id offered as a PAPER account is a kind mismatch.
    with pytest.raises(AppQueryError) as raised:
        query.history(_request(paper_account_id=_MANUAL_ACCOUNT))
    assert raised.value.details["code"] == "HISTORY_COMPARISON_ACCOUNT_KIND_MISMATCH"

    with pytest.raises(AppQueryError) as raised:
        query.history(_request(paper_session_id="unknown-session"))
    assert raised.value.details["code"] == "PAPER_HISTORY_SESSION_NOT_FOUND"

    with pytest.raises(AppQueryError) as raised:
        query.history(_request(strategy_id="missing-strategy"))
    assert raised.value.details["code"] == "MODEL_HISTORY_STRATEGY_NOT_FOUND"


def test_account_without_events_fails_closed() -> None:
    query, journal = _query()
    journal.events.clear()

    with pytest.raises(AppQueryError) as raised:
        query.history(_request())
    assert raised.value.details["code"] == "HISTORY_COMPARISON_LEDGER_EMPTY"


def test_invalid_requests_fail_closed() -> None:
    query, _ = _query()
    invalid: tuple[tuple[str, dict[str, object]], ...] = (
        ("empty strategy", {"strategy_id": " "}),
        ("empty paper session", {"paper_session_id": ""}),
        ("start after end", {"start_date": "2026-03-05"}),
        ("bad date", {"start_date": "not-a-date"}),
        (
            "naive cutoff",
            {"knowledge_cutoff": datetime(2026, 3, 5, 16, 0)},
        ),
        (
            "publication after knowledge",
            {"publication_cutoff": datetime(2026, 3, 5, 17, 0, tzinfo=UTC)},
        ),
        ("no snapshots", {"source_snapshot_ids": ()}),
        (
            "duplicate snapshots",
            {"source_snapshot_ids": (_SNAPSHOT_ID, _SNAPSHOT_ID)},
        ),
        ("zero capital", {"model_initial_capital": _D("0")}),
        (
            "duplicate artifact ids",
            {"model_artifact_ids": ("a", "a")},
        ),
    )
    for label, overrides in invalid:
        with pytest.raises(AppQueryError, match="failed closed") as raised:
            query.history(_request(**overrides))
        assert raised.value.details["code"] == "HISTORY_COMPARISON_REQUEST_INVALID", (
            label
        )


def test_gap_day_in_one_leg_limits_the_common_window() -> None:
    # Paper holds only instrument 2, whose 03-04 bar carries an invalid close:
    # the day stays a visible gap row instead of being silently dropped.
    bars = {
        1: (
            _bar("2026-03-02", 10.0),
            _bar("2026-03-03", 11.0),
            _bar("2026-03-04", 12.1),
        ),
        2: (
            _bar("2026-03-02", 20.0),
            _bar("2026-03-03", 22.0),
            _bar("2026-03-04", 0.0),
        ),
    }
    query, _ = _query(
        events=[*_paper_events(second_instrument_only=True), *_manual_events()],
        bars=bars,
    )

    view = query.history(_request())

    assert view.status == "comparable"
    assert [(run.start_date, run.end_date) for run in view.runs] == [
        ("2026-03-02", "2026-03-03")
    ]
    assert view.runs[0].window_returns == {
        "model": _D("0.1"),
        "paper": _D("0.1"),
        "manual": _D("0.08"),
    }
    paper_leg = next(leg for leg in view.legs if leg.kind == "paper")
    assert paper_leg.point_count == 3
    assert paper_leg.gap_count == 1


def test_no_valuation_overlap_is_explicitly_incomparable() -> None:
    # The manual account only starts after the compared range ends.
    query, _ = _query(
        events=[*_paper_events(), *_manual_events(opening_date="2026-03-10")]
    )

    view = query.history(_request())

    assert view.status == "incomparable"
    assert view.empty_reason == "no_common_valuation_dates"
    assert view.runs == ()
    manual_leg = next(leg for leg in view.legs if leg.kind == "manual")
    assert manual_leg.point_count == 0


def test_single_common_point_reports_assets_only() -> None:
    bars = {
        1: (_bar("2026-03-02", 10.0),),
        2: (_bar("2026-03-02", 20.0),),
    }
    records = [_artifact("compare-model-a", "2026-03-02", _FIRST_TARGET)]
    query, _ = _query(bars=bars, records=records)

    view = query.history(_request())

    assert view.status == "single_common_point"
    assert len(view.runs) == 1
    run = view.runs[0]
    assert run.point_count == 1
    assert run.window_returns == {"model": None, "paper": None, "manual": None}
    assert run.points[0].assets == {
        "model": _D("100.00"),
        "paper": _D("100.00"),
        "manual": _D("100.00"),
    }
