"""Tests for QualityEngine."""

from datetime import date, timedelta

import polars as pl
import pytest
from ditto_core.quality import QualityEngine
from ditto_core.quality.spec import (
    DatasetRules,
    DQResult,
    DQSpec,
)


class TestQualityEngine:
    """Test cases for QualityEngine."""

    def setup_method(self) -> None:
        """Set up test environment."""
        # Create real config with DatasetRules
        self.config = DQSpec(
            datasets={
                "test_dataset": DatasetRules(
                    dataset="test_dataset",
                    description="Test dataset for DQ engine",
                    technical=[
                        {
                            "rule": "not_null",
                            "columns": ["instrument_id"],
                            "message": "SID required",
                        }
                    ],
                    business=[
                        {
                            "rule": "positive",
                            "columns": ["value"],
                            "message": "Value positive",
                        }
                    ],
                    statistical=[],
                )
            }
        )

    def test_check_valid_data(self) -> None:
        """Test checking valid data passes all rules."""
        engine = QualityEngine(config=self.config)

        df = pl.DataFrame(
            {
                "instrument_id": [1, 2, 3],
                "trade_date": ["2024-01-01", "2024-01-02", "2024-01-03"],
                "value": [10.0, 20.0, 30.0],
            }
        )

        result = engine.check(df, "test_dataset")

        # Should pass since data is valid
        assert isinstance(result, DQResult)
        assert result.dataset == "test_dataset"
        assert result.passed is True  # No nulls in instrument_id, all values positive

    def test_check_with_null_sid(self) -> None:
        """Test checking data with null SID fails L1."""
        engine = QualityEngine(config=self.config)

        df = pl.DataFrame(
            {
                "instrument_id": [1, None, 3],  # One null SID
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
        engine = QualityEngine(config=self.config)

        df = pl.DataFrame(
            {
                "instrument_id": [1, 2, 3],
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
        engine = QualityEngine(config=self.config)

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
        engine = QualityEngine(config=self.config)

        df = pl.DataFrame({"instrument_id": [1, 2], "value": [-10.0, 20.0]})

        result = engine.check(df, "test_dataset", levels=levels)

        assert isinstance(result, DQResult)
        assert result.has_warnings is expected_has_warnings
        assert result.has_errors is expected_has_errors

    def test_check_with_context(self) -> None:
        """Test checking with additional context."""
        engine = QualityEngine(config=self.config)

        df = pl.DataFrame({"instrument_id": [1, 2], "value": [10.0, 20.0]})

        context = {"source": "test"}

        result = engine.check(df, "test_dataset", context=context)

        assert isinstance(result, DQResult)


class TestQualityEngineStatistical:
    """Test statistical check with new interface."""

    def setup_method(self) -> None:
        """Set up test environment."""
        self.config = DQSpec(
            datasets={
                "test_dataset": DatasetRules(
                    dataset="test_dataset",
                    description="Test dataset",
                    statistical=[
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

    @pytest.fixture
    def historical_data(self):
        """Create historical data."""
        dates = [date.today() - timedelta(days=i) for i in range(60, 0, -1)]
        rows = []
        for d in dates:
            rows.extend(
                [
                    {"instrument_id": 1, "trade_date": d, "close": 100.0},
                    {"instrument_id": 2, "trade_date": d, "close": 200.0},
                ]
            )
        return pl.DataFrame(rows)

    def test_check_statistical_basic(self, historical_data) -> None:
        """Test check_statistical with data injection."""
        engine = QualityEngine(config=self.config)

        current_data = pl.DataFrame(
            {
                "instrument_id": [1, 2],
                "trade_date": [date.today(), date.today()],
                "close": [105.0, 210.0],
            }
        )

        result = engine.check_statistical(
            dataset="test_dataset",
            current=current_data,
            historical=historical_data,
            calendar=None,
        )

        # check_statistical always passes (alerts only)
        assert result.passed is True
        assert result.dataset == "test_dataset"

    def test_check_statistical_unknown_dataset(self, historical_data) -> None:
        """Test check_statistical with unknown dataset."""
        engine = QualityEngine(config=DQSpec())

        current_data = pl.DataFrame(
            {
                "instrument_id": [1],
                "trade_date": [date.today()],
                "close": [105.0],
            }
        )

        result = engine.check_statistical(
            dataset="unknown_dataset",
            current=current_data,
            historical=historical_data,
            calendar=None,
        )

        # Unknown dataset should pass with no issues
        assert result.passed is True
        assert len(result.issues) == 0

    def test_check_statistical_detects_anomalies(self, historical_data) -> None:
        """Test check_statistical detects outliers."""
        engine = QualityEngine(config=self.config)

        # Current data with anomaly
        current_data = pl.DataFrame(
            {
                "instrument_id": [1, 2],
                "trade_date": [date.today(), date.today()],
                "close": [500.0, 210.0],  # 500 is way outside normal range
            }
        )

        result = engine.check_statistical(
            dataset="test_dataset",
            current=current_data,
            historical=historical_data,
            calendar=None,
        )

        # Should detect anomaly but still pass (L3 is alert only)
        assert result.passed is True
        assert result.alert_count >= 1


class TestQualityEngineEdgeCases:
    """Test edge cases and additional coverage for QualityEngine."""

    def test_init_with_empty_config(self) -> None:
        """Test engine initialization with empty config."""
        empty_config = DQSpec()
        engine = QualityEngine(config=empty_config)

        assert engine.config is empty_config
        assert isinstance(engine.config, DQSpec)

    def test_check_with_empty_rule_lists(self) -> None:
        """Test check with dataset rules but empty L1/L2 lists."""
        config = DQSpec(
            datasets={
                "test_dataset": DatasetRules(
                    dataset="test_dataset",
                    description="Test dataset with empty rules",
                    technical=[],  # Empty list
                    business=[],  # Empty list
                    statistical=[],
                )
            }
        )

        engine = QualityEngine(config=config)

        df = pl.DataFrame({"instrument_id": [1, 2, 3], "value": [10.0, 20.0, 30.0]})

        result = engine.check(df, "test_dataset")

        # Should pass with no issues
        assert result.passed is True
        assert len(result.issues) == 0

    def test_check_with_levels_none(self) -> None:
        """Test check with levels=None (default behavior)."""
        config = DQSpec(
            datasets={
                "test_dataset": DatasetRules(
                    dataset="test_dataset",
                    description="Test dataset",
                    technical=[
                        {
                            "rule": "not_null",
                            "columns": ["instrument_id"],
                            "message": "SID required",
                        }
                    ],
                    business=[],
                )
            }
        )

        engine = QualityEngine(config=config)

        df = pl.DataFrame({"instrument_id": [1, 2, 3]})

        # levels=None should default to ["l1", "l2"]
        result = engine.check(df, "test_dataset", levels=None)

        assert result.passed is True

    def test_check_with_both_levels(self) -> None:
        """Test check with both L1 and L2 levels."""
        config = DQSpec(
            datasets={
                "test_dataset": DatasetRules(
                    dataset="test_dataset",
                    description="Test dataset",
                    technical=[
                        {
                            "rule": "not_null",
                            "columns": ["instrument_id"],
                            "message": "SID required",
                        }
                    ],
                    business=[
                        {
                            "rule": "positive",
                            "columns": ["value"],
                            "message": "Value positive",
                        }
                    ],
                )
            }
        )

        engine = QualityEngine(config=config)

        df = pl.DataFrame({"instrument_id": [1, 2, 3], "value": [-5.0, 10.0, 20.0]})

        result = engine.check(df, "test_dataset", levels=["l1", "l2"])

        # L1 passes, L2 generates warning
        assert result.passed is True  # No L1 errors
        assert result.has_warnings is True  # L2 warning

    def test_check_with_empty_dataframe(self) -> None:
        """Test check with empty dataframe."""
        config = DQSpec(
            datasets={
                "test_dataset": DatasetRules(
                    dataset="test_dataset",
                    description="Test dataset",
                    technical=[
                        {
                            "rule": "not_null",
                            "columns": ["instrument_id"],
                            "message": "SID required",
                        }
                    ],
                    business=[],
                )
            }
        )

        engine = QualityEngine(config=config)

        df = pl.DataFrame({"instrument_id": [], "value": []})

        result = engine.check(df, "test_dataset")

        # Empty dataframe should pass
        assert result.passed is True
        assert len(result.issues) == 0
