"""
DataFrame schema validation module.

Validates Polars DataFrames against predefined schemas for datasets.
"""

import polars as pl

from ditto_datahub.errors import ValidationError
from ditto_datahub.meta.schemas import (
    ADJ_FACTOR_SCHEMA,
    ETF_DAILY_SCHEMA,
    INDEX_DAILY_SCHEMA,
    INDEX_WEIGHT_SCHEMA,
    STOCK_DAILY_SCHEMA,
    UNIVERSE_CONSTITUENT_SCHEMA,
)

# Dataset schema mapping
DATASET_SCHEMAS: dict[str, dict[str, type[pl.DataType]]] = {
    "stock_daily": STOCK_DAILY_SCHEMA,
    "market_daily": STOCK_DAILY_SCHEMA,  # Alias for backwards compatibility
    "etf_daily": ETF_DAILY_SCHEMA,
    "index_daily": INDEX_DAILY_SCHEMA,
    "adj_factor": ADJ_FACTOR_SCHEMA,
    "index_weight": INDEX_WEIGHT_SCHEMA,
    "universe_constituent": UNIVERSE_CONSTITUENT_SCHEMA,
}


def validate_dataframe_schema(df: pl.DataFrame, dataset: str) -> None:
    """
    Validate DataFrame against schema definition.

    Args:
        df: DataFrame to validate.
        dataset: Dataset name (e.g., "stock_daily", "adj_factor").

    Raises:
        ValidationError: If DataFrame doesn't match schema.

    """
    # Skip validation for unknown datasets
    if dataset not in DATASET_SCHEMAS:
        return

    schema = DATASET_SCHEMAS[dataset]

    # Check required columns
    _validate_required_columns(df, schema)

    # Check column types
    _validate_column_types(df, schema, dataset)


def _validate_required_columns(
    df: pl.DataFrame, schema: dict[str, type[pl.DataType]]
) -> None:
    """
    Validate that all required columns are present.

    Args:
        df: DataFrame to validate.
        schema: Schema definition.

    Raises:
        ValidationError: If required columns are missing.

    """
    required_columns = set(schema.keys())
    actual_columns = set(df.columns)

    missing = required_columns - actual_columns
    if missing:
        raise ValidationError(
            f"Missing required columns: {sorted(missing)}",
            details={
                "missing_columns": sorted(missing),
                "expected": sorted(required_columns),
            },
        )


def _validate_column_types(
    df: pl.DataFrame, schema: dict[str, type[pl.DataType]], dataset: str
) -> None:
    """
    Validate that columns have correct data types.

    Args:
        df: DataFrame to validate.
        schema: Schema definition.
        dataset: Dataset name (for error messages).

    Raises:
        ValidationError: If columns have wrong types.

    """
    for col_name, expected_type_base in schema.items():
        if col_name not in df.columns:
            continue  # Already checked in _validate_required_columns

        actual_type = df[col_name].dtype

        # Normalize types for comparison
        # pl.Utf8 == pl.String (they're the same)
        normalized_expected = (
            pl.String if expected_type_base == pl.Utf8 else expected_type_base
        )

        # Check type compatibility (compare base types by name)
        if not _is_type_compatible(actual_type, normalized_expected):
            msg = (
                f"Column '{col_name}' has wrong type: "
                f"expected {normalized_expected}, got {actual_type}"
            )
            raise ValidationError(
                msg,
                details={
                    "column": col_name,
                    "expected_type": str(normalized_expected),
                    "actual_type": str(actual_type),
                    "dataset": dataset,
                },
            )


def _is_type_compatible(
    actual: pl.DataType, expected_type_base: type[pl.DataType]
) -> bool:
    """
    Check if actual Polars type is compatible with expected type.

    Args:
        actual: Actual data type.
        expected_type_base: Expected data type class.

    Returns:
        True if types are compatible.

    """
    # Direct match - compare base type names
    actual_base = type(actual)
    if actual_base == expected_type_base:
        return True

    # Null types are compatible with any type (nullable columns)
    if isinstance(actual, pl.Null):
        return True

    # Categorical can be compatible with String/Utf8
    return bool(
        isinstance(actual, pl.Categorical)
        and expected_type_base in (pl.String, pl.Utf8)
    )
