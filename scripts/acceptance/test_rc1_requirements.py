from __future__ import annotations

from scripts.acceptance.rc1_requirements import (
    LAUNCH_DATASETS,
    validate_maturity_status,
)


def test_launch_dataset_list_contains_stock_etf_macro_requirements() -> None:
    assert "stock_daily" in LAUNCH_DATASETS
    assert "valuation_metrics" in LAUNCH_DATASETS
    assert "etf_daily" in LAUNCH_DATASETS
    assert "macro_indicators" in LAUNCH_DATASETS


def test_validate_maturity_status_rejects_blocked_dataset() -> None:
    payload = {
        "datasets": [
            {
                "dataset": "stock_daily",
                "dataset_maturity": "experimental",
                "dataset_promotion_status": "blocked",
                "catalog_storage_uri": "sqlite:///market.db",
                "catalog_schema_hash": "abc",
                "catalog_row_count": 10,
                "catalog_freshness_status": "fresh",
            }
        ]
    }

    result = validate_maturity_status(payload, required_datasets=("stock_daily",))

    assert not result.ok
    assert result.failures == (
        "stock_daily promotion status is blocked",
        "stock_daily maturity is experimental",
    )


def test_validate_maturity_status_accepts_promoted_fresh_dataset() -> None:
    payload = {
        "datasets": [
            {
                "dataset": "stock_daily",
                "dataset_maturity": "initial-focus",
                "dataset_promotion_status": "ready",
                "catalog_storage_uri": "sqlite:///market.db",
                "catalog_schema_hash": "abc",
                "catalog_row_count": 10,
                "catalog_freshness_status": "fresh",
            }
        ]
    }

    result = validate_maturity_status(payload, required_datasets=("stock_daily",))

    assert result.ok
    assert result.failures == ()
