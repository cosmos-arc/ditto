"""Tests for cross-section amplification logic."""

from __future__ import annotations

import polars as pl
import pytest
from ditto_app.process.materialization.orchestrator import apply_cs_amplification
from ditto_kernel.specs import DerivedRole, DerivedSpec, MaterializationProfile

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_spec(**overrides: object) -> DerivedSpec:
    defaults: dict[str, object] = {
        "id": "test.cs_factor",
        "version": 1,
        "role": DerivedRole.FEATURE,
        "materialization_profile": MaterializationProfile.SERIES,
        "expression": "cs_rank(close)",
    }
    defaults.update(overrides)
    return DerivedSpec(**defaults)  # type: ignore[arg-type]


def _make_frame(rows: list[dict[str, object]]) -> pl.DataFrame:
    return pl.DataFrame(rows)


# ---------------------------------------------------------------------------
# apply_cs_amplification — pure function
# ---------------------------------------------------------------------------


class TestApplyCSAmplification:
    """Tests for the module-level apply_cs_amplification function."""

    def test_expands_partial_cross_section_to_full(self) -> None:
        """Instruments missing from input should appear as null-value rows."""
        frame = _make_frame(
            [
                {"trade_date": "2026-03-11", "instrument_id": 1, "value": 0.5},
                {"trade_date": "2026-03-11", "instrument_id": 2, "value": 0.8},
                {"trade_date": "2026-03-12", "instrument_id": 1, "value": 0.3},
            ]
        )
        result = apply_cs_amplification(
            frame=frame,
            instrument_ids=[1, 2, 3],
        )
        assert result.height == 6  # 2 dates * 3 instruments
        # Instrument 3 on 2026-03-11 should have null value
        row_3_d1 = result.filter(
            (pl.col("instrument_id") == 3) & (pl.col("trade_date") == "2026-03-11"),
        )
        assert row_3_d1.height == 1
        assert row_3_d1["value"][0] is None
        # Instrument 3 on 2026-03-12 should have null value
        row_3_d2 = result.filter(
            (pl.col("instrument_id") == 3) & (pl.col("trade_date") == "2026-03-12"),
        )
        assert row_3_d2.height == 1
        assert row_3_d2["value"][0] is None
        # Existing values should be preserved
        row_1_d1 = result.filter(
            (pl.col("instrument_id") == 1) & (pl.col("trade_date") == "2026-03-11"),
        )
        assert row_1_d1["value"][0] == 0.5

    def test_no_amplification_when_frame_empty(self) -> None:
        """Empty input frame should be returned as-is."""
        frame = _make_frame(
            [
                {"trade_date": [], "instrument_id": [], "value": []},
            ]
        ).filter(pl.lit(False))
        result = apply_cs_amplification(
            frame=frame,
            instrument_ids=[1, 2, 3],
        )
        assert result.is_empty()

    def test_no_amplification_when_instrument_ids_empty(self) -> None:
        """Empty instrument list should return original frame unchanged."""
        frame = _make_frame(
            [
                {"trade_date": "2026-03-11", "instrument_id": 1, "value": 0.5},
            ]
        )
        result = apply_cs_amplification(
            frame=frame,
            instrument_ids=[],
        )
        assert result.height == 1
        assert result["value"][0] == 0.5

    def test_single_date_multiple_instruments(self) -> None:
        """Single date should expand to all instruments."""
        frame = _make_frame(
            [
                {"trade_date": "2026-03-11", "instrument_id": 1, "value": 0.5},
            ]
        )
        result = apply_cs_amplification(
            frame=frame,
            instrument_ids=[1, 2],
        )
        assert result.height == 2
        assert set(result["instrument_id"].to_list()) == {1, 2}

    def test_preserves_existing_values(self) -> None:
        """All existing (date, instrument) pairs should retain their values."""
        frame = _make_frame(
            [
                {"trade_date": "2026-03-11", "instrument_id": 1, "value": 0.1},
                {"trade_date": "2026-03-11", "instrument_id": 2, "value": 0.2},
            ]
        )
        result = apply_cs_amplification(
            frame=frame,
            instrument_ids=[1, 2],
        )
        assert result.height == 2
        sorted_result = result.sort("instrument_id")
        assert sorted_result["value"].to_list() == [0.1, 0.2]

    def test_multiple_dates(self) -> None:
        """Should expand across multiple dates."""
        frame = _make_frame(
            [
                {"trade_date": "2026-03-11", "instrument_id": 1, "value": 0.1},
                {"trade_date": "2026-03-12", "instrument_id": 1, "value": 0.2},
                {"trade_date": "2026-03-12", "instrument_id": 2, "value": 0.3},
            ]
        )
        result = apply_cs_amplification(
            frame=frame,
            instrument_ids=[1, 2, 3],
        )
        assert result.height == 6  # 2 dates * 3 instruments

    def test_result_columns_are_trade_date_instrument_id_value(self) -> None:
        """Result should contain exactly the expected columns."""
        frame = _make_frame(
            [
                {"trade_date": "2026-03-11", "instrument_id": 1, "value": 0.5},
            ]
        )
        result = apply_cs_amplification(
            frame=frame,
            instrument_ids=[1, 2],
        )
        assert set(result.columns) == {"trade_date", "instrument_id", "value"}


# ---------------------------------------------------------------------------
# DerivedSpec universe_id field
# ---------------------------------------------------------------------------


class TestDerivedSpecUniverseId:
    """Tests for the new universe_id field on DerivedSpec."""

    def test_default_is_none(self) -> None:
        """universe_id should default to None when not provided."""
        spec = _make_spec()
        assert spec.universe_id is None

    def test_explicit_universe_id(self) -> None:
        """universe_id should be stored when provided."""
        spec = _make_spec(universe_id="cn_stock_300")
        assert spec.universe_id == "cn_stock_300"

    def test_frozen_immutability(self) -> None:
        """DerivedSpec should remain frozen with universe_id."""
        spec = _make_spec(universe_id="cn_stock_300")
        with pytest.raises(AttributeError):
            spec.universe_id = "other"  # type: ignore[misc]
