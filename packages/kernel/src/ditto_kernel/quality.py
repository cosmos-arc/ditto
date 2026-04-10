"""
数据质量值对象 — 跨层共享的 DQ 类型定义.

提供 DQLevel、DQSeverity、DQIssue、DQResult 等 frozen dataclass，
供 ditto_data（检查引擎）、ditto_app（编排流程）、ditto_interfaces（任务）使用。

准入依据:
- DQIssue/DQResult 被 data + app + interfaces 三层使用
- 零外部依赖，纯值语义
- 稳定性高，不随子域迭代变更
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

__all__ = [
    "DQIssue",
    "DQLevel",
    "DQResult",
    "DQSeverity",
    "L3CheckResult",
    "ReconciliationResult",
]


class DQLevel(Enum):
    """DQ check level."""

    TECHNICAL = "technical"
    BUSINESS = "business"
    STATISTICAL = "statistical"


class DQSeverity(Enum):
    """
    DQ severity level.

    Represents the severity level of a data quality issue.
    Used across all layers for consistent issue classification.
    """

    ERROR = "error"
    WARNING = "warning"
    ALERT = "alert"


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


# ---------------------------------------------------------------------------
# L3 巡检结果
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class L3CheckResult:
    """L3 统计巡检结果（强类型）."""

    dataset: str
    trade_date: str
    passed: bool
    issue_count: int
    alert_count: int = 0
    issues: tuple[DQIssue, ...] = field(default_factory=tuple)
    error: str | None = None

    @property
    def has_error(self) -> bool:
        """是否存在异常."""
        return self.error is not None


# ---------------------------------------------------------------------------
# 对账结果
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReconciliationResult:
    """数据源对账结果（强类型）."""

    trade_date: str
    dataset: str
    passed: bool
    issue_count: int
    skipped: bool = False
    skip_reason: str | None = None
    error: str | None = None

    @property
    def has_error(self) -> bool:
        """是否存在异常."""
        return self.error is not None

    def to_dict(self) -> dict[str, object]:
        """转换为字典（兼容旧代码）."""
        result: dict[str, object] = {
            "trade_date": self.trade_date,
            "dataset": self.dataset,
            "passed": self.passed,
            "issue_count": self.issue_count,
        }
        if self.skipped and self.skip_reason:
            result["skipped"] = self.skip_reason
        if self.error:
            result["error"] = self.error
        return result
