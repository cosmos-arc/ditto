"""L1 Technical checker."""

from typing import Any

import polars as pl
from loguru import logger

from ditto_core.quality.spec import DQIssue, DQLevel, DQSeverity


class TechnicalChecker:
    """L1 technical validation checker."""

    def check(
        self,
        df: pl.DataFrame,
        rules: list[dict[str, Any]],
        context: dict[str, Any] | None = None,
    ) -> list[DQIssue]:
        """
        Execute L1 technical checks.

        Args:
            df: Data to check
            rules: List of L1 rule configurations
            context: Additional context (e.g., reference_values for FK checks)

        Returns:
            List of DQIssue (ERROR severity)

        """
        issues: list[DQIssue] = []

        for rule in rules:
            issue = self._check_rule(df, rule, context)
            if issue:
                issues.append(issue)

        return issues

    def _check_rule(
        self,
        df: pl.DataFrame,
        rule: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> DQIssue | None:
        """
        Check a single rule.

        Args:
            df: Data to check
            rule: Rule configuration
            context: Additional context

        Returns:
            DQIssue if rule violated, None otherwise

        """
        rule_type = rule.get("rule")

        if rule_type == "not_null":
            return self._check_not_null(df, rule)
        elif rule_type == "unique":
            return self._check_unique(df, rule)
        elif rule_type == "foreign_key":
            return self._check_foreign_key(df, rule, context)
        elif rule_type == "type_check":
            return self._check_type(df, rule)

        return None

    def _check_not_null(self, df: pl.DataFrame, rule: dict[str, Any]) -> DQIssue | None:
        """Check not null constraint."""
        columns = rule.get("columns", [])

        for col in columns:
            if col not in df.columns:
                continue
            null_count = df.filter(pl.col(col).is_null()).height
            if null_count > 0:
                logger.warning(
                    "dq_rule_not_null",
                    event="dq_check",
                    rule="not_null",
                    column=col,
                    null_count=null_count,
                )
                return DQIssue(
                    level=DQLevel.L1_TECHNICAL,
                    severity=DQSeverity.ERROR,
                    rule_name="not_null",
                    message=rule.get("message", f"{col} has null values"),
                    affected_rows=null_count,
                )

        return None

    def _check_unique(self, df: pl.DataFrame, rule: dict[str, Any]) -> DQIssue | None:
        """Check uniqueness constraint."""
        columns = rule.get("columns", [])

        # Check if all columns exist
        missing_cols = [c for c in columns if c not in df.columns]
        if missing_cols:
            return None

        # Check duplicates
        total_rows = df.height
        unique_rows = df.select(columns).n_unique()
        duplicate_count = total_rows - unique_rows

        if duplicate_count > 0:
            logger.warning(
                "dq_rule_unique",
                event="dq_check",
                rule="unique",
                columns=columns,
                duplicate_count=duplicate_count,
            )
            return DQIssue(
                level=DQLevel.L1_TECHNICAL,
                severity=DQSeverity.ERROR,
                rule_name="unique",
                message=rule.get("message", f"Duplicate key: {columns}"),
                affected_rows=duplicate_count,
            )

        return None

    def _check_foreign_key(
        self,
        df: pl.DataFrame,
        rule: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> DQIssue | None:
        """
        Check foreign key constraint.

        Args:
            df: Data to check
            rule: Rule config with "column" and "reference"
                (format: "dataset.column")
            context: Optional context containing "reference_values"
                (set of valid values) provided by Application Layer

        Returns:
            DQIssue if FK violation, None otherwise

        """
        column = rule.get("column")
        reference = rule.get("reference")

        # Validate rule configuration
        if not column or not reference:
            return None

        # Need reference_values from context (provided by Application Layer)
        if not context or "reference_values" not in context:
            logger.debug(
                "dq_fk_skip_no_context",
                event="dq_check",
                rule="foreign_key",
                column=column,
            )
            return None

        reference_values: set[Any] = context["reference_values"]
        issue: DQIssue | None = None

        if column not in df.columns:
            pass  # Column doesn't exist, skip check
        else:
            # Perform FK validation
            invalid_rows = df.filter(
                ~pl.col(column).is_null() & ~pl.col(column).is_in(reference_values)
            )

            if invalid_rows.height > 0:
                logger.warning(
                    "dq_rule_fk_violation",
                    event="dq_check",
                    rule="foreign_key",
                    column=column,
                    reference=reference,
                    invalid_count=invalid_rows.height,
                )
                msg = (
                    f"Column '{column}' has {invalid_rows.height} "
                    f"invalid references to {reference}"
                )
                issue = DQIssue(
                    level=DQLevel.L1_TECHNICAL,
                    severity=DQSeverity.ERROR,
                    rule_name="foreign_key",
                    message=msg,
                    affected_rows=invalid_rows.height,
                    sample_data=invalid_rows.select(column).head(5).to_dicts(),
                )

        return issue

    def _check_type(
        self,
        df: pl.DataFrame,
        rule: dict[str, Any],
    ) -> DQIssue | None:
        """
        Check data types.

        Args:
            df: Data to check
            rule: Rule config with "types" dict mapping column -> expected dtype

        Returns:
            DQIssue if type mismatch, None otherwise

        """
        expected_types = rule.get("types", {})

        for col, expected_type in expected_types.items():
            if col not in df.columns:
                continue

            actual_dtype = str(df[col].dtype)
            # Polars dtypes like "Int64", "Float64", "String"
            if not actual_dtype.startswith(expected_type):
                logger.warning(
                    "dq_rule_type_mismatch",
                    event="dq_check",
                    rule="type_check",
                    column=col,
                    expected=expected_type,
                    actual=actual_dtype,
                )
                msg = (
                    f"Column '{col}' has type {actual_dtype}, expected {expected_type}"
                )
                return DQIssue(
                    level=DQLevel.L1_TECHNICAL,
                    severity=DQSeverity.ERROR,
                    rule_name="type_check",
                    message=msg,
                    affected_rows=df.height,
                )

        return None
