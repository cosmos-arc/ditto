"""Frozen ordinary membership intervals and explicit daily participation."""

from __future__ import annotations

from datetime import date, timedelta
from itertools import pairwise
from typing import cast

import polars as pl
from ditto_data.services.metadata_service import MetadataService
from ditto_execution.reality.ordinary_equity import MIN_ORDINARY_LISTED_DAYS

from ditto_application.exceptions import AppBuilderError


def daily_participation(
    roster: list[dict[str, object]],
    days: list[str],
    *,
    warmup_days: int,
    knowledge_lag_days: int,
) -> pl.DataFrame:
    """Project half-open membership and listing life; count actual prior sessions."""
    intervals = pl.DataFrame(roster).with_columns(
        pl.col("effective_from", "effective_to", "list_date", "delist_date")
        .cast(pl.String)
        .str.to_date(),
    )
    calendar = pl.Series("trade_date", days).str.to_date().sort()
    grid = intervals.join(calendar.to_frame(), how="cross")
    membership = (pl.col("effective_from") <= pl.col("trade_date")) & (
        pl.col("effective_to").is_null()
        | (pl.col("trade_date") < pl.col("effective_to"))
    )
    grid = (
        grid.with_columns(membership.alias("member"))
        .group_by("instrument_id", "trade_date", "list_date", "delist_date")
        .agg(pl.col("member").any())
    )
    cutoff = grid["trade_date"] - timedelta(days=knowledge_lag_days)
    available = (
        calendar.search_sorted(cutoff).cast(pl.Int64)
        - calendar.search_sorted(grid["list_date"]).cast(pl.Int64)
    ).clip(lower_bound=0)
    grid = grid.with_columns(
        available.alias("warmup_available"),
        pl.lit(warmup_days).alias("warmup_required"),
        (
            (pl.col("list_date") <= pl.col("trade_date"))
            & (
                pl.col("delist_date").is_null()
                | (pl.col("trade_date") < pl.col("delist_date"))
            )
        ).alias("requires_quote"),
    )
    # IPO execution rules remain unqualified in this ordinary rule cohort.
    # Retain the interval and its explicit reason instead of deleting the security.
    return grid.with_columns(
        (
            pl.col("requires_quote")
            & (
                (pl.col("trade_date") - pl.col("list_date")).dt.total_days()
                >= MIN_ORDINARY_LISTED_DAYS
            )
        ).alias("execution_available"),
        pl.when(pl.col("trade_date") < pl.col("list_date"))
        .then(pl.lit("not_listed"))
        .when(pl.col("trade_date") >= pl.col("delist_date"))
        .then(pl.lit("delisted"))
        .when(~pl.col("member"))
        .then(pl.lit("outside_universe"))
        .when(pl.col("warmup_available") < warmup_days)
        .then(pl.lit("warmup"))
        .when(
            (pl.col("trade_date") - pl.col("list_date")).dt.total_days()
            < MIN_ORDINARY_LISTED_DAYS
        )
        .then(pl.lit("listing_rule_unavailable"))
        .otherwise(pl.lit("eligible"))
        .alias("status"),
        pl.col("trade_date").cast(pl.String),
    ).sort("trade_date", "instrument_id")


def freeze_roster(
    metadata: MetadataService,
    universe: str,
    *,
    start: str,
    end: str,
    source: str,
    original: dict[str, object] | None = None,
) -> list[dict[str, object]]:
    """Freeze interval and identity facts now; never claim original-vintage proof."""
    saved = original.get("roster") if original is not None else None
    if saved:
        if not isinstance(saved, list) or not all(
            isinstance(row, dict) for row in cast(list[object], saved)
        ):
            raise AppBuilderError("invalid frozen membership intervals")
        return _validated_roster(cast(list[dict[str, object]], saved))
    intervals = metadata.universe.get_constituent_history(universe)
    legacy_ids = original.get("instrument_ids") if original is not None else None
    if legacy_ids:
        if not isinstance(legacy_ids, list) or not all(
            type(iid) is int and iid > 0 for iid in cast(list[object], legacy_ids)
        ):
            raise AppBuilderError("invalid original historical security scope")
        # Legacy requests froze only the start-day IDs; repair must retain them.
        intervals = [
            {"instrument_id": iid, "effective_from": start, "effective_to": None}
            for iid in cast(list[int], legacy_ids)
        ]
    result: list[dict[str, object]] = []
    for interval in intervals:
        first, last = str(interval["effective_from"]), interval.get("effective_to")
        if first > end or (last is not None and str(last) <= start):
            continue
        iid = int(str(interval["instrument_id"]))
        record = metadata.instrument.get_instrument(iid)
        if record is None or not record.get("list_date"):
            raise AppBuilderError(f"missing historical listing identity: {iid}")
        listed = str(record["list_date"])
        ticker = metadata.instrument.get_source_ticker(iid, source, max(start, listed))
        if not ticker:
            raise AppBuilderError(f"missing historical provider identity: {iid}")
        result.append(
            {
                "instrument_id": iid,
                "effective_from": first,
                "effective_to": last,
                "list_date": listed,
                "delist_date": record.get("delist_date"),
                "ticker": str(record["ticker"]),
                "exchange": str(record["exchange"]),
                "asset_class": str(record["asset_class"]),
                "source_ticker": ticker,
            }
        )
    if not result:
        raise AppBuilderError(
            f"universe {universe} 在 {start}..{end} 解析到 0 成员; 检查成员历史区间"
        )
    return _validated_roster(result)


def _validated_roster(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    """Reject malformed frozen identities rather than refreshing a saved scope."""
    intervals: dict[int, list[tuple[str, str]]] = {}
    identities: dict[int, tuple[object, ...]] = {}
    for row in rows:
        iid = row.get("instrument_id")
        if type(iid) is not int or iid <= 0:
            raise AppBuilderError("invalid frozen instrument identity")
        required = (
            "effective_from",
            "list_date",
            "source_ticker",
            "ticker",
            "exchange",
            "asset_class",
        )
        if any(not isinstance(row.get(key), str) or not row[key] for key in required):
            raise AppBuilderError(f"missing frozen membership identity fields: {iid}")
        for key in ("effective_from", "effective_to", "list_date", "delist_date"):
            if row.get(key) is not None:
                date.fromisoformat(str(row[key]))
        first, last = (
            str(row["effective_from"]),
            str(row.get("effective_to") or "9999-12-31"),
        )
        identity = tuple(
            row.get(key)
            for key in (
                "list_date",
                "delist_date",
                "source_ticker",
                "ticker",
                "exchange",
                "asset_class",
            )
        )
        if first >= last or (iid in identities and identities[iid] != identity):
            raise AppBuilderError(f"conflicting frozen membership identity: {iid}")
        identities[iid] = identity
        intervals.setdefault(iid, []).append((first, last))
    for iid, periods in intervals.items():
        ordered = sorted(periods)
        if any(left[1] > right[0] for left, right in pairwise(ordered)):
            raise AppBuilderError(f"overlapping frozen membership intervals: {iid}")
    return rows
