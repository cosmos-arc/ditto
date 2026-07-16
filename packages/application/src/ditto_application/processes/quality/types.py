"""质量流程值对象 — L3 巡检结果 + 对账结果."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from ditto_data.quality.quality_types import DQIssue

__all__ = [
    "L3CheckResult",
    "QualityBatchDatasetResult",
    "QualityBatchRequest",
    "QualityBatchResult",
    "QualityCompletenessRequest",
    "QualityCompletenessResult",
    "ReconciliationResult",
]


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
    applicable: bool = True

    @property
    def has_error(self) -> bool:
        """是否存在异常."""
        return self.error is not None


@dataclass(frozen=True)
class QualityBatchRequest:
    """Transport-neutral request for one scheduled quality batch."""

    trade_date: str | None = None
    datasets: tuple[str, ...] | None = None
    market_wide: bool = False
    ingestion_results: Mapping[str, Mapping[str, object]] | None = None


@dataclass(frozen=True)
class QualityBatchDatasetResult:
    """Application DTO for one dataset in a quality batch."""

    passed: bool
    issue_count: int
    alert_count: int
    l3_status: str | None = None
    quality_evidence: Mapping[str, object] | None = None
    evidence: Mapping[str, object] | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, object]:
        """Serialize the stable job/CLI transport shape."""
        result: dict[str, object] = {
            "passed": self.passed,
            "issue_count": self.issue_count,
            "alert_count": self.alert_count,
        }
        if self.l3_status is not None:
            result["l3_status"] = self.l3_status
        if self.quality_evidence is not None:
            result["quality_evidence"] = dict(self.quality_evidence)
        if self.evidence is not None:
            result["evidence"] = dict(self.evidence)
        if self.error is not None:
            result["error"] = self.error
        return result


@dataclass(frozen=True)
class QualityBatchResult:
    """Application DTO returned by a quality batch run."""

    trade_date: str
    datasets_checked: tuple[str, ...]
    total_issues: int
    alert_count: int
    results_by_dataset: Mapping[str, QualityBatchDatasetResult]

    def to_dict(self) -> dict[str, object]:
        """Serialize the batch result at the apps transport boundary."""
        return {
            "trade_date": self.trade_date,
            "datasets_checked": list(self.datasets_checked),
            "total_issues": self.total_issues,
            "alert_count": self.alert_count,
            "results_by_dataset": {
                dataset: result.to_dict()
                for dataset, result in self.results_by_dataset.items()
            },
        }


@dataclass(frozen=True)
class QualityCompletenessRequest:
    """Transport-neutral request for one instrument completeness check."""

    trade_date: str
    dataset: str
    expected_sids: tuple[int, ...] | None = None
    market_wide: bool = False


@dataclass(frozen=True)
class QualityCompletenessResult:
    """Application result for one instrument completeness check."""

    trade_date: str
    dataset: str
    expected_count: int | None
    actual_count: int
    missing_sids: tuple[int, ...]
    extra_sids: tuple[int, ...]

    @property
    def is_complete(self) -> bool:
        """Return whether every expected instrument was present."""
        return not self.missing_sids

    def to_dict(self) -> dict[str, object]:
        """Serialize the stable Prefect transport shape."""
        return {
            "trade_date": self.trade_date,
            "dataset": self.dataset,
            "expected_count": self.expected_count,
            "actual_count": self.actual_count,
            "missing_count": len(self.missing_sids),
            "missing_sids": list(self.missing_sids),
            "extra_count": len(self.extra_sids),
            "extra_sids": list(self.extra_sids),
            "is_complete": self.is_complete,
        }


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
