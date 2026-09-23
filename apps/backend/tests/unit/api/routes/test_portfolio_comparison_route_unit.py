"""CMP-05 comparison and scenario HTTP contract tests."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Coroutine
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any, cast
from unittest.mock import patch

import pytest
from ditto_application.queries.history_comparison import GetHistoryComparisonQuery
from ditto_application.queries.model_history import GetModelHistoryQuery
from ditto_application.queries.portfolio_comparison import (
    GetPortfolioComparisonQuery,
    PortfolioComparisonRequest,
    PortfolioComparisonSource,
)
from ditto_application.queries.portfolio_scenario import PreviewPortfolioScenarioQuery
from ditto_application.signal_package_contract import compute_signal_package_checksum
from ditto_apps.api.routes.portfolio_comparison import (
    get_history_comparison,
    get_model_history,
    get_portfolio_comparison,
    preview_portfolio_scenario,
)
from ditto_apps.errors import UnprocessableEntityError
from ditto_apps.models.portfolio_comparison import (
    HistoryComparisonQueryParams,
    ModelHistoryQueryParams,
    PortfolioComparisonQueryParams,
    PortfolioScenarioBody,
)
from ditto_apps.openapi_contract import create_openapi_app
from ditto_data.catalog import DataAssetRef
from ditto_data.catalog.source_snapshot import (
    ProviderSnapshot,
    ProviderSnapshotDraft,
)
from ditto_data.query.contracts import PITQueryContext
from ditto_execution.paper.session import PaperSession, PaperSessionStatus
from ditto_execution.paper.sqlite_store import SqlitePaperSessionStore
from ditto_execution.storage.sqlite.account_journal import SqliteAccountEventJournal
from ditto_features.technical_analysis.contracts import TechnicalBar
from ditto_kernel.identity import InstrumentId
from ditto_portfolio.account_ledger import (
    AccountDefinition,
    AccountEventDraft,
    AccountEventSource,
    AccountEventType,
    AccountKind,
    FlowPosition,
    create_account_event,
    ledger_hash,
)
from ditto_portfolio.portfolio_comparison import (
    PortfolioHoldingInput,
    PortfolioValuationInput,
)
from ditto_strategy.models import ArtifactKind, StrategyArtifactRecord

NOW = datetime(2026, 8, 31, 15, tzinfo=UTC)


def _valuation(kind: str) -> PortfolioValuationInput:
    return PortfolioValuationInput(
        portfolio_id=f"{kind}-main",
        portfolio_kind=kind,
        as_of="2026-08-31",
        valuation_snapshot_id="portfolio-valuation:sha256:abc",
        source_snapshot_ids=("snapshot:stock",),
        currency="CNY",
        cash=Decimal("10000"),
        total_value=Decimal("100000"),
        positions=(
            PortfolioHoldingInput(
                instrument_id=600519,
                quantity=Decimal("100"),
                last_price=Decimal("600"),
                market_value=Decimal("60000"),
                industry="consumer",
            ),
            PortfolioHoldingInput(
                instrument_id=510300,
                quantity=Decimal("75"),
                last_price=Decimal("400"),
                market_value=Decimal("30000"),
                industry="fund",
            ),
        ),
        valuation_complete=True,
    )


class _Source:
    def load(self, request: PortfolioComparisonRequest) -> PortfolioComparisonSource:
        return PortfolioComparisonSource(
            model=_valuation("model"),
            paper=_valuation("paper"),
            manual=_valuation("manual"),
        )


async def _inline(function: Callable[..., object], /, *args, **kwargs):
    return function(*args, **kwargs)


def _original[T](
    function: Callable[..., Awaitable[T]],
) -> Callable[..., Coroutine[Any, Any, T]]:
    return cast(
        Callable[..., Coroutine[Any, Any, T]],
        function.__dict__["__dishka_orig_func__"],
    )


def test_routes_return_comparison_and_read_only_scenario() -> None:
    comparison = GetPortfolioComparisonQuery(source=_Source())
    scenario = PreviewPortfolioScenarioQuery(comparison=comparison)
    with patch(
        "ditto_apps.api.routes.portfolio_comparison.asyncio.to_thread",
        side_effect=_inline,
    ):
        compared = asyncio.run(
            _original(get_portfolio_comparison)(
                params=PortfolioComparisonQueryParams(
                    strategy_id="strategy-1",
                    model_portfolio_id="model-main",
                    paper_account_id="paper-main",
                    manual_account_id="manual-main",
                    paper_session_id="session-1",
                    as_of=date(2026, 8, 31),
                    knowledge_cutoff=NOW,
                    publication_cutoff=NOW,
                    source_snapshot_ids=("snapshot:stock",),
                ),
                query=comparison,
            )
        )
        previewed = asyncio.run(
            _original(preview_portfolio_scenario)(
                body=PortfolioScenarioBody(
                    strategy_id="strategy-1",
                    model_portfolio_id="model-main",
                    paper_account_id="paper-main",
                    manual_account_id="manual-main",
                    paper_session_id="session-1",
                    as_of=date(2026, 8, 31),
                    knowledge_cutoff=NOW,
                    publication_cutoff=NOW,
                    source_snapshot_ids=("snapshot:stock",),
                    baseline_kind="model",
                    excluded_instrument_ids=(),
                    max_position_weight=Decimal("0.50"),
                    cash_reserve_weight=Decimal("0.10"),
                    market_shock=-0.10,
                    industry_shocks={"consumer": -0.20},
                ),
                query=scenario,
            )
        )

    assert compared.data.model.portfolio_kind == "model"
    assert compared.data.model_vs_manual.attribution.user_choice_bps == Decimal("0")
    assert previewed.data.proposed_weights == {
        510300: Decimal("0.40000000"),
        600519: Decimal("0.50000000"),
    }
    assert previewed.data.risk.after.stressed_return == -0.19


def test_openapi_registers_stable_portfolio_comparison_operations() -> None:
    schema = create_openapi_app().openapi()
    comparison = schema["paths"]["/api/v1/portfolio/comparison"]["get"]

    assert comparison["operationId"] == "portfolio_get_comparison"
    assert "requestBody" not in comparison
    source_snapshots = next(
        parameter
        for parameter in comparison["parameters"]
        if parameter["name"] == "source_snapshot_ids"
    )
    assert source_snapshots["in"] == "query"
    assert source_snapshots["required"] is True
    assert source_snapshots["schema"]["type"] == "array"
    assert (
        schema["paths"]["/api/v1/portfolio/scenario-previews"]["post"]["operationId"]
        == "portfolio_preview_scenario"
    )
    model_history = schema["paths"]["/api/v1/portfolio/model-history"]["get"]
    assert model_history["operationId"] == "portfolio_get_model_history"
    parameter_names = {parameter["name"] for parameter in model_history["parameters"]}
    assert {"strategy_id", "initial_capital", "artifact_ids"} <= parameter_names
    assert "ModelHistoryResponse" in schema["components"]["schemas"]


def test_scenario_body_accepts_json_array_fields() -> None:
    body = PortfolioScenarioBody.model_validate(
        {
            "strategy_id": "strategy-1",
            "model_portfolio_id": "model-main",
            "paper_account_id": "paper-main",
            "manual_account_id": "manual-main",
            "paper_session_id": "session-1",
            "as_of": "2026-08-31",
            "knowledge_cutoff": NOW.isoformat(),
            "publication_cutoff": NOW.isoformat(),
            "source_snapshot_ids": ["snapshot:stock"],
            "baseline_kind": "model",
            "excluded_instrument_ids": [600519],
            "max_position_weight": "0.50",
            "cash_reserve_weight": "0.10",
        }
    )

    assert body.source_snapshot_ids == ("snapshot:stock",)
    assert body.excluded_instrument_ids == (600519,)


class _ArtifactReader:
    def __init__(self, records: tuple[StrategyArtifactRecord, ...]) -> None:
        self._records = records

    def list_by_strategy(self, strategy_id: str) -> tuple[StrategyArtifactRecord, ...]:
        return tuple(r for r in self._records if r.strategy_id == strategy_id)


class _ModelSnapshotReader:
    def __init__(self, snapshot: ProviderSnapshot) -> None:
        self._snapshot = snapshot

    def get_snapshot(self, snapshot_id: str) -> ProviderSnapshot | None:
        snapshot = self._snapshot
        return snapshot if snapshot.snapshot_id == snapshot_id else None

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


class _ModelValuationSource:
    def __init__(self, bars: dict[int, tuple[TechnicalBar, ...]]) -> None:
        self._bars = bars

    def load(
        self,
        context: PITQueryContext,
        *,
        instrument_id: InstrumentId,
        instrument_code: str,
    ) -> tuple[TechnicalBar, ...]:
        del context
        assert instrument_code == str(instrument_id)
        return self._bars.get(int(instrument_id), ())


def _model_bar(day: str, close: float, snapshot_id: str) -> TechnicalBar:
    occurred = datetime.fromisoformat(f"{day}T07:00:00+00:00")
    published = datetime.fromisoformat(f"{day}T10:00:00+00:00")
    return TechnicalBar(
        occurred_at=occurred,
        knowledge_at=published,
        publication_at=published,
        source_snapshot_id=snapshot_id,
        open=close,
        high=close,
        low=close,
        close=close,
        volume=1000.0,
        turnover=close * 1000.0,
        adjustment_factor=1.0,
        suspended=False,
    )


def _model_fixture() -> tuple[GetModelHistoryQuery, ProviderSnapshot]:
    snapshot = ProviderSnapshot.create(
        ProviderSnapshotDraft(
            dataset_id="stock_daily",
            source="model-route-fixture",
            request_start="2026-08-31",
            request_end="2026-09-02",
            schema_version="market.stock_daily.v1",
            checksum="sha256:model-route-bars",
            canonical_asset=DataAssetRef("stock_daily", "market"),
            request_parameters_hash="sha256:params",
            response_metadata=(("rows", "6"),),
            license_record_id="license:fixture",
            row_count=6,
            payload_uri="file:///tmp/model-route-bars.parquet",
            payload_retained=True,
            created_at=NOW,
        )
    )
    records = []
    for artifact_id, signal_date, weights in (
        ("model-route-a", "2026-08-31", {"600519": 0.6, "510300": 0.4}),
        ("model-route-b", "2026-09-01", {"600519": 1.0}),
    ):
        payload: dict[str, object] = {
            "dataset_snapshot_ids": {"stock_daily": snapshot.snapshot_id},
            "factor_ids": [],
            "factor_values": {},
            "intents": [],
            "risk_flags": [],
            "selection_reasons": {
                key: {"target_weight": weight} for key, weight in weights.items()
            },
            "signal_date": signal_date,
            "strategy_id": "strategy-model",
            "strategy_version": "1",
        }
        records.append(
            StrategyArtifactRecord(
                artifact_id=artifact_id,
                strategy_id="strategy-model",
                run_id=f"eod-{signal_date}-strategy-model-1",
                artifact_type=ArtifactKind.SIGNAL_PACKAGE,
                file_path=f"evidence/{artifact_id}.json",
                metadata={
                    **payload,
                    "schema_version": "1.0",
                    "business_payload": payload,
                    "batch_key": f"eod-{signal_date}-strategy-model-1",
                    "checksum": compute_signal_package_checksum(payload),
                    "no_rebalance": True,
                    "outcome": "no_rebalance",
                },
                status="active",
                created_at=NOW.isoformat(),
            )
        )
    bars = {
        600519: (
            _model_bar("2026-08-31", 10.0, snapshot.snapshot_id),
            _model_bar("2026-09-01", 11.0, snapshot.snapshot_id),
            _model_bar("2026-09-02", 12.1, snapshot.snapshot_id),
        ),
        510300: (
            _model_bar("2026-08-31", 20.0, snapshot.snapshot_id),
            _model_bar("2026-09-01", 22.0, snapshot.snapshot_id),
            _model_bar("2026-09-02", 20.0, snapshot.snapshot_id),
        ),
    }
    query = GetModelHistoryQuery(
        artifact_reader=_ArtifactReader(tuple(records)),
        snapshot_reader=_ModelSnapshotReader(snapshot),
        valuation_source=_ModelValuationSource(bars),
    )
    return query, snapshot


def test_model_history_route_replays_saved_targets() -> None:
    query, _ = _model_fixture()
    with patch(
        "ditto_apps.api.routes.portfolio_comparison.asyncio.to_thread",
        side_effect=_inline,
    ):
        result = asyncio.run(
            _original(get_model_history)(
                params=ModelHistoryQueryParams(
                    strategy_id="strategy-model",
                    start_date=date(2026, 8, 31),
                    end_date=date(2026, 9, 2),
                    initial_capital=Decimal("100"),
                    knowledge_cutoff=NOW,
                    publication_cutoff=NOW,
                ),
                query=query,
            )
        )

    assert [point.total_value for point in result.data.points] == [
        Decimal("100.00"),
        Decimal("110.00"),
        Decimal("121.00"),
    ]
    assert [target.artifact_id for target in result.data.targets] == [
        "model-route-a",
        "model-route-b",
    ]
    assert result.data.result_id.startswith("model-history:sha256:")
    assert result.data.method == "twr-linked-v1"


def test_model_history_query_params_coerce_plain_query_strings() -> None:
    """FastAPI hands query params as strings; the model must coerce them."""
    params = ModelHistoryQueryParams.model_validate(
        {
            "strategy_id": "strategy-model",
            "start_date": "2026-08-31",
            "end_date": "2026-09-02",
            "initial_capital": "100.00",
            "knowledge_cutoff": "2026-09-01T12:00:00+08:00",
            "publication_cutoff": "2026-09-01T12:00:00+08:00",
            "artifact_ids": ["model-route-a"],
        }
    )
    assert params.start_date == date(2026, 8, 31)
    assert params.initial_capital == Decimal("100.00")
    assert params.artifact_ids == ("model-route-a",)


def _comparison_fixture(
    tmp_path: Any,
) -> tuple[
    GetHistoryComparisonQuery,
    ProviderSnapshot,
    SqliteAccountEventJournal,
    SqlitePaperSessionStore,
]:
    from ditto_application.queries.portfolio_history import (
        GetManualHistoryQuery,
        GetPaperHistoryQuery,
    )

    model_query, snapshot = _model_fixture()
    database = str(tmp_path / "history-comparison.sqlite")
    journal = SqliteAccountEventJournal(database)
    store = SqlitePaperSessionStore(database)
    paper = AccountDefinition(
        account_id="cmp-paper",
        kind=AccountKind.PAPER,
        name="比较模拟账户",
        opened_at=NOW,
    )
    manual = AccountDefinition(
        account_id="cmp-manual",
        kind=AccountKind.MANUAL,
        name="比较实盘账户",
        opened_at=NOW,
    )
    journal.create_account(paper)
    journal.create_account(manual)
    store.create_session(
        PaperSession(
            session_id="cmp-paper-session",
            account_id="cmp-paper",
            strategy_id="strategy-model",
            trade_date="2026-08-31",
            status=PaperSessionStatus.RUNNING,
            revision=1,
            created_at=NOW,
            updated_at=NOW,
        )
    )
    for account, source, events in (
        (
            paper,
            AccountEventSource.PAPER_ENGINE,
            (
                (
                    "cmp-opening-paper",
                    AccountEventType.OPENING_CASH,
                    None,
                    "0",
                    "0",
                    "100",
                ),
                (
                    "cmp-buy-600519",
                    AccountEventType.BUY,
                    600519,
                    "5",
                    "10",
                    "0",
                ),
                (
                    "cmp-buy-510300",
                    AccountEventType.BUY,
                    510300,
                    "2",
                    "20",
                    "0",
                ),
            ),
        ),
        (
            manual,
            AccountEventSource.MANUAL_ENTRY,
            (
                (
                    "cmp-opening-manual",
                    AccountEventType.OPENING_CASH,
                    None,
                    "0",
                    "0",
                    "100",
                ),
                (
                    "cmp-buy-manual",
                    AccountEventType.BUY,
                    600519,
                    "8",
                    "10",
                    "0",
                ),
            ),
        ),
    ):
        for event_id, event_type, instrument, quantity, price, gross in events:
            journal.append(
                create_account_event(
                    account=account,
                    draft=AccountEventDraft(
                        event_type=event_type,
                        event_id=event_id,
                        trade_date="2026-08-31",
                        settlement_date="2026-08-31",
                        recorded_at=NOW,
                        idempotency_key=f"idem-{event_id}",
                        actor=(
                            "paper-session:cmp-paper-session"
                            if source is AccountEventSource.PAPER_ENGINE
                            else "user:fixture"
                        ),
                        source=source,
                        instrument_id=(
                            InstrumentId(instrument) if instrument is not None else None
                        ),
                        quantity=Decimal(quantity),
                        price=Decimal(price),
                        gross_amount=Decimal(gross),
                    ),
                )
            )
    snapshot_reader = _ModelSnapshotReader(snapshot)
    valuation_source = _ModelValuationSource(
        {
            600519: tuple(
                _model_bar(day, close, snapshot.snapshot_id)
                for day, close in (
                    ("2026-08-31", 10.0),
                    ("2026-09-01", 11.0),
                    ("2026-09-02", 12.1),
                )
            ),
            510300: tuple(
                _model_bar(day, close, snapshot.snapshot_id)
                for day, close in (
                    ("2026-08-31", 20.0),
                    ("2026-09-01", 22.0),
                    ("2026-09-02", 20.0),
                )
            ),
        }
    )
    query = GetHistoryComparisonQuery(
        manual_query=GetManualHistoryQuery(
            journal=journal,
            snapshot_reader=snapshot_reader,
            valuation_source=valuation_source,
        ),
        paper_query=GetPaperHistoryQuery(
            journal=journal,
            session_store=store,
            snapshot_reader=snapshot_reader,
            valuation_source=valuation_source,
        ),
        model_query=model_query,
        journal=journal,
    )
    return query, snapshot, journal, store


def _comparison_params(
    snapshot_id: str,
    *,
    manual_account_id: str = "cmp-manual",
    paper_ledger_event_count: int | None = None,
    paper_ledger_hash: str | None = None,
    manual_ledger_event_count: int | None = None,
    manual_ledger_hash: str | None = None,
) -> HistoryComparisonQueryParams:
    return HistoryComparisonQueryParams(
        strategy_id="strategy-model",
        paper_account_id="cmp-paper",
        paper_session_id="cmp-paper-session",
        manual_account_id=manual_account_id,
        start_date=date(2026, 8, 31),
        end_date=date(2026, 9, 2),
        model_initial_capital=Decimal("100"),
        knowledge_cutoff=datetime(2026, 9, 3, 12, tzinfo=UTC),
        publication_cutoff=datetime(2026, 9, 3, 12, tzinfo=UTC),
        source_snapshot_ids=(snapshot_id,),
        paper_ledger_event_count=paper_ledger_event_count,
        paper_ledger_hash=paper_ledger_hash,
        manual_ledger_event_count=manual_ledger_event_count,
        manual_ledger_hash=manual_ledger_hash,
    )


def test_history_comparison_route_composes_three_legs(tmp_path: Any) -> None:
    query, snapshot, journal, store = _comparison_fixture(tmp_path)
    try:
        with patch(
            "ditto_apps.api.routes.portfolio_comparison.asyncio.to_thread",
            side_effect=_inline,
        ):
            result = asyncio.run(
                _original(get_history_comparison)(
                    params=_comparison_params(snapshot.snapshot_id),
                    query=query,
                )
            )
        paper_events = journal.list_events("cmp-paper")
    finally:
        store.close()
        journal.close()

    data = result.data
    assert data.status == "comparable"
    assert data.result_id.startswith("history-comparison:sha256:")
    assert data.strategy_id == "strategy-model"
    assert data.paper_account_id == "cmp-paper"
    assert data.paper_session_id == "cmp-paper-session"
    assert data.manual_account_id == "cmp-manual"
    assert data.model_initial_capital == Decimal("100.00")
    assert data.currency == "CNY"
    assert data.method == "twr-linked-v1"
    assert data.comparison_policy_version == "common-window-twr-v1"
    assert [(run.start_date, run.end_date) for run in data.runs] == [
        ("2026-08-31", "2026-09-02")
    ]
    run = data.runs[0]
    assert run.points[2].growth["model"] == Decimal("1.21")
    assert run.points[2].growth["paper"] == Decimal("1.09") * (
        Decimal("110.5") / Decimal("109")
    )
    assert run.points[2].growth["manual"] == Decimal("1.08") * (
        Decimal("116.8") / Decimal("108")
    )
    legs = {leg.kind: leg for leg in data.legs}
    assert legs["paper"].ledger_revision is not None
    assert legs["paper"].ledger_revision.event_count == len(paper_events)
    assert legs["model"].target_count == 2
    assert legs["model"].ledger_revision is None


def test_history_comparison_route_pins_ledger_revisions(tmp_path: Any) -> None:
    query, snapshot, journal, store = _comparison_fixture(tmp_path)
    try:
        with patch(
            "ditto_apps.api.routes.portfolio_comparison.asyncio.to_thread",
            side_effect=_inline,
        ):
            first = asyncio.run(
                _original(get_history_comparison)(
                    params=_comparison_params(snapshot.snapshot_id),
                    query=query,
                )
            )
        paper_revision = journal.list_events("cmp-paper")
        manual_revision = journal.list_events("cmp-manual")
        pinned_params = _comparison_params(
            snapshot.snapshot_id,
            paper_ledger_event_count=len(paper_revision),
            paper_ledger_hash=ledger_hash(paper_revision),
            manual_ledger_event_count=len(manual_revision),
            manual_ledger_hash=ledger_hash(manual_revision),
        )
        # Future corrections land on both ledgers after the compared range.
        for account, event_id in (
            ("cmp-paper", "cmp-paper-deposit-late"),
            ("cmp-manual", "cmp-manual-deposit-late"),
        ):
            definition = journal.get_account(account)
            assert definition is not None
            journal.append(
                create_account_event(
                    account=definition,
                    draft=AccountEventDraft(
                        event_type=AccountEventType.DEPOSIT,
                        event_id=event_id,
                        trade_date="2026-09-10",
                        settlement_date="2026-09-10",
                        recorded_at=NOW,
                        idempotency_key=f"idem-{event_id}",
                        actor="user:fixture",
                        source=(
                            AccountEventSource.PAPER_ENGINE
                            if account == "cmp-paper"
                            else AccountEventSource.MANUAL_ENTRY
                        ),
                        gross_amount=Decimal("500"),
                        flow_position=FlowPosition.START_OF_DAY,
                    ),
                )
            )
        with patch(
            "ditto_apps.api.routes.portfolio_comparison.asyncio.to_thread",
            side_effect=_inline,
        ):
            pinned = asyncio.run(
                _original(get_history_comparison)(
                    params=pinned_params,
                    query=query,
                )
            )
            unpinned = asyncio.run(
                _original(get_history_comparison)(
                    params=_comparison_params(snapshot.snapshot_id),
                    query=query,
                )
            )
    finally:
        store.close()
        journal.close()

    assert pinned.data.result_id == first.data.result_id
    assert pinned.data.runs == first.data.runs
    assert unpinned.data.result_id != first.data.result_id
    pinned_legs = {leg.kind: leg for leg in pinned.data.legs}
    assert pinned_legs["paper"].ledger_revision is not None
    assert pinned_legs["paper"].ledger_revision.event_count == len(paper_revision)
    assert pinned_legs["manual"].ledger_revision is not None
    assert pinned_legs["manual"].ledger_revision.event_count == len(manual_revision)


def test_history_comparison_route_maps_account_errors_to_422(
    tmp_path: Any,
) -> None:
    query, snapshot, journal, store = _comparison_fixture(tmp_path)
    try:
        with patch(
            "ditto_apps.api.routes.portfolio_comparison.asyncio.to_thread",
            side_effect=_inline,
        ):
            with pytest.raises(UnprocessableEntityError) as raised:
                asyncio.run(
                    _original(get_history_comparison)(
                        params=_comparison_params(
                            snapshot.snapshot_id,
                            manual_account_id="missing-manual",
                        ),
                        query=query,
                    )
                )
    finally:
        store.close()
        journal.close()
    assert raised.value.error_code == "HISTORY_COMPARISON_ACCOUNT_NOT_FOUND"


def test_history_comparison_route_rejects_half_pinned_revisions(
    tmp_path: Any,
) -> None:
    query, snapshot, journal, store = _comparison_fixture(tmp_path)
    try:
        with patch(
            "ditto_apps.api.routes.portfolio_comparison.asyncio.to_thread",
            side_effect=_inline,
        ):
            with pytest.raises(UnprocessableEntityError) as raised:
                asyncio.run(
                    _original(get_history_comparison)(
                        params=_comparison_params(
                            snapshot.snapshot_id,
                            paper_ledger_event_count=3,
                        ),
                        query=query,
                    )
                )
    finally:
        store.close()
        journal.close()
    assert raised.value.error_code == "HISTORY_COMPARISON_REQUEST_INVALID"


def test_history_comparison_query_params_coerce_plain_query_strings() -> None:
    params = HistoryComparisonQueryParams.model_validate(
        {
            "strategy_id": "strategy-model",
            "paper_account_id": "cmp-paper",
            "paper_session_id": "cmp-paper-session",
            "manual_account_id": "cmp-manual",
            "start_date": "2026-08-31",
            "end_date": "2026-09-02",
            "model_initial_capital": "100.00",
            "knowledge_cutoff": "2026-09-01T12:00:00+08:00",
            "publication_cutoff": "2026-09-01T12:00:00+08:00",
            "source_snapshot_ids": ["snapshot:stock_daily:1"],
            "model_artifact_ids": ["model-route-a"],
            "paper_ledger_event_count": "3",
            "paper_ledger_hash": "account-ledger:sha256:paper",
            "manual_ledger_event_count": "2",
            "manual_ledger_hash": "account-ledger:sha256:manual",
        }
    )
    assert params.start_date == date(2026, 8, 31)
    assert params.model_initial_capital == Decimal("100.00")
    assert params.source_snapshot_ids == ("snapshot:stock_daily:1",)
    assert params.model_artifact_ids == ("model-route-a",)
    assert params.paper_ledger_event_count == 3
    assert params.paper_ledger_hash == "account-ledger:sha256:paper"
    assert params.manual_ledger_event_count == 2
    assert params.manual_ledger_hash == "account-ledger:sha256:manual"

    omitted = HistoryComparisonQueryParams.model_validate(
        {
            "strategy_id": "strategy-model",
            "paper_account_id": "cmp-paper",
            "paper_session_id": "cmp-paper-session",
            "manual_account_id": "cmp-manual",
            "start_date": "2026-08-31",
            "end_date": "2026-09-02",
            "model_initial_capital": "100.00",
            "knowledge_cutoff": "2026-09-01T12:00:00+08:00",
            "publication_cutoff": "2026-09-01T12:00:00+08:00",
            "source_snapshot_ids": ["snapshot:stock_daily:1"],
        }
    )
    assert omitted.paper_ledger_event_count is None
    assert omitted.paper_ledger_hash is None
    assert omitted.manual_ledger_event_count is None
    assert omitted.manual_ledger_hash is None


def test_history_comparison_openapi_declares_the_contract() -> None:
    schema = create_openapi_app().openapi()
    schemas = schema["components"]["schemas"]
    assert "HistoryComparisonResponse" in schemas
    properties = schemas["HistoryComparisonResponse"]["properties"]
    for field in ("runs", "legs", "status", "comparison_policy_version"):
        assert field in properties
    operation = schema["paths"]["/api/v1/portfolio/history-comparison"]["get"]
    parameter_names = {parameter["name"] for parameter in operation["parameters"]}
    for name in (
        "strategy_id",
        "paper_account_id",
        "paper_session_id",
        "manual_account_id",
        "model_initial_capital",
        "source_snapshot_ids",
        "model_artifact_ids",
        "paper_ledger_event_count",
        "paper_ledger_hash",
        "manual_ledger_event_count",
        "manual_ledger_hash",
    ):
        assert name in parameter_names
