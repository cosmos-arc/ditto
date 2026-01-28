"""DQ rule configuration models."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from ditto_foundation import DQSeverity
from pydantic import BaseModel, Field, field_validator


class DQLevel(Enum):
    """DQ check level."""

    TECHNICAL = "technical"  # 技术类 - 结构约束（非空、唯一、外键）
    BUSINESS = "business"  # 业务类 - 业务规则（OHLC、涨跌幅）
    STATISTICAL = "statistical"  # 统计类 - 异常检测（Z-score、完整性）


class RuleType(str, Enum):
    """Rule type enum."""

    NOT_NULL = "not_null"
    UNIQUE = "unique"
    FOREIGN_KEY = "foreign_key"
    TYPE_CHECK = "type_check"
    POSITIVE = "positive"
    EXPRESSION = "expression"
    RANGE_CHECK = "range_check"
    NO_ZERO_VOLUME = "no_zero_volume"
    ZSCORE = "zscore"
    COMPLETENESS = "COMPLETENESS"
    STALE_PRICE = "stale_price"
    CONSISTENCY = "consistency"
    MONOTONIC_DECREASE = "monotonic_decrease"
    OUTLIER = "outlier"
    CROSS_SOURCE_COMPARE = "cross_source_compare"


# Cross-Source Comparison Models


class CompareMethod(str, Enum):
    """跨源比对方法."""

    TICK_ALIGNED = "tick_aligned"  # Tick 对齐（价格类）
    RELATIVE = "relative"  # 相对容差（百分比）
    ABSOLUTE = "absolute"  # 绝对容差（成交量类）


@dataclass(frozen=True)
class ToleranceRule:
    """容差规则."""

    method: CompareMethod
    tick_size: float | None = None  # Tick 对齐时的 tick 大小
    relative_tol: float | None = None  # 相对容差（如 0.001 = 0.1%）
    absolute_tol: float | None = None  # 绝对容差


# Base Rule Models


class BaseRule(BaseModel):
    """
    Base rule configuration.

    配置文件解析模型：使用 lax 模式允许类型转换。
    extra='allow' 容纳不同规则类型的扩展字段。
    """

    rule: RuleType
    message: str

    model_config = {"extra": "allow"}


class ColumnRule(BaseRule):
    """Rule that operates on columns."""

    columns: list[str] = Field(default_factory=list)


class SingleColumnRule(BaseRule):
    """Rule that operates on a single column."""

    column: str | None = None


class ForeignKeyRule(BaseRule):
    """Foreign key validation rule."""

    rule: RuleType = RuleType.FOREIGN_KEY
    column: str
    reference: str  # e.g., "security.sid"


class TypeCheckRule(BaseRule):
    """Type checking rule."""

    rule: RuleType = RuleType.TYPE_CHECK
    columns: dict[str, str]  # column: type


class ExpressionRule(BaseRule):
    """Expression-based rule."""

    rule: RuleType = RuleType.EXPRESSION
    name: str
    expr: str


class RangeCheckRule(BaseRule):
    """Range validation rule."""

    rule: RuleType = RuleType.RANGE_CHECK
    column: str
    min: float | None = None
    max: float | None = None
    min_ratio: float | None = None
    max_ratio: float | None = None


class ZScoreRule(BaseRule):
    """Z-score anomaly detection rule."""

    rule: RuleType = RuleType.ZSCORE
    name: str
    column: str
    window: int = Field(default=60, ge=1)
    threshold: float = Field(default=3.0, gt=0)
    group_by: str | list[str] | None = None


class CompletenessRule(BaseRule):
    """Data completeness check rule."""

    rule: RuleType = RuleType.COMPLETENESS
    name: str
    expected_dates: str
    lookback_days: int = Field(default=5, ge=1)


# L1 Rules


class NotNullRule(ColumnRule):
    """Not null validation rule."""

    rule: RuleType = RuleType.NOT_NULL


class UniqueRule(ColumnRule):
    """Uniqueness validation rule."""

    rule: RuleType = RuleType.UNIQUE


# L2 Rules


class PositiveRule(ColumnRule):
    """Positive value validation rule."""

    rule: RuleType = RuleType.POSITIVE


class NoZeroVolumeRule(SingleColumnRule):
    """No zero volume validation rule."""

    rule: RuleType = RuleType.NO_ZERO_VOLUME


# L3 Rules


class StalePriceRule(BaseRule):
    """Stale price detection rule."""

    rule: RuleType = RuleType.STALE_PRICE
    name: str
    column: str
    threshold_days: int = Field(default=3, ge=1)


class ConsistencyRule(BaseRule):
    """Consistency check rule."""

    rule: RuleType = RuleType.CONSISTENCY
    name: str
    max_change_ratio: float | None = None
    reference_dataset: str | None = None
    window: int | None = None
    threshold_ratio: float | None = None
    group_by: str | list[str] | None = None


class MonotonicDecreaseRule(BaseRule):
    """Monotonic decrease validation rule."""

    rule: RuleType = RuleType.MONOTONIC_DECREASE
    column: str
    group_by: str | list[str]
    severity: str = "warning"


class OutlierRule(BaseRule):
    """Outlier detection rule."""

    rule: RuleType = RuleType.OUTLIER
    name: str
    column: str
    window: int
    threshold_ratio: float
    group_by: str | list[str] | None = None
    reference_dataset: str | None = None


class CrossSourceRule(BaseRule):
    """跨源对比规则（L3 统计检查）."""

    rule: RuleType = RuleType.CROSS_SOURCE_COMPARE
    fields: list[str]  # 要对比的字段（如 [open, high, low, close, vol]）
    key_columns: list[str]  # 对比键（如 [src_code, trade_date]）
    tolerance_rules: dict[str, dict[str, Any]] | None = None  # 字段 → 容差配置
    enabled: bool = True  # 开关控制


# Dataset Configuration


class DatasetRules(BaseModel):
    """
    DQ rules for a dataset.

    配置文件解析模型：使用 lax 模式允许 YAML 类型转换。
    """

    dataset: str
    description: str
    technical: list[dict[str, Any]] = Field(default_factory=list)  # 技术类规则
    business: list[dict[str, Any]] = Field(default_factory=list)  # 业务类规则
    statistical: list[dict[str, Any]] = Field(default_factory=list)  # 统计类规则

    @field_validator("technical", "business", "statistical", mode="before")
    @classmethod
    def parse_rules(cls, v: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Parse rule dicts into proper models."""
        return v


class DQSpec(BaseModel):
    """
    DQ specification for all datasets.

    配置文件解析模型：使用 lax 模式允许 YAML 类型转换。
    """

    datasets: dict[str, DatasetRules] = Field(default_factory=dict)

    def get_rules(self, dataset: str) -> DatasetRules | None:
        """
        Get rules for a specific dataset.

        Args:
            dataset: Dataset name

        Returns:
            DatasetRules if found, None otherwise

        """
        return self.datasets.get(dataset)

    def has_dataset(self, dataset: str) -> bool:
        """
        Check if dataset has rules configured.

        Args:
            dataset: Dataset name

        Returns:
            True if dataset has rules, False otherwise

        """
        return dataset in self.datasets


# Result Models


@dataclass(frozen=True)
class DQIssue:
    """Single DQ issue."""

    level: DQLevel
    severity: DQSeverity
    rule_name: str
    message: str
    affected_rows: int = 0
    sample_data: list[dict[str, Any]] = field(default_factory=lambda: [])


@dataclass(frozen=True)
class DQResult:
    """DQ check result."""

    dataset: str
    passed: bool
    issues: list[DQIssue] = field(default_factory=lambda: [])

    @property
    def has_errors(self) -> bool:
        """Has ERROR severity issues."""
        return any(i.severity == DQSeverity.ERROR for i in self.issues)

    @property
    def has_warnings(self) -> bool:
        """Has WARNING severity issues."""
        return any(i.severity == DQSeverity.WARNING for i in self.issues)

    @property
    def has_alerts(self) -> bool:
        """Has ALERT severity issues."""
        return any(i.severity == DQSeverity.ALERT for i in self.issues)

    @property
    def error_count(self) -> int:
        """Count of ERROR issues."""
        return sum(1 for i in self.issues if i.severity == DQSeverity.ERROR)

    @property
    def warn_count(self) -> int:
        """Count of WARNING issues."""
        return sum(1 for i in self.issues if i.severity == DQSeverity.WARNING)

    @property
    def alert_count(self) -> int:
        """Count of ALERT issues."""
        return sum(1 for i in self.issues if i.severity == DQSeverity.ALERT)

    @property
    def total_count(self) -> int:
        """Total count of all issues."""
        return len(self.issues)
