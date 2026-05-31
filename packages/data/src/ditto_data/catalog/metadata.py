"""
Dataset metadata registry for the data catalog.

Centralizes dataset maturity, domain, schedule, and quality profile
information that was previously scattered across enums, configs, and
application layer.

Each dataset is described by a frozen ``DatasetMetadata`` instance.
``default_dataset_metadata()`` returns the authoritative registry for all
known datasets.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

__all__ = [
    "DatasetMetadata",
    "default_dataset_metadata",
]

# ============ Literal types for field validation ============

type DatasetDomain = Literal[
    "metadata",
    "market",
    "capital",
    "fundamental",
    "macro",
]

type DatasetMaturity = Literal[
    "initial-focus",
    "experimental",
    "reserved",
]

type DatasetSchedule = Literal[
    "trading_days",
    "natural_days",
    "source_defined",
]

# ============ Validation constants ============

_VALID_DOMAINS: frozenset[str] = frozenset(
    {
        "metadata",
        "market",
        "capital",
        "fundamental",
        "macro",
    }
)
_VALID_MATURITIES: frozenset[str] = frozenset(
    {
        "initial-focus",
        "experimental",
        "reserved",
    }
)
_VALID_SCHEDULES: frozenset[str] = frozenset(
    {
        "trading_days",
        "natural_days",
        "source_defined",
    }
)

# ============ Dataset domain assignments ============

# Basic / Calendar datasets
_METADATA_DOMAINS: frozenset[str] = frozenset(
    {
        "stock_basic",
        "etf_basic",
        "index_basic",
        "calendar",
    }
)

# Market datasets
_MARKET_DOMAINS: frozenset[str] = frozenset(
    {
        "stock_daily",
        "etf_daily",
        "index_daily",
        "stock_status",
        "adj_factor",
        "fund_adj",
    }
)

# Capital datasets
_CAPITAL_DOMAINS: frozenset[str] = frozenset(
    {
        "valuation_metrics",
        "margin_trading",
        "pledge_ratio",
        "corporate_actions",
    }
)

# Fundamental datasets
_FUNDAMENTAL_DOMAINS: frozenset[str] = frozenset(
    {
        "balance_sheet",
        "income_statement",
        "cash_flow",
        "dividend",
    }
)

# Macro datasets (includes FX and commodity)
_MACRO_DOMAINS: frozenset[str] = frozenset(
    {
        "macro_indicators",
        "fx_daily",
        "commodity_daily",
    }
)

# Index reference datasets
_INDEX_DOMAINS: frozenset[str] = frozenset({"index_weight"})

# ============ Dataset maturity assignments ============

_INITIAL_FOCUS_DATASETS: frozenset[str] = frozenset(
    {
        "stock_basic",
        "etf_basic",
        "index_basic",
        "calendar",
        "stock_daily",
        "etf_daily",
        "index_daily",
        "stock_status",
        "adj_factor",
        "fund_adj",
    }
)

_EXPERIMENTAL_DATASETS: frozenset[str] = frozenset(
    {
        "balance_sheet",
        "income_statement",
        "cash_flow",
        "dividend",
        "valuation_metrics",
        "margin_trading",
        "pledge_ratio",
        "corporate_actions",
        "macro_indicators",
        "fx_daily",
        "commodity_daily",
        "index_weight",
    }
)


def _resolve_domain(dataset_id: str) -> DatasetDomain:
    """Resolve the domain for a given dataset ID."""
    if dataset_id in _METADATA_DOMAINS:
        return "metadata"
    if dataset_id in _MARKET_DOMAINS:
        return "market"
    if dataset_id in _CAPITAL_DOMAINS:
        return "capital"
    if dataset_id in _FUNDAMENTAL_DOMAINS:
        return "fundamental"
    if dataset_id in _MACRO_DOMAINS:
        return "macro"
    if dataset_id in _INDEX_DOMAINS:
        return "market"
    msg = f"Unknown dataset_id: {dataset_id}"
    raise ValueError(msg)


def _resolve_maturity(dataset_id: str) -> DatasetMaturity:
    """Resolve the maturity level for a given dataset ID."""
    if dataset_id in _INITIAL_FOCUS_DATASETS:
        return "initial-focus"
    if dataset_id in _EXPERIMENTAL_DATASETS:
        return "experimental"
    return "reserved"


def _resolve_schedule(dataset_id: str) -> DatasetSchedule:
    """Resolve the date schedule type for a given dataset ID."""
    # Natural-days datasets
    if dataset_id == "fx_daily":
        return "natural_days"
    # Source-defined datasets
    if dataset_id in {"macro_indicators", "commodity_daily"}:
        return "source_defined"
    # All others default to trading_days (basic datasets are also
    # effectively trading_days for scheduling purposes even though they
    # don't require a trade_date parameter)
    return "trading_days"


@dataclass(frozen=True)
class DatasetMetadata:
    """
    Metadata descriptor for a single dataset.

    Attributes:
        dataset_id: Stable identifier matching ``Dataset`` enum value.
        domain: Logical data domain.
        maturity: Capability maturity level.
        schedule: Date scheduling strategy for ingestion.
        quality_profile: DQ configuration profile name.

    """

    dataset_id: str
    domain: DatasetDomain
    maturity: DatasetMaturity
    schedule: DatasetSchedule
    quality_profile: str = "default"

    def __post_init__(self) -> None:  # noqa: D105
        if self.domain not in _VALID_DOMAINS:
            msg = f"Invalid domain: {self.domain!r}"
            raise ValueError(msg)
        if self.maturity not in _VALID_MATURITIES:
            msg = f"Invalid maturity: {self.maturity!r}"
            raise ValueError(msg)
        if self.schedule not in _VALID_SCHEDULES:
            msg = f"Invalid schedule: {self.schedule!r}"
            raise ValueError(msg)


# All known dataset IDs, in the same order as the Dataset enum.
_ALL_DATASET_IDS: tuple[str, ...] = (
    # Basic (T0, no trade_date)
    "stock_basic",
    "etf_basic",
    "index_basic",
    # Calendar
    "calendar",
    # Market (T1)
    "stock_daily",
    "etf_daily",
    "index_daily",
    "stock_status",
    # Reference
    "adj_factor",
    "fund_adj",
    # Fundamental
    "balance_sheet",
    "income_statement",
    "cash_flow",
    "dividend",
    # Capital
    "valuation_metrics",
    "margin_trading",
    "pledge_ratio",
    # Macro
    "macro_indicators",
    # Market extensions
    "fx_daily",
    "commodity_daily",
    # Capital extension
    "corporate_actions",
    # Index reference
    "index_weight",
)

_cached_metadata: dict[str, DatasetMetadata] | None = None


def default_dataset_metadata() -> dict[str, DatasetMetadata]:
    """
    Return the authoritative metadata registry for all known datasets.

    Cached on first call; subsequent calls return the same dict.
    """
    global _cached_metadata  # noqa: PLW0603
    if _cached_metadata is not None:
        return _cached_metadata
    _cached_metadata = {
        dataset_id: DatasetMetadata(
            dataset_id=dataset_id,
            domain=_resolve_domain(dataset_id),
            maturity=_resolve_maturity(dataset_id),
            schedule=_resolve_schedule(dataset_id),
        )
        for dataset_id in _ALL_DATASET_IDS
    }
    return _cached_metadata
