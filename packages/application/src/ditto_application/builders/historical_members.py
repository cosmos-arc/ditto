"""Frozen ordinary membership intervals and explicit daily participation."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from itertools import pairwise
from typing import cast

from ditto_data.services.metadata_service import MetadataService

from ditto_application.exceptions import AppBuilderError


def freeze_membership_intervals(
    metadata: MetadataService,
    universe: str,
    *,
    start: str,
    end: str,
    original: dict[str, object] | None = None,
) -> list[dict[str, object]]:
    """Pin the whole requested scope before any identity lookup can fail."""
    saved = (
        original.get("membership_intervals", original.get("roster"))
        if original is not None
        else None
    )
    if saved is not None and saved != []:
        if not isinstance(saved, list) or not all(
            isinstance(row, dict) for row in cast(list[object], saved)
        ):
            raise AppBuilderError("invalid frozen membership intervals")
        intervals = cast(list[dict[str, object]], saved)
    else:
        intervals = metadata.universe.get_constituent_history(universe)
        legacy_ids = original.get("instrument_ids") if original is not None else None
        if legacy_ids is not None and legacy_ids != []:
            if not isinstance(legacy_ids, list) or not all(
                type(iid) is int and iid > 0 for iid in cast(list[object], legacy_ids)
            ):
                raise AppBuilderError("invalid original historical security scope")
            intervals = [
                {"instrument_id": iid, "effective_from": start, "effective_to": None}
                for iid in cast(list[int], legacy_ids)
            ]
    selected: list[dict[str, object]] = []
    for interval in intervals:
        first, last = str(interval["effective_from"]), interval.get("effective_to")
        date.fromisoformat(first)
        if last is not None:
            date.fromisoformat(str(last))
        if first <= end and (last is None or str(last) > start):
            selected.append(
                {
                    "instrument_id": int(str(interval["instrument_id"])),
                    "effective_from": first,
                    "effective_to": last,
                }
            )
    if not selected:
        raise AppBuilderError(
            f"universe {universe} 在 {start}..{end} 解析到 0 成员; 检查成员历史区间"
        )
    return selected


def freeze_roster(
    metadata: MetadataService,
    intervals: list[dict[str, object]],
    *,
    start: str,
    source: str,
    original: dict[str, object] | None = None,
) -> Iterator[dict[str, object]]:
    """Retain every resolved identity even if a later member lacks evidence."""
    saved = original.get("roster") if original is not None else None
    known: dict[int, dict[str, object]] = {}
    if saved is not None and saved != []:
        if not isinstance(saved, list) or not all(
            isinstance(row, dict) for row in cast(list[object], saved)
        ):
            raise AppBuilderError("invalid frozen listing identities")
        known = {
            int(str(row["instrument_id"])): row
            for row in _validated_roster(cast(list[dict[str, object]], saved))
        }
    resolved: list[dict[str, object]] = []
    for interval in intervals:
        iid = int(str(interval["instrument_id"]))
        if iid not in known:
            record = metadata.instrument.get_instrument(iid)
            if record is None or not record.get("list_date"):
                raise AppBuilderError(f"missing historical listing identity: {iid}")
            listed = str(record["list_date"])
            ticker = metadata.instrument.get_source_ticker(
                iid, source, max(start, listed)
            )
            if not ticker:
                raise AppBuilderError(f"missing historical provider identity: {iid}")
            known[iid] = {
                "instrument_id": iid,
                "list_date": listed,
                "delist_date": record.get("delist_date"),
                "ticker": str(record["ticker"]),
                "exchange": str(record["exchange"]),
                "asset_class": str(record["asset_class"]),
                "source_ticker": ticker,
            }
        row = {**known[iid], **interval}
        _validated_roster([row])
        resolved.append(row)
        yield row
    _validated_roster(resolved)


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
