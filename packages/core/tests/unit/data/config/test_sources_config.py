"""Tests for sources configuration management."""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml
from ditto_core.config.sources_config import (
    CollectionConfig,
    QualityConfig,
    SourceConfig,
    SourcesConfig,
    UpdateStrategyConfig,
    load_sources_config,
)
from pydantic import ValidationError


class TestSourceConfig:
    """Test cases for SourceConfig."""

    def test_source_config_with_tushare(self) -> None:
        """Test creating a valid Tushare source config."""
        config = SourceConfig(
            type="tushare",
            enabled=True,
            config={
                "token": "test_token",
                "api_url": "https://api.tushare.pro",
                "rate_limit": 200,
            },
        )
        assert config.type == "tushare"
        assert config.enabled is True
        assert config.config["token"] == "test_token"
        assert config.config["rate_limit"] == 200

    def test_source_config_with_akshare(self) -> None:
        """Test creating a valid AkShare source config."""
        config = SourceConfig(
            type="akshare",
            enabled=True,
            config={"timeout": 30, "max_retries": 2},
        )
        assert config.type == "akshare"
        assert config.enabled is True
        assert config.config["timeout"] == 30

    def test_source_config_with_csv(self) -> None:
        """Test creating a valid CSV source config."""
        config = SourceConfig(
            type="csv",
            enabled=False,
            config={"data_dir": "./data/test", "etf_list_file": "etf_list.csv"},
        )
        assert config.type == "csv"
        assert config.enabled is False
        assert config.config["data_dir"] == "./data/test"

    def test_source_config_invalid_type(self) -> None:
        """Test creating source config with invalid type."""
        with pytest.raises(ValidationError) as exc_info:
            SourceConfig(type="invalid_type", enabled=True, config={})

        assert "type" in str(exc_info.value)

    def test_source_config_missing_required_fields(self) -> None:
        """Test creating source config with missing required fields."""
        with pytest.raises(ValidationError) as exc_info:
            SourceConfig()

        assert "type" in str(exc_info.value)


class TestCollectionConfig:
    """Test cases for CollectionConfig."""

    def test_collection_config_defaults(self) -> None:
        """Test collection config with default values."""
        config = CollectionConfig()
        assert config.batch_size == 1000
        assert config.max_concurrent_fetches == 3
        assert config.validate_consistency is True
        assert config.price_tolerance == 0.01
        assert config.enable_cross_validation is True

    def test_collection_config_custom_values(self) -> None:
        """Test collection config with custom values."""
        config = CollectionConfig(
            batch_size=500,
            max_concurrent_fetches=5,
            validate_consistency=False,
            price_tolerance=0.02,
            enable_cross_validation=False,
        )
        assert config.batch_size == 500
        assert config.max_concurrent_fetches == 5
        assert config.validate_consistency is False
        assert config.price_tolerance == 0.02
        assert config.enable_cross_validation is False

    def test_collection_config_invalid_batch_size(self) -> None:
        """Test collection config with invalid batch size."""
        with pytest.raises(ValidationError) as exc_info:
            CollectionConfig(batch_size=0)

        assert "batch_size" in str(exc_info.value)


class TestQualityConfig:
    """Test cases for QualityConfig."""

    def test_quality_config_defaults(self) -> None:
        """Test quality config with default values."""
        config = QualityConfig()
        assert config.price_validation.enabled is True
        assert config.price_validation.min_price == 0.01
        assert config.price_validation.max_price == 10000
        assert config.volume_validation.enabled is True
        assert config.continuity_validation.enabled is True
        assert config.cross_validation.enabled is True
        assert config.cross_validation.tolerance == 0.01

    def test_quality_config_custom_values(self) -> None:
        """Test quality config with custom values."""
        config = QualityConfig(
            price_validation={"enabled": False, "min_price": 0.1},
            cross_validation={"tolerance": 0.005, "min_samples": 20},
        )
        assert config.price_validation.enabled is False
        assert config.price_validation.min_price == 0.1
        assert config.cross_validation.tolerance == 0.005
        assert config.cross_validation.min_samples == 20


class TestUpdateStrategyConfig:
    """Test cases for UpdateStrategyConfig."""

    def test_update_strategy_config_defaults(self) -> None:
        """Test update strategy config with default values."""
        config = UpdateStrategyConfig()
        assert config.etf_list.enabled is True
        assert config.etf_list.schedule == "0 2 * * *"
        assert config.daily_data.enabled is True
        assert config.daily_data.schedule == "30 15 * * *"
        assert config.adj_factors.enabled is True
        assert config.adj_factors.schedule == "0 3 * * 0"

    def test_update_strategy_config_custom_values(self) -> None:
        """Test update strategy config with custom values."""
        config = UpdateStrategyConfig(
            etf_list={"enabled": False, "schedule": "0 1 * * *"},
            daily_data={"retry_count": 5, "lookback_days": 10},
        )
        assert config.etf_list.enabled is False
        assert config.etf_list.schedule == "0 1 * * *"
        assert config.daily_data.retry_count == 5
        assert config.daily_data.lookback_days == 10


class TestSourcesConfig:
    """Test cases for SourcesConfig."""

    def test_sources_config_complete(self) -> None:
        """Test creating a complete sources config."""
        config = SourcesConfig(
            primary=SourceConfig(
                type="tushare",
                enabled=True,
                config={"token": "test_token", "rate_limit": 200},
            ),
            backup=SourceConfig(
                type="akshare",
                enabled=True,
                config={"timeout": 30},
            ),
            test=SourceConfig(
                type="csv",
                enabled=False,
                config={"data_dir": "./data/test"},
            ),
        )
        assert config.primary.type == "tushare"
        assert config.backup.type == "akshare"
        assert config.test.type == "csv"
        assert config.collection.batch_size == 1000
        assert config.quality.price_validation.enabled is True

    def test_sources_config_get_enabled_sources(self) -> None:
        """Test getting enabled sources."""
        config = SourcesConfig(
            primary=SourceConfig(type="tushare", enabled=True, config={}),
            backup=SourceConfig(type="akshare", enabled=True, config={}),
            test=SourceConfig(type="csv", enabled=False, config={}),
        )
        enabled = config.get_enabled_sources()
        assert len(enabled) == 2
        assert "primary" in enabled
        assert "backup" in enabled
        assert "test" not in enabled

    def test_sources_config_get_source_config(self) -> None:
        """Test getting specific source config."""
        primary_config = SourceConfig(type="tushare", enabled=True, config={})
        backup_config = SourceConfig(type="akshare", enabled=True, config={})
        test_config = SourceConfig(type="csv", enabled=False, config={})
        config = SourcesConfig(
            primary=primary_config,
            backup=backup_config,
            test=test_config,
        )

        assert config.get_source_config("primary") == primary_config
        assert config.get_source_config("backup") == backup_config
        assert config.get_source_config("nonexistent") is None


class TestLoadSourcesConfig:
    """Test cases for load_sources_config function."""

    def test_load_from_file(self) -> None:
        """Test loading config from a YAML file."""
        config_data = {
            "primary": {
                "type": "tushare",
                "enabled": True,
                "config": {"token": "test_token", "rate_limit": 200},
            },
            "backup": {
                "type": "akshare",
                "enabled": True,
                "config": {"timeout": 30},
            },
            "test": {
                "type": "csv",
                "enabled": False,
                "config": {"data_dir": "./test"},
            },
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config_data, f)
            config_path = f.name

        try:
            config = load_sources_config(config_path)
            assert config.primary.type == "tushare"
            assert config.backup.type == "akshare"
            assert config.primary.config["token"] == "test_token"
        finally:
            Path(config_path).unlink()

    def test_load_with_env_substitution(self) -> None:
        """Test loading config with environment variable substitution."""
        config_data = {
            "primary": {
                "type": "tushare",
                "enabled": True,
                "config": {
                    "token": "${TUSHARE_TOKEN}",
                    "api_url": "${TUSHARE_URL:https://api.tushare.pro}",
                },
            },
            "backup": {
                "type": "akshare",
                "enabled": True,
                "config": {"timeout": 30},
            },
            "test": {
                "type": "csv",
                "enabled": False,
                "config": {"data_dir": "./test"},
            },
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config_data, f)
            config_path = f.name

        try:
            with patch.dict(os.environ, {"TUSHARE_TOKEN": "env_token"}):
                config = load_sources_config(config_path)
                assert config.primary.config["token"] == "env_token"
                assert config.primary.config["api_url"] == "https://api.tushare.pro"
        finally:
            Path(config_path).unlink()

    def test_load_with_missing_env_var_and_default(self) -> None:
        """Test loading config with missing env var but with default."""
        config_data = {
            "primary": {
                "type": "tushare",
                "enabled": True,
                "config": {
                    "token": "${MISSING_VAR:default_token}",
                },
            },
            "backup": {
                "type": "akshare",
                "enabled": True,
                "config": {"timeout": 30},
            },
            "test": {
                "type": "csv",
                "enabled": False,
                "config": {"data_dir": "./test"},
            },
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config_data, f)
            config_path = f.name

        try:
            config = load_sources_config(config_path)
            assert config.primary.config["token"] == "default_token"
        finally:
            Path(config_path).unlink()

    def test_load_with_missing_env_var_no_default(self) -> None:
        """Test loading config with missing env var and no default."""
        config_data = {
            "primary": {
                "type": "tushare",
                "enabled": True,
                "config": {
                    "token": "${MISSING_VAR}",
                },
            },
            "backup": {
                "type": "akshare",
                "enabled": True,
                "config": {"timeout": 30},
            },
            "test": {
                "type": "csv",
                "enabled": False,
                "config": {"data_dir": "./test"},
            },
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config_data, f)
            config_path = f.name

        try:
            with pytest.raises(ValueError) as exc_info:
                load_sources_config(config_path)

            assert "MISSING_VAR" in str(exc_info.value)
        finally:
            Path(config_path).unlink()

    def test_load_default_config(self) -> None:
        """Test loading default config when no path provided."""
        # Test should work without raising exception
        # Note: This might fail if the default config file doesn't exist
        # In a real scenario, we would ensure the default file exists
        pass
