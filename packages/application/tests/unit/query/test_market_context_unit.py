"""Application aggregation tests for exact PIT market context."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from ditto_application.catalog_freshness import aggregate_source_snapshot_ids
from ditto_application.exceptions import AppQueryError
from ditto_application.queries.market_context import (
    MarketContextFacade,
    MarketContextFacts,
    MarketContextMetric,
    MarketContextQueryService,
    MarketContextRequest,
    UnavailableMarketContextSource,
)
from ditto_data.catalog.contracts import DataAssetRef
from ditto_data.catalog.source_snapshot import ProviderSnapshot, ProviderSnapshotReader
from ditto_data.query.contracts import DatasetSnapshot, PITQueryContext
from ditto_features.market_context.contracts import MarketRegimeInput
from ditto_features.market_context.service import MarketRegimeService


def _snapshot(dataset_id: str, snapshot_id: str) -> DatasetSnapshot:
    return DatasetSnapshot(
        dataset_id=dataset_id,
        dataset_version=f"market.{dataset_id}.v1",
        source_snapshot_ids=(snapshot_id,),
        created_at=datetime(2026, 8, 31, 8, tzinfo=UTC),
    )


def _context() -> PITQueryContext:
    return PITQueryContext(
        as_of=datetime(2026, 8, 31, 9, tzinfo=UTC),
        knowledge_cutoff=datetime(2026, 8, 31, 9, tzinfo=UTC),
        publication_cutoff=datetime(2026, 8, 31, 8, 30, tzinfo=UTC),
        source_snapshots=(
            _snapshot("stock_daily", "snapshot:tushare:stock_daily:sha256:abc"),
            _snapshot(
                "macro_indicators",
                "snapshot:fred:macro_indicators:sha256:def",
            ),
        ),
    )


def _provider_snapshot(
    snapshot_id: str,
    *,
    dataset_id: str,
    schema_version: str = "v1",
    created_at: datetime = datetime(2026, 8, 30, 12, tzinfo=UTC),
) -> ProviderSnapshot:
    return ProviderSnapshot(
        snapshot_id=snapshot_id,
        dataset_id=dataset_id,
        source="tushare",
        request_start="2026-08-01",
        request_end="2026-08-30",
        schema_version=schema_version,
        checksum=f"checksum-{snapshot_id}",
        canonical_asset=DataAssetRef(dataset_id=dataset_id, namespace="market"),
        request_parameters_hash=f"request-{snapshot_id}",
        response_metadata=(),
        license_record_id="license-tushare",
        row_count=10,
        payload_uri=f"artifact://{snapshot_id}",
        payload_retained=True,
        created_at=created_at,
    )


def _regime_input(context: PITQueryContext) -> MarketRegimeInput:
    return MarketRegimeInput(
        as_of=context.as_of,
        knowledge_cutoff=context.knowledge_cutoff,
        publication_cutoff=context.publication_cutoff,
        source_snapshot_ids=context.source_snapshot_ids,
        advancing_count=800,
        declining_count=200,
        universe_count=1_000,
        benchmark_return_20d=0.05,
        small_cap_return_20d=0.04,
        large_cap_return_20d=0.0,
        realized_volatility_20d=0.125,
        global_return_1d=0.015,
        macro_surprise_score=0.4,
        macro_trend_score=0.6,
    )


@dataclass
class _Source:
    facts: MarketContextFacts
    calls: list[PITQueryContext]

    def load(self, context: PITQueryContext) -> MarketContextFacts:
        self.calls.append(context)
        return self.facts


def _facts(context: PITQueryContext) -> MarketContextFacts:
    return MarketContextFacts(
        regime_input=_regime_input(context),
        metrics=(
            MarketContextMetric(
                name="csi300_return_20d",
                category="a_share",
                value=0.05,
                unit="ratio",
                trend="rising",
                freshness="fresh",
                evidence_ref="dataset://stock_daily/csi300@2026-08-31",
            ),
            MarketContextMetric(
                name="macro_surprise",
                category="macro",
                value=0.4,
                unit="score",
                trend="rising",
                freshness="fresh",
                evidence_ref="dataset://macro_indicators/surprise@2026-08-31",
            ),
        ),
        data_conflicts=(),
        uncertainties=(),
    )


@pytest.mark.pit
def test_query_aggregates_exact_context_regime_metrics_and_impact_chain() -> None:
    context = _context()
    source = _Source(_facts(context), [])
    service = MarketContextQueryService(source, MarketRegimeService())

    view = service.get_context(context)

    assert source.calls == [context]
    assert view.as_of == context.as_of
    assert view.knowledge_cutoff == context.knowledge_cutoff
    assert view.publication_cutoff == context.publication_cutoff
    assert view.source_snapshot_ids == context.source_snapshot_ids
    assert view.source_snapshot_set_id == aggregate_source_snapshot_ids(
        context.source_snapshot_ids
    )
    assert view.status == "ready"
    assert view.regime_label == "risk_on"
    assert view.regime_score == pytest.approx(0.525)
    assert {metric.category for metric in view.metrics} == {"a_share", "macro"}
    assert {impact.target_domain for impact in view.impacts} == {
        "industry",
        "selection",
        "portfolio",
        "risk",
    }
    assert set(view.evidence_refs) == {
        "dataset://stock_daily/csi300@2026-08-31",
        "dataset://macro_indicators/surprise@2026-08-31",
    }


@pytest.mark.pit
def test_query_rejects_source_context_or_snapshot_drift() -> None:
    context = _context()
    facts = _facts(context)
    drifted = replace(
        facts,
        regime_input=replace(
            facts.regime_input,
            source_snapshot_ids=("snapshot:tushare:stock_daily:sha256:other",),
        ),
    )

    with pytest.raises(AppQueryError, match="PIT context drift"):
        MarketContextQueryService(
            _Source(drifted, []),
            MarketRegimeService(),
        ).get_context(context)


def test_blocked_features_do_not_emit_regime_or_downstream_impacts() -> None:
    context = _context()
    facts = _facts(context)
    blocked = replace(
        facts,
        regime_input=replace(facts.regime_input, benchmark_return_20d=None),
    )

    view = MarketContextQueryService(
        _Source(blocked, []),
        MarketRegimeService(),
    ).get_context(context)

    assert view.status == "blocked"
    assert view.regime_label is None
    assert view.regime_score is None
    assert view.impacts == ()
    assert "benchmark_return_20d" in view.missing_inputs


def test_unavailable_runtime_source_returns_explicit_blocked_evidence() -> None:
    context = _context()

    facts = UnavailableMarketContextSource().load(context)
    view = MarketContextQueryService(
        UnavailableMarketContextSource(),
        MarketRegimeService(),
    ).get_context(context)

    assert facts.metrics == ()
    assert facts.uncertainties == ("market_context_source_unavailable",)
    assert view.status == "blocked"
    assert set(view.missing_inputs) >= {
        "advancing_count",
        "benchmark_return_20d",
        "realized_volatility_20d",
    }


@pytest.mark.pit
def test_facade_resolves_exact_provider_snapshots_into_dataset_context() -> None:
    stock = _provider_snapshot("snapshot-stock-a", dataset_id="stock_daily")
    stock_b = _provider_snapshot("snapshot-stock-b", dataset_id="stock_daily")
    macro = _provider_snapshot("snapshot-macro", dataset_id="macro_indicators")
    reader = MagicMock(spec=ProviderSnapshotReader)
    reader.get_snapshot.side_effect = {
        stock.snapshot_id: stock,
        stock_b.snapshot_id: stock_b,
        macro.snapshot_id: macro,
    }.get
    query = MagicMock()
    query.get_context.return_value = "market-context-view"
    facade = MarketContextFacade(snapshot_reader=reader, query=query)
    request = MarketContextRequest(
        as_of=datetime(2026, 8, 31, 9, tzinfo=UTC),
        knowledge_cutoff=datetime(2026, 8, 31, 8, tzinfo=UTC),
        publication_cutoff=datetime(2026, 8, 31, 7, 30, tzinfo=UTC),
        source_snapshot_ids=(
            stock.snapshot_id,
            stock_b.snapshot_id,
            macro.snapshot_id,
        ),
    )

    assert facade.get_context(request) == "market-context-view"

    context = query.get_context.call_args.args[0]
    assert context.source_snapshot_ids == request.source_snapshot_ids
    assert [item.dataset_id for item in context.source_snapshots] == [
        "stock_daily",
        "macro_indicators",
    ]
    assert context.source_snapshots[0].source_snapshot_ids == (
        stock.snapshot_id,
        stock_b.snapshot_id,
    )
    assert context.source_snapshots[0].dataset_version == "v1"


@pytest.mark.parametrize(
    ("snapshots", "snapshot_ids", "message"),
    [
        ((), ("missing",), "not found"),
        (
            (
                _provider_snapshot(
                    "future",
                    dataset_id="stock_daily",
                    created_at=datetime(2026, 9, 1, tzinfo=UTC),
                ),
            ),
            ("future",),
            "not visible",
        ),
        (
            (
                _provider_snapshot("stock-v1", dataset_id="stock_daily"),
                _provider_snapshot(
                    "stock-v2",
                    dataset_id="stock_daily",
                    schema_version="v2",
                ),
            ),
            ("stock-v1", "stock-v2"),
            "mixed schema",
        ),
    ],
)
def test_facade_fails_closed_for_invalid_snapshot_evidence(
    snapshots: tuple[ProviderSnapshot, ...],
    snapshot_ids: tuple[str, ...],
    message: str,
) -> None:
    reader = MagicMock(spec=ProviderSnapshotReader)
    reader.get_snapshot.side_effect = {
        snapshot.snapshot_id: snapshot for snapshot in snapshots
    }.get
    facade = MarketContextFacade(snapshot_reader=reader, query=MagicMock())

    with pytest.raises(AppQueryError, match=message):
        facade.get_context(
            MarketContextRequest(
                as_of=datetime(2026, 8, 31, 9, tzinfo=UTC),
                knowledge_cutoff=datetime(2026, 8, 31, 8, tzinfo=UTC),
                publication_cutoff=datetime(2026, 8, 31, 7, 30, tzinfo=UTC),
                source_snapshot_ids=snapshot_ids,
            )
        )
