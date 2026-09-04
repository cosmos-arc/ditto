"""Exact SelectionRun reads and previous-run comparison tests."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest
from ditto_application.exceptions import AppQueryError
from ditto_application.queries.industry_rotations import IndustryRotationQueryService
from ditto_application.queries.selection_runs import SelectionRunQueryService
from ditto_application.queries.selection_views import (
    to_industry_rotation_view,
    to_selection_run_view,
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


class _Reader:
    def __init__(
        self,
        *runs: SelectionRun,
        rotations: tuple[IndustryRotationSnapshot, ...] = (),
    ) -> None:
        self._runs = {value.run_id: value for value in runs}
        self._rotations = {value.snapshot_id: value for value in rotations}

    def get(self, run_id: str) -> SelectionRun | None:
        return self._runs.get(run_id)

    def list_by_spec(self, spec_id: str, *, limit: int = 100) -> list[SelectionRun]:
        return [value for value in self._runs.values() if value.spec_id == spec_id][
            :limit
        ]

    def get_rotation(self, snapshot_id: str) -> IndustryRotationSnapshot | None:
        return self._rotations.get(snapshot_id)


def _rotation() -> IndustryRotationSnapshot:
    return IndustryRotationService().run(
        IndustryRotationInputBundle(
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
    )


def _instrument(instrument_id: InstrumentId, score: float) -> SelectionInstrumentInput:
    return SelectionInstrumentInput(
        instrument_id=instrument_id,
        instrument_name=f"Instrument {instrument_id}",
        industry_id="801010",
        factor_values=(SelectionFactorValue("momentum", score),),
        average_turnover=100_000_000.0,
        is_st=False,
        is_suspended=False,
        listing_days=500,
        limit_state=SelectionLimitState.NORMAL,
        tracking_error=None,
    )


def _input(
    scores: tuple[tuple[InstrumentId, float], ...],
    *,
    source_snapshot_ids: tuple[str, ...] = ("source-a",),
) -> SelectionInputBundle:
    return SelectionInputBundle(
        as_of=_AS_OF,
        knowledge_cutoff=_AS_OF,
        publication_cutoff=_AS_OF,
        universe_snapshot_id="universe:sha256:abc",
        industry_rotation_snapshot_id="industry-rotation:sha256:def",
        source_snapshot_ids=source_snapshot_ids,
        spec=StockSelectionSpec(
            spec_id="stock-core",
            spec_version="1",
            top_k=2,
            min_average_turnover=20_000_000.0,
            min_listing_days=120,
            factor_weights=(SelectionFactorWeight("momentum", 1.0),),
        ),
        seed=17,
        instruments=tuple(_instrument(item_id, score) for item_id, score in scores),
    )


def test_get_returns_the_exact_saved_run_and_missing_id_is_typed() -> None:
    run = SelectionPipeline().run(
        _input(((InstrumentId(600001), 1.0), (InstrumentId(600002), 0.5)))
    )
    query = SelectionRunQueryService(_Reader(run))

    assert query.get(run.run_id) == to_selection_run_view(run)
    with pytest.raises(AppQueryError, match="not found") as exc_info:
        query.get("selection-run:sha256:missing")
    assert exc_info.value.details["reason"] == "selection_run_not_found"


def test_get_industry_rotation_returns_exact_snapshot_and_fails_closed() -> None:
    rotation = _rotation()
    query = IndustryRotationQueryService(_Reader(rotations=(rotation,)))

    assert query.get(rotation.snapshot_id) == to_industry_rotation_view(rotation)
    with pytest.raises(AppQueryError, match="not found") as exc_info:
        query.get("industry-rotation:sha256:missing")
    assert exc_info.value.details["reason"] == "industry_rotation_not_found"


def test_compare_reports_candidate_rank_reason_and_source_changes() -> None:
    previous = SelectionPipeline().run(
        _input(
            (
                (InstrumentId(600001), 1.0),
                (InstrumentId(600002), 0.5),
                (InstrumentId(600003), -0.5),
            )
        )
    )
    current_input = _input(
        (
            (InstrumentId(600001), -0.5),
            (InstrumentId(600002), 1.0),
            (InstrumentId(600003), 0.5),
        ),
        source_snapshot_ids=("source-b",),
    )
    current = SelectionPipeline().run(current_input)
    query = SelectionRunQueryService(_Reader(previous, current))

    diff = query.compare(previous.run_id, current.run_id)

    assert diff.data_changed is True
    assert diff.spec_changed is False
    assert diff.seed_changed is False
    assert diff.added_candidate_ids == (InstrumentId(600003),)
    assert diff.removed_candidate_ids == (InstrumentId(600001),)
    assert [
        (item.instrument_id, item.before_rank, item.after_rank)
        for item in diff.rank_changes
    ] == [
        (InstrumentId(600002), 2, 1),
    ]
    assert [
        (item.instrument_id, item.before_reason, item.after_reason)
        for item in diff.exclusion_changes
    ] == [
        (InstrumentId(600001), None, "below_top_k"),
        (InstrumentId(600003), "below_top_k", None),
    ]


def test_compare_rejects_identical_run_ids() -> None:
    run = SelectionPipeline().run(_input(((InstrumentId(600001), 1.0),)))

    with pytest.raises(AppQueryError, match="distinct"):
        SelectionRunQueryService(_Reader(run)).compare(run.run_id, run.run_id)


def test_list_by_spec_preserves_reader_order_and_validates_limit() -> None:
    first = SelectionPipeline().run(_input(((InstrumentId(600001), 1.0),)))
    second = SelectionPipeline().run(
        replace(_input(((InstrumentId(600002), 1.0),)), seed=18)
    )
    query = SelectionRunQueryService(_Reader(first, second))

    assert query.list_by_spec("stock-core", limit=1) == (to_selection_run_view(first),)
    with pytest.raises(AppQueryError, match="limit"):
        query.list_by_spec("stock-core", limit=0)
