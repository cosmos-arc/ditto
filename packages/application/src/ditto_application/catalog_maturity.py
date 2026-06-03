"""Catalog-backed capability maturity gates for application runtime paths."""

from __future__ import annotations

from collections.abc import Iterable

from ditto_data.catalog import DatasetMetadata, default_dataset_metadata
from ditto_data.catalog.metadata import DatasetAssetClass, dataset_asset_class
from ditto_data.catalog.promotion import (
    DatasetMaturityPromotionReader,
    apply_dataset_maturity_promotion,
)
from ditto_strategy.alpha.specs import StrategySpec

from ditto_application.exceptions import AppBuilderError

__all__ = [
    "assert_strategy_runtime_data_allowed",
    "blocked_catalog_datasets",
    "catalog_dataset_asset_class",
    "strategy_runtime_dataset_ids",
]

_ASSET_CLASS_DATASETS: dict[str, tuple[str, str]] = {
    "etf": ("etf_daily", "etf_basic"),
    "index": ("index_daily", "index_basic"),
    "stock": ("stock_daily", "stock_basic"),
}

_DEFAULT_ALLOWED_MATURITIES = frozenset({"initial-focus"})


def catalog_dataset_asset_class(dataset_id: str) -> DatasetAssetClass | None:
    """Return the catalog-owned asset class for a known dataset."""
    return dataset_asset_class(dataset_id)


def strategy_runtime_dataset_ids(spec: StrategySpec) -> tuple[str, ...]:
    """Return catalog dataset IDs required by a strategy runtime path."""
    asset_class = spec.asset_class.lower()
    dataset_pair = _ASSET_CLASS_DATASETS.get(asset_class)
    if dataset_pair is None:
        msg = f"Unsupported strategy asset_class for maturity gate: {spec.asset_class}"
        raise AppBuilderError(msg)

    dataset_ids: list[str] = [*dataset_pair]
    if spec.benchmark is not None and asset_class != "index":
        dataset_ids.extend(("index_daily", "index_basic"))
    return tuple(dict.fromkeys(dataset_ids))


def assert_strategy_runtime_data_allowed(
    spec: StrategySpec,
    *,
    allow_experimental_data: bool = False,
    maturity_promotion_reader: DatasetMaturityPromotionReader | None = None,
    context: str = "strategy runtime",
) -> None:
    """Fail closed when a strategy runtime would use non-initial-focus data."""
    blocked = _blocked_datasets(
        strategy_runtime_dataset_ids(spec),
        allow_experimental_data=allow_experimental_data,
        maturity_promotion_reader=maturity_promotion_reader,
    )
    if not blocked:
        return
    joined = ", ".join(blocked)
    msg = (
        f"{context} requires experimental dataset or other non-initial-focus "
        f"dataset maturity: "
        f"{joined}. Set allow_experimental_data=True only for explicit research use."
    )
    raise AppBuilderError(msg)


def blocked_catalog_datasets(
    dataset_ids: Iterable[str],
    *,
    allow_experimental_data: bool = False,
    maturity_promotion_reader: DatasetMaturityPromotionReader | None = None,
) -> tuple[str, ...]:
    """Return dataset maturity labels that are not allowed for production reads."""
    return _blocked_datasets(
        dataset_ids,
        allow_experimental_data=allow_experimental_data,
        maturity_promotion_reader=maturity_promotion_reader,
    )


def _blocked_datasets(
    dataset_ids: Iterable[str],
    *,
    allow_experimental_data: bool,
    maturity_promotion_reader: DatasetMaturityPromotionReader | None = None,
) -> tuple[str, ...]:
    metadata_by_dataset = default_dataset_metadata()
    blocked: list[str] = []
    for dataset_id in dataset_ids:
        metadata = metadata_by_dataset.get(dataset_id)
        if metadata is None:
            blocked.append(f"{dataset_id}=unknown")
            continue
        metadata = _apply_maturity_promotion(metadata, maturity_promotion_reader)
        if metadata.maturity in _DEFAULT_ALLOWED_MATURITIES:
            continue
        if allow_experimental_data and metadata.maturity == "experimental":
            continue
        blocked.append(f"{dataset_id}={metadata.maturity}")
    return tuple(blocked)


def _apply_maturity_promotion(
    metadata: DatasetMetadata,
    reader: DatasetMaturityPromotionReader | None,
) -> DatasetMetadata:
    if reader is None:
        return metadata
    promotion = reader.get_dataset_maturity_promotion(metadata.dataset_id)
    if promotion is None:
        return metadata
    return apply_dataset_maturity_promotion(metadata, promotion)
