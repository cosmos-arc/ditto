"""L3 Statistical checker."""

from typing import Any

import polars as pl
import polars.exceptions as pl_exceptions
from loguru import logger

from ditto_core.quality.spec import DQIssue, DQLevel, DQSeverity


class StatisticalChecker:
    """L3 statistical anomaly checker (pure functional)."""

    def check(
        self,
        current: pl.DataFrame,
        historical: pl.DataFrame | None = None,
        calendar: pl.DataFrame | None = None,
        rules: list[dict[str, Any]] | None = None,
    ) -> list[DQIssue]:
        """
        Execute L3 statistical checks.

        Args:
            current: Current data to check
            historical: Historical data for statistical calculations
                (optional, for zscore)
            calendar: Trading calendar (optional, for completeness check)
            rules: List of L3 rule configurations

        Returns:
            List of DQIssue (ALERT severity)

        """
        if not rules:
            return []

        issues: list[DQIssue] = []

        for rule in rules:
            issue = self._check_rule(current, historical, calendar, rule)
            if issue:
                issues.append(issue)

        return issues

    def _check_rule(
        self,
        current: pl.DataFrame,
        historical: pl.DataFrame | None,
        calendar: pl.DataFrame | None,
        rule: dict[str, Any],
    ) -> DQIssue | None:
        """
        Check a single rule.

        Args:
            current: Current data to check
            historical: Historical data for statistical calculations
            calendar: Trading calendar
            rule: Rule configuration

        Returns:
            DQIssue if rule violated, None otherwise

        """
        rule_type = rule.get("rule")

        if rule_type == "zscore":
            return self._check_zscore(current, historical, rule)
        elif rule_type == "completeness":
            return self._check_completeness(current, calendar, rule)

        return None

    def _check_zscore(
        self,
        current: pl.DataFrame,
        historical: pl.DataFrame | None,
        rule: dict[str, Any],
    ) -> DQIssue | None:
        """
        Check Z-score anomaly.

        Args:
            current: Current data to check (must contain columns to analyze)
            historical: Historical data for calculating statistics
                (must include same columns)
            rule: Rule config with column, window, threshold, group_by

        Returns:
            DQIssue if anomaly detected, None otherwise

        """
        column = rule.get("column")
        threshold = rule.get("threshold", 3.0)
        group_by = rule.get("group_by")

        if not column:
            return None

        if historical is None or historical.is_empty():
            logger.debug(
                "dq_zscore_no_historical",
                event="dq_check",
                column=column,
            )
            return None

        if current.is_empty() or column not in current.columns:
            return None

        try:
            # Prepare working data
            df = current.clone()

            # Calculate statistics by group or overall
            if group_by:
                stats = historical.group_by(group_by).agg(
                    pl.col(column).mean().alias("mean"),
                    pl.col(column).std().alias("std"),
                )
                # Join stats to current data
                df = df.join(stats, on=group_by, how="left")
            else:
                mean_val = historical[column].mean()
                std_val = historical[column].std()
                df = df.with_columns(
                    pl.lit(mean_val).alias("mean"),
                    pl.lit(std_val).alias("std"),
                )

            # Calculate Z-score
            df = df.with_columns(
                ((pl.col(column) - pl.col("mean")) / pl.col("std")).alias("zscore")
            )

            # Find anomalies
            anomalies = df.filter(
                pl.col("zscore").is_finite() & (pl.col("zscore").abs() > threshold)
            )

            if anomalies.height > 0:
                logger.warning(
                    "dq_rule_zscore_anomaly",
                    event="dq_check",
                    column=column,
                    anomaly_count=anomalies.height,
                    threshold=threshold,
                )
                msg = (
                    f"Found {anomalies.height} Z-score anomalies in "
                    f"'{column}' (threshold: {threshold})"
                )
                return DQIssue(
                    level=DQLevel.STATISTICAL,
                    severity=DQSeverity.ALERT,
                    rule_name="zscore",
                    message=msg,
                    affected_rows=anomalies.height,
                    sample_data=anomalies.select(["sid", column, "zscore"])
                    .head(10)
                    .to_dicts(),
                )

        except (
            pl_exceptions.ComputeError,
            pl_exceptions.SchemaError,
            pl_exceptions.ColumnNotFoundError,
        ) as e:
            # Polars 相关错误 - ALERT 级别
            logger.exception(
                "dq_zscore_computation_failed",
                error_type=type(e).__name__,
                column=column,
                rule_type="zscore",
            )
            exc_type = type(e).__name__
            return DQIssue(
                level=DQLevel.STATISTICAL,
                severity=DQSeverity.ALERT,
                rule_name="zscore",
                message=f"Z-score check failed for column '{column}': {exc_type}",
                affected_rows=0,
                sample_data=[],
            )
        except ValueError as e:
            # 数值错误（如除零）- WARNING 级别
            logger.warning(
                "dq_zscore_invalid_value",
                error=str(e),
                column=column,
                rule_type="zscore",
            )
            return DQIssue(
                level=DQLevel.STATISTICAL,
                severity=DQSeverity.WARNING,
                rule_name="zscore",
                message=f"Invalid statistical value for '{column}': {e}",
                affected_rows=0,
                sample_data=[],
            )

    def _check_completeness(
        self,
        current: pl.DataFrame,
        calendar: pl.DataFrame | None,
        rule: dict[str, Any],
    ) -> DQIssue | None:
        """
        Check data completeness.

        Args:
            current: Current data (must contain 'trade_date' column)
            calendar: Trading calendar (must contain 'trade_date' and 'is_open' columns)
            rule: Rule config with lookback_days

        Returns:
            DQIssue if missing data detected, None otherwise

        """
        if calendar is None or calendar.is_empty():
            logger.debug(
                "dq_completeness_no_calendar",
                event="dq_check",
            )
            return None

        if current.is_empty():
            msg = "No data found for completeness check"
            return DQIssue(
                level=DQLevel.STATISTICAL,
                severity=DQSeverity.ALERT,
                rule_name="completeness",
                message=msg,
                affected_rows=0,
            )

        try:
            # Get expected trading days (open days only)
            expected_dates = set(
                calendar.filter(pl.col("is_open"))["trade_date"].cast(str).to_list()
            )

            # Get actual data dates
            actual_dates = set(current["trade_date"].cast(str).unique().to_list())

            # Check for missing dates
            missing_dates = expected_dates - actual_dates

            if missing_dates:
                sorted_missing = sorted(missing_dates)
                logger.warning(
                    "dq_rule_completeness_gap",
                    event="dq_check",
                    missing_count=len(missing_dates),
                    missing_dates=sorted_missing,
                )
                msg = (
                    f"Missing data for {len(missing_dates)} trading days: "
                    f"{sorted_missing}"
                )
                return DQIssue(
                    level=DQLevel.STATISTICAL,
                    severity=DQSeverity.ALERT,
                    rule_name="completeness",
                    message=msg,
                    affected_rows=len(missing_dates),
                )

        except (
            pl_exceptions.ComputeError,
            pl_exceptions.SchemaError,
            pl_exceptions.ColumnNotFoundError,
        ) as e:
            # Polars 相关错误 - ALERT 级别
            logger.exception(
                "dq_completeness_check_failed",
                error_type=type(e).__name__,
                rule_type="completeness",
            )
            return DQIssue(
                level=DQLevel.STATISTICAL,
                severity=DQSeverity.ALERT,
                rule_name="completeness",
                message=f"Completeness check failed: {type(e).__name__}",
                affected_rows=0,
                sample_data=[],
            )
        except ValueError as e:
            # 数值错误 - WARNING 级别
            logger.warning(
                "dq_completeness_invalid_value",
                error=str(e),
                rule_type="completeness",
            )
            return DQIssue(
                level=DQLevel.STATISTICAL,
                severity=DQSeverity.WARNING,
                rule_name="completeness",
                message=f"Invalid value in completeness check: {e}",
                affected_rows=0,
                sample_data=[],
            )
