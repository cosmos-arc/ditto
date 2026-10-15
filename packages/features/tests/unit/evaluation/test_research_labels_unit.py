"""Unit tests for the v1 forward-return research label builder."""

from __future__ import annotations

from datetime import date

import polars as pl
import pytest
from ditto_features.errors import EvaluationError
from ditto_features.evaluation.research_labels import (
    HOLDING_SESSIONS_V1,
    LABEL_STATUS_MATURE,
    LABEL_STATUS_PATH_INCOMPLETE,
    LABEL_STATUS_UNFILLABLE_ENTRY,
    LABEL_STATUS_UNFILLABLE_EXIT,
    RESEARCH_LABEL_FORWARD_RETURN_V1,
    build_forward_return_labels,
    label_spec_hash,
    label_spec_payload,
)

SESSIONS = [date(2026, 1, d) for d in range(1, 9)]  # d0..d7, 8 sessions
_EPOCH_BASE = 1_000_000_000_000_000  # fixed microseconds for hand checks


def _price_frame(
    rows: list[tuple[str, int, float, float, float, bool, bool]],
) -> pl.DataFrame:
    """Rows: (instrument, session_index, open, close, adj, buy_open, sell_close)."""
    return pl.DataFrame(
        {
            "instrument_id": [item[0] for item in rows],
            "session": [SESSIONS[item[1]] for item in rows],
            "open": [float(item[2]) for item in rows],
            "close": [float(item[3]) for item in rows],
            "adj_factor": [float(item[4]) for item in rows],
            "buy_fillable_open": [item[5] for item in rows],
            "sell_fillable_close": [item[6] for item in rows],
            "session_close_known_at_epoch_us": [
                _EPOCH_BASE + item[1] * 86_400_000_000 for item in rows
            ],
        },
        schema={
            "instrument_id": pl.String,
            "session": pl.Date,
            "open": pl.Float64,
            "close": pl.Float64,
            "adj_factor": pl.Float64,
            "buy_fillable_open": pl.Boolean,
            "sell_fillable_close": pl.Boolean,
            "session_close_known_at_epoch_us": pl.Int64,
        },
    )


def _full_instrument(
    instrument: str, *, adj: float = 1.0
) -> list[tuple[str, int, float, float, float, bool, bool]]:
    return [
        (instrument, index, 10.0 + index, 10.5 + index, adj, True, True)
        for index in range(len(SESSIONS))
    ]


def test_label_spec_payload_is_stable_and_hashed() -> None:
    payload = label_spec_payload()
    assert payload["label_id"] == RESEARCH_LABEL_FORWARD_RETURN_V1
    assert payload["holding_sessions"] == 5
    assert label_spec_hash() == label_spec_hash()
    assert len(label_spec_hash()) == 64


def test_mature_label_value_matches_hand_computation() -> None:
    # A: entry d1 open=11.0, exit d5 close=15.5, adj 1.0 -> 15.5/11.0-1
    frame = build_forward_return_labels(_price_frame(_full_instrument("A")), SESSIONS)
    rows = frame.frame.filter(
        (pl.col("instrument_id") == "A") & (pl.col("decision_session") == SESSIONS[0])
    )
    assert rows.height == 1
    row = rows.to_dicts()[0]
    assert row["entry_session"] == SESSIONS[1]
    assert row["exit_session"] == SESSIONS[5]
    assert row["status"] == LABEL_STATUS_MATURE
    assert row["label_value"] == pytest.approx(15.5 / 11.0 - 1.0)
    assert row["mature_at_epoch_us"] == _EPOCH_BASE + 5 * 86_400_000_000


def test_decision_sessions_limited_by_calendar_tail() -> None:
    frame = build_forward_return_labels(_price_frame(_full_instrument("A")), SESSIONS)
    decisions = frame.frame.get_column("decision_session").to_list()
    # last decision d2: entry d3, exit d7 still inside the calendar.
    assert decisions == [SESSIONS[0], SESSIONS[1], SESSIONS[2]]


def test_adjustment_factor_scales_total_return() -> None:
    # entry d1 open=11.0 adj=2.0, exit d5 close=15.5 adj=2.2:
    # (15.5*2.2)/(11.0*2.0)-1
    rows_raw = _full_instrument("B")
    rows = []
    for item in rows_raw:
        rows.append((*item[:4], 2.0 if item[1] <= 1 else 2.2, *item[5:]))
    frame = build_forward_return_labels(_price_frame(rows), SESSIONS)
    row = frame.frame.filter(pl.col("decision_session") == SESSIONS[0]).to_dicts()[0]
    assert row["status"] == LABEL_STATUS_MATURE
    assert row["label_value"] == pytest.approx((15.5 * 2.2) / (11.0 * 2.0) - 1.0)


def test_unfillable_entry_and_exit_are_marked_not_dropped() -> None:
    rows = _full_instrument("C")
    rows[3] = ("C", 3, 13.0, 13.5, 1.0, False, True)  # entry d3 buy blocked
    rows[6] = ("C", 6, 16.0, 16.5, 1.0, True, False)  # exit d6 sell blocked
    frame = build_forward_return_labels(_price_frame(rows), SESSIONS)
    by_decision = {row["decision_session"]: row for row in frame.frame.to_dicts()}
    assert by_decision[SESSIONS[2]]["status"] == LABEL_STATUS_UNFILLABLE_ENTRY
    assert by_decision[SESSIONS[2]]["label_value"] is None
    assert by_decision[SESSIONS[1]]["status"] == LABEL_STATUS_UNFILLABLE_EXIT
    assert by_decision[SESSIONS[1]]["label_value"] is None


def test_missing_exit_path_is_path_incomplete() -> None:
    rows = [item for item in _full_instrument("D") if item[1] != 5]
    frame = build_forward_return_labels(_price_frame(rows), SESSIONS)
    statuses = {
        row["decision_session"]: row["status"] for row in frame.frame.to_dicts()
    }
    assert statuses[SESSIONS[0]] == LABEL_STATUS_PATH_INCOMPLETE
    assert statuses[SESSIONS[1]] == LABEL_STATUS_MATURE  # exit d6 intact


def test_duplicate_price_rows_fail_closed() -> None:
    rows = _full_instrument("E")
    duplicated = [*rows, rows[0]]
    with pytest.raises(EvaluationError):
        build_forward_return_labels(_price_frame(duplicated), SESSIONS)


def test_nonpositive_prices_fail_closed() -> None:
    rows = _full_instrument("F")
    rows[3] = ("F", 3, 0.0, 13.5, 1.0, True, True)
    with pytest.raises(EvaluationError):
        build_forward_return_labels(_price_frame(rows), SESSIONS)


def test_short_calendar_fail_closed() -> None:
    with pytest.raises(EvaluationError):
        build_forward_return_labels(_price_frame(_full_instrument("G")), SESSIONS[:5])


def test_holding_sessions_constant_matches_spec() -> None:
    assert HOLDING_SESSIONS_V1 == 5
