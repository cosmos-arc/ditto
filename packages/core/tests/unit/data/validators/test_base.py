"""Tests for base validator classes."""

import polars as pl
import pytest
from ditto_core.data.validators.base import BaseValidator, ValidationResult


class TestValidationResult:
    """Test ValidationResult class."""

    def test_init_with_all_params(self):
        """Test initialization with all parameters."""
        details = {"error_count": 5, "warnings": 1}
        result = ValidationResult(
            is_valid=False, message="Validation failed", details=details
        )

        assert result.is_valid is False
        assert result.message == "Validation failed"
        assert result.details == details

    def test_init_with_defaults(self):
        """Test initialization with default values."""
        result = ValidationResult(is_valid=True)

        assert result.is_valid is True
        assert result.message == ""
        assert result.details == {}

    def test_repr(self):
        """Test string representation."""
        result = ValidationResult(is_valid=True, message="All good")
        assert repr(result) == "ValidationResult(is_valid=True, message='All good')"

    def test_to_dict(self):
        """Test conversion to dictionary."""
        details = {"records": 100}
        result = ValidationResult(is_valid=False, message="Error", details=details)

        expected = {"is_valid": False, "message": "Error", "details": details}
        assert result.to_dict() == expected

    def test_to_dict_with_empty_details(self):
        """Test to_dict with None details."""
        result = ValidationResult(is_valid=True)

        expected = {"is_valid": True, "message": "", "details": {}}
        assert result.to_dict() == expected


class ConcreteValidator(BaseValidator):
    """Concrete implementation of BaseValidator for testing."""

    @property
    def name(self) -> str:
        return "test_validator"

    def validate(self, data: pl.DataFrame) -> ValidationResult:
        return ValidationResult(
            is_valid=len(data) > 0,
            message=f"DataFrame has {len(data)} rows",
            details={"row_count": len(data)},
        )


class TestBaseValidator:
    """Test BaseValidator abstract class."""

    def test_cannot_instantiate_abstract(self):
        """Test that BaseValidator cannot be instantiated directly."""
        with pytest.raises(TypeError):
            BaseValidator()

    def test_concrete_implementation(self):
        """Test concrete implementation works correctly."""
        validator = ConcreteValidator()

        assert validator.name == "test_validator"
        assert isinstance(validator, BaseValidator)

    def test_repr(self):
        """Test string representation of validator."""
        validator = ConcreteValidator()
        assert repr(validator) == "ConcreteValidator(name='test_validator')"

    def test_validate_method(self):
        """Test validate method returns correct result."""
        validator = ConcreteValidator()

        # Test with non-empty DataFrame
        df = pl.DataFrame({"a": [1, 2, 3]})
        result = validator.validate(df)

        assert result.is_valid is True
        assert result.details["row_count"] == 3

        # Test with empty DataFrame
        empty_df = pl.DataFrame()
        result = validator.validate(empty_df)

        assert result.is_valid is False
