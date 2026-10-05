"""
跨源对比检查器 - L3 统计检查.

Engine 层：纯业务逻辑，无数据访问依赖。
接收两个 DataFrame 进行对比，不关心数据从哪来。

#395 对账语义：
- 比较键为 instrument_id + trade_date（辅源帧经来源映射反解为 instrument_id）；
- 零交集 = 不可比较（显式状态 ``not_comparable``，不算通过）；
- 结果报告两侧数量/匹配数/主侧未匹配/辅侧未匹配/重复键/差异数，
  inner join 升级为 outer/anti 分析；
- 除权日（adj_factor 事件日）差异单列标记（``ex_dividend_day``）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

import polars as pl
from ditto_platform.foundation import logger

from ditto_data.quality.quality_types import DQIssue, DQLevel, DQSeverity
from ditto_data.quality.spec import (
    CompareMethod,
    ToleranceRule,
)

type ComparisonStatus = Literal["compared", "not_comparable"]


@dataclass(frozen=True)
class CrossSourceComparison:
    """一次跨源对比的完整报告（两侧数量、匹配、未匹配、重复键、差异）。"""

    status: ComparisonStatus
    key_columns: tuple[str, ...]
    primary_count: int
    secondary_count: int
    matched_count: int
    primary_unmatched_count: int
    secondary_unmatched_count: int
    primary_duplicate_keys: int
    secondary_duplicate_keys: int
    diff_count: int
    diff_rows: list[dict[str, Any]] = field(default_factory=list)
    field_matched_counts: dict[str, int] = field(default_factory=dict)

    @property
    def comparable(self) -> bool:
        """零交集 = 不可比较；非零交集才算有效比较。"""
        return self.status == "compared" and self.matched_count > 0


class CrossSourceChecker:
    """
    跨源对比检查器.

    Engine 层：纯函数式，接收两个 DataFrame 进行对比。
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

    # ------------------------------------------------------------------
    # 结构化对比：报告两侧数量/匹配/未匹配/重复键/差异
    # ------------------------------------------------------------------

    def compare(
        self,
        primary: pl.DataFrame,
        secondary: pl.DataFrame,
        *,
        key_columns: list[str] | tuple[str, ...] = ("instrument_id", "trade_date"),
        fields: list[str] | tuple[str, ...] = (),
        tolerance_rules: dict[str, ToleranceRule] | None = None,
        ex_dividend_instruments: frozenset[int] | None = None,
    ) -> CrossSourceComparison:
        """
        执行 outer/anti 结构分析并按容差比对字段。

        Args:
            primary: 主数据源帧（含 key_columns 与比对字段）.
            secondary: 辅助数据源帧（同上，经来源映射反解为 instrument_id）.
            key_columns: 比较键（默认 instrument_id + trade_date）.
            fields: 比对字段列表.
            tolerance_rules: 字段 → 容差规则（缺省用 checker 默认）.
            ex_dividend_instruments: 除权日（adj_factor 事件日）标的集合，
                命中的差异行单列标记 ex_dividend_day.

        Returns:
            CrossSourceComparison 结构化报告.

        """
        keys = list(key_columns)
        tolerance = dict(self.tolerance_rules)
        if tolerance_rules:
            tolerance.update(tolerance_rules)

        primary_keys = self._distinct_keys(primary, keys)
        secondary_keys = self._distinct_keys(secondary, keys)
        matched_keys = primary_keys & secondary_keys
        primary_unmatched = primary_keys - secondary_keys
        secondary_unmatched = secondary_keys - primary_keys

        common_fields = [
            name
            for name in fields
            if name in primary.columns
            and name in secondary.columns
            and name in tolerance
        ]
        merged = pl.DataFrame()
        if matched_keys and common_fields:
            # Keep conflicting values visible; collapse only identical comparison rows.
            columns = [*keys, *common_fields]
            merged = (
                primary.select(columns)
                .unique()
                .sort(columns)
                .join(
                    secondary.select(columns).unique().sort(columns),
                    on=keys,
                    how="inner",
                    suffix="_secondary",
                )
            )
        compared_keys: set[tuple[Any, ...]] = set()
        field_matched_counts = dict.fromkeys(fields, 0)
        for name in common_fields:
            if merged.is_empty():
                continue
            valid = merged.filter(
                pl.col(name).cast(pl.Float64, strict=False).is_finite()
                & pl.col(f"{name}_secondary").cast(pl.Float64, strict=False).is_finite()
            )
            valid_keys = self._distinct_keys(valid, keys)
            compared_keys.update(valid_keys)
            field_matched_counts[name] = len(valid_keys)
        status: ComparisonStatus = "compared" if compared_keys else "not_comparable"
        diff_rows = (
            self._field_diffs(
                merged,
                keys,
                common_fields,
                tolerance,
                ex_dividend_instruments or frozenset(),
            )
            if compared_keys
            else []
        )

        return CrossSourceComparison(
            status=status,
            key_columns=tuple(keys),
            primary_count=primary.height,
            secondary_count=secondary.height,
            matched_count=len(compared_keys),
            primary_unmatched_count=len(primary_unmatched),
            secondary_unmatched_count=len(secondary_unmatched),
            primary_duplicate_keys=self._duplicate_key_count(primary, keys),
            secondary_duplicate_keys=self._duplicate_key_count(secondary, keys),
            diff_count=len(diff_rows),
            diff_rows=diff_rows,
            field_matched_counts=field_matched_counts,
        )

    @staticmethod
    def _distinct_keys(frame: pl.DataFrame, keys: list[str]) -> set[tuple[Any, ...]]:
        """帧的键集合（空帧/缺键列 → 空集）。"""
        missing = [key for key in keys if key not in frame.columns]
        if missing or frame.is_empty():
            return set()
        # select 仅键列后转元组
        return {
            tuple(row) for row in frame.select(keys).drop_nulls().unique().iter_rows()
        }

    @staticmethod
    def _duplicate_key_count(frame: pl.DataFrame, keys: list[str]) -> int:
        """重复键数量（同键多行的键个数）。"""
        missing = [key for key in keys if key not in frame.columns]
        if missing or frame.is_empty():
            return 0
        return frame.group_by(keys).len().filter(pl.col("len") > 1).height

    def _field_diffs(
        self,
        merged: pl.DataFrame,
        keys: list[str],
        comparable_fields: list[str],
        tolerance: dict[str, ToleranceRule],
        ex_dividend_instruments: frozenset[int],
    ) -> list[dict[str, Any]]:
        """Compare all distinct values; input row order cannot settle conflicts."""
        diff_rows: list[dict[str, Any]] = []
        for field_name in comparable_fields:
            rule = tolerance.get(field_name)
            if rule is None:
                continue
            violating = self._violating_rows(merged, field_name, rule)
            if violating.height == 0:
                continue
            for row in violating.to_dicts():
                diff_rows.append(
                    {
                        **{key: row.get(key) for key in keys},
                        "field": field_name,
                        "primary_value": row.get(field_name),
                        "secondary_value": row.get(f"{field_name}_secondary"),
                        "diff": abs(
                            float(row.get(field_name) or 0.0)
                            - float(row.get(f"{field_name}_secondary") or 0.0)
                        ),
                        # 除权日（adj_factor 事件日）差异单列标记：
                        # 原始/复权口径差异不与单位错误混排
                        "ex_dividend_day": (
                            "instrument_id" in keys
                            and row.get("instrument_id") in ex_dividend_instruments
                        ),
                    }
                )
        return diff_rows

    @staticmethod
    def _violating_rows(
        merged: pl.DataFrame, field_name: str, rule: ToleranceRule
    ) -> pl.DataFrame:
        """返回超出容差的交集行。"""
        primary_col = pl.col(field_name).cast(pl.Float64, strict=False)
        secondary_col = pl.col(f"{field_name}_secondary").cast(pl.Float64, strict=False)
        merged = merged.filter(primary_col.is_finite() & secondary_col.is_finite())
        if rule.method == CompareMethod.TICK_ALIGNED:
            diff = (primary_col - secondary_col).abs()
            return merged.filter(
                pl.col(field_name).is_not_null()
                & pl.col(f"{field_name}_secondary").is_not_null()
                & (diff > (rule.tick_size or 0.0))
            )
        if rule.method == CompareMethod.RELATIVE:
            if rule.relative_tol is None:
                return pl.DataFrame()
            difference = (primary_col - secondary_col).abs()
            return merged.filter(
                primary_col.is_finite()
                & secondary_col.is_finite()
                & (difference > rule.relative_tol * secondary_col.abs())
            )
        if rule.method == CompareMethod.ABSOLUTE:
            if rule.absolute_tol is None:
                return pl.DataFrame()
            diff = (primary_col - secondary_col).abs()
            return merged.filter(
                pl.col(field_name).is_not_null()
                & pl.col(f"{field_name}_secondary").is_not_null()
                & (diff > rule.absolute_tol)
            )
        return pl.DataFrame()

    # ------------------------------------------------------------------
    # DQIssue 适配（写入时/巡检路径）
    # ------------------------------------------------------------------

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
            secondary: 辅助数据源 DataFrame（如 fuyao）
            rules: 跨源对比规则列表
            context: 额外上下文（可含 ex_dividend_instruments）

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
        """把结构化对比折叠为单条 DQIssue（保留可比较性语义）。"""
        key_columns = rule.get("key_columns", ["instrument_id", "trade_date"])
        fields = rule.get("fields", [])
        custom_tolerance = rule.get("tolerance_rules", {})
        tolerance = self.tolerance_rules.copy()
        for field_name, rule_config in custom_tolerance.items():
            tolerance[field_name] = ToleranceRule(
                method=CompareMethod(rule_config.get("method", "relative")),
                tick_size=rule_config.get("tick_size"),
                relative_tol=rule_config.get("relative_tol"),
                absolute_tol=rule_config.get("absolute_tol"),
            )
        ex_dividend: frozenset[int] = frozenset(
            (context or {}).get("ex_dividend_instruments") or ()
        )

        comparison = self.compare(
            primary,
            secondary,
            key_columns=key_columns,
            fields=fields,
            tolerance_rules=tolerance,
            ex_dividend_instruments=ex_dividend,
        )

        if not comparison.comparable:
            logger.warning(
                "cross_source_not_comparable",
                event="dq_check",
                rule="cross_source_compare",
                primary_count=comparison.primary_count,
                secondary_count=comparison.secondary_count,
                matched_count=comparison.matched_count,
            )
            return DQIssue(
                level=DQLevel.STATISTICAL,
                severity=DQSeverity.WARNING,
                rule_name="cross_source_not_comparable",
                message=(
                    "Cross-source comparison has no valid numeric pairs "
                    f"(primary={comparison.primary_count}, "
                    f"secondary={comparison.secondary_count}); "
                    "comparison is incomplete, not passing"
                ),
                affected_rows=0,
                sample_data=[],
            )

        duplicate_keys = (
            comparison.primary_duplicate_keys + comparison.secondary_duplicate_keys
        )
        if duplicate_keys:
            logger.warning(
                "cross_source_duplicate_keys",
                event="dq_check",
                rule="cross_source_compare",
                primary_duplicates=comparison.primary_duplicate_keys,
                secondary_duplicates=comparison.secondary_duplicate_keys,
            )
            return DQIssue(
                level=DQLevel.STATISTICAL,
                severity=DQSeverity.WARNING,
                rule_name="cross_source_duplicate_keys",
                message=(
                    f"Cross-source frames contain {duplicate_keys} duplicate keys"
                ),
                affected_rows=duplicate_keys,
                sample_data=comparison.diff_rows[:10],
            )

        if comparison.diff_rows:
            logger.warning(
                "cross_source_difference_found",
                event="dq_check",
                rule="cross_source_compare",
                diff_count=comparison.diff_count,
            )
            return DQIssue(
                level=DQLevel.STATISTICAL,
                severity=DQSeverity.ALERT,
                rule_name="cross_source_compare",
                message=rule.get(
                    "message", "Cross-source comparison found differences"
                ),
                affected_rows=comparison.diff_count,
                sample_data=comparison.diff_rows[:10],  # 最多 10 个样本
            )

        return None
