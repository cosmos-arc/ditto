"""质量流程值对象 — L3 巡检结果 + 对账结果."""

from __future__ import annotations

from dataclasses import dataclass, field

from ditto_kernel.quality import DQIssue

__all__ = ["L3CheckResult", "ReconciliationResult"]


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
