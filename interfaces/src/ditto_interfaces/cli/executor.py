"""
CLI 本地执行器.

封装 IngestionCoordinator 和 BackfillManager，为 CLI 命令提供统一执行接口。

重构后（ARCH-004）：
- CLIExecutor 不再直接依赖 Data 服务
- 只接收已组装好的 coordinator + backfill_manager
- 所有依赖组装由 create_cli_executor 上下文管理器处理
"""

from __future__ import annotations

from typing import Any

from ditto_app._reexports import InstrumentIngestParams
from ditto_app.process.backfill_manager import BackfillManager
from ditto_app.process.ingestion_coordinator import IngestionCoordinator


class CLIExecutor:
    """CLI 本地执行器，封装 IngestionCoordinator 和 BackfillManager."""

    def __init__(
        self,
        coordinator: IngestionCoordinator,
        backfill_manager: BackfillManager,
    ) -> None:
        """
        初始化 CLIExecutor.

        Args:
            coordinator: IngestionCoordinator 实例
            backfill_manager: BackfillManager 实例

        """
        self._coordinator = coordinator
        self._backfill_manager = backfill_manager

    @property
    def coordinator(self) -> IngestionCoordinator:
        """获取 coordinator."""
        return self._coordinator

    @property
    def backfill_manager(self) -> BackfillManager:
        """获取 backfill_manager."""
        return self._backfill_manager

    def ingest_daily(
        self, dataset: str, trade_date: str, force: bool = False
    ) -> dict[str, Any]:
        """
        执行单日摄取.

        Args:
            dataset: 数据集名称
            trade_date: 交易日期 (YYYY-MM-DD)
            force: 是否强制重新摄取

        Returns:
            包含摄取结果的字典

        """
        result = self.coordinator.ingest_date(dataset, trade_date, force)
        return {
            "dataset": dataset,
            "trade_date": trade_date,
            "status": result.status,
            "row_count": result.row_count,
            "message": result.message,
            "error": result.error,
        }

    def backfill_range(
        self,
        dataset: str,
        start_date: str,
        end_date: str,
        parallel: int = 1,
    ) -> dict[str, Any]:
        """
        执行日期范围回补.

        Args:
            dataset: 数据集名称
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)
            parallel: 并行度

        Returns:
            包含回补结果的字典

        """
        result = self.backfill_manager.backfill_range(
            dataset=dataset,
            start_date=start_date,
            end_date=end_date,
            parallel=parallel,
        )
        return {
            "dataset": dataset,
            "total_dates": result.total_dates,
            "success_count": result.success_count,
            "skipped_count": result.skipped_count,
            "failed_count": result.failed_count,
        }

    def ingest_by_instrument(
        self,
        dataset: str,
        ticker: str | None = None,
        standard_ticker: str | None = None,
        instrument_id: int | None = None,
        start_date: str = "",
        end_date: str = "",
        force: bool = False,
    ) -> dict[str, Any]:
        """
        执行按标的+时间范围摄取.

        Args:
            dataset: 数据集名称
            ticker: 裸代码（如 "000001"）
            standard_ticker: Ditto 标准格式（如 "000001.XSHE"）
            instrument_id: 内部 ID（如 1000001）
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)
            force: 是否强制覆盖已有数据

        Returns:
            包含摄取结果的字典

        """
        params = InstrumentIngestParams(
            ticker=ticker,
            standard_ticker=standard_ticker,
            instrument_id=instrument_id,
            start_date=start_date,
            end_date=end_date,
        )
        result = self.coordinator.ingest_by_instrument(dataset, params, force)

        # 构建标识符信息用于返回
        identifier_info = ticker or standard_ticker or str(instrument_id)

        return {
            "dataset": dataset,
            "identifier": identifier_info,
            "start_date": start_date,
            "end_date": end_date,
            "status": result.status,
            "row_count": result.row_count,
            "message": result.message,
            "error": result.error,
        }
