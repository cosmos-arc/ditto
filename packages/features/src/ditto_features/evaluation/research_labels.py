"""
Versioned forward-return research labels with maturity and fillability.

Label semantics (v1, fixed by the P1-ML parent spec): decide on the close
information of session ``D``, enter at the open of the next trading session,
hold five target trading sessions, exit at the close of the fifth held
session. The label value is the adjustment-factor-scaled total return between
the planned entry fill and the planned exit fill.

Samples that cannot fill at the planned entry or exit are explicitly marked
and never silently rolled forward onto another interval. Maturity is exposed
as the exit session's close knowledge time; consumers must apply their own
knowledge cutoff (fail-closed PIT filtering happens at consumption).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date
from itertools import pairwise
from typing import cast

import orjson
import polars as pl

from ditto_features.errors import EvaluationError

__all__ = [
    "HOLDING_SESSIONS_V1",
    "LABEL_PRICE_FRAME_SCHEMA",
    "RESEARCH_LABEL_FORWARD_RETURN_V1",
    "ResearchLabelFrame",
    "build_forward_return_labels",
    "label_spec_payload",
]

RESEARCH_LABEL_FORWARD_RETURN_V1 = "research.label.forward_return.next_open_hold5.v1"
HOLDING_SESSIONS_V1 = 5

LABEL_STATUS_MATURE = "mature"
LABEL_STATUS_UNFILLABLE_ENTRY = "unfillable_entry"
LABEL_STATUS_UNFILLABLE_EXIT = "unfillable_exit"
LABEL_STATUS_PATH_INCOMPLETE = "path_incomplete"
LABEL_STATUSES = frozenset(
    {
        LABEL_STATUS_MATURE,
        LABEL_STATUS_UNFILLABLE_ENTRY,
        LABEL_STATUS_UNFILLABLE_EXIT,
        LABEL_STATUS_PATH_INCOMPLETE,
    }
)

_PRICE_COLUMNS: tuple[tuple[str, pl.DataType], ...] = (
    ("instrument_id", pl.String()),
    ("session", pl.Date()),
    ("open", pl.Float64()),
    ("close", pl.Float64()),
    ("adj_factor", pl.Float64()),
    ("buy_fillable_open", pl.Boolean()),
    ("sell_fillable_close", pl.Boolean()),
    ("session_close_known_at_epoch_us", pl.Int64()),
)
LABEL_PRICE_FRAME_SCHEMA = frozenset(name for name, _ in _PRICE_COLUMNS)

_LABEL_COLUMNS: tuple[tuple[str, pl.DataType], ...] = (
    ("instrument_id", pl.String()),
    ("decision_session", pl.Date()),
    ("entry_session", pl.Date()),
    ("exit_session", pl.Date()),
    ("label_value", pl.Float64()),
    ("status", pl.String()),
    ("mature_at_epoch_us", pl.Int64()),
)


def _labels_error(reason: str, **details: object) -> EvaluationError:
    return EvaluationError(
        f"forward-return research label build failed closed: {reason}",
        details={"reason": reason, **details},
    )


def label_spec_payload() -> dict[str, object]:
    """Return the canonical label definition payload bound at registration."""
    return {
        "schema_version": 1,
        "label_id": RESEARCH_LABEL_FORWARD_RETURN_V1,
        "decision_information": "decision_session_close",
        "entry_rule": "next_session_open",
        "holding_sessions": HOLDING_SESSIONS_V1,
        "exit_rule": "holding_end_session_close",
        "total_return_basis": "adj_factor_scaled_open_close_ratio",
    }


def label_spec_hash() -> str:
    """Return the SHA-256 identity of the v1 label definition."""
    encoded = orjson.dumps(label_spec_payload(), option=orjson.OPT_SORT_KEYS)
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class ResearchLabelFrame:
    """Validated label rows plus the exact spec identity they were built under."""

    label_id: str
    holding_sessions: int
    frame: pl.DataFrame

    def __post_init__(self) -> None:
        """Validate identity, then delegate row-level consistency checks."""
        if self.label_id != RESEARCH_LABEL_FORWARD_RETURN_V1:
            raise _labels_error("unsupported_label_id", label_id=self.label_id)
        if self.holding_sessions != HOLDING_SESSIONS_V1:
            raise _labels_error(
                "unsupported_holding_sessions",
                holding_sessions=self.holding_sessions,
            )
        if type(self.frame) is not pl.DataFrame:
            raise _labels_error("label_frame_not_dataframe")
        _validate_label_frame(self.frame)


def _validate_label_frame(frame: pl.DataFrame) -> None:
    """Validate schema, key uniqueness, and status/label consistency."""
    schema = frame.schema
    for name, dtype in _LABEL_COLUMNS:
        if schema.get(name) != dtype:
            raise _labels_error(
                "label_frame_schema_invalid",
                column=name,
                expected=str(dtype),
                observed=str(schema.get(name)),
            )
    if frame.is_empty():
        raise _labels_error("label_frame_empty")
    duplicate_keys = (
        frame.select(["instrument_id", "decision_session"]).is_duplicated().any()
    )
    if duplicate_keys:
        raise _labels_error("label_frame_duplicate_decision_key")
    if not frame.get_column("status").is_in(list(LABEL_STATUSES)).all():
        raise _labels_error("label_frame_status_invalid")
    status = pl.col("status")
    if (
        frame.filter(
            (status == LABEL_STATUS_MATURE).ne_missing(
                pl.col("label_value").is_not_null()
            )
        ).height
        != 0
    ):
        raise _labels_error("label_frame_value_status_inconsistent")
    mature_rows = frame.filter(status == LABEL_STATUS_MATURE)
    if mature_rows.height and (
        mature_rows.get_column("mature_at_epoch_us").null_count() != 0
    ):
        raise _labels_error("label_frame_maturity_missing")


def _require_price_frame(prices: pl.DataFrame) -> pl.DataFrame:
    if type(prices) is not pl.DataFrame:
        raise _labels_error("price_frame_not_dataframe")
    schema = prices.schema
    for name, dtype in _PRICE_COLUMNS:
        if schema.get(name) != dtype:
            raise _labels_error(
                "price_frame_schema_invalid",
                column=name,
                expected=str(dtype),
                observed=str(schema.get(name)),
            )
    if prices.is_empty():
        raise _labels_error("price_frame_empty")
    duplicate_keys = prices.select(["instrument_id", "session"]).is_duplicated().any()
    if duplicate_keys:
        raise _labels_error("price_frame_duplicate_instrument_session")
    positive = prices.select(
        (
            (pl.col("open") > 0.0)
            & (pl.col("close") > 0.0)
            & (pl.col("adj_factor") > 0.0)
            & pl.col("open").is_not_null()
            & pl.col("close").is_not_null()
            & pl.col("adj_factor").is_not_null()
        ).all()
    ).item()
    if positive is not True:
        raise _labels_error("price_frame_nonpositive_prices")
    if prices.get_column("session_close_known_at_epoch_us").null_count() != 0:
        raise _labels_error("price_frame_known_at_missing")
    return prices


def _require_trading_sessions(sessions: list[date] | tuple[date, ...]) -> pl.Series:
    if isinstance(sessions, (str, bytes)):
        raise _labels_error("trading_sessions_invalid")
    if not sessions:
        raise _labels_error("trading_sessions_empty")
    series = pl.Series(
        "calendar_session",
        values=cast("list[object]", list(sessions)),
        dtype=pl.Date,
        strict=True,
    )
    if series.len() <= HOLDING_SESSIONS_V1:
        raise _labels_error("trading_sessions_too_short")
    values = series.to_list()
    if any(current >= following for current, following in pairwise(values)):
        raise _labels_error("trading_sessions_not_strictly_increasing")
    return series


def build_forward_return_labels(
    prices: pl.DataFrame,
    trading_sessions: list[date] | tuple[date, ...],
) -> ResearchLabelFrame:
    """
    Build one label row per (instrument, decision session).

    The caller owns the price/limit semantics: ``buy_fillable_open`` and
    ``sell_fillable_close`` already encode suspension and locked-limit days so
    this builder never re-derives exchange rules.
    """
    validated = _require_price_frame(prices)
    calendar = _require_trading_sessions(trading_sessions)
    calendar_frame = calendar.to_frame().with_row_index(name="session_ordinal")
    last_decision_ordinal = calendar_frame.height - 1 - HOLDING_SESSIONS_V1
    if last_decision_ordinal < 0:
        raise _labels_error("trading_sessions_too_short")

    priced = validated.join(
        calendar_frame,
        left_on="session",
        right_on="calendar_session",
        how="inner",
    ).filter(pl.col("session_ordinal") <= last_decision_ordinal)

    entry_target = calendar_frame.rename(
        {"calendar_session": "entry_session", "session_ordinal": "entry_ordinal"}
    )
    exit_target = calendar_frame.rename(
        {"calendar_session": "exit_session", "session_ordinal": "exit_ordinal"}
    )
    entry_source = validated.select(
        [
            pl.col("instrument_id"),
            pl.col("session").alias("entry_match_session"),
            pl.col("open").alias("entry_open"),
            pl.col("adj_factor").alias("entry_adj_factor"),
            pl.col("buy_fillable_open").alias("entry_buy_fillable"),
        ]
    )
    exit_source = validated.select(
        [
            pl.col("instrument_id"),
            pl.col("session").alias("exit_match_session"),
            pl.col("close").alias("exit_close"),
            pl.col("adj_factor").alias("exit_adj_factor"),
            pl.col("sell_fillable_close").alias("exit_sell_fillable"),
            pl.col("session_close_known_at_epoch_us").alias("exit_known_at"),
        ]
    )

    decisions = (
        priced.select(
            [
                pl.col("instrument_id"),
                pl.col("session").alias("decision_session"),
                pl.col("session_ordinal").alias("decision_ordinal"),
            ]
        )
        .with_columns(
            (pl.col("decision_ordinal") + 1).alias("entry_ordinal"),
            (pl.col("decision_ordinal") + HOLDING_SESSIONS_V1).alias("exit_ordinal"),
        )
        .join(entry_target, on="entry_ordinal", how="left")
        .join(exit_target, on="exit_ordinal", how="left")
        .join(
            entry_source,
            left_on=["instrument_id", "entry_session"],
            right_on=["instrument_id", "entry_match_session"],
            how="left",
        )
        .join(
            exit_source,
            left_on=["instrument_id", "exit_session"],
            right_on=["instrument_id", "exit_match_session"],
            how="left",
        )
    )

    entry_present = (
        pl.col("entry_session").is_not_null()
        & pl.col("entry_open").is_not_null()
        & pl.col("entry_adj_factor").is_not_null()
    )
    exit_present = (
        pl.col("exit_session").is_not_null()
        & pl.col("exit_close").is_not_null()
        & pl.col("exit_adj_factor").is_not_null()
    )
    labels = decisions.with_columns(
        pl.when(~entry_present | ~exit_present)
        .then(pl.lit(LABEL_STATUS_PATH_INCOMPLETE))
        .when(pl.col("entry_buy_fillable").ne_missing(True))
        .then(pl.lit(LABEL_STATUS_UNFILLABLE_ENTRY))
        .when(pl.col("exit_sell_fillable").ne_missing(True))
        .then(pl.lit(LABEL_STATUS_UNFILLABLE_EXIT))
        .otherwise(pl.lit(LABEL_STATUS_MATURE))
        .alias("status"),
        (
            (pl.col("exit_close") * pl.col("exit_adj_factor"))
            / (pl.col("entry_open") * pl.col("entry_adj_factor"))
            - 1.0
        ).alias("label_value"),
    )
    # Only mature rows carry a label value; excluded samples stay visible with
    # their interval, status, and (when known) exit knowledge time.
    labels = labels.with_columns(
        pl.when(pl.col("status") == LABEL_STATUS_MATURE)
        .then(pl.col("label_value"))
        .otherwise(None)
        .alias("label_value"),
    )
    frame = labels.select(
        [
            pl.col("instrument_id"),
            pl.col("decision_session"),
            pl.col("entry_session"),
            pl.col("exit_session"),
            pl.col("label_value"),
            pl.col("status"),
            pl.col("exit_known_at").alias("mature_at_epoch_us"),
        ]
    ).sort(["instrument_id", "decision_session"])
    return ResearchLabelFrame(
        label_id=RESEARCH_LABEL_FORWARD_RETURN_V1,
        holding_sessions=HOLDING_SESSIONS_V1,
        frame=frame,
    )
