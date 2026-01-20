"""DQ rule configuration models."""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import yaml
from loguru import logger
from pydantic import BaseModel, Field, ValidationError, field_validator


class DQLevel(Enum):
    """DQ check level."""

    L1_TECHNICAL = "l1_technical"
    L2_BUSINESS = "l2_business"
    L3_STATISTICAL = "l3_statistical"


class DQSeverity(Enum):
    """DQ severity level."""

    ERROR = "error"
    WARNING = "warning"
    ALERT = "alert"


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


# Dataset Configuration


class DatasetRules(BaseModel):
    """
    DQ rules for a dataset.

    配置文件解析模型：使用 lax 模式允许 YAML 类型转换。
    """

    dataset: str
    description: str
    l1_technical: list[dict[str, Any]] = Field(default_factory=lambda: [])
    l2_business: list[dict[str, Any]] = Field(default_factory=lambda: [])
    l3_statistical: list[dict[str, Any]] = Field(default_factory=lambda: [])

    @field_validator("l1_technical", "l2_business", "l3_statistical", mode="before")
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

    @classmethod
    def from_yaml_dir(cls, config_dir: str | Path) -> "DQSpec":
        """
        Load DQ spec from YAML directory.

        Args:
            config_dir: Path to directory containing YAML rule files

        Returns:
            DQSpec instance

        """
        config_path = Path(config_dir)
        if not config_path.exists():
            return cls()

        datasets: dict[str, DatasetRules] = {}

        for yaml_file in config_path.glob("*.yml"):
            try:
                with yaml_file.open(encoding="utf-8") as f:
                    data = yaml.safe_load(f)

                if data and "dataset" in data:
                    dataset_rules = DatasetRules(**data)
                    datasets[dataset_rules.dataset] = dataset_rules
            except (ValidationError, ValueError) as e:
                logger.warning(
                    "Invalid DQ config file, skipping",
                    event="dq_config_invalid",
                    file=str(yaml_file),
                    error=str(e),
                )
                continue
            except yaml.YAMLError as e:
                logger.warning(
                    "Failed to parse YAML config, skipping",
                    event="dq_config_parse_error",
                    file=str(yaml_file),
                    error=str(e),
                )
                continue

        return cls(datasets=datasets)

    @classmethod
    def load_with_user_override(
        cls, default_config_dir: str | Path, data_root: str | Path
    ) -> "DQSpec":
        """
        加载 DQ 配置，支持用户自定义覆盖。

        加载优先级:
        1. 用户配置: {data_root}/config/dq/*.yml
        2. 默认配置: {default_config_dir}/*.yml

        Args:
            default_config_dir: 包内默认配置目录
            data_root: 数据根目录

        Returns:
            DQSpec 实例

        """
        # 1. 加载包内默认配置
        default_config = cls.from_yaml_dir(default_config_dir)

        # 2. 加载用户自定义配置（覆盖默认配置）
        user_config_dir = Path(data_root) / "config" / "dq"
        user_config = cls.from_yaml_dir(user_config_dir)

        # 3. 合并配置（用户配置覆盖默认配置）
        merged_datasets = default_config.datasets.copy()
        merged_datasets.update(user_config.datasets)

        return cls(datasets=merged_datasets)

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
