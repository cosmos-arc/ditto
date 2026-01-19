"""数据摄取相关模型。"""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class IngestionResult:
    """数据摄取结果。"""

    dataset: str
    trade_date: str
    status: Literal["success", "skipped", "failed"]
    row_count: int | None = None
    checksum: str | None = None
    message: str = ""
    error: str | None = None


@dataclass(frozen=True)
class ResultCounts:
    """摄取结果统计。"""

    success: int
    failed: int
    skipped: int


@dataclass(frozen=True)
class BackfillResult:
    """回补结果统计。"""

    dataset: str
    total_dates: int
    success_count: int
    skipped_count: int
    failed_count: int
    results: tuple[IngestionResult, ...]


@dataclass(frozen=True)
class RetryResult:
    """重试结果。"""

    dataset: str
    total_failed: int
    retried_count: int
    success_count: int
    still_failed_count: int
    results: tuple[IngestionResult, ...]
