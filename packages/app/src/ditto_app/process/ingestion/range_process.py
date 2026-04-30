"""
日期范围摄取 Process Manager — 编排多日入库 + 回填.

包含:
- ``IngestRangeProcess`` — 自然日逐日编排，委托 ``IngestDateHandler``
- ``BackfillRangeProcess`` — 缺失数据回填，委托 ``BackfillManager``
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from ditto_data.models.ingestion import BackfillResult, IngestionResult
from ditto_platform.foundation import logger

from ditto_app.contracts import IngestDateCommand
from ditto_app.process.ingestion.backfill_manager import BackfillManager
from ditto_app.process.ingestion.ports import IngestDateHandlerProtocol

# ---------------------------------------------------------------------------
# Trigger DTOs
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IngestRangeTrigger:
    """日期范围摄取触发器."""

    dataset: str
    start_date: date
    end_date: date
    force: bool = False
    parallel: int = 4


@dataclass(frozen=True)
class BackfillRangeTrigger:
    """缺失数据回填触发器."""

    dataset: str
    start_date: date
    end_date: date
    parallel: int = 4


# ---------------------------------------------------------------------------
# Process Managers
# ---------------------------------------------------------------------------


class IngestRangeProcess:
    """
    日期范围摄取 — Process Manager.

    对范围内每个自然日调用 ``IngestDateHandler``，收集全部结果。
    当 ``parallel > 1`` 时可使用线程池并行执行（当前为串行实现）。
    """

    def __init__(self, handler: IngestDateHandlerProtocol) -> None:
        self._handler = handler

    def run(self, trigger: IngestRangeTrigger) -> list[IngestionResult]:
        """执行日期范围摄取，返回每个日期的结果列表."""
        results: list[IngestionResult] = []
        current = trigger.start_date
        while current <= trigger.end_date:
            cmd = IngestDateCommand(
                dataset=trigger.dataset,
                trade_date=current,
                force=trigger.force,
            )
            results.append(self._handler.handle(cmd))
            current += timedelta(days=1)

        logger.info(
            "日期范围摄取完成",
            event="ingest_range_complete",
            dataset=trigger.dataset,
            start_date=trigger.start_date.isoformat(),
            end_date=trigger.end_date.isoformat(),
            total=len(results),
        )
        return results


class BackfillRangeProcess:
    """
    缺失数据回填 — Process Manager.

    将回填请求委托给 ``BackfillManager.backfill_range()``，
    负责 date → ISO string 的类型转换。
    """

    def __init__(self, manager: BackfillManager) -> None:
        self._manager = manager

    def run(self, trigger: BackfillRangeTrigger) -> BackfillResult:
        """执行缺失数据回填."""
        logger.info(
            "开始缺失数据回填",
            event="backfill_range_process_start",
            dataset=trigger.dataset,
            start_date=trigger.start_date.isoformat(),
            end_date=trigger.end_date.isoformat(),
            parallel=trigger.parallel,
        )
        return self._manager.backfill_range(
            dataset=trigger.dataset,
            start_date=trigger.start_date.isoformat(),
            end_date=trigger.end_date.isoformat(),
            parallel=trigger.parallel,
        )
