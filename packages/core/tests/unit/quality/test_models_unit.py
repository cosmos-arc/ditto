"""Tests for DQ configuration models."""

from pathlib import Path

import pytest
import yaml
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

    def test_from_yaml_dir(self) -> None:
        """Test loading config from YAML directory."""
        # Use the actual config directory
        config_dir = (
            Path(__file__).parent.parent.parent.parent
            / "config"
            / "default"
            / "dq_rules"
        )

        if not config_dir.exists():
            pytest.skip(f"Config directory not found: {config_dir}")

        config = DQSpec.from_yaml_dir(config_dir)

        # Should load datasets
        assert len(config.datasets) > 0

        # Check etf_daily dataset
        etf_rules = config.get_rules("etf_daily")
        assert etf_rules is not None
        assert etf_rules.dataset == "etf_daily"
        assert len(etf_rules.l1_technical) > 0

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


class TestDQSpecErrorHandling:
    """Test error handling in DQSpec.from_yaml_dir."""

    def test_skips_invalid_yaml_files(self, tmp_path: Path) -> None:
        """Test that invalid YAML files are skipped without crashing."""
        # Create a valid YAML file
        valid_file = tmp_path / "valid.yml"
        valid_file.write_text(
            yaml.dump(
                {
                    "dataset": "valid_dataset",
                    "description": "Valid dataset",
                    "l1_technical": [],
                    "l2_business": [],
                    "l3_statistical": [],
                }
            )
        )

        # Create an invalid YAML file (malformed YAML)
        invalid_yaml_file = tmp_path / "invalid.yml"
        invalid_yaml_file.write_text(
            "dataset: test\n  invalid_indent: value\n  bad: [unclosed"
        )

        # Load config - should skip invalid file and not crash
        config = DQSpec.from_yaml_dir(tmp_path)

        # Should load only the valid file
        assert len(config.datasets) == 1
        assert "valid_dataset" in config.datasets

    def test_skips_validation_error_files(self, tmp_path: Path) -> None:
        """Test that files with validation errors are skipped without crashing."""
        # Create a valid YAML file
        valid_file = tmp_path / "valid.yml"
        valid_file.write_text(
            yaml.dump(
                {
                    "dataset": "valid_dataset",
                    "description": "Valid dataset",
                    "l1_technical": [],
                    "l2_business": [],
                    "l3_statistical": [],
                }
            )
        )

        # Create a file that fails Pydantic validation (missing required fields)
        validation_error_file = tmp_path / "validation_error.yml"
        validation_error_file.write_text(
            yaml.dump(
                {
                    "dataset": "invalid_dataset",
                    # Missing 'description' field which is required
                }
            )
        )

        # Load config - should skip invalid file and not crash
        config = DQSpec.from_yaml_dir(tmp_path)

        # Should load only the valid file
        assert len(config.datasets) == 1
        assert "valid_dataset" in config.datasets
        assert "invalid_dataset" not in config.datasets

    def test_skips_files_without_dataset_key(self, tmp_path: Path) -> None:
        """Test that files without 'dataset' key are silently skipped."""
        # Create a valid YAML file
        valid_file = tmp_path / "valid.yml"
        valid_file.write_text(
            yaml.dump(
                {
                    "dataset": "valid_dataset",
                    "description": "Valid dataset",
                    "l1_technical": [],
                    "l2_business": [],
                    "l3_statistical": [],
                }
            )
        )

        # Create a file without 'dataset' key
        no_dataset_file = tmp_path / "no_dataset.yml"
        no_dataset_file.write_text(
            yaml.dump(
                {
                    "description": "No dataset key",
                    "l1_technical": [],
                }
            )
        )

        # Load config - should skip file without dataset key (no error expected)
        config = DQSpec.from_yaml_dir(tmp_path)

        # Should load only the valid file
        assert len(config.datasets) == 1
        assert "valid_dataset" in config.datasets

    def test_handles_mixed_valid_and_invalid_files(self, tmp_path: Path) -> None:
        """Test handling of mixed valid and invalid files."""
        # Create multiple valid files
        for i in range(3):
            valid_file = tmp_path / f"valid_{i}.yml"
            valid_file.write_text(
                yaml.dump(
                    {
                        "dataset": f"dataset_{i}",
                        "description": f"Dataset {i}",
                        "l1_technical": [],
                        "l2_business": [],
                        "l3_statistical": [],
                    }
                )
            )

        # Create invalid files
        # Malformed YAML
        (tmp_path / "invalid_yaml.yml").write_text("{invalid yaml content")
        # Missing required field
        (tmp_path / "invalid_validation.yml").write_text(
            yaml.dump({"dataset": "no_description"})
        )
        # Empty file
        (tmp_path / "empty.yml").write_text("")

        # Load config - should load only valid files and skip invalid ones
        config = DQSpec.from_yaml_dir(tmp_path)

        # Should load 3 valid files
        assert len(config.datasets) == 3
        for i in range(3):
            assert f"dataset_{i}" in config.datasets

    def test_returns_empty_config_for_nonexistent_dir(self) -> None:
        """Test that nonexistent directory returns empty config."""
        nonexistent_path = Path("/nonexistent/path/that/does/not/exist")
        config = DQSpec.from_yaml_dir(nonexistent_path)

        assert len(config.datasets) == 0
