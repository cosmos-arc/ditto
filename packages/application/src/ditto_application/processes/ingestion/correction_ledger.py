"""
存量纠正账本行写入（#658 批次2）.

apps 层（ops 脚本）不得导入 ditto_data.models（importlinter
apps-service-isolation），而纠正原因行须构造 IngestionLog 模型——本模块
把「构造+落账」收敛为 application 层单一入口，脚本只传纯字段。
"""

from __future__ import annotations

from typing import Protocol

from ditto_data.models.ingestion import IngestionLog, IngestionStatus

__all__ = [
    "CORRECTION_LEDGER_SOURCE",
    "CorrectionLogStore",
    "save_kd_correction_ledger_row",
]

CORRECTION_LEDGER_SOURCE = "kd_correction"


class CorrectionLogStore(Protocol):
    """纠正账本所需的最小写入端口（IngestionLogStore 结构满足）."""

    def save_log(self, log: IngestionLog) -> IngestionLog:
        """幂等落一条摄取账本行."""
        ...


def save_kd_correction_ledger_row(
    log_store: CorrectionLogStore,
    *,
    dataset: str,
    trade_date: str,
    rows: int,
    checksum: str,
    recorded_at: str,
) -> None:
    """落一条 source=kd_correction 的 SUCCESS 原因行（幂等 upsert）."""
    log_store.save_log(
        IngestionLog(
            dataset=dataset,
            source=CORRECTION_LEDGER_SOURCE,
            trade_date=trade_date,
            status=IngestionStatus.SUCCESS,
            checksum=checksum,
            rows=rows,
            attempts=1,
            first_attempt_at=recorded_at,
            last_attempt_at=recorded_at,
        )
    )
