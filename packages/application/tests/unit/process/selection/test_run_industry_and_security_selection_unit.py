"""Cross-plane industry and security selection orchestration tests."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest
from ditto_application.exceptions import AppProcessError
from ditto_application.processes.selection.run_industry_and_security_selection import (
    RunIndustryAndSecuritySelection,
    RunIndustryAndSecuritySelectionRequest,
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

_AS_OF = datetime(2026, 8, 31, 7, 0, tzinfo=UTC)


class _Store:
    def __init__(self) -> None:
        self.saved: dict[str, SelectionRun] = {}
        self.saved_rotations: dict[str, IndustryRotationSnapshot] = {}

    def save(self, value: SelectionRun) -> None:
        self.saved.setdefault(value.run_id, value)

    def get(self, run_id: str) -> SelectionRun | None:
        return self.saved.get(run_id)

    def list_by_spec(self, spec_id: str, *, limit: int = 100) -> list[SelectionRun]:
        return [value for value in self.saved.values() if value.spec_id == spec_id][
            :limit
        ]

    def save_rotation(self, value: IndustryRotationSnapshot) -> None:
        self.saved_rotations.setdefault(value.snapshot_id, value)


def _rotation_input() -> IndustryRotationInputBundle:
    return IndustryRotationInputBundle(
        as_of=_AS_OF,
        knowledge_cutoff=_AS_OF,
        publication_cutoff=_AS_OF,
        source_snapshot_ids=("market-a",),
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


def _selection_input() -> SelectionInputBundle:
    return SelectionInputBundle(
        as_of=_AS_OF,
        knowledge_cutoff=_AS_OF,
        publication_cutoff=_AS_OF,
        universe_snapshot_id="universe:sha256:abc",
        industry_rotation_snapshot_id=None,
        source_snapshot_ids=("market-a", "fundamental-a"),
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
        ),
    )


def _process(store: _Store) -> RunIndustryAndSecuritySelection:
    return RunIndustryAndSecuritySelection(
        rotation_service=IndustryRotationService(),
        selection_pipeline=SelectionPipeline(),
        rotation_writer=store,
        run_writer=store,
    )


def test_process_binds_exact_rotation_snapshot_and_saves_selection_run() -> None:
    store = _Store()

    receipt = _process(store).execute(
        RunIndustryAndSecuritySelectionRequest(
            rotation_input=_rotation_input(),
            selection_input=_selection_input(),
        )
    )

    assert receipt.selection_run.industry_rotation_snapshot_id == (
        receipt.industry_rotation.snapshot_id
    )
    assert store.saved_rotations == {
        receipt.industry_rotation.snapshot_id: receipt.industry_rotation
    }
    assert store.saved == {receipt.selection_run.run_id: receipt.selection_run}


def test_exact_replay_is_idempotent() -> None:
    store = _Store()
    process = _process(store)
    request = RunIndustryAndSecuritySelectionRequest(
        rotation_input=_rotation_input(),
        selection_input=_selection_input(),
    )

    first = process.execute(request)
    second = process.execute(request)

    assert first == second
    assert len(store.saved) == 1
    assert len(store.saved_rotations) == 1


def test_process_rejects_stale_rotation_identity_before_write() -> None:
    store = _Store()
    stale = replace(
        _selection_input(),
        industry_rotation_snapshot_id="industry-rotation:sha256:stale",
    )

    with pytest.raises(AppProcessError, match="rotation snapshot"):
        _process(store).execute(
            RunIndustryAndSecuritySelectionRequest(
                rotation_input=_rotation_input(),
                selection_input=stale,
            )
        )

    assert store.saved == {}
    assert store.saved_rotations == {}


def test_process_rejects_cross_plane_time_drift_before_write() -> None:
    store = _Store()
    drifted = replace(
        _selection_input(),
        as_of=datetime(2026, 8, 31, 8, 0, tzinfo=UTC),
    )

    with pytest.raises(AppProcessError, match="temporal identity"):
        _process(store).execute(
            RunIndustryAndSecuritySelectionRequest(
                rotation_input=_rotation_input(),
                selection_input=drifted,
            )
        )

    assert store.saved == {}
    assert store.saved_rotations == {}
