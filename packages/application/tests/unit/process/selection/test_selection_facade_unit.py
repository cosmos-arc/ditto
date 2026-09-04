"""Typed public selection facade mapping tests."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest
from ditto_application.exceptions import AppProcessError
from ditto_application.processes.selection.facade import (
    CreateSelectionRunRequest,
    EtfSelectionSpecDraft,
    IndustryRotationObservationDraft,
    SelectionFactorValueDraft,
    SelectionFactorWeightDraft,
    SelectionInstrumentDraft,
    SelectionWorkspaceFacade,
)
from ditto_application.processes.selection.run_industry_and_security_selection import (
    RunIndustryAndSecuritySelection,
)
from ditto_kernel.identity import InstrumentId
from ditto_strategy.industry_rotation.contracts import IndustryRotationSnapshot
from ditto_strategy.industry_rotation.service import IndustryRotationService
from ditto_strategy.selection.contracts import SelectionRun
from ditto_strategy.selection.pipeline import SelectionPipeline

_AS_OF = datetime(2026, 8, 31, 7, 0, tzinfo=UTC)


class _Writer:
    def __init__(self) -> None:
        self.saved: list[SelectionRun] = []
        self.saved_rotations: list[IndustryRotationSnapshot] = []

    def save(self, value: SelectionRun) -> None:
        self.saved.append(value)

    def save_rotation(self, value: IndustryRotationSnapshot) -> None:
        self.saved_rotations.append(value)


def _request() -> CreateSelectionRunRequest:
    return CreateSelectionRunRequest(
        as_of=_AS_OF,
        knowledge_cutoff=_AS_OF,
        publication_cutoff=_AS_OF,
        rotation_source_snapshot_ids=("market-a",),
        market_context_feature_set_id="market-context:sha256:abc",
        membership_version="sw-l1:2026-08-31",
        rotation_algorithm_version="industry-rotation-v1",
        industries=(
            IndustryRotationObservationDraft(
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
        universe_snapshot_id="universe:sha256:abc",
        selection_source_snapshot_ids=("market-a", "fundamental-a"),
        selection_spec=EtfSelectionSpecDraft(
            spec_id="etf-core",
            spec_version="1",
            top_k=1,
            min_average_turnover=50_000_000.0,
            min_listing_days=60,
            factor_weights=(SelectionFactorWeightDraft("momentum", 1.0),),
            max_tracking_error=0.03,
        ),
        seed=17,
        instruments=(
            SelectionInstrumentDraft(
                instrument_id=InstrumentId(510300),
                instrument_name="CSI 300 ETF",
                industry_id=None,
                factor_values=(SelectionFactorValueDraft("momentum", 0.7),),
                average_turnover=100_000_000.0,
                is_st=True,
                is_suspended=False,
                listing_days=5000,
                limit_state="normal",
                tracking_error=0.01,
            ),
        ),
    )


def _facade(writer: _Writer) -> SelectionWorkspaceFacade:
    return SelectionWorkspaceFacade(
        RunIndustryAndSecuritySelection(
            rotation_service=IndustryRotationService(),
            selection_pipeline=SelectionPipeline(),
            rotation_writer=writer,
            run_writer=writer,
        )
    )


def test_facade_maps_typed_etf_request_to_exact_process_receipt() -> None:
    writer = _Writer()

    receipt = _facade(writer).create(_request())

    assert receipt.selection_run.asset_kind == "etf"
    assert [item.instrument_id for item in receipt.selection_run.candidates] == [
        InstrumentId(510300)
    ]
    assert [item.run_id for item in writer.saved] == [receipt.selection_run.run_id]


def test_facade_maps_domain_validation_to_application_process_error() -> None:
    writer = _Writer()
    request = _request()
    invalid_spec = replace(
        request.selection_spec,
        factor_weights=(SelectionFactorWeightDraft("momentum", 0.5),),
    )

    with pytest.raises(AppProcessError, match="weights"):
        _facade(writer).create(replace(request, selection_spec=invalid_spec))

    assert writer.saved == []
