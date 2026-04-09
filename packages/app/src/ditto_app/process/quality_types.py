"""L3 检查结果类型."""

from __future__ import annotations

__all__ = ["L3CheckResult"]

from dataclasses import dataclass, field

from ditto_kernel.quality import DQIssue


@dataclass(frozen=True)
class L3CheckResult:
    """L3 批量检查结果（强类型）."""

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
