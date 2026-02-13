"""Quality execution engine."""

from __future__ import annotations

from typing import Any, Literal

import polars as pl
from ditto_infra.foundation import DQSeverity

from ditto_core.quality.checkers.business import BusinessChecker
from ditto_core.quality.checkers.cross_source import CrossSourceChecker
from ditto_core.quality.checkers.statistical import StatisticalChecker
from ditto_core.quality.checkers.technical import TechnicalChecker
from ditto_core.quality.config import DQSettings
from ditto_core.quality.spec import DQIssue, DQResult, DQSpec


class QualityEngine:
    """
    Quality execution engine.

    Orchestrates data quality checks across technical/business/statistical categories.
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
        self.cross_source_checker = CrossSourceChecker()  # 新增

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

        # Run technical class checks (L1)
        if "l1" in levels and dataset_rules.technical:
            # ✅ 检查技术类开关
            if self._dq_settings and not self._dq_settings.l1_enabled:
                pass  # 跳过技术类检查
            else:
                l1_issues = self.technical_checker.check(
                    df=df,
                    rules=dataset_rules.technical,
                    context=context,
                )
                issues.extend(l1_issues)

        # Run business class checks (L2)
        if "l2" in levels and dataset_rules.business:
            # ✅ 检查业务类开关
            if self._dq_settings and not self._dq_settings.l2_enabled:
                pass  # 跳过业务类检查
            else:
                l2_issues = self.business_checker.check(
                    df=df,
                    rules=dataset_rules.business,
                    context=context,
                )
                issues.extend(l2_issues)

        # Determine if passed (technical class errors cause failure)
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
        Execute statistical class anomaly checks (batch).

        Args:
            dataset: Dataset identifier
            current: Current data to check
            historical: Historical data for statistical calculations (for zscore)
            calendar: Trading calendar (for completeness check)

        Returns:
            DQResult with statistical class check results

        """
        issues: list[DQIssue] = []

        # Get dataset rules
        dataset_rules = self.config.get_rules(dataset)
        if dataset_rules is None:
            return DQResult(dataset=dataset, passed=True, issues=[])

        # Run statistical class checks
        if dataset_rules.statistical:
            l3_issues = self.statistical_checker.check(
                current=current,
                historical=historical,
                calendar=calendar,
                rules=dataset_rules.statistical,
            )
            issues.extend(l3_issues)

        # Statistical class checks always pass (alerts only)
        return DQResult(
            dataset=dataset,
            passed=True,  # 统计类不阻塞
            issues=issues,
        )

    def check_cross_source(
        self,
        primary: pl.DataFrame,
        secondary: pl.DataFrame,
        dataset: str,
        context: dict[str, Any] | None = None,
    ) -> DQResult:
        """
        执行跨源对比检查（统计类）.

        Args:
            primary: 主数据源 DataFrame（如 Tushare）
            secondary: 辅助数据源 DataFrame（如 TDX）
            dataset: 数据集标识
            context: 额外上下文

        Returns:
            DQResult with cross-source comparison results

        """
        # 检查统计类开关
        if self._dq_settings and not self._dq_settings.l3_enabled:
            return DQResult(dataset=dataset, passed=True, issues=[])

        issues: list[DQIssue] = []

        # 获取数据集规则
        dataset_rules = self.config.get_rules(dataset)
        if dataset_rules is None:
            return DQResult(dataset=dataset, passed=True, issues=[])

        # 执行跨源对比检查（在统计类检查规则中）
        if dataset_rules.statistical:
            cross_source_issues = self.cross_source_checker.check(
                primary=primary,
                secondary=secondary,
                rules=dataset_rules.statistical,
                context=context,
            )
            issues.extend(cross_source_issues)

        # 统计类检查始终通过（仅告警）
        return DQResult(
            dataset=dataset,
            passed=True,  # 统计类不阻塞
            issues=issues,
        )
