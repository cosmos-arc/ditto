"""全量回补管理器 — BackfillManager."""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor, as_completed

from ditto_data.ingestion.ingestion_log_store import (
    IngestionLogStore,
)
from ditto_data.models.ingestion import (
    BackfillResult,
    IngestionLog,
    IngestionResult,
    IngestionStatus,
)
from ditto_data.services.metadata_service import MetadataService
from ditto_platform.foundation import logger

from ditto_application.catalog_freshness import PersistedIngestionEvidenceVerifier
from ditto_application.processes.ingestion.bootstrap_planner import (
    BootstrapPlan,
    BootstrapPlanner,
)
from ditto_application.processes.ingestion.result_handler import count_results
from ditto_application.processes.ingestion.source_selection import (
    IngestionCoordinatorLike,
)


class BackfillManager:
    """全量回补管理器。"""

    def __init__(
        self,
        coordinator: IngestionCoordinatorLike,
        metadata_service: MetadataService,
        ingestion_log_store: IngestionLogStore,
        bootstrap_planner: BootstrapPlanner | None = None,
        evidence_verifier: PersistedIngestionEvidenceVerifier | None = None,
    ) -> None:
        """
        初始化 BackfillManager。

        Args:
            coordinator: 摄取协调器端口。
            metadata_service: MetadataService 实例。
            ingestion_log_store: IngestionLogStore 实例。
            bootstrap_planner: 日程和分块感知的持久回补规划器。
            evidence_verifier: 可选的目录与摄取日志一致性校验器。

        """
        self._coordinator = coordinator
        self._metadata_service = metadata_service
        self._ingestion_log_store = ingestion_log_store
        self._bootstrap_planner = bootstrap_planner or BootstrapPlanner(
            metadata_service=metadata_service
        )
        self._evidence_verifier = evidence_verifier

    def backfill_range(
        self,
        dataset: str,
        start_date: str,
        end_date: str,
        parallel: int = 1,
        source: str = "tushare",
    ) -> BackfillResult:
        """
        全量回补指定日期范围。

        Args:
            dataset: 数据集名称。
            start_date: 开始日期 (YYYY-MM-DD)。
            end_date: 结束日期 (YYYY-MM-DD)。
            parallel: 并行度，默认为 1（串行）。
            source: 数据源标识符（默认: "tushare"）。

        Returns:
            BackfillResult: 回补结果。

        """
        logger.info(
            "开始回补数据",
            event="backfill_range_start",
            dataset=dataset,
            start_date=start_date,
            end_date=end_date,
            parallel=parallel,
        )

        plan = self._bootstrap_planner.plan(
            dataset_id=dataset,
            source=source,
            start_date=start_date,
            end_date=end_date,
        )
        partition_dates = _planned_dates(plan)
        if not partition_dates:
            return BackfillResult(
                dataset=dataset,
                total_dates=0,
                success_count=0,
                skipped_count=0,
                failed_count=0,
                results=(),
            )

        result = self._execute_backfill(
            dataset=dataset,
            trade_dates=partition_dates,
            parallel=parallel,
            log_event="backfill_range_complete",
        )
        return result

    def backfill_missing(
        self,
        dataset: str,
        source: str = "tushare",
        parallel: int = 1,
    ) -> BackfillResult:
        """
        回补缺失的交易日。

        Args:
            dataset: 数据集名称。
            source: 数据源标识符（默认: "tushare"）。
            parallel: 并行度，默认为 1（串行）。

        Returns:
            BackfillResult: 回补结果。

        """
        logger.info(
            "开始回补缺失数据",
            event="backfill_missing_start",
            dataset=dataset,
            parallel=parallel,
        )

        first_date = self._metadata_service.calendar.get_first_trading_day()
        last_date = self._metadata_service.get_last_trading_day()
        if not first_date or not last_date:
            return BackfillResult(
                dataset=dataset,
                total_dates=0,
                success_count=0,
                skipped_count=0,
                failed_count=0,
                results=(),
            )

        plan = self._bootstrap_planner.plan(
            dataset_id=dataset,
            source=source,
            start_date=first_date,
            end_date=last_date,
        )
        expected_dates = _planned_dates(plan)
        if not expected_dates:
            return BackfillResult(
                dataset=dataset,
                total_dates=0,
                success_count=0,
                skipped_count=0,
                failed_count=0,
                results=(),
            )

        ingested_dates = self._ingestion_log_store.list_ingested_dates(
            dataset,
            source,
            IngestionStatus.SUCCESS,
        )
        evidenced_dates = self._evidenced_dates(
            dataset=dataset,
            source=source,
            ingested_dates=ingested_dates,
        )
        missing_dates = set(expected_dates) - evidenced_dates
        if not missing_dates:
            return BackfillResult(
                dataset=dataset,
                total_dates=0,
                success_count=0,
                skipped_count=0,
                failed_count=0,
                results=(),
            )

        sorted_missing_dates = sorted(missing_dates)

        return self._execute_backfill(
            dataset=dataset,
            trade_dates=sorted_missing_dates,
            parallel=parallel,
            log_event="backfill_missing_complete",
        )

    def _evidenced_dates(
        self,
        *,
        dataset: str,
        source: str,
        ingested_dates: list[str],
    ) -> set[str]:
        """Return dates whose success log is backed by exact catalog evidence."""
        if self._evidence_verifier is None:
            return set(ingested_dates)

        evidenced: set[str] = set()
        for trade_date in ingested_dates:
            log = self._ingestion_log_store.get_log(dataset, source, trade_date)
            payload = _verifiable_payload(log)
            if payload is None:
                continue
            checksum, row_count = payload
            if self._evidence_verifier.verify_exact_date(
                dataset=dataset,
                source=source,
                trade_date=trade_date,
                checksum=checksum,
                row_count=row_count,
            ):
                evidenced.add(trade_date)
        return evidenced

    def _execute_backfill(
        self,
        dataset: str,
        trade_dates: list[str],
        parallel: int,
        log_event: str,
    ) -> BackfillResult:
        """
        执行回补：并行/串行摄取 + 结果统计。

        Args:
            dataset: 数据集名称。
            trade_dates: 待回补的交易日期列表。
            parallel: 并行度。
            log_event: 完成日志事件名。

        Returns:
            BackfillResult: 回补结果。

        """
        results: list[IngestionResult] = []

        if parallel > 1:
            with ThreadPoolExecutor(max_workers=parallel) as executor:
                futures: dict[Future[IngestionResult], str] = {
                    executor.submit(self._coordinator.ingest_date, dataset, d): d
                    for d in trade_dates
                }
                for future in as_completed(futures):
                    results.append(future.result())
        else:
            for trade_date in trade_dates:
                results.append(self._coordinator.ingest_date(dataset, trade_date))

        counts = count_results(results)
        backfill_result = BackfillResult(
            dataset=dataset,
            total_dates=len(trade_dates),
            success_count=counts.success,
            skipped_count=counts.skipped,
            failed_count=counts.failed,
            results=tuple(results),
        )

        logger.info(
            "回补完成",
            event=log_event,
            dataset=dataset,
            total_dates=backfill_result.total_dates,
            success_count=backfill_result.success_count,
            skipped_count=backfill_result.skipped_count,
            failed_count=backfill_result.failed_count,
        )

        return backfill_result


def _planned_dates(plan: BootstrapPlan) -> list[str]:
    """Flatten deterministic planner chunks into unique ordered partitions."""
    return sorted(
        {
            partition_date
            for chunk in plan.chunks
            for partition_date in chunk.partition_dates
        }
    )


def _verifiable_payload(log: IngestionLog | None) -> tuple[str, int] | None:
    if (
        log is None
        or log.status is not IngestionStatus.SUCCESS
        or not isinstance(log.checksum, str)
        or not log.checksum
        or not isinstance(log.rows, int)
        or log.rows < 0
    ):
        return None
    return log.checksum, log.rows


__all__ = ["BackfillManager"]
