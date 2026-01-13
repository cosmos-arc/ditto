"""结果统计辅助函数。"""

from collections import Counter
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ditto_port.services.ingestion.coordinator import IngestionResult


@dataclass(frozen=True)
class ResultCounts:
    """结果统计。"""

    success: int
    failed: int
    skipped: int


def count_results(
    results: list["IngestionResult"] | dict[str, dict],
) -> ResultCounts:
    """
    统计摄取结果。

    Args:
        results: 摄取结果列表或字典

    Returns:
        ResultCounts: 包含 success/failed/skipped 计数

    Examples:
        >>> from ditto_port.services.ingestion.coordinator import (
        ...     IngestionResult,
        ... )
        >>> results = [
        ...     IngestionResult(
        ...         dataset="stock_daily",
        ...         trade_date="2024-01-01",
        ...         status="success",
        ...     ),
        ...     IngestionResult(
        ...         dataset="stock_daily",
        ...         trade_date="2024-01-02",
        ...         status="failed",
        ...         error="FETCH_ERROR",
        ...     ),
        ... ]
        >>> counts = count_results(results)
        >>> counts.success, counts.failed, counts.skipped
        (1, 1, 0)

        >>> # 字典类型结果
        >>> dict_results = {
        ...     "task1": {"status": "success"},
        ...     "task2": {"status": "failed"},
        ... }
        >>> counts = count_results(dict_results)
        >>> counts.success, counts.failed, counts.skipped
        (1, 1, 0)

    """
    if isinstance(results, list):
        # 处理 IngestionResult 列表
        statuses = [r.status for r in results if r is not None and hasattr(r, "status")]
    elif isinstance(results, dict):
        # 处理字典类型结果
        statuses = [
            v.get("status")
            for v in results.values()
            if isinstance(v, dict) and "status" in v
        ]
    else:
        statuses = []

    # 使用 Counter 统计
    counter = Counter(statuses)

    return ResultCounts(
        success=counter.get("success", 0),
        failed=counter.get("failed", 0),
        skipped=counter.get("skipped", 0),
    )
