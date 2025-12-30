"""L3 Statistical checker."""

from datetime import datetime, timedelta
from typing import Any

import polars as pl
from ditto_foundation import logger

from ditto_datahub.dq.models import DQIssue, DQLevel, DQSeverity


class StatisticalChecker:
    """L3 statistical anomaly checker."""

    def check(
        self,
        dataset: str,
        trade_date: str,
        rules: list[dict[str, Any]],
        hub: Any,  # DataHub instance
    ) -> list[DQIssue]:
        """
        Execute L3 statistical checks.

        Args:
            dataset: Dataset identifier
            trade_date: Trade date to check
            rules: List of L3 rule configurations
            hub: DataHub instance for historical data access

        Returns:
            List of DQIssue (ALERT severity)

        """
        issues: list[DQIssue] = []

        for rule in rules:
            issue = self._check_rule(dataset, trade_date, rule, hub)
            if issue:
                issues.append(issue)

        return issues

    def _check_rule(
        self,
        dataset: str,
        trade_date: str,
        rule: dict[str, Any],
        hub: Any,
    ) -> DQIssue | None:
        """
        Check a single rule.

        Args:
            dataset: Dataset identifier
            trade_date: Trade date to check
            rule: Rule configuration
            hub: DataHub instance

        Returns:
            DQIssue if rule violated, None otherwise

        """
        rule_type = rule.get("rule")

        if rule_type == "zscore":
            return self._check_zscore(dataset, trade_date, rule, hub)
        elif rule_type == "completeness":
            return self._check_completeness(dataset, trade_date, rule, hub)

        return None

    def _check_zscore(
        self,
        dataset: str,
        trade_date: str,
        rule: dict[str, Any],
        hub: Any,
    ) -> DQIssue | None:
        """
        Check Z-score anomaly.

        Args:
            dataset: Dataset identifier
            trade_date: Trade date to check (YYYY-MM-DD)
            rule: Rule config with column, window, threshold, group_by
            hub: DataHub instance for historical data access

        Returns:
            DQIssue if anomaly detected, None otherwise

        """
        column = rule.get("column")
        window = rule.get("window", 60)
        threshold = rule.get("threshold", 3.0)
        group_by = rule.get("group_by")

        if not column:
            return None

        try:
            # Calculate start date for historical data
            trade_dt = datetime.fromisoformat(trade_date)
            start_dt = trade_dt - timedelta(
                days=window * 2
            )  # Get extra days for weekends
            start_date = start_dt.strftime("%Y-%m-%d")

            # Query historical data
            historical = hub.bars.get(
                start=start_date,
                end=trade_date,
            )

            if historical.is_empty() or column not in historical.columns:
                logger.debug(
                    "dq_zscore_no_historical",
                    event="dq_check",
                    dataset=dataset,
                    column=column,
                )
                return None

            # Get current data to check
            current = hub.bars.get(
                start=trade_date,
                end=trade_date,
            )

            if current.is_empty():
                return None

            # Calculate statistics by group or overall
            if group_by:
                stats = historical.group_by(group_by).agg(
                    pl.col(column).mean().alias("mean"),
                    pl.col(column).std().alias("std"),
                )
                # Join stats to current data
                current = current.join(stats, on=group_by, how="left")
            else:
                mean_val = historical[column].mean()
                std_val = historical[column].std()
                current = current.with_columns(
                    pl.lit(mean_val).alias("mean"),
                    pl.lit(std_val).alias("std"),
                )

            # Calculate Z-score
            current = current.with_columns(
                ((pl.col(column) - pl.col("mean")) / pl.col("std")).alias("zscore")
            )

            # Find anomalies
            anomalies = current.filter(
                pl.col("zscore").is_finite() & (pl.col("zscore").abs() > threshold)
            )

            if anomalies.height > 0:
                logger.warning(
                    "dq_rule_zscore_anomaly",
                    event="dq_check",
                    dataset=dataset,
                    column=column,
                    anomaly_count=anomalies.height,
                    threshold=threshold,
                )
                msg = (
                    f"Found {anomalies.height} Z-score anomalies in "
                    f"'{column}' (threshold: {threshold})"
                )
                return DQIssue(
                    level=DQLevel.L3_STATISTICAL,
                    severity=DQSeverity.ALERT,
                    rule_name="zscore",
                    message=msg,
                    affected_rows=anomalies.height,
                    sample_data=anomalies.select(["sid", column, "zscore"])
                    .head(10)
                    .to_dicts(),
                )

        except Exception as e:
            logger.error(
                "dq_zscore_error",
                event="dq_check",
                error=str(e),
            )
            return None

        return None

    def _check_completeness(
        self,
        dataset: str,
        trade_date: str,
        rule: dict[str, Any],
        hub: Any,
    ) -> DQIssue | None:
        """
        Check data completeness.

        Args:
            dataset: Dataset identifier
            trade_date: Trade date to check
            rule: Rule config with lookback_days, expected_dates
            hub: DataHub instance

        Returns:
            DQIssue if missing data detected, None otherwise

        """
        # TODO: Implement completeness check
        # 1. Query trade calendar for expected dates
        # 2. Check if all expected dates have data
        # 3. Report missing dates
        return None
