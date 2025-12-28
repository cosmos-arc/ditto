"""DQ result models."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


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


@dataclass
class DQIssue:
    """Single DQ issue."""

    level: DQLevel
    severity: DQSeverity
    rule_name: str
    message: str
    affected_rows: int = 0
    sample_data: list[dict] = field(default_factory=list)


@dataclass
class DQResult:
    """DQ check result."""

    dataset: str
    passed: bool
    issues: list[DQIssue] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        """Has ERROR severity issues."""
        return any(i.severity == DQSeverity.ERROR for i in self.issues)

    @property
    def has_warnings(self) -> bool:
        """Has WARNING severity issues."""
        return any(i.severity == DQSeverity.WARNING for i in self.issues)

    @property
    def error_count(self) -> int:
        """Count of ERROR issues."""
        return sum(1 for i in self.issues if i.severity == DQSeverity.ERROR)

    @property
    def warn_count(self) -> int:
        """Count of WARNING issues."""
        return sum(1 for i in self.issues if i.severity == DQSeverity.WARNING)
