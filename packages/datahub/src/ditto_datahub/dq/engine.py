"""DQ execution engine."""

from pathlib import Path
from typing import Any, Literal

import polars as pl

from ditto_datahub.dq.checkers.business import BusinessChecker
from ditto_datahub.dq.checkers.statistical import StatisticalChecker
from ditto_datahub.dq.checkers.technical import TechnicalChecker
from ditto_datahub.dq.models import DQConfig, DQIssue, DQLevel, DQResult, DQSeverity


class DQEngine:
    """
    DQ execution engine.

    Orchestrates data quality checks across L1/L2/L3 levels.
    """

    def __init__(
        self,
        config: DQConfig | None = None,
        config_path: str | Path | None = None,
    ) -> None:
        """
        Initialize DQ engine.

        Args:
            config: Pre-loaded DQ configuration
            config_path: Path to YAML configuration directory

        """
        if config is not None:
            self.config = config
        elif config_path is not None:
            self.config = DQConfig.from_yaml_dir(config_path)
        else:
            self.config = DQConfig()

        # Initialize checkers
        self.technical_checker = TechnicalChecker()
        self.business_checker = BusinessChecker()
        self.statistical_checker = StatisticalChecker()

    def check(
        self,
        df: pl.DataFrame,
        dataset: str,
        levels: list[Literal["l1", "l2"]] | None = None,
        context: dict[str, Any] | None = None,
    ) -> DQResult:
        """
        Execute DQ checks (write-time).

        Args:
            df: Data to check
            dataset: Dataset identifier
            levels: Check levels to run (default: ["l1", "l2"])
            context: Additional context (e.g., hub for foreign key checks)

        Returns:
            DQResult with check results

        """
        if levels is None:
            levels = ["l1", "l2"]

        issues: list[DQIssue] = []

        # Get dataset rules
        dataset_rules = self.config.get_rules(dataset)
        if dataset_rules is None:
            # No rules configured, return passing result
            return DQResult(dataset=dataset, passed=True, issues=[])

        # Run L1 technical checks
        if "l1" in levels and dataset_rules.l1_technical:
            l1_issues = self.technical_checker.check(
                df=df,
                rules=dataset_rules.l1_technical,
                context=context,
            )
            issues.extend(l1_issues)

        # Run L2 business checks
        if "l2" in levels and dataset_rules.l2_business:
            l2_issues = self.business_checker.check(
                df=df,
                rules=dataset_rules.l2_business,
                context=context,
            )
            issues.extend(l2_issues)

        # Determine if passed (L1 errors cause failure)
        has_errors = any(i.severity == DQSeverity.ERROR for i in issues)
        passed = not has_errors

        return DQResult(
            dataset=dataset,
            passed=passed,
            issues=issues,
        )

    def check_statistical(
        self,
        dataset: str,
        trade_date: str,
        hub: Any,  # DataHub instance
        market_wide: bool = False,
    ) -> DQResult:
        """
        Execute L3 statistical anomaly checks (batch).

        Args:
            dataset: Dataset identifier
            trade_date: Trade date to check (YYYY-MM-DD)
            hub: DataHub instance for historical data access
            market_wide: Whether to use market-wide query mode

        Returns:
            DQResult with L3 check results

        """
        issues: list[DQIssue] = []

        # Get dataset rules
        dataset_rules = self.config.get_rules(dataset)
        if dataset_rules is None:
            return DQResult(dataset=dataset, passed=True, issues=[])

        # Run L3 statistical checks
        if dataset_rules.l3_statistical:
            l3_issues = self.statistical_checker.check(
                dataset=dataset,
                trade_date=trade_date,
                rules=dataset_rules.l3_statistical,
                hub=hub,
                market_wide=market_wide,
            )
            issues.extend(l3_issues)

        # L3 checks always pass (alerts only)
        return DQResult(
            dataset=dataset,
            passed=True,  # L3 doesn't block
            issues=issues,
        )
