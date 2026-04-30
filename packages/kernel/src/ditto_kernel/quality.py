"""
数据质量值对象 — 跨层共享的 DQ 类型定义.

提供 DQLevel、DQSeverity、DQIssue、DQResult 等 frozen dataclass，
供 ditto_data（检查引擎）、ditto_app（编排流程）、ditto_apps（任务）使用。

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
]


class DQLevel(Enum):
    """DQ check level."""

    TECHNICAL = "technical"
    BUSINESS = "business"
    STATISTICAL = "statistical"


class DQSeverity(Enum):
    """
    数据质量严重程度。

    ERROR: 数据存在严重问题，应阻断后续处理。
    WARNING: 数据存在潜在风险，可继续处理但需记录。
    ALERT: 信息性提示，数据可正常使用。
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

    @property
    def is_error(self) -> bool:
        """是否为 ERROR 级别。"""
        return self.severity == DQSeverity.ERROR


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
