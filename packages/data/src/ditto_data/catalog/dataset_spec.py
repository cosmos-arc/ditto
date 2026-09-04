"""Immutable dataset specs, independent of catalog runtime metadata."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

__all__ = ["DatasetSpec", "resolve_dataset_spec"]

type R2Scope = Literal["hard", "deferred"]
type BootstrapChunk = Literal["month", "quarter", "year", "source_defined"]
type FallbackMode = Literal["automatic", "manual", "none"]
type RevisionPolicy = Literal["append_only", "effective_dated", "not_applicable"]
type DatasetFrequency = Literal[
    "static",
    "trading_daily",
    "monthly",
    "quarterly",
    "event",
    "source_defined",
]
type DatasetCurrency = Literal["CNY", "mixed"] | None
type CoverageTargets = tuple[str | None, str | None, str]


@dataclass(frozen=True)
class DatasetSpec:
    """Catalog-owned identity and operating contract for one dataset."""

    dataset_id: str
    r2_scope: R2Scope
    owner: str
    primary_key: tuple[str, ...]
    partition_keys: tuple[str, ...]
    provider_datasets: tuple[str, ...]
    schema_version: str
    frequency: DatasetFrequency
    timezone: str
    currency: DatasetCurrency
    bootstrap_chunk: BootstrapChunk
    coverage_start_rule: str
    raw_target_from: str | None
    certified_target_from: str | None
    fallback_mode: FallbackMode
    knowledge_date_field: str | None
    revision_policy: RevisionPolicy
    runbook: str
    license_policy: Literal["provider_ledger_required"] = "provider_ledger_required"

    def __post_init__(self) -> None:
        """Reject incomplete contracts before they enter the registry."""
        required_text = {
            "dataset_id": self.dataset_id,
            "owner": self.owner,
            "schema_version": self.schema_version,
            "timezone": self.timezone,
            "coverage_start_rule": self.coverage_start_rule,
            "runbook": self.runbook,
        }
        for field, value in required_text.items():
            if not value or value.strip() != value:
                raise ValueError(f"Invalid product contract {field}: {value!r}")
        for field, values in (
            ("primary_key", self.primary_key),
            ("partition_keys", self.partition_keys),
            ("provider_datasets", self.provider_datasets),
        ):
            if not values or len(set(values)) != len(values):
                raise ValueError(f"Invalid product contract {field}: {values!r}")
            if any(not value or value.strip() != value for value in values):
                raise ValueError(f"Invalid product contract {field}: {values!r}")
        if not self.runbook.startswith("docs/operations/"):
            raise ValueError(f"Invalid product contract runbook: {self.runbook!r}")
        if not self.schema_version.endswith((".v1", ".v2")):
            raise ValueError(
                f"Invalid product contract schema_version: {self.schema_version!r}"
            )
        if self.r2_scope == "hard" and (
            self.raw_target_from is None or self.certified_target_from is None
        ):
            raise ValueError(
                f"Hard-scope product requires coverage targets: {self.dataset_id}"
            )


_R2_HARD_SCOPE = frozenset(
    {
        "calendar",
        "stock_basic",
        "etf_basic",
        "index_basic",
        "stock_daily",
        "etf_daily",
        "index_daily",
        "global_index_daily",
        "adj_factor",
        "fund_adj",
        "stock_status",
        "index_weight",
        "corporate_actions",
        "balance_sheet",
        "income_statement",
        "cash_flow",
        "dividend",
        "valuation_metrics",
        "macro_indicators",
        "commodity_daily",
        "industry_classification",
        "industry_mapping",
    }
)

_PRIMARY_KEYS: dict[str, tuple[str, ...]] = {
    "stock_basic": ("source", "source_ticker", "knowledge_date"),
    "etf_basic": ("source", "source_ticker", "knowledge_date"),
    "index_basic": ("source", "source_ticker", "knowledge_date"),
    "calendar": ("exchange", "trade_date"),
    "stock_daily": ("instrument_id", "trade_date"),
    "etf_daily": ("instrument_id", "trade_date"),
    "index_daily": ("instrument_id", "trade_date"),
    "global_index_daily": (
        "source_ticker",
        "trade_date",
        "knowledge_date",
    ),
    "stock_status": ("instrument_id", "trade_date"),
    "adj_factor": ("instrument_id", "trade_date", "knowledge_date"),
    "fund_adj": ("instrument_id", "trade_date", "knowledge_date"),
    "balance_sheet": (
        "instrument_id",
        "report_date",
        "report_type",
        "knowledge_date",
        "revision_id",
    ),
    "income_statement": (
        "instrument_id",
        "report_date",
        "report_type",
        "knowledge_date",
        "revision_id",
    ),
    "cash_flow": (
        "instrument_id",
        "report_date",
        "report_type",
        "knowledge_date",
        "revision_id",
    ),
    "dividend": (
        "instrument_id",
        "announcement_date",
        "ex_date",
        "knowledge_date",
        "revision_id",
    ),
    "valuation_metrics": ("instrument_id", "trade_date", "knowledge_date"),
    "margin_trading": ("instrument_id", "trade_date", "knowledge_date"),
    "pledge_ratio": ("instrument_id", "trade_date", "knowledge_date"),
    "macro_indicators": ("indicator_code", "observation_date", "knowledge_date"),
    "fx_daily": ("instrument_code", "trade_date", "knowledge_date"),
    "commodity_daily": ("instrument_code", "trade_date", "knowledge_date"),
    "corporate_actions": (
        "instrument_id",
        "action_type",
        "announcement_date",
        "effective_date",
    ),
    "index_weight": ("index_id", "constituent_id", "effective_from"),
    "industry_classification": (
        "source",
        "classification_version",
        "industry_id",
        "knowledge_date",
    ),
    "industry_mapping": (
        "source",
        "classification_version",
        "instrument_id",
        "industry_id",
        "industry_date",
        "knowledge_date",
    ),
}

_PROVIDER_DATASETS: dict[str, tuple[str, ...]] = {
    "stock_basic": ("tushare:stock_basic", "tushare:bak_basic"),
    "etf_basic": ("tushare:fund_basic",),
    "index_basic": ("tushare:index_basic",),
    "calendar": ("tushare:trade_cal",),
    "stock_daily": ("tushare:daily", "local_tdx:day"),
    "etf_daily": ("tushare:fund_daily", "local_tdx:day"),
    "index_daily": ("tushare:index_daily", "local_tdx:day"),
    "global_index_daily": ("tushare:index_global",),
    "stock_status": (
        "tushare:stock_st",
        "tushare:suspend_d",
        "tushare:bak_basic",
    ),
    "adj_factor": ("tushare:adj_factor",),
    "fund_adj": ("tushare:fund_adj",),
    "balance_sheet": ("tushare:balancesheet",),
    "income_statement": ("tushare:income",),
    "cash_flow": ("tushare:cashflow",),
    "dividend": ("tushare:dividend",),
    "valuation_metrics": ("tushare:daily_basic",),
    "margin_trading": ("tushare:margin_detail",),
    "pledge_ratio": ("tushare:pledge_stat",),
    "macro_indicators": (
        "tushare:cn_macro",
        "fred:series_observations",
        "alfred:vintages",
    ),
    "fx_daily": ("tushare:fx_daily",),
    "commodity_daily": (
        "fred:commodity_series",
        "tushare:commodity_reference",
    ),
    "corporate_actions": ("tushare:corporate_actions",),
    "index_weight": ("tushare:index_weight",),
    "industry_classification": ("tushare:index_classify",),
    "industry_mapping": ("tushare:index_member_all",),
}

_BOOTSTRAP_CHUNKS: dict[str, BootstrapChunk] = {
    "stock_basic": "year",
    "etf_basic": "year",
    "index_basic": "year",
    "calendar": "year",
    "stock_daily": "month",
    "etf_daily": "month",
    "index_daily": "month",
    "global_index_daily": "month",
    "stock_status": "month",
    "adj_factor": "month",
    "fund_adj": "month",
    "balance_sheet": "quarter",
    "income_statement": "quarter",
    "cash_flow": "quarter",
    "dividend": "quarter",
    "valuation_metrics": "month",
    "margin_trading": "month",
    "pledge_ratio": "quarter",
    "macro_indicators": "source_defined",
    "fx_daily": "month",
    "commodity_daily": "source_defined",
    "corporate_actions": "quarter",
    "index_weight": "month",
    "industry_classification": "year",
    "industry_mapping": "month",
}

_SCHEMA_VERSION_OVERRIDES: dict[str, str] = {
    "stock_daily": "market.stock_daily.v1",
    "adj_factor": "market.adj_factor.v1",
    "stock_status": "market.stock_status.v1",
    "etf_daily": "etf.daily.v1",
    "corporate_actions": "fundamental.corporate_actions.v2",
    "dividend": "fundamental.dividend.v2",
}

_DATASET_DOMAINS: dict[str, str] = {
    "stock_basic": "metadata",
    "etf_basic": "metadata",
    "index_basic": "metadata",
    "calendar": "metadata",
    "stock_daily": "market",
    "etf_daily": "market",
    "index_daily": "market",
    "global_index_daily": "market",
    "stock_status": "market",
    "adj_factor": "market",
    "fund_adj": "market",
    "balance_sheet": "fundamental",
    "income_statement": "fundamental",
    "cash_flow": "fundamental",
    "dividend": "fundamental",
    "valuation_metrics": "capital",
    "margin_trading": "capital",
    "pledge_ratio": "capital",
    "macro_indicators": "macro",
    "fx_daily": "macro",
    "commodity_daily": "macro",
    "corporate_actions": "fundamental",
    "index_weight": "market",
    "industry_classification": "metadata",
    "industry_mapping": "metadata",
}

_STATIC_DATASETS = frozenset({"stock_basic", "etf_basic", "index_basic"})
_QUARTERLY_DATASETS = frozenset(
    {"balance_sheet", "income_statement", "cash_flow", "pledge_ratio"}
)
_EVENT_DATASETS = frozenset({"dividend", "corporate_actions"})
_MONTHLY_DATASETS = frozenset({"index_weight"})
_SOURCE_DEFINED_DATASETS = frozenset(
    {
        "macro_indicators",
        "commodity_daily",
        "global_index_daily",
        "industry_classification",
        "industry_mapping",
    }
)
_CNY_DATASETS = frozenset(
    {
        "stock_daily",
        "etf_daily",
        "index_daily",
        "balance_sheet",
        "income_statement",
        "cash_flow",
        "dividend",
        "valuation_metrics",
        "margin_trading",
        "pledge_ratio",
        "corporate_actions",
    }
)
_MIXED_CURRENCY_DATASETS = frozenset(
    {"macro_indicators", "fx_daily", "commodity_daily", "global_index_daily"}
)

_APPEND_ONLY_DATASETS = frozenset(
    {
        "adj_factor",
        "fund_adj",
        "balance_sheet",
        "income_statement",
        "cash_flow",
        "dividend",
        "valuation_metrics",
        "margin_trading",
        "pledge_ratio",
        "macro_indicators",
        "fx_daily",
        "commodity_daily",
        "global_index_daily",
    }
)
_EFFECTIVE_DATED_DATASETS = frozenset(
    {
        "stock_basic",
        "etf_basic",
        "index_basic",
        "stock_status",
        "corporate_actions",
        "index_weight",
        "industry_classification",
        "industry_mapping",
    }
)
_KNOWLEDGE_DATE_DATASETS = _APPEND_ONLY_DATASETS | frozenset(
    {
        "stock_basic",
        "etf_basic",
        "index_basic",
        "corporate_actions",
        "industry_classification",
        "industry_mapping",
    }
)

_DEFAULT_R2_COVERAGE_TARGET: CoverageTargets = (
    "2015-01-01",
    "evidence-determined",
    "R2 modern A-share window",
)
_R2_COVERAGE_TARGETS: dict[str, CoverageTargets] = {
    "stock_status": (
        "2016-01-01",
        "2016-01-01",
        "provider history starts in 2016",
    ),
    "stock_basic": (
        "2015-01-01",
        "2016-01-01",
        "daily historical universe reconstruction",
    ),
    "etf_daily": (
        "2015-01-01",
        "evidence-determined",
        "not earlier than listing date",
    ),
    "etf_basic": (
        "2015-01-01",
        "evidence-determined",
        "not earlier than listing date",
    ),
    "index_weight": (
        "provider-native",
        "core-index-specific",
        "effective-dated intervals",
    ),
    "macro_indicators": (
        "series-native",
        "series-specific",
        "release and revision schedule",
    ),
    "commodity_daily": (
        "product-native",
        "product-specific",
        "declared product schedule",
    ),
    "balance_sheet": (
        "2015-01-01",
        "evidence-determined",
        "knowledge_date on or after R2 operational window",
    ),
    "income_statement": (
        "2015-01-01",
        "evidence-determined",
        "knowledge_date on or after R2 operational window",
    ),
    "cash_flow": (
        "2015-01-01",
        "evidence-determined",
        "knowledge_date on or after R2 operational window",
    ),
    "dividend": (
        "2015-01-01",
        "evidence-determined",
        "knowledge_date on or after R2 operational window",
    ),
    "global_index_daily": (
        "provider-native",
        "evidence-determined",
        "per-market trading calendar and actual retrieval visibility",
    ),
    "industry_classification": (
        "SW2021-native",
        "evidence-determined",
        "classification version and actual retrieval visibility",
    ),
    "industry_mapping": (
        "SW2021-native",
        "evidence-determined",
        "effective interval and actual retrieval visibility",
    ),
}


def _coverage_targets(dataset_id: str) -> CoverageTargets:
    if dataset_id not in _R2_HARD_SCOPE:
        return None, None, "outside R2 release gate"
    return _R2_COVERAGE_TARGETS.get(dataset_id, _DEFAULT_R2_COVERAGE_TARGET)


def _partition_keys(dataset_id: str) -> tuple[str, ...]:
    if dataset_id == "macro_indicators":
        return ("observation_date",)
    if dataset_id == "index_weight":
        return ("effective_from",)
    if dataset_id in {"industry_classification", "industry_mapping"}:
        return ("knowledge_date",)
    if dataset_id in {
        "calendar",
        "stock_daily",
        "etf_daily",
        "index_daily",
        "global_index_daily",
        "stock_status",
        "adj_factor",
        "fund_adj",
        "valuation_metrics",
        "margin_trading",
        "fx_daily",
        "commodity_daily",
    }:
        return ("trade_date",)
    return ("knowledge_date",)


def _schema_version(dataset_id: str) -> str:
    return _SCHEMA_VERSION_OVERRIDES.get(
        dataset_id,
        f"{_DATASET_DOMAINS[dataset_id]}.{dataset_id}.v1",
    )


def _frequency(dataset_id: str) -> DatasetFrequency:
    if dataset_id in _STATIC_DATASETS:
        return "static"
    if dataset_id in _QUARTERLY_DATASETS:
        return "quarterly"
    if dataset_id in _EVENT_DATASETS:
        return "event"
    if dataset_id in _MONTHLY_DATASETS:
        return "monthly"
    if dataset_id in _SOURCE_DEFINED_DATASETS:
        return "source_defined"
    return "trading_daily"


def _currency(dataset_id: str) -> DatasetCurrency:
    if dataset_id in _CNY_DATASETS:
        return "CNY"
    if dataset_id in _MIXED_CURRENCY_DATASETS:
        return "mixed"
    return None


def resolve_dataset_spec(dataset_id: str) -> DatasetSpec:
    """Build the immutable specification for one known catalog dataset."""
    raw_from, certified_from, coverage_rule = _coverage_targets(dataset_id)
    revision_policy: RevisionPolicy = "not_applicable"
    if dataset_id in _APPEND_ONLY_DATASETS:
        revision_policy = "append_only"
    elif dataset_id in _EFFECTIVE_DATED_DATASETS:
        revision_policy = "effective_dated"
    fallback_mode: FallbackMode = (
        "manual" if dataset_id in {"macro_indicators", "commodity_daily"} else "none"
    )
    return DatasetSpec(
        dataset_id=dataset_id,
        r2_scope="hard" if dataset_id in _R2_HARD_SCOPE else "deferred",
        owner="data-platform",
        primary_key=_PRIMARY_KEYS[dataset_id],
        partition_keys=_partition_keys(dataset_id),
        provider_datasets=_PROVIDER_DATASETS[dataset_id],
        schema_version=_schema_version(dataset_id),
        frequency=_frequency(dataset_id),
        timezone=(
            "source_defined"
            if dataset_id in _SOURCE_DEFINED_DATASETS | {"fx_daily"}
            else "Asia/Shanghai"
        ),
        currency=_currency(dataset_id),
        bootstrap_chunk=_BOOTSTRAP_CHUNKS[dataset_id],
        coverage_start_rule=coverage_rule,
        raw_target_from=raw_from,
        certified_target_from=certified_from,
        fallback_mode=fallback_mode,
        knowledge_date_field=(
            "knowledge_date" if dataset_id in _KNOWLEDGE_DATE_DATASETS else None
        ),
        revision_policy=revision_policy,
        runbook=f"docs/operations/r2-data-product-runbook.md#{dataset_id}",
    )
