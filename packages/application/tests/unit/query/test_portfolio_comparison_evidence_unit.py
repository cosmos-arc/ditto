"""Agent-facing portfolio evidence keeps model identities outside temporal authority."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from ditto_application.catalog_freshness import aggregate_source_snapshot_ids
from ditto_application.exceptions import AppQueryError
from ditto_application.queries.evidence_contracts import EvidenceTemporalContext
from ditto_application.queries.portfolio_comparison import (
    GetPortfolioComparisonQuery,
    PortfolioComparisonRequest,
    PortfolioComparisonSource,
)
from ditto_application.queries.portfolio_comparison_evidence import (
    PortfolioComparisonEvidenceQueryFacade,
)
from ditto_application.queries.portfolio_comparison_evidence_contracts import (
    PortfolioComparisonEvidenceIdentity,
    PortfolioScenarioEvidenceRequest,
)
from ditto_application.queries.portfolio_scenario import PreviewPortfolioScenarioQuery
from ditto_application.signal_package_contract import compute_signal_package_checksum
from ditto_portfolio.portfolio_comparison import (
    PortfolioAttribution,
    PortfolioHoldingInput,
    PortfolioValuationInput,
)
from ditto_strategy.models import ArtifactKind, StrategyArtifactRecord

_SNAPSHOTS = tuple(sorted(("provider-snapshot:stock", "provider-snapshot:etf")))
_SNAPSHOT_SET = aggregate_source_snapshot_ids(_SNAPSHOTS)
assert _SNAPSHOT_SET is not None


def _valuation(kind: str) -> PortfolioValuationInput:
    values = {
        "model": ("60000", "30000"),
        "paper": ("55000", "35000"),
        "manual": ("50000", "40000"),
    }[kind]
    return PortfolioValuationInput(
        portfolio_id=f"{kind}-main",
        portfolio_kind=kind,
        as_of="2026-08-31",
        valuation_snapshot_id="portfolio-valuation:sha256:" + "c" * 64,
        source_snapshot_ids=_SNAPSHOTS,
        currency="CNY",
        cash=Decimal("10000"),
        total_value=Decimal("100000"),
        positions=(
            PortfolioHoldingInput(
                instrument_id=1,
                quantity=Decimal("100"),
                last_price=Decimal("600"),
                market_value=Decimal(values[0]),
                industry="consumer",
            ),
            PortfolioHoldingInput(
                instrument_id=2,
                quantity=Decimal("75"),
                last_price=Decimal("400"),
                market_value=Decimal(values[1]),
                industry="fund",
            ),
        ),
        valuation_complete=True,
    )


class _ComparisonSource:
    def __init__(self) -> None:
        self.requests: list[PortfolioComparisonRequest] = []

    def load(self, request: PortfolioComparisonRequest) -> PortfolioComparisonSource:
        self.requests.append(request)
        return PortfolioComparisonSource(
            model=_valuation("model"),
            paper=_valuation("paper"),
            manual=_valuation("manual"),
            paper_attribution=PortfolioAttribution(
                unfilled_bps=Decimal("250"),
                slippage_amount=Decimal("12.50"),
                fee_amount=Decimal("5.00"),
                risk_blocked_bps=Decimal("100"),
            ),
        )


class _ArtifactReader:
    def __init__(self) -> None:
        payload: dict[str, object] = {
            "dataset_snapshot_ids": {
                "stock_daily": "provider-snapshot:stock",
                "etf_daily": "provider-snapshot:etf",
            },
            "factor_ids": [],
            "factor_values": {},
            "intents": [],
            "risk_flags": [],
            "selection_reasons": {"1": {"target_weight": 0.6}},
            "signal_date": "2026-08-31",
            "strategy_id": "strategy-1",
            "strategy_version": "1",
        }
        checksum = compute_signal_package_checksum(payload)
        self._artifact = StrategyArtifactRecord(
            artifact_id="model-main",
            strategy_id="strategy-1",
            run_id="run-1",
            artifact_type=ArtifactKind.SIGNAL_PACKAGE,
            file_path="signal-package.json",
            metadata={
                **payload,
                "schema_version": "1.0",
                "business_payload": payload,
                "batch_key": "eod-2026-08-31-strategy-1-1",
                "checksum": checksum,
                "no_rebalance": True,
                "outcome": "no_rebalance",
            },
            status="active",
        )

    def list_by_strategy(self, strategy_id: str) -> list[StrategyArtifactRecord]:
        return [self._artifact] if strategy_id == "strategy-1" else []


def _context(snapshot_set: str = _SNAPSHOT_SET) -> EvidenceTemporalContext:
    return EvidenceTemporalContext(
        decision_time=datetime(2026, 8, 31, 7, tzinfo=UTC),
        knowledge_cutoff=datetime(2026, 8, 31, 7, tzinfo=UTC),
        publication_cutoff=datetime(2026, 8, 31, 7, tzinfo=UTC),
        source_snapshot_id=snapshot_set,
    )


def _identity() -> PortfolioComparisonEvidenceIdentity:
    return PortfolioComparisonEvidenceIdentity(
        strategy_id="strategy-1",
        model_portfolio_id="model-main",
        paper_account_id="paper-main",
        manual_account_id="manual-main",
        paper_session_id="paper-session-1",
    )


def _facade() -> tuple[PortfolioComparisonEvidenceQueryFacade, _ComparisonSource]:
    source = _ComparisonSource()
    comparison = GetPortfolioComparisonQuery(source=source)
    return (
        PortfolioComparisonEvidenceQueryFacade(
            artifact_reader=_ArtifactReader(),
            comparison=comparison,
            scenario=PreviewPortfolioScenarioQuery(comparison=comparison),
        ),
        source,
    )


def test_comparison_evidence_resolves_exact_snapshots_from_checksum_bound_package() -> (
    None
):
    facade, source = _facade()

    evidence = facade.get_comparison_evidence(
        identity=_identity(),
        context=_context(),
    )

    assert source.requests[0].source_snapshot_ids == _SNAPSHOTS
    assert source.requests[0].valuation_snapshot_id is None
    assert evidence.source_snapshot_set_id == _SNAPSHOT_SET
    assert evidence.source_snapshot_ids == _SNAPSHOTS
    assert evidence.payload.value["model"]["total_value"] == "100000.00"
    assert (
        evidence.payload.value["model_vs_paper"]["attribution"]["unfilled_bps"] == "250"
    )
    assert evidence.artifact_refs[0].artifact_id == "model-main"


def test_scenario_evidence_returns_host_computed_weights_without_writes() -> None:
    facade, source = _facade()

    evidence = facade.preview_scenario(
        request=PortfolioScenarioEvidenceRequest(
            identity=_identity(),
            baseline_kind="model",
            excluded_instrument_ids=frozenset({2}),
            max_position_weight=Decimal("0.55"),
            cash_reserve_weight=Decimal("0.45"),
            market_shock=-0.10,
            industry_shocks={"consumer": -0.05},
        ),
        context=_context(),
    )

    proposed = evidence.payload.value["proposed_weights"]
    assert proposed == {"1": "0.55000000"}
    assert evidence.payload.value["risk"]["after"]["stressed_return"] == -0.0825
    assert len(source.requests) == 1


def test_evidence_fails_closed_when_host_snapshot_set_does_not_match_package() -> None:
    facade, source = _facade()

    with pytest.raises(AppQueryError, match="snapshot set"):
        facade.get_comparison_evidence(
            identity=_identity(),
            context=_context("snapshot-set:sha256:future"),
        )

    assert source.requests == []
