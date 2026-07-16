"""Application-owned policy for scheduled quality batch coverage."""

from __future__ import annotations

from typing import Literal

from ditto_application.catalog_maturity import catalog_dataset_asset_class
from ditto_application.config import get_all_datasets
from ditto_application.exceptions import AppProcessError

type QualityAssetClass = Literal["stock", "etf", "index", "fx", "commodity"]

__all__ = [
    "DEFAULT_QUALITY_DATASETS",
    "QualityAssetClass",
    "quality_asset_class",
]

DEFAULT_QUALITY_DATASETS: tuple[str, ...] = (
    "etf_daily",
    "index_daily",
    "stock_daily",
    "adj_factor",
    "index_weight",
    "balance_sheet",
    "income_statement",
    "cash_flow",
    "dividend",
    "corporate_actions",
    "valuation_metrics",
    "margin_trading",
    "pledge_ratio",
    "macro_indicators",
    "fx_daily",
    "commodity_daily",
)

_REGISTERED_DATASETS = frozenset(dataset.value for dataset in get_all_datasets())
_QUALITY_ASSET_CLASS_OVERRIDES: dict[str, QualityAssetClass] = {
    "fx_daily": "fx",
    "commodity_daily": "commodity",
}


def quality_asset_class(dataset: str) -> QualityAssetClass | None:
    """Resolve the optional market asset class for a registered dataset."""
    if dataset not in _REGISTERED_DATASETS:
        raise AppProcessError(
            f"Unknown dataset: {dataset}",
            field="dataset",
            value=dataset,
        )
    override = _QUALITY_ASSET_CLASS_OVERRIDES.get(dataset)
    if override is not None:
        return override
    return catalog_dataset_asset_class(dataset)
