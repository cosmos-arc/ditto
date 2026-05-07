"""Dependency reference classification for durable persistence."""

from __future__ import annotations

__all__ = ["dependency_refs"]


def dependency_refs(
    dependencies: tuple[str, ...],
) -> tuple[tuple[str, str], ...]:
    """Classify each dependency into (kind, ref) pairs for persistence."""
    refs: list[tuple[str, str]] = []
    for dependency in dependencies:
        if dependency.startswith("market."):
            refs.append(("dataset", _market_dependency_ref(dependency)))
            continue
        if dependency.startswith("etf."):
            refs.append(("dataset", _etf_dependency_ref(dependency)))
            continue
        if "." not in dependency:
            continue
        refs.append(("derived", dependency))
    deduped: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for item in refs:
        if item in seen:
            continue
        deduped.append(item)
        seen.add(item)
    return tuple(deduped)


def _market_dependency_ref(dependency: str) -> str:
    column_name = dependency.removeprefix("market.")
    if column_name in {"open", "high", "low", "close", "pre_close", "volume", "amount"}:
        return "market.stock_daily"
    if column_name == "adj_factor":
        return "market.adj_factor"
    if column_name in {
        "is_suspended",
        "suspend_timing",
        "is_st",
        "st_type",
        "list_status",
    }:
        return "market.stock_status"
    raise NotImplementedError(
        "Unsupported market dependency for durable persistence: "
        + f"dependency={dependency}"
    )


_ETF_DAILY_COLUMNS = frozenset(
    {"open", "high", "low", "close", "pre_close", "volume", "amount", "pct_change"}
)


def _etf_dependency_ref(dependency: str) -> str:
    column_name = dependency.removeprefix("etf.")
    if column_name in _ETF_DAILY_COLUMNS:
        return "etf.daily"
    raise NotImplementedError(
        "Unsupported ETF dependency for durable persistence: "
        + f"dependency={dependency}"
    )
