"""Tests for DataSource abstract base class."""

from typing import Any

import polars as pl
import pytest
from ditto_core.data.datasources.base import DataSource


def test_datasource_is_abstract() -> None:
    """Test that DataSource cannot be instantiated directly."""
    with pytest.raises(TypeError, match="Can't instantiate abstract class"):
        DataSource()


def test_datasource_attributes() -> None:
    """Test DataSource base class attributes."""

    # Create a concrete implementation
    class TestDataSource(DataSource):
        def __init__(self, config: dict[str, Any] | None = None) -> None:
            self.init_called = False
            super().__init__(config)

        def _get_source_type(self) -> str:
            self.init_called = True
            return "test"

        def connect(self) -> None:
            pass

        def disconnect(self) -> None:
            pass

        def get_etf_list(self) -> pl.DataFrame:
            return pl.DataFrame()

        def get_daily_data(
            self, symbol: str, start_date: str, end_date: str
        ) -> pl.DataFrame:
            return pl.DataFrame()

    # Test initialization - _get_source_type is called during parent init
    source = TestDataSource()
    assert source.init_called is True  # Called during parent __init__
    assert source.config == {}
    assert source.source_type == "test"

    # Test with config
    config = {"api_key": "test"}
    source = TestDataSource(config)
    assert source.init_called is True  # Called during parent __init__
    assert source.config == config
    assert source.source_type == "test"
