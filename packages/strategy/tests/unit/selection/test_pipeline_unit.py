"""Selection pipeline hard-filter and replay golden tests."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest
from ditto_kernel.identity import InstrumentId
from ditto_strategy.selection.contracts import (
    EtfSelectionSpec,
    SelectionExclusionReason,
    SelectionFactorValue,
    SelectionFactorWeight,
    SelectionInputBundle,
    SelectionInstrumentInput,
    SelectionLimitState,
    SelectionRunStatus,
    StockSelectionSpec,
)
from ditto_strategy.selection.identity import canonical_selection_run_hash
from ditto_strategy.selection.pipeline import SelectionPipeline

_AS_OF = datetime(2026, 8, 31, 7, 0, tzinfo=UTC)
_WEIGHTS = (
    SelectionFactorWeight(name="quality", weight=0.4),
    SelectionFactorWeight(name="momentum", weight=0.6),
)


def _stock_spec(*, top_k: int = 2) -> StockSelectionSpec:
    return StockSelectionSpec(
        spec_id="stock-core",
        spec_version="1",
        top_k=top_k,
        min_average_turnover=20_000_000.0,
        min_listing_days=120,
        factor_weights=_WEIGHTS,
    )


def _etf_spec(*, top_k: int = 2) -> EtfSelectionSpec:
    return EtfSelectionSpec(
        spec_id="etf-core",
        spec_version="1",
        top_k=top_k,
        min_average_turnover=50_000_000.0,
        min_listing_days=60,
        factor_weights=_WEIGHTS,
        max_tracking_error=0.03,
    )


def _instrument(
    instrument_id: InstrumentId,
    *,
    quality: float = 0.5,
    momentum: float = 0.5,
    average_turnover: float | None = 100_000_000.0,
    is_st: bool | None = False,
    is_suspended: bool | None = False,
    listing_days: int | None = 500,
    limit_state: SelectionLimitState | None = SelectionLimitState.NORMAL,
    tracking_error: float | None = None,
) -> SelectionInstrumentInput:
    return SelectionInstrumentInput(
        instrument_id=instrument_id,
        instrument_name=f"Instrument {instrument_id}",
        industry_id="801010",
        factor_values=(
            SelectionFactorValue(name="quality", value=quality),
            SelectionFactorValue(name="momentum", value=momentum),
        ),
        average_turnover=average_turnover,
        is_st=is_st,
        is_suspended=is_suspended,
        listing_days=listing_days,
        limit_state=limit_state,
        tracking_error=tracking_error,
    )


def _bundle(
    instruments: tuple[SelectionInstrumentInput, ...],
    *,
    spec: StockSelectionSpec | EtfSelectionSpec | None = None,
    seed: int = 17,
) -> SelectionInputBundle:
    return SelectionInputBundle(
        as_of=_AS_OF,
        knowledge_cutoff=_AS_OF,
        publication_cutoff=_AS_OF,
        universe_snapshot_id="universe:sha256:abc",
        industry_rotation_snapshot_id="industry-rotation:sha256:def",
        source_snapshot_ids=("source-a", "source-b"),
        spec=spec or _stock_spec(),
        seed=seed,
        instruments=instruments,
    )


@pytest.mark.parametrize(
    ("instrument", "reason"),
    [
        (
            _instrument(InstrumentId(1), average_turnover=None),
            SelectionExclusionReason.MISSING_DATA,
        ),
        (
            _instrument(InstrumentId(2), average_turnover=1.0),
            SelectionExclusionReason.INSUFFICIENT_LIQUIDITY,
        ),
        (_instrument(InstrumentId(3), is_st=True), SelectionExclusionReason.ST_STATUS),
        (
            _instrument(InstrumentId(4), is_suspended=True),
            SelectionExclusionReason.SUSPENDED,
        ),
        (
            _instrument(InstrumentId(5), listing_days=119),
            SelectionExclusionReason.INSUFFICIENT_LISTING_DAYS,
        ),
        (
            _instrument(InstrumentId(6), limit_state=SelectionLimitState.LIMIT_UP),
            SelectionExclusionReason.PRICE_LIMITED,
        ),
        (
            _instrument(InstrumentId(7), limit_state=SelectionLimitState.LIMIT_DOWN),
            SelectionExclusionReason.PRICE_LIMITED,
        ),
    ],
)
def test_stock_hard_filters_emit_one_stable_reason(
    instrument: SelectionInstrumentInput,
    reason: SelectionExclusionReason,
) -> None:
    run = SelectionPipeline().run(_bundle((instrument,)))

    assert run.candidates == ()
    assert len(run.exclusions) == 1
    assert run.exclusions[0].reason_code is reason


def test_ranking_factor_contributions_and_below_top_k_are_deterministic() -> None:
    value = _bundle(
        (
            _instrument(InstrumentId(600003), quality=-0.5, momentum=-0.5),
            _instrument(InstrumentId(600001), quality=1.0, momentum=1.0),
            _instrument(InstrumentId(600002), quality=0.5, momentum=0.5),
        ),
        spec=_stock_spec(top_k=2),
    )

    first = SelectionPipeline().run(value)
    second = SelectionPipeline().run(value)

    assert first == second
    assert first.run_id == f"selection-run:sha256:{canonical_selection_run_hash(first)}"
    assert [
        (item.instrument_id, item.rank, item.score) for item in first.candidates
    ] == [
        (InstrumentId(600001), 1, 1.0),
        (InstrumentId(600002), 2, 0.5),
    ]
    assert first.candidates[0].factor_contributions[0].factor_name == "momentum"
    assert first.exclusions[0].instrument_id == InstrumentId(600003)
    assert first.exclusions[0].reason_code is SelectionExclusionReason.BELOW_TOP_K
    assert {item.instrument_id for item in first.candidates} | {
        item.instrument_id for item in first.exclusions
    } == {item.instrument_id for item in value.instruments}


def test_ties_are_seeded_and_exactly_replayable() -> None:
    instruments = (
        _instrument(InstrumentId(600001)),
        _instrument(InstrumentId(600002)),
    )

    first = SelectionPipeline().run(_bundle(instruments, spec=_stock_spec(top_k=1)))
    replay = SelectionPipeline().run(_bundle(instruments, spec=_stock_spec(top_k=1)))
    another_seed = SelectionPipeline().run(
        _bundle(instruments, spec=_stock_spec(top_k=1), seed=18)
    )

    assert first == replay
    assert first.run_id == replay.run_id
    assert first.knowledge_cutoff == _AS_OF
    assert first.publication_cutoff == _AS_OF
    assert first.input_hash != another_seed.input_hash


def test_etf_rules_ignore_stock_st_flag_and_apply_tracking_error() -> None:
    run = SelectionPipeline().run(
        _bundle(
            (
                _instrument(InstrumentId(510300), is_st=True, tracking_error=0.01),
                _instrument(InstrumentId(510500), tracking_error=0.04),
            ),
            spec=_etf_spec(),
        )
    )

    assert [item.instrument_id for item in run.candidates] == [InstrumentId(510300)]
    assert run.exclusions[0].instrument_id == InstrumentId(510500)
    assert (
        run.exclusions[0].reason_code
        is SelectionExclusionReason.EXCESSIVE_TRACKING_ERROR
    )


def test_missing_factor_degrades_the_run_and_fails_closed() -> None:
    instrument = replace(
        _instrument(InstrumentId(600001)),
        factor_values=(SelectionFactorValue(name="quality", value=0.5),),
    )

    run = SelectionPipeline().run(_bundle((instrument,)))

    assert run.status is SelectionRunStatus.DEGRADED
    assert run.candidates == ()
    assert run.exclusions[0].reason_code is SelectionExclusionReason.MISSING_DATA
    assert run.missing_inputs == ("instrument:600001:factor:momentum",)


def test_empty_universe_is_blocked() -> None:
    run = SelectionPipeline().run(_bundle(()))

    assert run.status is SelectionRunStatus.BLOCKED
    assert run.candidates == ()
    assert run.exclusions == ()
    assert run.missing_inputs == ("instruments",)
