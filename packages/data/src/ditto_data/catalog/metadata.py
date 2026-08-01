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
from functools import cache
from typing import Literal

from ditto_data.catalog.product_contract import (
    DatasetProductContract,
    resolve_product_contract,
)

__all__ = [
    "DatasetAssetClass",
    "DatasetMetadata",
    "dataset_asset_class",
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

type DatasetIngestionGranularity = Literal[
    "date",
    "instrument",
]

type DatasetAssetClass = Literal[
    "stock",
    "etf",
    "index",
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
_VALID_INGESTION_GRANULARITIES: frozenset[str] = frozenset(
    {
        "date",
        "instrument",
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
        "etf_basic",
        "index_basic",
        "calendar",
        "etf_daily",
        "index_daily",
        "adj_factor",
        "fund_adj",
    }
)

_EXPERIMENTAL_DATASETS: frozenset[str] = frozenset(
    {
        "stock_basic",
        "stock_daily",
        "stock_status",
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

_EXPERIMENTAL_PROMOTION_CRITERIA: tuple[str, ...] = (
    "complete PIT/replay coverage for the dataset",
    "document runtime owner, freshness SLA, and source failover policy",
    "pass catalog-backed runtime/read-model tests without research opt-in",
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


def _resolve_promotion_criteria(dataset_id: str) -> tuple[str, ...]:
    """Resolve criteria required before promoting an experimental dataset."""
    if dataset_id in _EXPERIMENTAL_DATASETS:
        return _EXPERIMENTAL_PROMOTION_CRITERIA
    return ()


def _resolve_asset_class(dataset_id: str) -> DatasetAssetClass | None:
    """Resolve the instrument asset class for datasets that are instrument-scoped."""
    if dataset_id in {
        "stock_daily",
        "stock_status",
        "adj_factor",
        "balance_sheet",
        "income_statement",
        "cash_flow",
        "dividend",
        "valuation_metrics",
        "margin_trading",
        "pledge_ratio",
        "corporate_actions",
    }:
        return "stock"
    if dataset_id in {"etf_daily", "fund_adj"}:
        return "etf"
    if dataset_id in {"index_daily", "index_weight"}:
        return "index"
    return None


def _resolve_schedule(dataset_id: str) -> DatasetSchedule:
    """Resolve the date schedule type for a given dataset ID."""
    # Natural-days datasets
    if dataset_id in {"fx_daily", "dividend", "corporate_actions"}:
        return "natural_days"
    # Source-defined datasets
    if dataset_id in {"macro_indicators", "commodity_daily"}:
        return "source_defined"
    # All others default to trading_days (basic datasets are also
    # effectively trading_days for scheduling purposes even though they
    # don't require a trade_date parameter)
    return "trading_days"


def _validate_source_name(field: str, source: str) -> None:
    if not source or source != source.lower() or source.strip() != source:
        msg = f"Invalid {field}: {source!r}"
        raise ValueError(msg)


def _validate_source_tuple(field: str, sources: tuple[str, ...]) -> None:
    if len(set(sources)) != len(sources):
        msg = f"Invalid {field}: duplicate source"
        raise ValueError(msg)
    for source in sources:
        _validate_source_name(field, source)


def _validate_supported_default_source(
    *,
    default_source: str | None,
    supported_sources: tuple[str, ...],
) -> None:
    if default_source is None:
        if supported_sources:
            msg = "default_source is required when supported_sources is not empty"
            raise ValueError(msg)
        return
    _validate_source_name("default_source", default_source)
    if default_source not in supported_sources:
        msg = "default_source must be in supported_sources"
        raise ValueError(msg)


def _validate_ingestion_granularities(
    *,
    ingestion_granularities: tuple[DatasetIngestionGranularity, ...],
    supported_sources: tuple[str, ...],
) -> None:
    for granularity in ingestion_granularities:
        if granularity not in _VALID_INGESTION_GRANULARITIES:
            msg = f"Invalid ingestion granularity: {granularity!r}"
            raise ValueError(msg)
    if ingestion_granularities and not supported_sources:
        msg = "supported_sources is required when ingestion_granularities is not empty"
        raise ValueError(msg)


def _validate_freshness_sla(
    *,
    freshness_sla_hours: int | None,
    supported_sources: tuple[str, ...],
) -> None:
    if freshness_sla_hours is None:
        return
    if freshness_sla_hours <= 0:
        msg = "freshness_sla_hours must be positive"
        raise ValueError(msg)
    if not supported_sources:
        msg = "freshness_sla_hours requires at least one supported runtime source"
        raise ValueError(msg)


def _validate_promotion_criteria(
    promotion_criteria: tuple[str, ...],
) -> None:
    if len(set(promotion_criteria)) != len(promotion_criteria):
        msg = "Invalid promotion_criteria: duplicate criteria"
        raise ValueError(msg)
    for criterion in promotion_criteria:
        if not criterion or criterion.strip() != criterion:
            msg = f"Invalid promotion_criteria: {criterion!r}"
            raise ValueError(msg)


def _validate_schema_version(
    *,
    schema_version: str | None,
    ingestion_granularities: tuple[DatasetIngestionGranularity, ...],
) -> None:
    if schema_version is None:
        if ingestion_granularities:
            msg = "schema_version is required when ingestion_granularities is not empty"
            raise ValueError(msg)
        return
    if not schema_version or schema_version.strip() != schema_version:
        msg = f"Invalid schema_version: {schema_version!r}"
        raise ValueError(msg)
    if schema_version != schema_version.lower():
        msg = f"Invalid schema_version: {schema_version!r}"
        raise ValueError(msg)


def _default_storage_uri_prefixes(
    dataset_id: str,
    domain: DatasetDomain,
) -> tuple[str, ...]:
    prefixes = [
        f"{dataset_id}/",
        f"{domain}/{dataset_id}/",
        f"lake://{domain}/{dataset_id}/",
        f"sqlite:///{domain}/{dataset_id}/",
    ]
    if dataset_id == "calendar":
        prefixes.append("calendar_store:")
    if dataset_id in {"stock_basic", "etf_basic", "index_basic"}:
        prefixes.extend(
            (
                f"instrument_reader:{dataset_id}",
                f"instrument_store:{dataset_id}",
            )
        )
    return tuple(prefixes)


def _validate_storage_uri_prefixes(
    *,
    storage_uri_prefixes: tuple[str, ...],
    ingestion_granularities: tuple[DatasetIngestionGranularity, ...],
) -> None:
    if ingestion_granularities and not storage_uri_prefixes:
        msg = "storage_uri_prefixes is required for runtime ingestion datasets"
        raise ValueError(msg)
    if len(set(storage_uri_prefixes)) != len(storage_uri_prefixes):
        msg = "Invalid storage_uri_prefixes: duplicate prefix"
        raise ValueError(msg)
    for prefix in storage_uri_prefixes:
        if (
            not prefix
            or prefix.strip() != prefix
            or prefix != prefix.lower()
            or "\\" in prefix
            or ".." in prefix
        ):
            msg = f"Invalid storage_uri_prefixes: {prefix!r}"
            raise ValueError(msg)


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
        default_source: Primary runtime source that drives ingestion.
        supported_sources: Runtime sources allowed to drive ingestion.
        auxiliary_sources: Optional secondary sources used by a blended route.
        ingestion_granularities: Supported runtime ingestion granularities.
        freshness_sla_hours: Operational freshness SLA for status/read models.
        promotion_criteria: Criteria required before runtime promotion.
        schema_version: Semantic schema contract version for runtime catalog assets.
        asset_class: Instrument asset class for instrument-scoped datasets.
        storage_uri_prefixes: Storage URI prefixes allowed for runtime catalog writes.

    """

    dataset_id: str
    domain: DatasetDomain
    maturity: DatasetMaturity
    schedule: DatasetSchedule
    quality_profile: str = "default"
    default_source: str | None = "tushare"
    supported_sources: tuple[str, ...] = ("tushare",)
    auxiliary_sources: tuple[str, ...] = ()
    ingestion_granularities: tuple[DatasetIngestionGranularity, ...] = ("date",)
    freshness_sla_hours: int | None = 36
    promotion_criteria: tuple[str, ...] = ()
    schema_version: str | None = None
    asset_class: DatasetAssetClass | None = None
    storage_uri_prefixes: tuple[str, ...] = ()
    product_contract: DatasetProductContract | None = None

    def __post_init__(self) -> None:
        """验证域字段合法性。"""
        if self.domain not in _VALID_DOMAINS:
            msg = f"Invalid domain: {self.domain!r}"
            raise ValueError(msg)
        if self.maturity not in _VALID_MATURITIES:
            msg = f"Invalid maturity: {self.maturity!r}"
            raise ValueError(msg)
        if self.schedule not in _VALID_SCHEDULES:
            msg = f"Invalid schedule: {self.schedule!r}"
            raise ValueError(msg)
        _validate_source_tuple("supported_sources", self.supported_sources)
        _validate_source_tuple("auxiliary_sources", self.auxiliary_sources)
        _validate_supported_default_source(
            default_source=self.default_source,
            supported_sources=self.supported_sources,
        )
        _validate_ingestion_granularities(
            ingestion_granularities=self.ingestion_granularities,
            supported_sources=self.supported_sources,
        )
        _validate_freshness_sla(
            freshness_sla_hours=self.freshness_sla_hours,
            supported_sources=self.supported_sources,
        )
        _validate_promotion_criteria(self.promotion_criteria)
        _validate_schema_version(
            schema_version=self.schema_version,
            ingestion_granularities=self.ingestion_granularities,
        )
        if not self.storage_uri_prefixes and self.ingestion_granularities:
            object.__setattr__(
                self,
                "storage_uri_prefixes",
                _default_storage_uri_prefixes(self.dataset_id, self.domain),
            )
        _validate_storage_uri_prefixes(
            storage_uri_prefixes=self.storage_uri_prefixes,
            ingestion_granularities=self.ingestion_granularities,
        )
        if (
            self.product_contract is not None
            and self.product_contract.dataset_id != self.dataset_id
        ):
            msg = "product_contract.dataset_id must match dataset_id"
            raise ValueError(msg)

    def supports_source(self, source: str) -> bool:
        """Return whether ``source`` may drive ingestion for this dataset."""
        return source.lower() in self.supported_sources

    def uses_auxiliary_source(self, source: str) -> bool:
        """Return whether ``source`` is used as an auxiliary route input."""
        return source.lower() in self.auxiliary_sources

    @property
    def supports_date_ingestion(self) -> bool:
        """Return whether date-level ingestion is supported."""
        return "date" in self.ingestion_granularities

    @property
    def supports_instrument_ingestion(self) -> bool:
        """Return whether instrument-range ingestion is supported."""
        return "instrument" in self.ingestion_granularities


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

_INSTRUMENT_INGESTION_DATASETS: frozenset[str] = frozenset(
    {
        "stock_daily",
        "etf_daily",
        "index_daily",
        "adj_factor",
        "fund_adj",
        "balance_sheet",
        "income_statement",
        "cash_flow",
        "dividend",
        "valuation_metrics",
        "margin_trading",
        "pledge_ratio",
        "index_weight",
    }
)

_UNSUPPORTED_INGESTION_DATASETS: frozenset[str] = frozenset()

_SCHEMA_VERSION_OVERRIDES: dict[str, str] = {
    "stock_daily": "market.stock_daily.v1",
    "adj_factor": "market.adj_factor.v1",
    "stock_status": "market.stock_status.v1",
    "etf_daily": "etf.daily.v1",
    "corporate_actions": "fundamental.corporate_actions.v2",
    "dividend": "fundamental.dividend.v2",
}


def _resolve_ingestion_granularities(
    dataset_id: str,
) -> tuple[DatasetIngestionGranularity, ...]:
    """Resolve supported ingestion granularities for a dataset."""
    if dataset_id in _UNSUPPORTED_INGESTION_DATASETS:
        return ()
    if dataset_id in _INSTRUMENT_INGESTION_DATASETS:
        return ("date", "instrument")
    return ("date",)


def _resolve_supported_sources(dataset_id: str) -> tuple[str, ...]:
    """Resolve runtime sources that may drive ingestion for a dataset."""
    if dataset_id in _UNSUPPORTED_INGESTION_DATASETS:
        return ()
    if dataset_id == "macro_indicators":
        return ("tushare", "fred")
    return ("tushare",)


def _resolve_default_source(dataset_id: str) -> str | None:
    """Resolve the default runtime source for a dataset."""
    supported_sources = _resolve_supported_sources(dataset_id)
    if not supported_sources:
        return None
    return supported_sources[0]


def _resolve_auxiliary_sources(dataset_id: str) -> tuple[str, ...]:
    """Resolve auxiliary sources used by blended ingestion routes."""
    if dataset_id == "commodity_daily":
        return ("fred",)
    return ()


def _resolve_freshness_sla_hours(dataset_id: str) -> int | None:
    """Resolve operational freshness SLA for catalog status overlays."""
    if dataset_id in _UNSUPPORTED_INGESTION_DATASETS:
        return None
    if dataset_id in {"stock_basic", "etf_basic", "index_basic"}:
        return 168
    if dataset_id in _MACRO_DOMAINS:
        return 72
    if dataset_id in _FUNDAMENTAL_DOMAINS | _CAPITAL_DOMAINS:
        return 24 * 45
    return 36


def _resolve_schema_version(dataset_id: str) -> str | None:
    """Resolve the semantic catalog schema version for runtime assets."""
    if dataset_id in _UNSUPPORTED_INGESTION_DATASETS:
        return None
    schema_version = _SCHEMA_VERSION_OVERRIDES.get(dataset_id)
    if schema_version is not None:
        return schema_version
    return f"{_resolve_domain(dataset_id)}.{dataset_id}.v1"


@cache
def default_dataset_metadata() -> dict[str, DatasetMetadata]:
    """
    Return the authoritative metadata registry for all known datasets.

    Cached on first call; subsequent calls return the same dict.
    """
    return {
        dataset_id: DatasetMetadata(
            dataset_id=dataset_id,
            domain=_resolve_domain(dataset_id),
            maturity=_resolve_maturity(dataset_id),
            schedule=_resolve_schedule(dataset_id),
            default_source=_resolve_default_source(dataset_id),
            supported_sources=_resolve_supported_sources(dataset_id),
            auxiliary_sources=_resolve_auxiliary_sources(dataset_id),
            ingestion_granularities=_resolve_ingestion_granularities(dataset_id),
            freshness_sla_hours=_resolve_freshness_sla_hours(dataset_id),
            promotion_criteria=_resolve_promotion_criteria(dataset_id),
            schema_version=_resolve_schema_version(dataset_id),
            asset_class=_resolve_asset_class(dataset_id),
            product_contract=resolve_product_contract(dataset_id),
        )
        for dataset_id in _ALL_DATASET_IDS
    }


def dataset_asset_class(dataset_id: str) -> DatasetAssetClass | None:
    """Return the catalog-owned asset class for a known dataset."""
    try:
        metadata = default_dataset_metadata()[dataset_id]
    except KeyError:
        msg = f"Unknown dataset_id: {dataset_id}"
        raise ValueError(msg) from None
    return metadata.asset_class
