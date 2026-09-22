"""Unit tests for research dataset helper time precision (issue #287)."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

import polars as pl
import pytest
from ditto_analysis.research.specs import KnownAtPolicy
from ditto_application.exceptions import AppQueryError
from ditto_application.processes.research_dataset_helpers import (
    _attach_known_at,
    _pit_join,
)

SHANGHAI = ZoneInfo("Asia/Shanghai")


def _sample_frame(*trade_dates: date) -> pl.DataFrame:
    """Spine-like left frame with SAMPLE_TIME known_at instants."""
    frame = pl.DataFrame(
        {
            "sample_row_id": range(len(trade_dates)),
            "instrument_id": [1] * len(trade_dates),
            "trade_date": list(trade_dates),
        }
    )
    return _attach_known_at(
        frame=frame,
        known_at_policy=KnownAtPolicy.SAMPLE_TIME,
        explicit_cutoff=None,
    )


class TestAttachKnownAt:
    """known_at must stay a timezone-aware instant, never a bare date."""

    def test_sample_time_uses_shanghai_midnight(self) -> None:
        frame = _sample_frame(date(2026, 3, 10), date(2026, 3, 11))
        assert frame["known_at"].to_list() == [
            datetime(2026, 3, 10, tzinfo=SHANGHAI),
            datetime(2026, 3, 11, tzinfo=SHANGHAI),
        ]

    def test_explicit_cutoff_keeps_intraday_precision(self) -> None:
        frame = pl.DataFrame({"instrument_id": [1], "trade_date": [date(2026, 3, 10)]})
        attached = _attach_known_at(
            frame=frame,
            known_at_policy=KnownAtPolicy.EXPLICIT_CUTOFF,
            explicit_cutoff="2026-03-12T15:30:00+08:00",
        )
        assert attached["known_at"].to_list() == [
            datetime(2026, 3, 12, 15, 30, tzinfo=SHANGHAI)
        ]

    @pytest.mark.parametrize(
        ("cutoff", "expected"),
        [
            ("2026-03-12", datetime(2026, 3, 12, tzinfo=SHANGHAI)),
            (
                "2026-03-12T07:30:00+00:00",
                datetime(2026, 3, 12, 15, 30, tzinfo=SHANGHAI),
            ),
        ],
    )
    def test_explicit_cutoff_normalizes_date_and_utc(
        self, cutoff: str, expected: datetime
    ) -> None:
        frame = pl.DataFrame({"instrument_id": [1], "trade_date": [date(2026, 3, 10)]})
        attached = _attach_known_at(
            frame=frame,
            known_at_policy=KnownAtPolicy.EXPLICIT_CUTOFF,
            explicit_cutoff=cutoff,
        )
        assert attached["known_at"].to_list() == [expected]

    def test_explicit_cutoff_equivalent_timezones_agree(self) -> None:
        frame = pl.DataFrame(
            {"instrument_id": [1, 2], "trade_date": [date(2026, 3, 10)] * 2}
        )
        attached_cst = _attach_known_at(
            frame=frame,
            known_at_policy=KnownAtPolicy.EXPLICIT_CUTOFF,
            explicit_cutoff="2026-03-12T15:30:00+08:00",
        )
        attached_utc = _attach_known_at(
            frame=frame,
            known_at_policy=KnownAtPolicy.EXPLICIT_CUTOFF,
            explicit_cutoff="2026-03-12T07:30:00+00:00",
        )
        assert attached_cst["known_at"].to_list() == attached_utc["known_at"].to_list()

    def test_explicit_cutoff_requires_value(self) -> None:
        frame = pl.DataFrame({"instrument_id": [1], "trade_date": [date(2026, 3, 10)]})
        with pytest.raises(AppQueryError):
            _attach_known_at(
                frame=frame,
                known_at_policy=KnownAtPolicy.EXPLICIT_CUTOFF,
                explicit_cutoff=None,
            )

    def test_explicit_cutoff_rejects_garbage(self) -> None:
        frame = pl.DataFrame({"instrument_id": [1], "trade_date": [date(2026, 3, 10)]})
        with pytest.raises(AppQueryError):
            _attach_known_at(
                frame=frame,
                known_at_policy=KnownAtPolicy.EXPLICIT_CUTOFF,
                explicit_cutoff="not-a-date",
            )


class TestPitJoinAvailabilityPrecision:
    """availability_time must be honored at full timestamp precision."""

    @pytest.mark.pit
    def test_same_day_intraday_availability_is_excluded_from_midnight_sample(
        self,
    ) -> None:
        """The exact #287 reproduction: a 15:30-known factor must not leak."""
        left = _sample_frame(date(2026, 3, 10))
        source = pl.DataFrame(
            {
                "instrument_id": [1, 1],
                "trade_date": ["2026-03-09", "2026-03-10"],
                "availability_time": [
                    "2026-03-09T18:00:00+08:00",
                    "2026-03-10T15:30:00+08:00",
                ],
                "value": [1.0, 999999.0],
            }
        )
        joined = _pit_join(left_frame=left, source_frame=source, derived_id="factor")
        assert joined["factor"].to_list() == [1.0]

    @pytest.mark.pit
    def test_just_visible_instant_is_included_at_equality(self) -> None:
        left = _sample_frame(date(2026, 3, 10))
        source = pl.DataFrame(
            {
                "instrument_id": [1],
                "trade_date": ["2026-03-09"],
                "availability_time": ["2026-03-10T00:00:00+08:00"],
                "value": [7.0],
            }
        )
        joined = _pit_join(left_frame=left, source_frame=source, derived_id="factor")
        assert joined["factor"].to_list() == [7.0]

    @pytest.mark.pit
    def test_date_only_availability_waits_for_end_of_day(self) -> None:
        """Date-only precision never claims the value was known at day start."""
        left = _sample_frame(date(2026, 3, 10), date(2026, 3, 11))
        source = pl.DataFrame(
            {
                "instrument_id": [1],
                "trade_date": [date(2026, 3, 10)],
                "availability_time": [date(2026, 3, 10)],
                "value": [5.0],
            }
        )
        joined = _pit_join(left_frame=left, source_frame=source, derived_id="factor")
        assert joined["factor"].to_list() == [None, 5.0]

    @pytest.mark.pit
    def test_utf8_date_only_availability_is_conservative(self) -> None:
        left = _sample_frame(date(2026, 3, 10), date(2026, 3, 11))
        source = pl.DataFrame(
            {
                "instrument_id": [1],
                "trade_date": ["2026-03-10"],
                "availability_time": ["2026-03-10"],
                "value": [5.0],
            }
        )
        joined = _pit_join(left_frame=left, source_frame=source, derived_id="factor")
        assert joined["factor"].to_list() == [None, 5.0]

    @pytest.mark.pit
    def test_missing_availability_falls_back_to_conservative_trade_date(self) -> None:
        left = _sample_frame(date(2026, 3, 10), date(2026, 3, 11))
        source = pl.DataFrame(
            {
                "instrument_id": [1, 1],
                "trade_date": [date(2026, 3, 9), date(2026, 3, 10)],
                "value": [3.0, 4.0],
            }
        )
        joined = _pit_join(left_frame=left, source_frame=source, derived_id="factor")
        assert joined["factor"].to_list() == [3.0, 4.0]

    @pytest.mark.pit
    def test_null_availability_rows_fall_back_to_trade_date(self) -> None:
        left = _sample_frame(date(2026, 3, 10))
        source = pl.DataFrame(
            {
                "instrument_id": [1, 1],
                "trade_date": [date(2026, 3, 9), date(2026, 3, 10)],
                "availability_time": [None, None],
                "value": [3.0, 4.0],
            }
        )
        joined = _pit_join(left_frame=left, source_frame=source, derived_id="factor")
        assert joined["factor"].to_list() == [3.0]

    def test_naive_datetime_availability_is_exact_wall_time(self) -> None:
        left = _sample_frame(date(2026, 3, 10))
        source = pl.DataFrame(
            {
                "instrument_id": [1],
                "trade_date": [date(2026, 3, 10)],
                "availability_time": [datetime(2026, 3, 10, 0, 0, 0)],
                "value": [9.0],
            }
        )
        joined = _pit_join(left_frame=left, source_frame=source, derived_id="factor")
        assert joined["factor"].to_list() == [9.0]

    def test_utc_offset_availability_is_converted(self) -> None:
        left = _sample_frame(date(2026, 3, 10))
        source = pl.DataFrame(
            {
                "instrument_id": [1, 1],
                "trade_date": ["2026-03-09", "2026-03-09"],
                "availability_time": [
                    "2026-03-09T18:00:00+08:00",
                    "2026-03-09T10:00:00+00:00",
                ],
                "value": [1.0, 2.0],
            }
        )
        joined = _pit_join(left_frame=left, source_frame=source, derived_id="factor")
        # Both rows declare the same instant; the later row in stable sort order
        # wins the backward-asof tie.
        assert joined["factor"].to_list() == [2.0]

    def test_unparseable_availability_fails_closed(self) -> None:
        left = _sample_frame(date(2026, 3, 10))
        source = pl.DataFrame(
            {
                "instrument_id": [1],
                "trade_date": [date(2026, 3, 10)],
                "availability_time": ["garbage"],
                "value": [1.0],
            }
        )
        with pytest.raises(AppQueryError):
            _pit_join(left_frame=left, source_frame=source, derived_id="factor")

    def test_empty_source_keeps_left_rows_with_nulls(self) -> None:
        left = _sample_frame(date(2026, 3, 10), date(2026, 3, 11))
        joined = _pit_join(
            left_frame=left, source_frame=pl.DataFrame(), derived_id="factor"
        )
        assert joined["factor"].to_list() == [None, None]

    def test_multiple_instruments_partition_independently(self) -> None:
        left = _attach_known_at(
            frame=pl.DataFrame(
                {
                    "sample_row_id": [0, 1],
                    "instrument_id": [1, 2],
                    "trade_date": [date(2026, 3, 10), date(2026, 3, 10)],
                }
            ),
            known_at_policy=KnownAtPolicy.SAMPLE_TIME,
            explicit_cutoff=None,
        )
        source = pl.DataFrame(
            {
                "instrument_id": [1, 2],
                "trade_date": [date(2026, 3, 10), date(2026, 3, 10)],
                "availability_time": [
                    "2026-03-10T15:30:00+08:00",
                    "2026-03-09T18:00:00+08:00",
                ],
                "value": [11.0, 22.0],
            }
        )
        joined = _pit_join(left_frame=left, source_frame=source, derived_id="factor")
        assert joined["factor"].to_list() == [None, 22.0]
