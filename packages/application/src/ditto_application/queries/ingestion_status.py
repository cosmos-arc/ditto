"""摄取状态查询 Facade."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from ditto_data.catalog import (
    DataCatalogReader,
    DatasetMetadata,
    default_dataset_metadata,
)
from ditto_data.ingestion.ingestion_log_store import IngestionLogStore
from ditto_data.models.ingestion import IngestionStatus

from ditto_application.catalog_freshness import (
    assess_catalog_freshness,
    latest_catalog_entry_for_dataset,
)

__all__ = [
    "DatasetMaturitySummary",
    "DatasetStatus",
    "HistoryItem",
    "IngestionStatusQueryFacade",
    "summarize_status_by_maturity",
]


@dataclass(frozen=True, slots=True)
class DatasetStatus:
    """单个数据集的摄取状态."""

    dataset: str
    latest_date: str | None
    latest_status: str | None
    dataset_maturity: str | None
    record_count: int
    last_attempt: str | None
    dataset_maturity_warning: str | None = None
    catalog_freshness_at: datetime | None = None
    catalog_storage_uri: str | None = None
    catalog_schema_hash: str | None = None
    catalog_row_count: int | None = None
    catalog_freshness_status: str | None = None
    catalog_freshness_sla_hours: int | None = None


@dataclass(frozen=True, slots=True)
class DatasetMaturitySummary:
    """Maturity-aware operational status summary."""

    maturity: str
    dataset_count: int
    fresh_count: int
    stale_count: int
    missing_count: int
    not_applicable_count: int
    failed_count: int
    warning_count: int


@dataclass(slots=True)
class _DatasetMaturitySummaryCounts:
    dataset_count: int = 0
    fresh_count: int = 0
    stale_count: int = 0
    missing_count: int = 0
    not_applicable_count: int = 0
    failed_count: int = 0
    warning_count: int = 0


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


_MATURITY_SORT_ORDER = {
    "production": 0,
    "initial-focus": 1,
    "experimental": 2,
    "infrastructure": 3,
    "reserved": 4,
    "historical-compat": 5,
    "unknown": 99,
}


def summarize_status_by_maturity(
    statuses: list[DatasetStatus],
) -> list[DatasetMaturitySummary]:
    """Group dataset status rows by capability maturity for reporting."""
    counts_by_maturity: dict[str, _DatasetMaturitySummaryCounts] = {}
    for status in statuses:
        maturity = status.dataset_maturity or "unknown"
        counts = counts_by_maturity.setdefault(
            maturity,
            _DatasetMaturitySummaryCounts(),
        )
        counts.dataset_count += 1
        match status.catalog_freshness_status:
            case "fresh":
                counts.fresh_count += 1
            case "stale":
                counts.stale_count += 1
            case "missing":
                counts.missing_count += 1
            case "not_applicable":
                counts.not_applicable_count += 1
            case _:
                pass
        if status.latest_status == "failed":
            counts.failed_count += 1
        if status.dataset_maturity_warning is not None:
            counts.warning_count += 1

    return [
        DatasetMaturitySummary(
            maturity=maturity,
            dataset_count=counts.dataset_count,
            fresh_count=counts.fresh_count,
            stale_count=counts.stale_count,
            missing_count=counts.missing_count,
            not_applicable_count=counts.not_applicable_count,
            failed_count=counts.failed_count,
            warning_count=counts.warning_count,
        )
        for maturity, counts in sorted(
            counts_by_maturity.items(),
            key=lambda item: (_MATURITY_SORT_ORDER.get(item[0], 98), item[0]),
        )
    ]


class IngestionStatusQueryFacade:
    """摄取状态查询编排."""

    def __init__(
        self,
        ingestion_log_store: IngestionLogStore,
        data_catalog_reader: DataCatalogReader,
        *,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._log_service = ingestion_log_store
        self._data_catalog_reader = data_catalog_reader
        self._now = now or _utcnow

    def get_status(self, datasets: list[str]) -> list[DatasetStatus]:
        """
        获取各数据集的最新摄取状态.

        Args:
            datasets: 要查询的数据集名称列表

        Returns:
            每个数据集的状态

        """
        results: list[DatasetStatus] = []
        dataset_metadata = default_dataset_metadata()
        for dataset in datasets:
            metadata = dataset_metadata.get(dataset)
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

            catalog_entry = latest_catalog_entry_for_dataset(
                self._data_catalog_reader,
                dataset,
            )
            freshness = assess_catalog_freshness(
                dataset=dataset,
                catalog_entry=catalog_entry,
                now=self._now,
            )
            results.append(
                DatasetStatus(
                    dataset=dataset,
                    latest_date=latest_date,
                    latest_status=latest_status,
                    dataset_maturity=(
                        metadata.maturity if metadata is not None else None
                    ),
                    dataset_maturity_warning=_dataset_maturity_warning(metadata),
                    record_count=record_count,
                    last_attempt=None,
                    catalog_freshness_at=catalog_entry.freshness_at
                    if catalog_entry is not None
                    else None,
                    catalog_storage_uri=catalog_entry.storage_uri
                    if catalog_entry is not None
                    else None,
                    catalog_schema_hash=catalog_entry.schema.schema_hash
                    if catalog_entry is not None
                    else None,
                    catalog_row_count=catalog_entry.schema.row_count
                    if catalog_entry is not None
                    else None,
                    catalog_freshness_status=freshness.status,
                    catalog_freshness_sla_hours=freshness.sla_hours,
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


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _dataset_maturity_warning(metadata: DatasetMetadata | None) -> str | None:
    if metadata is None:
        return None
    if metadata.maturity == "experimental":
        return (
            "experimental data requires explicit research opt-in before "
            "initial-focus use"
        )
    if metadata.maturity == "reserved":
        return "reserved data is not available for runtime use"
    return None
