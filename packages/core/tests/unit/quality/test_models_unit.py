"""Tests for DQ configuration models."""

import pytest
from ditto_core.quality.spec import (
    DatasetRules,
    DQSpec,
    NotNullRule,
    RangeCheckRule,
    UniqueRule,
    ZScoreRule,
)
from pydantic import ValidationError


class TestDatasetRules:
    """Test DatasetRules model."""

    def test_create_minimal_rules(self) -> None:
        """Test creating dataset rules with minimal config."""
        config = DatasetRules(
            dataset="test_dataset",
            description="Test dataset",
        )

        assert config.dataset == "test_dataset"
        assert config.description == "Test dataset"
        assert len(config.l1_technical) == 0
        assert len(config.l2_business) == 0
        assert len(config.l3_statistical) == 0

    def test_create_with_rules(self) -> None:
        """Test creating dataset rules with rules."""
        config = DatasetRules(
            dataset="etf_daily",
            description="ETF daily data",
            l1_technical=[
                {
                    "rule": "not_null",
                    "columns": ["sid", "trade_date"],
                    "message": "Required",
                },
                {
                    "rule": "unique",
                    "columns": ["sid", "trade_date"],
                    "message": "Unique",
                },
            ],
            l2_business=[
                {
                    "rule": "positive",
                    "columns": ["open", "high", "low", "close"],
                    "message": "Positive",
                }
            ],
        )

        assert config.dataset == "etf_daily"
        assert len(config.l1_technical) == 2
        assert len(config.l2_business) == 1


class TestRuleModels:
    """Test individual rule models."""

    def test_not_null_rule(self) -> None:
        """Test NotNullRule validation."""
        rule = NotNullRule(
            rule="not_null",
            columns=["sid", "trade_date"],
            message="Fields required",
        )

        assert rule.rule == "not_null"
        assert rule.columns == ["sid", "trade_date"]

    def test_unique_rule(self) -> None:
        """Test UniqueRule validation."""
        rule = UniqueRule(
            rule="unique",
            columns=["sid", "trade_date"],
            message="Primary key unique",
        )

        assert rule.rule == "unique"
        assert rule.columns == ["sid", "trade_date"]

    def test_zscore_rule_validation(self) -> None:
        """Test ZScoreRule validation."""
        # Valid rule
        rule = ZScoreRule(
            rule="zscore",
            name="volume_spike",
            column="volume",
            window=60,
            threshold=5.0,
            group_by="sid",
            message="Volume spike",
        )

        assert rule.window == 60
        assert rule.threshold == 5.0
        assert rule.group_by == "sid"

        # Invalid threshold
        with pytest.raises(ValidationError):
            ZScoreRule(
                rule="zscore",
                name="test",
                column="volume",
                threshold=-1.0,  # Must be > 0
                message="Invalid",
            )

        # Invalid window
        with pytest.raises(ValidationError):
            ZScoreRule(
                rule="zscore",
                name="test",
                column="volume",
                window=0,  # Must be >= 1
                message="Invalid",
            )

    def test_range_check_rule(self) -> None:
        """Test RangeCheckRule validation."""
        rule = RangeCheckRule(
            rule="range_check",
            column="close",
            min_ratio=0.01,
            max_ratio=1.11,
            message="Price range check",
        )

        assert rule.column == "close"
        assert rule.min_ratio == 0.01
        assert rule.max_ratio == 1.11


class TestDQSpec:
    """Test DQSpec model."""

    def test_empty_config(self) -> None:
        """Test creating empty config."""
        config = DQSpec()

        assert len(config.datasets) == 0
        assert config.get_rules("nonexistent") is None

    def test_has_dataset(self) -> None:
        """Test has_dataset method."""
        config = DQSpec(
            datasets={
                "etf_daily": DatasetRules(
                    dataset="etf_daily",
                    description="ETF daily",
                )
            }
        )

        assert config.has_dataset("etf_daily") is True
        assert config.has_dataset("nonexistent") is False

    def test_get_rules(self) -> None:
        """Test get_rules method."""
        dataset_rules = DatasetRules(
            dataset="stock_daily",
            description="Market daily",
        )

        config = DQSpec(datasets={"stock_daily": dataset_rules})

        assert config.get_rules("stock_daily") is dataset_rules
        assert config.get_rules("nonexistent") is None
