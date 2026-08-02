"""Build exact live R3 frame inputs from the isolated R2 SQLite root."""

from __future__ import annotations

import sqlite3
from bisect import bisect_left
from datetime import date, timedelta
from math import isfinite
from pathlib import Path
from typing import Literal, cast

import polars as pl

type LiveLane = Literal["stock", "etf"]

LIVE_START = date(2015, 2, 1)
LIVE_END = date(2026, 7, 31)
_STOCK_INDEX = "000300.SH"
_ETF_IDS = (2_002_506, 2_002_571, 2_002_631)


def open_live_database(data_root: Path) -> sqlite3.Connection:
    """Open the exact isolated live metadata database with named rows."""
    path = data_root / "metadata" / "metadata.sqlite"
    if not path.is_file():
        raise ValueError(f"live metadata database is missing: {path}")
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    return connection


def build_calendar_frame(
    connection: sqlite3.Connection,
    *,
    authority_snapshot_id: str,
) -> tuple[pl.DataFrame, tuple[date, ...]]:
    """Build the complete natural-day calendar and ordered open sessions."""
    rows = connection.execute(
        """
        SELECT trade_date, is_open
        FROM trading_calendar
        WHERE trade_date BETWEEN ? AND ?
        ORDER BY trade_date
        """,
        (LIVE_START.isoformat(), LIVE_END.isoformat()),
    ).fetchall()
    expected_days = (LIVE_END - LIVE_START).days + 1
    if len(rows) != expected_days:
        raise ValueError("live calendar does not contain every natural day")
    dates = tuple(date.fromisoformat(str(row["trade_date"])) for row in rows)
    sessions = tuple(
        observed
        for observed, row in zip(dates, rows, strict=True)
        if bool(row["is_open"])
    )
    if not sessions:
        raise ValueError("live calendar contains no open sessions")
    return (
        pl.DataFrame(
            {
                "trade_date": dates,
                "is_open": tuple(bool(row["is_open"]) for row in rows),
                "source_snapshot_id": (authority_snapshot_id,) * len(rows),
            },
            schema={
                "trade_date": pl.Date,
                "is_open": pl.Boolean,
                "source_snapshot_id": pl.String,
            },
        ),
        sessions,
    )


def build_stock_membership_frame(
    connection: sqlite3.Connection,
    sessions: tuple[date, ...],
    *,
    authority_snapshot_id: str,
) -> pl.DataFrame:
    """Project point-in-time CSI300 membership onto every open session."""
    rows = connection.execute(
        """
        SELECT instrument_id, effective_from
        FROM index_weight
        WHERE index_id = ? AND effective_from <= ?
        ORDER BY effective_from, instrument_id
        """,
        (_STOCK_INDEX, LIVE_END.isoformat()),
    ).fetchall()
    by_effective: dict[date, list[int]] = {}
    for row in rows:
        effective = date.fromisoformat(str(row["effective_from"]))
        by_effective.setdefault(effective, []).append(int(row["instrument_id"]))
    effective_dates = tuple(sorted(by_effective))
    if not effective_dates:
        raise ValueError("CSI300 PIT membership evidence is missing")
    output_dates: list[date] = []
    instrument_ids: list[int] = []
    known_at: list[date] = []
    for session in sessions:
        position = bisect_left(effective_dates, session) - 1
        if position < 0:
            continue
        effective = effective_dates[position]
        members = by_effective[effective]
        output_dates.extend((session,) * len(members))
        instrument_ids.extend(members)
        known_at.extend((effective,) * len(members))
    if not output_dates:
        raise ValueError("CSI300 PIT membership projection is empty")
    return pl.DataFrame(
        {
            "trade_date": output_dates,
            "instrument_id": instrument_ids,
            "is_member": (True,) * len(output_dates),
            "known_at": known_at,
            "source_snapshot_id": (authority_snapshot_id,) * len(output_dates),
        },
        schema={
            "trade_date": pl.Date,
            "instrument_id": pl.Int64,
            "is_member": pl.Boolean,
            "known_at": pl.Date,
            "source_snapshot_id": pl.String,
        },
    ).sort(["trade_date", "instrument_id"])


def build_etf_membership_frame(
    sessions: tuple[date, ...],
    *,
    authority_snapshot_id: str,
) -> pl.DataFrame:
    """Build the fixed ETF proving-lane membership with prior-day knowledge."""
    return pl.DataFrame(
        {
            "trade_date": tuple(day for day in sessions for _ in _ETF_IDS),
            "instrument_id": _ETF_IDS * len(sessions),
            "is_member": (True,) * (len(sessions) * len(_ETF_IDS)),
            "known_at": tuple(
                day - timedelta(days=1) for day in sessions for _ in _ETF_IDS
            ),
            "source_snapshot_id": (authority_snapshot_id,)
            * (len(sessions) * len(_ETF_IDS)),
        },
        schema={
            "trade_date": pl.Date,
            "instrument_id": pl.Int64,
            "is_member": pl.Boolean,
            "known_at": pl.Date,
            "source_snapshot_id": pl.String,
        },
    )


def build_fundamental_frame(
    connection: sqlite3.Connection,
    lane: LiveLane,
    instrument_ids: tuple[int, ...],
    *,
    authority_snapshot_id: str,
) -> pl.DataFrame:
    """Build complete PIT stock fundamentals or the neutral ETF schema."""
    if lane == "etf":
        return pl.DataFrame(
            {
                "instrument_id": instrument_ids,
                "known_at": (LIVE_START - timedelta(days=1),) * len(instrument_ids),
                "roe": (0.0,) * len(instrument_ids),
                "net_margin": (0.0,) * len(instrument_ids),
                "eps": (0.0,) * len(instrument_ids),
                "market_cap": (0.0,) * len(instrument_ids),
                "source_snapshot_id": (authority_snapshot_id,) * len(instrument_ids),
            },
            schema={
                "instrument_id": pl.Int64,
                "known_at": pl.Date,
                "roe": pl.Float64,
                "net_margin": pl.Float64,
                "eps": pl.Float64,
                "market_cap": pl.Float64,
                "source_snapshot_id": pl.String,
            },
        )
    query = (
        "SELECT i.instrument_id, i.knowledge_date AS income_known_at, "
        "b.knowledge_date AS balance_known_at, i.net_profit, i.revenue, "
        "i.eps, b.net_assets FROM income_statement AS i "
        "LEFT JOIN balance_sheet AS b ON b.instrument_id = i.instrument_id "
        "AND b.report_date = i.report_date WHERE i.instrument_id = ? "
        "AND i.knowledge_date <= ? "
        "ORDER BY i.instrument_id, i.knowledge_date, i.report_date"
    )
    rows = tuple(
        row
        for instrument_id in instrument_ids
        for row in connection.execute(
            query,
            (instrument_id, LIVE_END.isoformat()),
        ).fetchall()
    )
    output: list[dict[str, object]] = []
    for row in rows:
        instrument_id = int(row["instrument_id"])
        income_known = date.fromisoformat(str(row["income_known_at"]))
        balance_known = (
            income_known
            if row["balance_known_at"] is None
            else date.fromisoformat(str(row["balance_known_at"]))
        )
        net_profit = None if row["net_profit"] is None else float(row["net_profit"])
        revenue = None if row["revenue"] is None else float(row["revenue"])
        net_assets = None if row["net_assets"] is None else float(row["net_assets"])
        eps = None if row["eps"] is None else float(row["eps"])
        if (
            net_profit is None
            or revenue in {None, 0.0}
            or net_assets in {None, 0.0}
            or eps is None
        ):
            continue
        roe = net_profit / cast("float", net_assets)
        net_margin = net_profit / cast("float", revenue)
        if not all(isfinite(value) for value in (roe, net_margin, eps)):
            continue
        output.append(
            {
                "instrument_id": instrument_id,
                "known_at": max(income_known, balance_known),
                "roe": roe,
                "net_margin": net_margin,
                "eps": eps,
                "source_snapshot_id": authority_snapshot_id,
            }
        )
    financial = (
        pl.DataFrame(
            output,
            schema={
                "instrument_id": pl.Int64,
                "known_at": pl.Date,
                "roe": pl.Float64,
                "net_margin": pl.Float64,
                "eps": pl.Float64,
                "source_snapshot_id": pl.String,
            },
        )
        .unique(subset=("instrument_id", "known_at"), keep="last")
        .sort(["instrument_id", "known_at"])
    )
    if financial.is_empty():
        return financial.with_columns(
            pl.lit(None, dtype=pl.Float64).alias("market_cap")
        )

    placeholders = ",".join("?" for _ in instrument_ids)
    valuation_query = (
        f"SELECT instrument_id, trade_date, knowledge_date, market_cap FROM "  # noqa: S608 -- placeholders only
        f"valuation_metrics WHERE instrument_id IN ({placeholders}) "
        "AND knowledge_date <= ? AND market_cap IS NOT NULL ORDER BY "
        "instrument_id, knowledge_date, trade_date"
    )
    valuation = pl.read_database(
        query=valuation_query,
        connection=connection,
        execute_options={"parameters": (*instrument_ids, LIVE_END.isoformat())},
    )
    if valuation.is_empty():
        return financial.head(0).with_columns(
            pl.lit(None, dtype=pl.Float64).alias("market_cap")
        )
    valuation = (
        valuation.with_columns(
            pl.col("trade_date").cast(pl.String).str.to_date(),
            pl.col("knowledge_date").cast(pl.String).str.to_date().alias("known_at"),
            pl.col("market_cap").cast(pl.Float64),
        )
        .filter(pl.col("market_cap").is_finite() & (pl.col("market_cap") > 0.0))
        .sort(["instrument_id", "known_at", "trade_date"])
        .unique(subset=("instrument_id", "known_at"), keep="last")
        .select("instrument_id", "known_at", "market_cap")
        .sort(["instrument_id", "known_at"])
    )
    return (
        valuation.join_asof(
            financial.drop("source_snapshot_id"),
            on="known_at",
            by="instrument_id",
            strategy="backward",
            check_sortedness=False,
        )
        .drop_nulls(("roe", "net_margin", "eps", "market_cap"))
        .with_columns(pl.lit(authority_snapshot_id).alias("source_snapshot_id"))
        .select(
            "instrument_id",
            "known_at",
            "roe",
            "net_margin",
            "eps",
            "market_cap",
            "source_snapshot_id",
        )
        .sort(["instrument_id", "known_at"])
    )


def retain_complete_fundamental_membership(
    membership: pl.DataFrame,
    fundamental: pl.DataFrame,
) -> pl.DataFrame:
    """Start stock eligibility only after one complete PIT row is knowable."""
    first_known = fundamental.group_by("instrument_id").agg(
        pl.col("known_at").min().alias("first_fundamental_known_at")
    )
    return (
        membership.join(first_known, on="instrument_id", how="left")
        .filter(
            pl.col("first_fundamental_known_at").is_not_null()
            & (pl.col("first_fundamental_known_at") < pl.col("trade_date"))
        )
        .drop("first_fundamental_known_at")
        .sort(["trade_date", "instrument_id"])
    )


def align_instrument_lifecycle(
    connection: sqlite3.Connection,
    membership: pl.DataFrame,
) -> pl.DataFrame:
    """Remove index rows outside exact listed and delisted date boundaries."""
    instrument_ids = tuple(
        sorted(int(item) for item in membership["instrument_id"].unique())
    )
    if not instrument_ids:
        raise ValueError("live membership has no instrument identities")
    requested_ids = set(instrument_ids)
    rows = tuple(
        row
        for row in connection.execute(
            "SELECT instrument_id, list_date, delist_date FROM instrument"
        ).fetchall()
        if int(row["instrument_id"]) in requested_ids
    )
    observed_ids = {int(row["instrument_id"]) for row in rows}
    missing = sorted(set(instrument_ids) - observed_ids)
    if missing:
        rendered = ", ".join(str(item) for item in missing)
        raise ValueError(f"live membership instrument metadata is missing: {rendered}")
    lifecycle = pl.DataFrame(
        {
            "instrument_id": tuple(int(row["instrument_id"]) for row in rows),
            "_list_date": tuple(
                None
                if row["list_date"] is None
                else date.fromisoformat(str(row["list_date"]))
                for row in rows
            ),
            "_delist_date": tuple(
                None
                if row["delist_date"] is None
                else date.fromisoformat(str(row["delist_date"]))
                for row in rows
            ),
        },
        schema={
            "instrument_id": pl.Int64,
            "_list_date": pl.Date,
            "_delist_date": pl.Date,
        },
    )
    aligned = (
        membership.join(lifecycle, on="instrument_id", how="inner")
        .filter(
            (
                pl.col("_list_date").is_null()
                | (pl.col("trade_date") >= pl.col("_list_date"))
            )
            & (
                pl.col("_delist_date").is_null()
                | (pl.col("trade_date") <= pl.col("_delist_date"))
            )
        )
        .drop("_list_date", "_delist_date")
        .sort(["trade_date", "instrument_id"])
    )
    if aligned.is_empty():
        raise ValueError("live membership is empty after lifecycle alignment")
    return aligned
