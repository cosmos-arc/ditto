"""
DQ 违规数据过滤函数。

根据不同 DQ 规则类型过滤失败的数据行。
"""

from itertools import combinations

import polars as pl

from ditto_datahub.models import DQIssue


def filter_not_null_violations(df: pl.DataFrame, issue: DQIssue) -> pl.DataFrame:
    """
    Filter rows with null values for not_null rule.

    Args:
        df: Input DataFrame.
        issue: DQ issue with rule information.

    Returns:
        Filtered DataFrame with rows containing null values.

    """
    # Extract column name from message (format: "{col} has null values")
    message = issue.message.lower()
    for col in df.columns:
        if col.lower() in message and "has null values" in message:
            return df.filter(pl.col(col).is_null())
    # Fallback: check all columns for null values
    null_cols = [pl.col(c).is_null() for c in df.columns]
    if null_cols:
        return df.filter(pl.any_horizontal(null_cols))
    return df


def filter_unique_violations(df: pl.DataFrame, issue: DQIssue) -> pl.DataFrame:
    """
    Filter duplicate rows for unique rule.

    Args:
        df: Input DataFrame.
        issue: DQ issue with rule information.

    Returns:
        Filtered DataFrame with duplicate rows.

    """
    # For unique constraint, find duplicate rows
    # Check all column combinations to find duplicates
    for col_count in range(1, len(df.columns) + 1):
        for cols in combinations(df.columns, col_count):
            duplicates = (
                df.group_by(cols)
                .agg(pl.len().alias("_count"))
                .filter(pl.col("_count") > 1)
            )
            if not duplicates.is_empty():
                # Join back to get original rows
                return df.join(duplicates.select(cols), on=cols, how="inner")
    return df  # Fallback: return all rows


def filter_foreign_key_violations(df: pl.DataFrame, issue: DQIssue) -> pl.DataFrame:
    """
    Filter rows with foreign key violations.

    Args:
        df: Input DataFrame.
        issue: DQ issue with rule information.

    Returns:
        All rows for manual review (cannot filter without reference data).

    """
    # Cannot filter without reference data
    # Return all rows for manual review
    return df


def filter_type_check_violations(df: pl.DataFrame, issue: DQIssue) -> pl.DataFrame:
    """
    Filter rows with type check violations.

    Args:
        df: Input DataFrame.
        issue: DQ issue with rule information.

    Returns:
        All rows for manual review (cannot filter without type info).

    """
    # Cannot filter without type info
    # Return all rows for manual review
    return df


def filter_failed_rows(df: pl.DataFrame, issue: DQIssue) -> pl.DataFrame:
    """
    Filter failed rows based on DQ issue.

    Args:
        df: Input DataFrame.
        issue: DQ issue with rule information.

    Returns:
        Filtered DataFrame with failed rows.

    """
    # Map rule names to their filter functions
    rule_filters = {
        "not_null": filter_not_null_violations,
        "unique": filter_unique_violations,
        "foreign_key": filter_foreign_key_violations,
        "type_check": filter_type_check_violations,
    }

    rule_name = issue.rule_name.lower()
    filter_func = rule_filters.get(rule_name)

    if filter_func is not None:
        return filter_func(df, issue)

    # Default: return all rows for manual review
    return df
