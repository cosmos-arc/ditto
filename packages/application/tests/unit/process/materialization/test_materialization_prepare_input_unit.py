"""Tests for prepare_input_frame and MissingDependencyError."""

from __future__ import annotations

import polars as pl
import pytest
from ditto_application.processes.materialization.types import (
    MissingDependencyError,
    prepare_input_frame,
)
from ditto_features.derived_types import (
    DerivedRole,
    DerivedSpec,
    MaterializationProfile,
)


def _make_spec(**overrides: object) -> DerivedSpec:
    defaults: dict[str, object] = {
        "id": "test.derived",
        "version": 1,
        "role": DerivedRole.FEATURE,
        "materialization_profile": MaterializationProfile.DERIVE,
        "expression": "close",
    }
    defaults.update(overrides)
    return DerivedSpec(**defaults)  # type: ignore[arg-type]


def _make_frame(*columns: str) -> pl.DataFrame:
    """Create a minimal frame with given columns plus the required key columns."""
    data = {col: [1.0] for col in columns}
    data.setdefault("instrument_id", ["000001.SZ"])
    data.setdefault("trade_date", ["2024-01-01"])
    return pl.DataFrame(data)


# ---------------------------------------------------------------------------
# MissingDependencyError
# ---------------------------------------------------------------------------


class TestMissingDependencyError:
    def test_stores_missing_and_available(self) -> None:
        err = MissingDependencyError(
            missing=["market.close", "market.volume"],
            available=["instrument_id", "trade_date", "open"],
        )
        assert err.missing == ["market.close", "market.volume"]
        assert err.available == ["instrument_id", "trade_date", "open"]

    def test_message_contains_missing_columns(self) -> None:
        err = MissingDependencyError(
            missing=["market.close"],
            available=["instrument_id", "trade_date"],
        )
        assert "market.close" in str(err)

    def test_message_contains_available_columns(self) -> None:
        err = MissingDependencyError(
            missing=["market.close"],
            available=["instrument_id", "trade_date"],
        )
        assert "instrument_id" in str(err)
        assert "trade_date" in str(err)


# ---------------------------------------------------------------------------
# prepare_input_frame — success cases
# ---------------------------------------------------------------------------


class TestPrepareInputFrameSuccess:
    def test_returns_sorted_frame_with_all_dependencies(self) -> None:
        spec = _make_spec()
        frame = _make_frame("close", "open", "volume")
        result = prepare_input_frame(
            frame=frame,
            spec=spec,
            dependencies=("market.close", "market.volume"),
        )
        assert set(result.columns) == {
            "instrument_id",
            "trade_date",
            "close",
            "open",
            "volume",
        }

    def test_dependency_found_via_stripped_prefix(self) -> None:
        """Dependency 'market.close' is matched by input column 'close'."""
        spec = _make_spec()
        frame = _make_frame("close")
        result = prepare_input_frame(
            frame=frame,
            spec=spec,
            dependencies=("market.close",),
        )
        assert "close" in result.columns

    def test_empty_dependencies_returns_sorted_frame(self) -> None:
        spec = _make_spec()
        frame = _make_frame("close")
        result = prepare_input_frame(
            frame=frame,
            spec=spec,
            dependencies=(),
        )
        assert result.height == 1

    def test_does_not_add_extra_alias_columns(self) -> None:
        """Ensure no fallback alias is injected when a dependency exists."""
        spec = _make_spec()
        frame = _make_frame("close")
        result = prepare_input_frame(
            frame=frame,
            spec=spec,
            dependencies=("market.close",),
        )
        # Must NOT contain a spurious alias column
        assert "market.close" not in result.columns


# ---------------------------------------------------------------------------
# prepare_input_frame — failure cases
# ---------------------------------------------------------------------------


class TestPrepareInputFrameFailure:
    def test_raises_on_missing_dependency(self) -> None:
        spec = _make_spec()
        frame = _make_frame("open")
        with pytest.raises(MissingDependencyError) as exc_info:
            prepare_input_frame(
                frame=frame,
                spec=spec,
                dependencies=("market.close",),
            )
        assert "market.close" in exc_info.value.missing

    def test_raises_with_all_missing_dependencies(self) -> None:
        spec = _make_spec()
        frame = _make_frame("some_other_column")
        with pytest.raises(MissingDependencyError) as exc_info:
            prepare_input_frame(
                frame=frame,
                spec=spec,
                dependencies=("market.close", "market.volume", "market.high"),
            )
        assert set(exc_info.value.missing) == {
            "market.close",
            "market.volume",
            "market.high",
        }

    def test_error_message_lists_available_columns(self) -> None:
        spec = _make_spec()
        frame = _make_frame("open")
        with pytest.raises(MissingDependencyError) as exc_info:
            prepare_input_frame(
                frame=frame,
                spec=spec,
                dependencies=("market.close",),
            )
        assert "open" in str(exc_info.value)
