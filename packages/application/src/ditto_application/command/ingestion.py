"""入库命令 DTO + Handler — 单次写入操作的输入参数与处理."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from ditto_data.models.ingestion import IngestionResult

from ditto_application.contracts import IngestDateCommand
from ditto_application.process.ingestion.coordinator import IngestionCoordinator

__all__ = [
    "BackfillRangeCommand",
    "IngestDateHandler",
    "IngestRangeCommand",
]


@dataclass(frozen=True)
class IngestRangeCommand:
    """日期范围入库命令."""

    dataset: str
    start_date: date
    end_date: date
    force: bool = False
    parallel: int = 4


@dataclass(frozen=True)
class BackfillRangeCommand:
    """缺失数据回填命令."""

    dataset: str
    start_date: date
    end_date: date
    parallel: int = 4


class IngestDateHandler:
    """
    单日入库的原子写操作 — Command Handler.

    将 ``IngestDateCommand`` 委托给 ``IngestionCoordinator.ingest_date()``，
    负责 date → ISO string 的类型转换。
    """

    def __init__(self, coordinator: IngestionCoordinator) -> None:
        self._coordinator = coordinator

    def handle(self, command: IngestDateCommand) -> IngestionResult:
        """处理单日入库命令，委托给 IngestionCoordinator."""
        return self._coordinator.ingest_date(
            command.dataset,
            command.trade_date.isoformat(),
            force=command.force,
        )
