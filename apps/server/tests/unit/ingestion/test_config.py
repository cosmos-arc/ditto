"""Tests for IngestionConfig."""

from pathlib import Path

from ditto_server.ingestion.config import IngestionConfig


def test_config_default_values() -> None:
    """Test default configuration values."""
    config = IngestionConfig()

    assert config.data_root == Path("data")
    assert config.default_source == "tushare"
    assert config.auto_register_securities is True


def test_config_from_env(monkeypatch) -> None:
    """Test loading configuration from environment variables."""
    monkeypatch.setenv("DITTO_DATA_ROOT", "/tmp/data")
    monkeypatch.setenv("DITTO_DEFAULT_SOURCE", "akshare")
    monkeypatch.setenv("DITTO_AUTO_REGISTER_SECURITIES", "false")

    config = IngestionConfig()

    assert config.data_root == Path("/tmp/data")
    assert config.default_source == "akshare"
    assert config.auto_register_securities is False
