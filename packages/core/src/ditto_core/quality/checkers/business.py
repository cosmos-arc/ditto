"""L2 Business checker."""

from typing import Any

import polars as pl
from loguru import logger

from ditto_core.quality.spec import DQIssue, DQLevel, DQSeverity


class BusinessChecker:
    """L2 business rule checker."""

    def check(
        self,
        df: pl.DataFrame,
        rules: list[dict[str, Any]],
        context: dict[str, Any] | None = None,
    ) -> list[DQIssue]:
        """
        Execute L2 business checks.

        Args:
            df: Data to check
            rules: List of L2 rule configurations
            context: Additional context

        Returns:
            List of DQIssue (WARNING severity)

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

        if rule_type == "positive":
            return self._check_positive(df, rule)
        elif rule_type == "expression":
            return self._check_expression(df, rule)
        elif rule_type == "range_check":
            return self._check_range(df, rule)
        elif rule_type == "no_zero_volume":
            return self._check_no_zero_volume(df, rule)

        return None

    def _check_positive(self, df: pl.DataFrame, rule: dict[str, Any]) -> DQIssue | None:
        """Check positive values."""
        columns = rule.get("columns", [])

        for col in columns:
            if col not in df.columns:
                continue
            invalid_count = df.filter(pl.col(col) <= 0).height
            if invalid_count > 0:
                logger.warning(
                    "dq_rule_positive",
                    event="dq_check",
                    rule="positive",
                    column=col,
                    invalid_count=invalid_count,
                )
                return DQIssue(
                    level=DQLevel.L2_BUSINESS,
                    severity=DQSeverity.WARNING,
                    rule_name="positive",
                    message=rule.get("message", f"{col} has non-positive values"),
                    affected_rows=invalid_count,
                )

        return None

    def _check_expression(
        self, df: pl.DataFrame, rule: dict[str, Any]
    ) -> DQIssue | None:
        """Check expression-based rule (e.g., OHLC consistency)."""
        name = rule.get("name", "expression")

        # OHLC consistency check
        if "ohlc" in name.lower():
            required_cols = ["open", "high", "low", "close"]
            if not all(col in df.columns for col in required_cols):
                return None

            # high >= max(open, close) and low <= min(open, close)
            bad_count = df.filter(
                (pl.col("high") < pl.col("open"))
                | (pl.col("high") < pl.col("close"))
                | (pl.col("low") > pl.col("open"))
                | (pl.col("low") > pl.col("close"))
            ).height

            if bad_count > 0:
                logger.warning(
                    "dq_rule_ohlc_consistency",
                    event="dq_check",
                    rule="ohlc_consistency",
                    bad_count=bad_count,
                )
                return DQIssue(
                    level=DQLevel.L2_BUSINESS,
                    severity=DQSeverity.WARNING,
                    rule_name="ohlc_consistency",
                    message=rule.get("message", "OHLC relationship violated"),
                    affected_rows=bad_count,
                )

        return None

    def _check_range(self, df: pl.DataFrame, rule: dict[str, Any]) -> DQIssue | None:
        """Check range constraint."""
        column = rule.get("column")
        if not column or column not in df.columns:
            return None

        min_val = rule.get("min")
        max_val = rule.get("max")

        conditions: list[pl.Expr] = []
        if min_val is not None:
            conditions.append(pl.col(column) < min_val)
        if max_val is not None:
            conditions.append(pl.col(column) > max_val)

        if not conditions:
            return None

        # Combine conditions with OR
        condition: pl.Expr = conditions[0]
        for cond in conditions[1:]:
            condition = condition | cond

        bad_count = df.filter(condition).height

        if bad_count > 0:
            logger.warning(
                "dq_rule_range",
                event="dq_check",
                rule="range_check",
                column=column,
                bad_count=bad_count,
            )
            return DQIssue(
                level=DQLevel.L2_BUSINESS,
                severity=DQSeverity.WARNING,
                rule_name="range_check",
                message=rule.get("message", f"{column} out of range"),
                affected_rows=bad_count,
            )

        return None

    def _check_no_zero_volume(
        self, df: pl.DataFrame, rule: dict[str, Any]
    ) -> DQIssue | None:
        """Check no zero volume."""
        column = rule.get("column", "volume")
        if column not in df.columns:
            return None

        zero_count = df.filter(pl.col(column) == 0).height

        if zero_count > 0:
            logger.warning(
                "dq_rule_no_zero_volume",
                event="dq_check",
                rule="no_zero_volume",
                column=column,
                zero_count=zero_count,
            )
            return DQIssue(
                level=DQLevel.L2_BUSINESS,
                severity=DQSeverity.WARNING,
                rule_name="no_zero_volume",
                message=rule.get("message", f"{column} has zero values"),
                affected_rows=zero_count,
            )

        return None
