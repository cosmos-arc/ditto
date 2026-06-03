"""Application catalog maturity helper tests."""

import pytest
from ditto_application.catalog_maturity import catalog_dataset_asset_class


class TestCatalogDatasetAssetClass:
    """Application-facing dataset asset-class resolution."""

    def test_known_instrument_dataset_returns_asset_class(self) -> None:
        assert catalog_dataset_asset_class("stock_daily") == "stock"

    def test_metadata_dataset_returns_none(self) -> None:
        assert catalog_dataset_asset_class("stock_basic") is None

    def test_unknown_dataset_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="Unknown dataset_id"):
            catalog_dataset_asset_class("unknown_dataset")
