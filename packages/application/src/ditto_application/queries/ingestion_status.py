"""摄取状态查询 Facade."""

from __future__ import annotations

from dataclasses import dataclass

from ditto_data.ingestion.ingestion_log_service import IngestionLogService
from ditto_data.models.ingestion import IngestionStatus


@dataclass(frozen=True, slots=True)
class DatasetStatus:
    """单个数据集的摄取状态."""

    dataset: str
    latest_date: str | None
    latest_status: str | None
    record_count: int
    last_attempt: str | None


@dataclass(frozen=True, slots=True)
class HistoryItem:
    """单条摄取历史记录."""

    dataset: str
    trade_date: str
    status: str
    rows: int | None
    error_message: str | None
    attempts: int
    last_attempt_at: str | None


class IngestionStatusQueryFacade:
    """摄取状态查询编排."""

    def __init__(self, ingestion_log_service: IngestionLogService) -> None:
        self._log_service = ingestion_log_service

    def get_status(self, datasets: list[str]) -> list[DatasetStatus]:
        """
        获取各数据集的最新摄取状态.

        Args:
            datasets: 要查询的数据集名称列表

        Returns:
            每个数据集的状态

        """
        results: list[DatasetStatus] = []
        for dataset in datasets:
            stats = self._log_service.get_stats(dataset)
            last_success = self._log_service.get_last_success_date(dataset)

            fail_dates = self._log_service.list_ingested_dates(
                dataset, status=IngestionStatus.FAIL
            )

            # 确定最新状态
            latest_date: str | None = last_success
            latest_status: str | None = "success" if last_success else None
            record_count = stats.get("success_count", 0)

            # 如果有失败记录，需要检查是否比最新成功更晚
            if fail_dates:
                latest_fail = fail_dates[-1] if fail_dates else None
                if latest_fail and (not latest_date or latest_fail > latest_date):
                    latest_date = latest_fail
                    latest_status = "failed"

            results.append(
                DatasetStatus(
                    dataset=dataset,
                    latest_date=latest_date,
                    latest_status=latest_status,
                    record_count=record_count,
                    last_attempt=None,
                )
            )
        return results

    def get_history(
        self,
        dataset: str,
        limit: int = 20,
    ) -> list[HistoryItem]:
        """
        获取数据集的摄取历史.

        Args:
            dataset: 数据集名称
            limit: 返回条数上限

        Returns:
            摄取历史记录列表

        """
        success_dates = self._log_service.list_ingested_dates(
            dataset, status=IngestionStatus.SUCCESS
        )
        fail_dates = self._log_service.list_ingested_dates(
            dataset, status=IngestionStatus.FAIL
        )

        history: list[HistoryItem] = []
        for date in success_dates[-limit:]:
            log = self._log_service.get_log(dataset, "tushare", date)
            history.append(
                HistoryItem(
                    dataset=dataset,
                    trade_date=date,
                    status="success",
                    rows=log.rows if log else None,
                    error_message=None,
                    attempts=log.attempts if log else 1,
                    last_attempt_at=log.last_attempt_at if log else None,
                )
            )
        for date in fail_dates[-limit:]:
            log = self._log_service.get_log(dataset, "tushare", date)
            history.append(
                HistoryItem(
                    dataset=dataset,
                    trade_date=date,
                    status="failed",
                    rows=None,
                    error_message=log.error_message if log else None,
                    attempts=log.attempts if log else 1,
                    last_attempt_at=log.last_attempt_at if log else None,
                )
            )

        # 按日期降序排序
        history.sort(key=lambda x: x.trade_date, reverse=True)
        return history[:limit]
