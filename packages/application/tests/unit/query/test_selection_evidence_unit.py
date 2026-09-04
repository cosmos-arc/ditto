"""Exact PIT-bound industry and SelectionRun evidence query tests."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest
from ditto_application.catalog_freshness import aggregate_source_snapshot_ids
from ditto_application.exceptions import AppQueryError
from ditto_application.queries.evidence_contracts import EvidenceTemporalContext
from ditto_application.queries.selection_evidence import (
    IndustryRotationEvidenceQueryFacade,
    SelectionRunEvidenceQueryFacade,
)
from ditto_kernel.identity import InstrumentId
from ditto_strategy.industry_rotation.contracts import (
    IndustryRotationIndustryInput,
    IndustryRotationInputBundle,
    IndustryRotationSnapshot,
)
from ditto_strategy.industry_rotation.service import IndustryRotationService
from ditto_strategy.selection.contracts import (
    SelectionFactorValue,
    SelectionFactorWeight,
    SelectionInputBundle,
    SelectionInstrumentInput,
    SelectionLimitState,
    SelectionRun,
    StockSelectionSpec,
)
from ditto_strategy.selection.pipeline import SelectionPipeline

_AS_OF = datetime(2026, 8, 31, 7, tzinfo=UTC)
_SOURCE_IDS = ("fundamental-a", "market-a")


def _artifacts() -> tuple[IndustryRotationSnapshot, SelectionRun]:
    rotation = IndustryRotationService().run(
        IndustryRotationInputBundle(
            as_of=_AS_OF,
            knowledge_cutoff=_AS_OF,
            publication_cutoff=_AS_OF,
            source_snapshot_ids=_SOURCE_IDS,
            market_context_feature_set_id="market-context:sha256:abc",
            membership_version="sw-l1:2026-08-31",
            algorithm_version="industry-rotation-v1",
            industries=(
                IndustryRotationIndustryInput(
                    industry_id="801010",
                    industry_name="Agriculture",
                    relative_strength_5d=0.5,
                    relative_strength_20d=0.5,
                    relative_strength_60d=0.5,
                    advancing_count=6,
                    declining_count=4,
                    member_count=10,
                    trend_score=0.5,
                    fundamental_score=0.5,
                    regime_alignment_score=0.5,
                ),
            ),
        )
    )
    run = SelectionPipeline().run(
        SelectionInputBundle(
            as_of=_AS_OF,
            knowledge_cutoff=_AS_OF,
            publication_cutoff=_AS_OF,
            universe_snapshot_id="universe:sha256:abc",
            industry_rotation_snapshot_id=rotation.snapshot_id,
            source_snapshot_ids=_SOURCE_IDS,
            spec=StockSelectionSpec(
                spec_id="stock-core",
                spec_version="1",
                top_k=1,
                min_average_turnover=20_000_000.0,
                min_listing_days=120,
                factor_weights=(SelectionFactorWeight("momentum", 1.0),),
            ),
            seed=17,
            instruments=(
                SelectionInstrumentInput(
                    instrument_id=InstrumentId(600000),
                    instrument_name="Pudong Bank",
                    industry_id="801010",
                    factor_values=(SelectionFactorValue("momentum", 0.7),),
                    average_turnover=100_000_000.0,
                    is_st=False,
                    is_suspended=False,
                    listing_days=5000,
                    limit_state=SelectionLimitState.NORMAL,
                    tracking_error=None,
                ),
                SelectionInstrumentInput(
                    instrument_id=InstrumentId(600001),
                    instrument_name="Excluded Bank",
                    industry_id="801010",
                    factor_values=(SelectionFactorValue("momentum", 0.9),),
                    average_turnover=1.0,
                    is_st=False,
                    is_suspended=False,
                    listing_days=5000,
                    limit_state=SelectionLimitState.NORMAL,
                    tracking_error=None,
                ),
            ),
        )
    )
    return rotation, run


class _Reader:
    def __init__(self, rotation: IndustryRotationSnapshot, run: SelectionRun) -> None:
        self.rotation = rotation
        self.run = run

    def get_rotation(self, snapshot_id: str) -> IndustryRotationSnapshot | None:
        return self.rotation if snapshot_id == self.rotation.snapshot_id else None

    def get(self, run_id: str) -> SelectionRun | None:
        return self.run if run_id == self.run.run_id else None

    def list_by_spec(self, spec_id: str, *, limit: int = 100) -> list[SelectionRun]:
        return [self.run] if spec_id == self.run.spec_id and limit > 0 else []


def _context() -> EvidenceTemporalContext:
    snapshot_set_id = aggregate_source_snapshot_ids(_SOURCE_IDS)
    assert snapshot_set_id is not None
    return EvidenceTemporalContext(
        decision_time=_AS_OF,
        knowledge_cutoff=_AS_OF,
        publication_cutoff=_AS_OF,
        source_snapshot_id=snapshot_set_id,
    )


def test_exact_evidence_preserves_rank_factors_and_exclusion_reason() -> None:
    rotation, run = _artifacts()
    reader = _Reader(rotation, run)

    rotation_evidence = IndustryRotationEvidenceQueryFacade(reader).get_evidence(
        snapshot_id=rotation.snapshot_id,
        context=_context(),
    )
    selection_evidence = SelectionRunEvidenceQueryFacade(reader).get_evidence(
        run_id=run.run_id,
        context=_context(),
    )

    assert rotation_evidence.payload.value["rankings"][0]["rank"] == 1
    assert selection_evidence.payload.value["candidates"][0]["instrument_id"] == (
        InstrumentId(600000)
    )
    assert selection_evidence.payload.value["exclusions"][0]["reason_code"] == (
        "insufficient_liquidity"
    )


def test_evidence_rejects_temporal_or_snapshot_drift() -> None:
    rotation, run = _artifacts()
    reader = _Reader(rotation, run)
    facade = SelectionRunEvidenceQueryFacade(reader)

    with pytest.raises(AppQueryError, match="context"):
        facade.get_evidence(
            run_id=run.run_id,
            context=replace(_context(), source_snapshot_id="snapshot-set:stale"),
        )
