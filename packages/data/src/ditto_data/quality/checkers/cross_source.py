"""
跨源对比检查器 - L3 统计检查.

Core 层：纯业务逻辑，无数据访问依赖。
接收两个 DataFrame 进行对比，不关心数据从哪来。
"""

from typing import Any

import polars as pl
from loguru import logger

from ditto_data.quality.severity import DQSeverity
from ditto_data.quality.spec import (
    CompareMethod,
    DQIssue,
    DQLevel,
    ToleranceRule,
)


class CrossSourceChecker:
    """
    跨源对比检查器.

    Core 层：纯函数式，接收两个 DataFrame 进行对比。
    """

    def __init__(
        self,
        tolerance_rules: dict[str, ToleranceRule] | None = None,
    ) -> None:
        """
        初始化检查器.

        Args:
            tolerance_rules: 默认容差规则（字段 → 规则）

        """
        self.tolerance_rules = tolerance_rules or self._default_rules()

    def _default_rules(self) -> dict[str, ToleranceRule]:
        """默认容差规则（与配置文件保持一致）."""
        return {
            "open": ToleranceRule(method=CompareMethod.TICK_ALIGNED, tick_size=0.001),
            "high": ToleranceRule(method=CompareMethod.TICK_ALIGNED, tick_size=0.001),
            "low": ToleranceRule(method=CompareMethod.TICK_ALIGNED, tick_size=0.001),
            "close": ToleranceRule(method=CompareMethod.TICK_ALIGNED, tick_size=0.001),
            "volume": ToleranceRule(method=CompareMethod.RELATIVE, relative_tol=0.001),
            "amount": ToleranceRule(method=CompareMethod.RELATIVE, relative_tol=0.001),
        }

    def check(
        self,
        primary: pl.DataFrame,
        secondary: pl.DataFrame,
        rules: list[dict[str, Any]],
        context: dict[str, Any] | None = None,
    ) -> list[DQIssue]:
        """
        执行跨源对比检查.

        Args:
            primary: 主数据源 DataFrame（如 Tushare）
            secondary: 辅助数据源 DataFrame（如 TDX）
            rules: 跨源对比规则列表
            context: 额外上下文

        Returns:
            DQIssue 列表

        """
        issues: list[DQIssue] = []

        for rule in rules:
            if rule.get("rule") != "cross_source_compare":
                continue
            if not rule.get("enabled", True):
                continue

            issue = self._check_cross_source(primary, secondary, rule, context)
            if issue:
                issues.append(issue)

        return issues

    def _check_cross_source(
        self,
        primary: pl.DataFrame,
        secondary: pl.DataFrame,
        rule: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> DQIssue | None:
        """
        检查单个跨源对比规则.

        Args:
            primary: 主数据源
            secondary: 辅助数据源
            rule: 规则配置
            context: 额外上下文

        Returns:
            DQIssue if rule violated, None otherwise

        """
        key_columns = rule.get("key_columns", ["ticker", "trade_date"])
        fields = rule.get("fields", [])
        custom_tolerance = rule.get("tolerance_rules", {})

        # 合并容差规则（自定义覆盖默认）
        tolerance = self.tolerance_rules.copy()
        for field, rule_config in custom_tolerance.items():
            tolerance[field] = ToleranceRule(
                method=CompareMethod(rule_config.get("method", "relative")),
                tick_size=rule_config.get("tick_size"),
                relative_tol=rule_config.get("relative_tol"),
                absolute_tol=rule_config.get("absolute_tol"),
            )

        # 使用 key_columns 进行 join
        merged = primary.join(
            secondary, on=key_columns, how="inner", suffix="_secondary"
        )

        if merged.height == 0:
            logger.debug(
                "cross_source_no_overlap",
                event="dq_check",
                rule="cross_source_compare",
                reason="No overlapping records found",
            )
            return None

        # 检查每个字段
        diff_samples: list[dict[str, Any]] = []
        # 使用 key_columns 的第一列作为标识符（通常是 ticker 或 instrument_id）
        identifier_column = key_columns[0]
        for field in fields:
            if field not in primary.columns or field not in secondary.columns:
                continue

            field_diff = self._check_field(
                merged, field, tolerance.get(field), identifier_column
            )
            if field_diff is not None:
                diff_samples.extend(field_diff)

        if diff_samples:
            logger.warning(
                "cross_source_difference_found",
                event="dq_check",
                rule="cross_source_compare",
                diff_count=len(diff_samples),
            )
            return DQIssue(
                level=DQLevel.STATISTICAL,
                severity=DQSeverity.ALERT,
                rule_name="cross_source_compare",
                message=rule.get(
                    "message", "Cross-source comparison found differences"
                ),
                affected_rows=len(diff_samples),
                sample_data=diff_samples[:10],  # 最多 10 个样本
            )

        return None

    def _check_field(
        self,
        merged: pl.DataFrame,
        field: str,
        tolerance: ToleranceRule | None,
        identifier_column: str,
    ) -> list[dict[str, Any]] | None:
        """
        检查单个字段的差异.

        Args:
            merged: 合并后的 DataFrame
            field: 字段名
            tolerance: 容差规则
            identifier_column: 标识符列名（ticker 或 instrument_id）

        Returns:
            差异样本列表，无差异返回 None

        """
        if tolerance is None:
            return None

        primary_col = pl.col(field)
        secondary_col = pl.col(f"{field}_secondary")

        if tolerance.method == CompareMethod.TICK_ALIGNED:
            # Tick 对齐：差异应 <= tick_size
            diff = (primary_col - secondary_col).abs()
            diff_rows = merged.filter(diff > tolerance.tick_size)
        elif tolerance.method == CompareMethod.RELATIVE:
            # 相对容差：|primary - secondary| / secondary <= tolerance
            if tolerance.relative_tol is None:
                return None
            ratio = (primary_col - secondary_col).abs() / secondary_col
            diff_rows = merged.filter(ratio > tolerance.relative_tol)
        elif tolerance.method == CompareMethod.ABSOLUTE:
            # 绝对容差：|primary - secondary| <= tolerance
            if tolerance.absolute_tol is None:
                return None
            diff = (primary_col - secondary_col).abs()
            diff_rows = merged.filter(diff > tolerance.absolute_tol)
        else:
            return None

        if diff_rows.height > 0:
            # 返回完整的差异样本，包含上下文信息
            return (
                diff_rows.select(
                    [
                        identifier_column,
                        "trade_date",
                        pl.col(field).alias("primary_value"),
                        pl.col(f"{field}_secondary").alias("secondary_value"),
                        (pl.col(field) - pl.col(f"{field}_secondary"))
                        .abs()
                        .alias("diff"),
                        pl.lit(field).alias("field"),
                    ]
                )
                .head(10)
                .to_dicts()
            )

        return None
