"""SelectionRun, stock/ETF spec, and canonical identity contracts."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime

import pytest
from ditto_kernel.identity import InstrumentId
from ditto_strategy.errors import StrategySpecError
from ditto_strategy.selection.contracts import (
    EtfSelectionSpec,
    SelectionFactorValue,
    SelectionFactorWeight,
    SelectionInputBundle,
    SelectionInstrumentInput,
    SelectionLimitState,
    StockSelectionSpec,
)
from ditto_strategy.selection.identity import (
    canonical_selection_input_hash,
    canonical_selection_spec_hash,
)

_AS_OF = datetime(2026, 8, 31, 7, 0, tzinfo=UTC)


def _weights() -> tuple[SelectionFactorWeight, ...]:
    return (
        SelectionFactorWeight(name="quality", weight=0.4),
        SelectionFactorWeight(name="momentum", weight=0.6),
    )


def _stock_spec() -> StockSelectionSpec:
    return StockSelectionSpec(
        spec_id="stock-core",
        spec_version="1",
        top_k=2,
        min_average_turnover=20_000_000.0,
        min_listing_days=120,
        factor_weights=_weights(),
    )


def _instrument(instrument_id: InstrumentId) -> SelectionInstrumentInput:
    return SelectionInstrumentInput(
        instrument_id=instrument_id,
        instrument_name=f"Instrument {instrument_id}",
        industry_id="801010",
        factor_values=(
            SelectionFactorValue(name="quality", value=0.4),
            SelectionFactorValue(name="momentum", value=0.7),
        ),
        average_turnover=50_000_000.0,
        is_st=False,
        is_suspended=False,
        listing_days=500,
        limit_state=SelectionLimitState.NORMAL,
        tracking_error=None,
    )


def _bundle() -> SelectionInputBundle:
    return SelectionInputBundle(
        as_of=_AS_OF,
        knowledge_cutoff=_AS_OF,
        publication_cutoff=_AS_OF,
        universe_snapshot_id="universe:sha256:abc",
        industry_rotation_snapshot_id="industry-rotation:sha256:def",
        source_snapshot_ids=("source-b", "source-a"),
        spec=_stock_spec(),
        seed=17,
        instruments=(
            _instrument(InstrumentId(600001)),
            _instrument(InstrumentId(600000)),
        ),
    )


def test_stock_and_etf_specs_are_distinct_identity_types() -> None:
    stock = _stock_spec()
    etf = EtfSelectionSpec(
        spec_id=stock.spec_id,
        spec_version=stock.spec_version,
        top_k=stock.top_k,
        min_average_turnover=stock.min_average_turnover,
        min_listing_days=stock.min_listing_days,
        factor_weights=stock.factor_weights,
        max_tracking_error=0.03,
    )

    assert stock.asset_kind.value == "stock"
    assert etf.asset_kind.value == "etf"
    assert canonical_selection_spec_hash(stock) != canonical_selection_spec_hash(etf)


def test_input_identity_normalizes_set_like_order_and_tracks_replay_boundaries() -> (
    None
):
    first = _bundle()
    second = replace(
        first,
        source_snapshot_ids=tuple(reversed(first.source_snapshot_ids)),
        instruments=tuple(reversed(first.instruments)),
    )

    assert first.source_snapshot_ids == ("source-a", "source-b")
    assert tuple(item.instrument_id for item in first.instruments) == (
        InstrumentId(600000),
        InstrumentId(600001),
    )
    assert canonical_selection_input_hash(first) == canonical_selection_input_hash(
        second
    )
    assert canonical_selection_input_hash(replace(first, seed=18)) != (
        canonical_selection_input_hash(first)
    )
    assert canonical_selection_input_hash(
        replace(first, universe_snapshot_id="universe:sha256:changed")
    ) != canonical_selection_input_hash(first)


def test_factor_order_is_canonical_but_duplicate_names_fail_closed() -> None:
    baseline = _stock_spec()
    reordered = replace(
        baseline, factor_weights=tuple(reversed(baseline.factor_weights))
    )

    assert canonical_selection_spec_hash(reordered) == canonical_selection_spec_hash(
        baseline
    )
    with pytest.raises(StrategySpecError, match="unique factor"):
        replace(baseline, factor_weights=(baseline.factor_weights[0],) * 2)


def test_selection_inputs_are_immutable_and_reject_future_knowledge() -> None:
    bundle = _bundle()

    with pytest.raises(FrozenInstanceError):
        bundle.seed = 2  # type: ignore[misc]
    with pytest.raises(StrategySpecError, match="knowledge_cutoff"):
        replace(
            bundle,
            knowledge_cutoff=datetime(2026, 8, 31, 8, 0, tzinfo=UTC),
        )


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1.01, 1.01])
def test_factor_values_are_finite_unit_scores(value: float) -> None:
    with pytest.raises(StrategySpecError, match="factor value"):
        SelectionFactorValue(name="momentum", value=value)
