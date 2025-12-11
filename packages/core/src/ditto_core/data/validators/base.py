"""Base classes for data validators."""

from abc import ABC, abstractmethod
from typing import Any

import polars as pl


class ValidationResult:
    """
    Result of a data validation operation.

    Attributes:
        is_valid (bool): Whether the data passed validation.
        message (str): Human-readable validation message.
        details (Dict[str, Any]): Additional details about the validation.

    """

    def __init__(
        self, is_valid: bool, message: str = "", details: dict[str, Any] | None = None
    ) -> None:
        """
        Initialize validation result.

        Args:
            is_valid: Whether the validation passed.
            message: Human-readable message describing the result.
            details: Additional validation details.

        """
        self.is_valid = is_valid
        self.message = message
        self.details = details or {}

    def __repr__(self) -> str:
        """String representation of validation result."""
        return f"ValidationResult(is_valid={self.is_valid}, message='{self.message}')"

    def to_dict(self) -> dict[str, Any]:
        """
        Convert result to dictionary.

        Returns:
            Dictionary representation of the validation result.

        """
        return {
            "is_valid": self.is_valid,
            "message": self.message,
            "details": self.details,
        }


class BaseValidator(ABC):
    """
    Abstract base class for data validators.

    All validators should inherit from this class and implement the validate method.
    """

    @abstractmethod
    def validate(self, data: pl.DataFrame) -> ValidationResult:
        """
        Validate a DataFrame of data.

        Args:
            data: DataFrame containing data to validate.

        Returns:
            ValidationResult with validation outcome.

        """
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """
        Get the validator name.

        Returns:
            String identifier for this validator.

        """
        pass

    def __repr__(self) -> str:
        """String representation of validator."""
        return f"{self.__class__.__name__}(name='{self.name}')"
