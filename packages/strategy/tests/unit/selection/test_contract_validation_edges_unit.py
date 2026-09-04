"""Adversarial validation tests for selection input and run contracts."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import cast

import pytest
from ditto_kernel.identity import InstrumentId
from ditto_strategy.errors import StrategySpecError
from ditto_strategy.selection.contracts import (
    SelectionAssetKind,
    SelectionCandidate,
    SelectionExclusion,
    SelectionExclusionReason,
    SelectionFactorContribution,
    SelectionFactorValue,
    SelectionFactorWeight,
    SelectionInputBundle,
    SelectionInstrumentInput,
    SelectionLimitState,
    SelectionRun,
    SelectionRunStatus,
    StockSelectionSpec,
)

_NOW = datetime(2026, 9, 4, tzinfo=UTC)


def _spec() -> StockSelectionSpec:
    return StockSelectionSpec(
        spec_id="stock-core",
        spec_version="1",
        top_k=2,
        min_average_turnover=20_000_000.0,
        min_listing_days=120,
        factor_weights=(SelectionFactorWeight("momentum", 1.0),),
    )


def _instrument(instrument_id: int = 600000) -> SelectionInstrumentInput:
    return SelectionInstrumentInput(
        instrument_id=InstrumentId(instrument_id),
        instrument_name=f"Instrument {instrument_id}",
        industry_id="801010",
        factor_values=(SelectionFactorValue("momentum", 0.5),),
        average_turnover=50_000_000.0,
        is_st=False,
        is_suspended=False,
        listing_days=500,
        limit_state=SelectionLimitState.NORMAL,
        tracking_error=None,
    )


def _bundle() -> SelectionInputBundle:
    return SelectionInputBundle(
        as_of=_NOW,
        knowledge_cutoff=_NOW,
        publication_cutoff=_NOW,
        universe_snapshot_id="universe:sha256:abc",
        industry_rotation_snapshot_id="industry-rotation:sha256:def",
        source_snapshot_ids=("source-1",),
        spec=_spec(),
        seed=17,
        instruments=(_instrument(), _instrument(600001)),
    )


def _candidate(instrument_id: int = 600000, *, rank: int = 1) -> SelectionCandidate:
    return SelectionCandidate(
        instrument_id=InstrumentId(instrument_id),
        instrument_name=f"Instrument {instrument_id}",
        industry_id="801010",
        rank=rank,
        score=0.5,
        factor_contributions=(SelectionFactorContribution("momentum", 0.5, 1.0, 0.5),),
    )


def _exclusion(instrument_id: int = 600001) -> SelectionExclusion:
    return SelectionExclusion(
        instrument_id=InstrumentId(instrument_id),
        instrument_name=f"Instrument {instrument_id}",
        reason_code=SelectionExclusionReason.INSUFFICIENT_LIQUIDITY,
        stage="liquidity",
        detail="turnover below threshold",
    )


def _run() -> SelectionRun:
    bundle = _bundle()
    return SelectionRun(
        input_hash=bundle.input_hash,
        spec_hash=bundle.spec_hash,
        asset_kind=SelectionAssetKind.STOCK,
        spec_id=bundle.spec.spec_id,
        spec_version=bundle.spec.spec_version,
        seed=bundle.seed,
        as_of=bundle.as_of,
        knowledge_cutoff=bundle.knowledge_cutoff,
        publication_cutoff=bundle.publication_cutoff,
        universe_snapshot_id=bundle.universe_snapshot_id,
        industry_rotation_snapshot_id=bundle.industry_rotation_snapshot_id,
        source_snapshot_ids=bundle.source_snapshot_ids,
        status=SelectionRunStatus.READY,
        candidates=(_candidate(),),
        exclusions=(_exclusion(),),
        missing_inputs=(),
    )


def test_factor_weight_cannot_exceed_one() -> None:
    with pytest.raises(StrategySpecError) as exc_info:
        SelectionFactorWeight("momentum", 1.01)

    assert exc_info.value.details["reason"] == "invalid_selection_factor_weight"


@pytest.mark.parametrize(
    "states",
    [
        (SelectionLimitState.NORMAL,),
        (SelectionLimitState.LIMIT_UP, SelectionLimitState.LIMIT_UP),
    ],
)
def test_spec_rejects_normal_or_duplicate_excluded_limit_states(
    states: tuple[SelectionLimitState, ...],
) -> None:
    with pytest.raises(StrategySpecError) as exc_info:
        replace(_spec(), excluded_limit_states=states)

    assert exc_info.value.details["reason"] == "invalid_selection_limit_policy"


def test_instrument_rejects_duplicate_factor_values() -> None:
    factor = SelectionFactorValue("momentum", 0.5)

    with pytest.raises(StrategySpecError) as exc_info:
        replace(_instrument(), factor_values=(factor, factor))

    assert exc_info.value.details["reason"] == "duplicate_selection_factor"


def test_instrument_rejects_untyped_limit_state() -> None:
    with pytest.raises(StrategySpecError) as exc_info:
        replace(
            _instrument(),
            limit_state=cast("SelectionLimitState", "normal"),
        )

    assert exc_info.value.details["reason"] == "invalid_selection_limit_state"


@pytest.mark.pit
def test_input_bundle_rejects_unaware_and_future_visible_times() -> None:
    bundle = _bundle()
    future = _NOW + timedelta(seconds=1)

    with pytest.raises(StrategySpecError) as unaware_exc:
        replace(bundle, as_of=datetime(2026, 9, 4))
    with pytest.raises(StrategySpecError) as publication_exc:
        replace(bundle, publication_cutoff=future)

    assert unaware_exc.value.details["reason"] == "invalid_selection_time"
    assert publication_exc.value.details["reason"] == "invalid_selection_cutoff"


def test_input_bundle_requires_lineage_and_unique_instruments() -> None:
    bundle = _bundle()

    with pytest.raises(StrategySpecError) as lineage_exc:
        replace(bundle, source_snapshot_ids=())
    with pytest.raises(StrategySpecError) as duplicate_exc:
        replace(bundle, instruments=(_instrument(), _instrument()))

    assert lineage_exc.value.details["reason"] == "missing_selection_lineage"
    assert duplicate_exc.value.details["reason"] == "duplicate_selection_instrument"


def test_input_bundle_requires_a_typed_selection_spec() -> None:
    with pytest.raises(StrategySpecError) as exc_info:
        replace(_bundle(), spec=cast("StockSelectionSpec", "stock-core@1"))

    assert exc_info.value.details["reason"] == "invalid_selection_spec"


@pytest.mark.parametrize("seed", [True, -1, 1.5, "17"])
def test_input_bundle_seed_requires_an_exact_non_negative_integer(
    seed: object,
) -> None:
    with pytest.raises(StrategySpecError) as exc_info:
        replace(_bundle(), seed=cast("int", seed))

    assert exc_info.value.details["reason"] == "invalid_selection_seed"


def test_candidate_score_must_equal_factor_contribution_total() -> None:
    with pytest.raises(StrategySpecError) as exc_info:
        replace(_candidate(), score=0.75)

    assert exc_info.value.details["reason"] == "invalid_selection_score_total"


def test_exclusion_requires_a_typed_reason_code() -> None:
    with pytest.raises(StrategySpecError) as exc_info:
        replace(
            _exclusion(),
            reason_code=cast(
                "SelectionExclusionReason",
                "insufficient_liquidity",
            ),
        )

    assert exc_info.value.details["reason"] == "invalid_selection_exclusion_reason"


@pytest.mark.parametrize("field_name", ["input_hash", "spec_hash"])
def test_run_requires_lowercase_sha256_hashes(field_name: str) -> None:
    with pytest.raises(StrategySpecError) as exc_info:
        replace(_run(), **{field_name: "A" * 64})

    assert exc_info.value.details == {
        "reason": "invalid_selection_hash",
        "field_name": field_name,
    }


@pytest.mark.parametrize("field_name", ["input_hash", "spec_hash"])
def test_run_rejects_non_string_hashes(field_name: str) -> None:
    with pytest.raises(StrategySpecError) as exc_info:
        replace(_run(), **{field_name: 7})

    assert exc_info.value.details == {
        "reason": "invalid_selection_hash",
        "field_name": field_name,
    }


@pytest.mark.parametrize(
    ("field_name", "value", "reason"),
    [
        ("asset_kind", "stock", "invalid_selection_asset_kind"),
        ("status", "ready", "invalid_selection_run_status"),
    ],
)
def test_run_requires_exact_asset_kind_and_status(
    field_name: str,
    value: object,
    reason: str,
) -> None:
    with pytest.raises(StrategySpecError) as exc_info:
        replace(_run(), **{field_name: value})

    assert exc_info.value.details["reason"] == reason


@pytest.mark.parametrize("seed", [True, -1, 1.5, "17"])
def test_run_seed_requires_an_exact_non_negative_integer(seed: object) -> None:
    with pytest.raises(StrategySpecError) as exc_info:
        replace(_run(), seed=cast("int", seed))

    assert exc_info.value.details["reason"] == "invalid_selection_seed"


def test_run_requires_contiguous_ranks_and_unique_output_instruments() -> None:
    with pytest.raises(StrategySpecError) as rank_exc:
        replace(_run(), candidates=(_candidate(rank=2),))
    with pytest.raises(StrategySpecError) as duplicate_exc:
        replace(_run(), exclusions=(_exclusion(600000),))

    assert rank_exc.value.details["reason"] == "invalid_selection_rank_order"
    assert duplicate_exc.value.details["reason"] == "duplicate_selection_output"
