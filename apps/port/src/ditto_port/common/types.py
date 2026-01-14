"""共享类型定义。"""

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
