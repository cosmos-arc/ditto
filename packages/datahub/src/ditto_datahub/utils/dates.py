"""
Date normalization utilities for DataHub.

Provides functions to normalize various date input types (str, date, datetime)
to a consistent string format (YYYY-MM-DD) used throughout DataHub.
"""

from datetime import date, datetime

# Type alias for date inputs accepted by DataHub APIs
DateInput = str | date | datetime | None


def normalize_date(value: DateInput) -> str | None:
    """
    Normalize various date input types to YYYY-MM-DD string format.

    Args:
        value: Date input (str, date, datetime, or None).

    Returns:
        Normalized date string in YYYY-MM-DD format, or None if input is None.

    Raises:
        ValueError: If string is not in valid YYYY-MM-DD format.

    """
    if value is None:
        return None

    if isinstance(value, str):
        # Validate string format by attempting to parse it
        try:
            datetime.strptime(value, "%Y-%m-%d")
            return value
        except ValueError as e:
            raise ValueError(f"Invalid date format: {value}") from e

    if isinstance(value, datetime):
        # Convert datetime to date, then format
        return value.strftime("%Y-%m-%d")

    if isinstance(value, date):
        # Format date object
        return value.strftime("%Y-%m-%d")

    raise TypeError(f"Unsupported date type: {type(value)}")
