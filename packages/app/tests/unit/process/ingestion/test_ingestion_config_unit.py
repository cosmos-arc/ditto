"""Tests for IngestionConfig."""

from pathlib import Path

import pytest
from ditto_app.process.ingestion_config import IngestionConfig


@pytest.mark.unit
def test_config_default_values() -> None:
    """Test default configuration values."""
    config = IngestionConfig()

    assert config.data_root == Path("data")
    assert config.default_source == "tushare"
    assert config.auto_register_securities is True


@pytest.mark.unit
def test_config_explicit_values() -> None:
    """Test configuration with explicit values."""
    config = IngestionConfig(
        data_root=Path("/tmp/data"),
        default_source="akshare",
        auto_register_securities=False,
    )

    assert config.data_root == Path("/tmp/data")
    assert config.default_source == "akshare"
    assert config.auto_register_securities is False
