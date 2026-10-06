"""L1 Technical checker."""

from typing import Any

import polars as pl
from ditto_platform.foundation import logger

from ditto_data.quality.quality_types import DQIssue, DQLevel, DQSeverity

# yml 期望记号 → Polars dtype 基名（str 为 macro_indicators.yml 既有记号）
_EXPECTED_DTYPE_ALIASES = {"str": "string", "bool": "boolean"}


def _dtype_base(actual_dtype: str) -> str:
    """
    Polars dtype repr 的比较基名：去参数、去位宽、小写。

    "Int64"→"int"、"Float64"→"float"、"Date"→"date"、
    "Datetime(time_unit='us')"→"datetime"、"String"→"string"——基名精确
    相等使 date 不匹配 datetime、int 不匹配 uint。
    """
    return actual_dtype.lower().split("(", 1)[0].rstrip("0123456789")


def _expected_dtype_base(expected_type: str) -> str:
    normalized = expected_type.strip().lower()
    return _EXPECTED_DTYPE_ALIASES.get(normalized, normalized)


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
        elif rule_type == "required_columns":
            return self._check_required_columns(df, rule)

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
                    level=DQLevel.TECHNICAL,
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
                level=DQLevel.TECHNICAL,
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

        # Need reference_values from context (provided by Application Layer).
        #
        # #513 裁决说明：不为「ETF 域混入 LOF」接线此处——品种边界由
        # ETFTushareAdapter 在源层按 etf_basic universe 交集/拒绝把关
        # （写入前过滤），写入时 instrument 解析本身即天然 FK；此处
        # reference_values 机制留给未来需要跨数据集值域校验的规则。
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
                    level=DQLevel.TECHNICAL,
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
            rule: Rule config with "columns" dict mapping column -> expected
                dtype token (int/float/date/datetime/str/string/bool)

        Returns:
            DQIssue if type mismatch, None otherwise

        """
        # #529：键名对齐 TypeCheckRule（spec 定义为 columns: dict[str, str]；
        # 旧实现读 "types" 键使全部 yml 规则自始未生效）。
        expected_types = rule.get("columns", {})

        for col, expected_type in expected_types.items():
            if col not in df.columns:
                continue

            actual_dtype = str(df[col].dtype)
            if _dtype_base(actual_dtype) != _expected_dtype_base(expected_type):
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
                    level=DQLevel.TECHNICAL,
                    severity=DQSeverity.ERROR,
                    rule_name="type_check",
                    message=msg,
                    affected_rows=df.height,
                )

        return None

    def _check_required_columns(
        self, df: pl.DataFrame, rule: dict[str, Any]
    ) -> DQIssue | None:
        """
        Check required columns exist.

        Args:
            df: Data to check
            rule: Rule config with "columns" key containing required column names

        Returns:
            DQIssue if columns missing, None otherwise

        """
        columns = rule.get("columns", [])
        missing = [col for col in columns if col not in df.columns]

        if missing:
            logger.warning(
                "dq_rule_missing_columns",
                event="dq_check",
                rule="required_columns",
                missing_columns=missing,
            )
            return DQIssue(
                level=DQLevel.TECHNICAL,
                severity=DQSeverity.ERROR,
                rule_name="required_columns",
                message=f"Missing required columns: {missing}",
                affected_rows=len(missing),
            )

        return None
