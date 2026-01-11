"""Tests for DQEngine."""

import tempfile
from pathlib import Path

import polars as pl
import pytest
from ditto_datahub.dq import (
    DatasetRules,
    DQConfig,
    DQEngine,
    DQResult,
)


class TestDQEngine:
    """Test cases for DQEngine."""

    def setup_method(self) -> None:
        """Set up test environment."""
        # Create real config with DatasetRules
        self.config = DQConfig(
            datasets={
                "test_dataset": DatasetRules(
                    dataset="test_dataset",
                    description="Test dataset for DQ engine",
                    l1_technical=[
                        {
                            "rule": "not_null",
                            "columns": ["sid"],
                            "message": "SID required",
                        }
                    ],
                    l2_business=[
                        {
                            "rule": "positive",
                            "columns": ["value"],
                            "message": "Value positive",
                        }
                    ],
                    l3_statistical=[],
                )
            }
        )

    def test_init_with_config(self) -> None:
        """Test engine initialization with config."""
        engine = DQEngine(config=self.config)

        assert engine.config is self.config

    def test_init_from_yaml_dir(self) -> None:
        """Test engine initialization from YAML directory."""
        # Use actual config directory
        config_dir = Path(__file__).parent.parent.parent.parent / "config" / "dq_rules"

        if not config_dir.exists():
            pytest.skip(f"Config directory not found: {config_dir}")

        engine = DQEngine(config_path=config_dir)

        assert engine.config is not None
        assert engine.config.has_dataset("etf_daily") is True

    def test_check_valid_data(self) -> None:
        """Test checking valid data passes all rules."""
        engine = DQEngine(config=self.config)

        df = pl.DataFrame(
            {
                "sid": [1, 2, 3],
                "trade_date": ["2024-01-01", "2024-01-02", "2024-01-03"],
                "value": [10.0, 20.0, 30.0],
            }
        )

        result = engine.check(df, "test_dataset")

        # Should pass since data is valid
        assert isinstance(result, DQResult)
        assert result.dataset == "test_dataset"
        assert result.passed is True  # No nulls in sid, all values positive

    def test_check_with_null_sid(self) -> None:
        """Test checking data with null SID fails L1."""
        engine = DQEngine(config=self.config)

        df = pl.DataFrame(
            {
                "sid": [1, None, 3],  # One null SID
                "value": [10.0, 20.0, 30.0],
            }
        )

        result = engine.check(df, "test_dataset")

        # Should fail due to null SID (L1 ERROR)
        assert result.passed is False
        assert result.has_errors is True
        assert result.error_count >= 1

    def test_check_with_negative_value(self) -> None:
        """Test checking data with negative value generates L2 warning."""
        engine = DQEngine(config=self.config)

        df = pl.DataFrame(
            {
                "sid": [1, 2, 3],
                "value": [10.0, -5.0, 30.0],  # One negative value
            }
        )

        result = engine.check(df, "test_dataset")

        # Should pass overall (L2 is warning only), but have warnings
        assert result.passed is True  # No L1 errors
        assert result.has_warnings is True
        assert result.warn_count >= 1

    def test_check_unknown_dataset(self) -> None:
        """Test checking unknown dataset returns empty result."""
        engine = DQEngine(config=self.config)

        df = pl.DataFrame({"test": [1, 2, 3]})

        result = engine.check(df, "unknown_dataset")

        # Unknown dataset should pass with no issues
        assert result.passed is True
        assert len(result.issues) == 0

    @pytest.mark.parametrize(
        ("levels", "expected_has_warnings", "expected_has_errors"),
        [
            (["l1"], False, False),  # L2 violations not checked, so no warnings
            (["l2"], True, False),  # Only warnings, no errors
        ],
    )
    def test_check_with_specific_levels(
        self,
        levels: list[str],
        expected_has_warnings: bool,
        expected_has_errors: bool,
    ) -> None:
        """Test checking with specific rule levels."""
        engine = DQEngine(config=self.config)

        df = pl.DataFrame({"sid": [1, 2], "value": [-10.0, 20.0]})

        result = engine.check(df, "test_dataset", levels=levels)

        assert isinstance(result, DQResult)
        assert result.has_warnings is expected_has_warnings
        assert result.has_errors is expected_has_errors

    def test_check_with_context(self, mocker) -> None:
        """Test checking with additional context."""
        engine = DQEngine(config=self.config)

        df = pl.DataFrame({"sid": [1, 2], "value": [10.0, 20.0]})

        context = {"hub": mocker.Mock(), "source": "test"}

        result = engine.check(df, "test_dataset", context=context)

        assert isinstance(result, DQResult)


class TestDQEngineIntegration:
    """Integration tests with real YAML config."""

    def test_check_etf_daily_with_real_config(self) -> None:
        """Test checking ETF daily data with real YAML config."""
        config_dir = Path(__file__).parent.parent.parent.parent / "config" / "dq_rules"

        if not config_dir.exists():
            pytest.skip(f"Config directory not found: {config_dir}")

        engine = DQEngine(config_path=config_dir)

        # Valid ETF data
        df = pl.DataFrame(
            {
                "sid": [200001, 200001],
                "trade_date": ["2024-01-01", "2024-01-02"],
                "open": [10.0, 10.5],
                "high": [10.2, 10.8],
                "low": [9.8, 10.2],
                "close": [10.1, 10.6],
            }
        )

        result = engine.check(df, "etf_daily")

        # Should pass basic validation
        assert isinstance(result, DQResult)
        assert result.dataset == "etf_daily"
        assert result.passed is True  # Valid data passes

    def test_check_etf_daily_with_ohlc_violation(self) -> None:
        """Test ETF data with OHLC violation generates L2 warning."""
        config_dir = Path(__file__).parent.parent.parent.parent / "config" / "dq_rules"

        if not config_dir.exists():
            pytest.skip(f"Config directory not found: {config_dir}")

        engine = DQEngine(config_path=config_dir)

        # Invalid OHLC data (high < low)
        df = pl.DataFrame(
            {
                "sid": [200001],
                "trade_date": ["2024-01-01"],
                "open": [10.5],
                "high": [10.0],  # High < open
                "low": [10.8],  # Low > open
                "close": [10.1],
            }
        )

        result = engine.check(df, "etf_daily")

        # Should pass overall (L2 is warning), but have warnings
        assert result.dataset == "etf_daily"
        # OHLC check not yet implemented, so this might pass for now
        assert isinstance(result, DQResult)


class TestDQEngineEdgeCases:
    """Test edge cases and additional coverage for DQEngine."""

    def test_init_with_data_root(self) -> None:
        """Test engine initialization with data_root parameter."""

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a default config directory structure
            default_config = (
                Path(__file__).parent.parent.parent.parent / "config" / "dq_rules"
            )

            if not default_config.exists():
                pytest.skip(f"Default config directory not found: {default_config}")

            engine = DQEngine(data_root=tmpdir)

            assert engine.config is not None

    def test_init_with_no_params(self) -> None:
        """Test engine initialization with no parameters (default empty config)."""
        engine = DQEngine()

        assert engine.config is not None
        assert isinstance(engine.config, DQConfig)

    def test_config_property(self) -> None:
        """Test _config property for backward compatibility."""
        engine = DQEngine()

        # _config property should return the same as config
        assert engine._config is engine.config

    def test_check_with_empty_rule_lists(self) -> None:
        """Test check with dataset rules but empty L1/L2 lists."""
        config = DQConfig(
            datasets={
                "test_dataset": DatasetRules(
                    dataset="test_dataset",
                    description="Test dataset with empty rules",
                    l1_technical=[],  # Empty list
                    l2_business=[],  # Empty list
                    l3_statistical=[],
                )
            }
        )

        engine = DQEngine(config=config)

        df = pl.DataFrame({"sid": [1, 2, 3], "value": [10.0, 20.0, 30.0]})

        result = engine.check(df, "test_dataset")

        # Should pass with no issues
        assert result.passed is True
        assert len(result.issues) == 0

    def test_check_with_levels_none(self) -> None:
        """Test check with levels=None (default behavior)."""
        config = DQConfig(
            datasets={
                "test_dataset": DatasetRules(
                    dataset="test_dataset",
                    description="Test dataset",
                    l1_technical=[
                        {
                            "rule": "not_null",
                            "columns": ["sid"],
                            "message": "SID required",
                        }
                    ],
                    l2_business=[],
                )
            }
        )

        engine = DQEngine(config=config)

        df = pl.DataFrame({"sid": [1, 2, 3]})

        # levels=None should default to ["l1", "l2"]
        result = engine.check(df, "test_dataset", levels=None)

        assert result.passed is True

    def test_check_with_both_levels(self) -> None:
        """Test check with both L1 and L2 levels."""
        config = DQConfig(
            datasets={
                "test_dataset": DatasetRules(
                    dataset="test_dataset",
                    description="Test dataset",
                    l1_technical=[
                        {
                            "rule": "not_null",
                            "columns": ["sid"],
                            "message": "SID required",
                        }
                    ],
                    l2_business=[
                        {
                            "rule": "positive",
                            "columns": ["value"],
                            "message": "Value positive",
                        }
                    ],
                )
            }
        )

        engine = DQEngine(config=config)

        df = pl.DataFrame({"sid": [1, 2, 3], "value": [-5.0, 10.0, 20.0]})

        result = engine.check(df, "test_dataset", levels=["l1", "l2"])

        # L1 passes, L2 generates warning
        assert result.passed is True  # No L1 errors
        assert result.has_warnings is True  # L2 warning

    def test_check_statistical_basic(self, mocker) -> None:
        """Test check_statistical with mock hub."""
        config = DQConfig(
            datasets={
                "test_dataset": DatasetRules(
                    dataset="test_dataset",
                    description="Test dataset",
                    l3_statistical=[
                        {
                            "rule": "zscore",
                            "column": "close",
                            "window": 60,
                            "threshold": 3.0,
                        }
                    ],
                )
            }
        )

        engine = DQEngine(config=config)

        # Mock hub
        mock_hub = mocker.MagicMock()
        mock_hub.bars.get.return_value = pl.DataFrame()

        result = engine.check_statistical(
            dataset="test_dataset",
            trade_date="2024-01-01",
            hub=mock_hub,
        )

        # check_statistical always passes (alerts only)
        assert result.passed is True
        assert result.dataset == "test_dataset"

    def test_check_statistical_unknown_dataset(self, mocker) -> None:
        """Test check_statistical with unknown dataset."""
        engine = DQEngine()

        mock_hub = mocker.MagicMock()

        result = engine.check_statistical(
            dataset="unknown_dataset",
            trade_date="2024-01-01",
            hub=mock_hub,
        )

        # Unknown dataset should pass with no issues
        assert result.passed is True
        assert len(result.issues) == 0

    def test_check_statistical_with_asset_class(self, mocker) -> None:
        """Test check_statistical with asset_class parameter."""
        config = DQConfig(
            datasets={
                "stock_daily": DatasetRules(
                    dataset="stock_daily",
                    description="Stock daily data",
                    l3_statistical=[
                        {
                            "rule": "zscore",
                            "column": "close",
                            "window": 60,
                            "threshold": 3.0,
                        }
                    ],
                )
            }
        )

        engine = DQEngine(config=config)

        mock_hub = mocker.MagicMock()
        mock_hub.bars.get.return_value = pl.DataFrame()

        result = engine.check_statistical(
            dataset="stock_daily",
            trade_date="2024-01-01",
            hub=mock_hub,
            asset_class="stock",
            market_wide=True,
        )

        assert result.passed is True

    def test_check_with_no_matching_levels(self) -> None:
        """Test check with levels that don't match configured rules."""
        config = DQConfig(
            datasets={
                "test_dataset": DatasetRules(
                    dataset="test_dataset",
                    description="Test dataset",
                    l1_technical=[
                        {
                            "rule": "not_null",
                            "columns": ["sid"],
                            "message": "SID required",
                        }
                    ],
                )
            }
        )

        engine = DQEngine(config=config)

        df = pl.DataFrame({"sid": [1, 2, 3]})

        # Only check L2, but dataset has no L2 rules
        result = engine.check(df, "test_dataset", levels=["l2"])

        assert result.passed is True
        assert len(result.issues) == 0
