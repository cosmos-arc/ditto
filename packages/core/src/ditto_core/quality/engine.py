"""Quality execution engine."""

from __future__ import annotations

from typing import Any, Literal

import polars as pl
from ditto_foundation import DQSeverity

from ditto_core.quality.checkers.business import BusinessChecker
from ditto_core.quality.checkers.statistical import StatisticalChecker
from ditto_core.quality.checkers.technical import TechnicalChecker
from ditto_core.quality.config import DQSettings
from ditto_core.quality.spec import DQIssue, DQResult, DQSpec


class QualityEngine:
    """
    Quality execution engine.

    Orchestrates data quality checks across L1/L2/L3 levels.
    Core layer: Pure business logic, no data access dependencies.
    """

    def __init__(
        self,
        config: DQSpec,
        # ✅ 新增：接受 DQSettings 注入
        dq_settings: DQSettings | None = None,
    ) -> None:
        """
        Initialize Quality engine.

        Args:
            config: DQ 配置规范（由上层通过 DI 注入）
            dq_settings: DQ 配置（可选，用于检查开关状态）

        """
        self.config = config
        self._dq_settings = dq_settings

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
            context: Additional context (e.g., reference_values for foreign key checks)

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
            # ✅ 检查 L1 开关
            if self._dq_settings and not self._dq_settings.l1_enabled:
                pass  # 跳过 L1 检查
            else:
                l1_issues = self.technical_checker.check(
                    df=df,
                    rules=dataset_rules.l1_technical,
                    context=context,
                )
                issues.extend(l1_issues)

        # Run L2 business checks
        if "l2" in levels and dataset_rules.l2_business:
            # ✅ 检查 L2 开关
            if self._dq_settings and not self._dq_settings.l2_enabled:
                pass  # 跳过 L2 检查
            else:
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
        current: pl.DataFrame,
        historical: pl.DataFrame | None = None,
        calendar: pl.DataFrame | None = None,
    ) -> DQResult:
        """
        Execute L3 statistical anomaly checks (batch).

        Args:
            dataset: Dataset identifier
            current: Current data to check
            historical: Historical data for statistical calculations (for zscore)
            calendar: Trading calendar (for completeness check)

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
                current=current,
                historical=historical,
                calendar=calendar,
                rules=dataset_rules.l3_statistical,
            )
            issues.extend(l3_issues)

        # L3 checks always pass (alerts only)
        return DQResult(
            dataset=dataset,
            passed=True,  # L3 doesn't block
            issues=issues,
        )
