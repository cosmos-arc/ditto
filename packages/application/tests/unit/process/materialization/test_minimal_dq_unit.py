"""Unit tests for minimal DQ summary construction."""

from __future__ import annotations

from datetime import date

import polars as pl
from ditto_application.processes.materialization.minimal_dq import (
    build_minimal_dq_record,
)
from ditto_features.derived_types import (
    DerivedRole,
    DerivedSpec,
    MaterializationProfile,
)


def _spec(
    *,
    entity_keys: tuple[str, ...] = ("instrument_id",),
    time_keys: tuple[str, ...] | None = ("trade_date",),
) -> DerivedSpec:
    return DerivedSpec(
        id="factor.minimal_dq",
        version=1,
        role=DerivedRole.FACTOR,
        materialization_profile=MaterializationProfile.SERIES,
        expression="close",
        entity_keys=entity_keys,
        time_keys=time_keys,
    )


def _payload(frame: pl.DataFrame, spec: DerivedSpec | None = None) -> dict[str, object]:
    record = build_minimal_dq_record(
        spec=spec or _spec(),
        run_id="run-minimal-dq",
        version=1,
        frame=frame,
    )
    return dict(record.payload)


class TestBuildMinimalDQRecord:
    def test_empty_frame_marks_row_primary_key_and_value_checks_failed(self) -> None:
        payload = _payload(pl.DataFrame())

        assert payload["row_count"] == 0
        assert payload["missing_primary_key_columns"] == (
            "instrument_id",
            "trade_date",
        )
        assert payload["failed_checks"] == (
            "row_count_positive",
            "primary_keys_present",
            "value_column_present",
        )
        assert payload["computable_value_count"] == 0

    def test_null_and_duplicate_primary_keys_are_counted_as_failures(self) -> None:
        payload = _payload(
            pl.DataFrame(
                {
                    "instrument_id": [1, 1, None, 2],
                    "trade_date": [
                        date(2026, 1, 1),
                        date(2026, 1, 1),
                        date(2026, 1, 2),
                        date(2026, 1, 2),
                    ],
                    "value": [1.0, 2.0, 3.0, float("nan")],
                }
            )
        )

        assert payload["null_primary_key_count"] == 1
        assert payload["duplicate_key_count"] == 1
        assert payload["nan_value_count"] == 1
        assert payload["failed_checks"] == (
            "primary_keys_present",
            "primary_keys_unique",
            "value_has_no_nan",
        )

    def test_all_null_values_fail_computable_rows_and_track_null_streak(self) -> None:
        payload = _payload(
            pl.DataFrame(
                {
                    "instrument_id": [1, 1, 1],
                    "trade_date": [
                        date(2026, 1, 1),
                        date(2026, 1, 2),
                        date(2026, 1, 3),
                    ],
                    "value": [None, None, None],
                },
                schema={
                    "instrument_id": pl.Int64,
                    "trade_date": pl.Date,
                    "value": pl.Float64,
                },
            )
        )

        assert payload["null_value_count"] == 3
        assert payload["computable_value_count"] == 0
        assert payload["max_consecutive_nulls"] == 3
        assert payload["failed_checks"] == ("value_has_computable_rows",)

    def test_non_float_value_column_has_no_nan_count(self) -> None:
        payload = _payload(
            pl.DataFrame(
                {
                    "instrument_id": [1, 2],
                    "trade_date": [date(2026, 1, 1), date(2026, 1, 1)],
                    "value": [10, 20],
                }
            )
        )

        assert payload["nan_value_count"] == 0
        assert payload["computable_value_count"] == 2
        assert payload["failed_checks"] == ()

    def test_frame_without_entity_or_time_columns_counts_null_streak_in_order(
        self,
    ) -> None:
        payload = _payload(
            pl.DataFrame(
                {"value": [None, None, 1.0, None]},
                schema={"value": pl.Float64},
            ),
            spec=_spec(entity_keys=(), time_keys=()),
        )

        assert payload["primary_key_columns"] == ("trade_date",)
        assert payload["missing_primary_key_columns"] == ("trade_date",)
        assert payload["max_consecutive_nulls"] == 2
        assert payload["coverage_rate"] == 0.25
