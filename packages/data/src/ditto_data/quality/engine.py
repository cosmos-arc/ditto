"""Quality execution engine."""

from __future__ import annotations

from typing import Any, Literal

import polars as pl

from ditto_data.quality.checkers.business import BusinessChecker
from ditto_data.quality.checkers.cross_source import (
    CrossSourceChecker,
    CrossSourceComparison,
)
from ditto_data.quality.checkers.statistical import StatisticalChecker
from ditto_data.quality.checkers.technical import TechnicalChecker
from ditto_data.quality.config import DQSettings
from ditto_data.quality.quality_types import DQIssue, DQResult, DQSeverity
from ditto_data.quality.spec import CompareMethod, DQSpec, ToleranceRule


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
        reference: pl.DataFrame | None = None,
    ) -> DQResult:
        """
        Execute statistical class anomaly checks (batch).

        Args:
            dataset: Dataset identifier
            current: Current data to check
            historical: Historical data for statistical calculations (for zscore)
            calendar: Trading calendar (for completeness check)
            reference: Companion-dataset frame for cross-dataset consistency
                rules (e.g. stock_status for suspension_contradiction)

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
                reference=reference,
            )
            issues.extend(l3_issues)

        # Statistical class checks always pass (alerts only)
        return DQResult(
            dataset=dataset,
            passed=True,  # 统计类不阻塞
            issues=issues,
        )

    def has_statistical_rules(self, dataset: str) -> bool:
        """Return whether ``dataset`` has configured statistical rules."""
        dataset_rules = self.config.get_rules(dataset)
        return bool(dataset_rules is not None and dataset_rules.statistical)

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
            secondary: 辅助数据源 DataFrame（如 fuyao）
            dataset: 数据集标识
            context: 额外上下文（可含 ex_dividend_instruments）

        Returns:
            DQResult with cross-source comparison results

        """
        if self._dq_settings and not self._dq_settings.l3_enabled:
            return DQResult(dataset=dataset, passed=True, issues=[])

        issues = self.cross_source_checker.check(
            primary=primary,
            secondary=secondary,
            rules=self._cross_source_rules(dataset),
            context=context,
        )
        # 统计类检查始终通过（仅告警）——零交集/重复键是显式 WARNING
        return DQResult(dataset=dataset, passed=True, issues=issues)

    def compare_cross_source(
        self,
        primary: pl.DataFrame,
        secondary: pl.DataFrame,
        dataset: str,
        context: dict[str, Any] | None = None,
    ) -> CrossSourceComparison:
        """
        执行跨源对比并返回结构化报告（#395）。

        报告两侧数量/匹配数/主辅侧未匹配/重复键/差异数；
        零交集返回 ``not_comparable``（不可比较，不算通过）。
        """
        rules = self._cross_source_rules(dataset)
        if not rules:
            return CrossSourceComparison(
                status="not_comparable",
                key_columns=("instrument_id", "trade_date"),
                primary_count=primary.height,
                secondary_count=secondary.height,
                matched_count=0,
                primary_unmatched_count=0,
                secondary_unmatched_count=0,
                primary_duplicate_keys=0,
                secondary_duplicate_keys=0,
                diff_count=0,
            )
        rule = rules[0]
        ex_dividend = frozenset((context or {}).get("ex_dividend_instruments") or ())
        return self.cross_source_checker.compare(
            primary,
            secondary,
            key_columns=rule.get("key_columns", ["instrument_id", "trade_date"]),
            fields=rule.get("fields", []),
            tolerance_rules=self._cross_source_tolerances(rule),
            ex_dividend_instruments=ex_dividend,
        )

    def _cross_source_rules(self, dataset: str) -> list[dict[str, Any]]:
        """返回数据集配置中启用的 cross_source 规则。"""
        dataset_rules = self.config.get_rules(dataset)
        if dataset_rules is None:
            return []
        return [
            rule
            for rule in dataset_rules.statistical
            if rule.get("rule") == "cross_source_compare" and rule.get("enabled", True)
        ]

    @staticmethod
    def _cross_source_tolerances(
        rule: dict[str, Any],
    ) -> dict[str, ToleranceRule]:
        """规则内的自定义容差（字段 → ToleranceRule）。"""
        tolerances: dict[str, ToleranceRule] = {}
        for field_name, config in rule.get("tolerance_rules", {}).items():
            tolerances[field_name] = ToleranceRule(
                method=CompareMethod(config.get("method", "relative")),
                tick_size=config.get("tick_size"),
                relative_tol=config.get("relative_tol"),
                absolute_tol=config.get("absolute_tol"),
            )
        return tolerances
