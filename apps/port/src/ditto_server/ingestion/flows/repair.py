"""
修补 Flow。

该模块实现数据修补功能：
- 重试失败任务
- 扫描并修补数据空洞
- 每日修补流程
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from prefect import flow

from ditto_server.ingestion.services.retry import RetryManager

if TYPE_CHECKING:
    pass


@flow(name="retry-failed", description="重试失败任务")
def retry_failed_flow(
    dataset: str,
    max_attempts: int = 3,
    limit: int = 10,
    source: str = "tushare",
    data_root: str = "data",
) -> dict[str, object]:
    """
    重试失败任务流程。

    Args:
        dataset: 数据集名称（如 "stock_daily"）
        max_attempts: 最大尝试次数筛选条件
        limit: 重试的最大任务数量
        source: 数据源名称
        data_root: DataHub 根目录

    Returns:
        重试结果字典

    """
    from ditto_datahub import DataHub  # noqa: PLC0415

    from ditto_server.ingestion.services.coordinator import (  # noqa: PLC0415
        IngestionCoordinator,
    )

    hub = DataHub(data_root=data_root)

    try:
        # 获取数据源
        data_source = hub.sources.get(source)

        # 创建协调器
        coordinator = IngestionCoordinator(
            hub=hub,
            source=data_source,
            source_name=source,
        )

        # 创建重试管理器
        retry_manager = RetryManager(
            coordinator=coordinator,
            ingestion_log_store=hub.ingestion_log,
            source=source,
        )

        # 执行重试
        result = retry_manager.retry_failed(
            dataset=dataset,
            max_attempts=max_attempts,
            limit=limit,
        )

        return {
            "dataset": result.dataset,
            "total_failed": result.total_failed,
            "retried_count": result.retried_count,
            "success_count": result.success_count,
            "still_failed_count": result.still_failed_count,
            "message": f"重试完成: {result.success_count}/{result.retried_count} 成功",
        }
    finally:
        hub.close()


@flow(name="repair-holes", description="扫描并修补数据空洞")
def repair_holes_flow(
    dataset: str,
    source: str = "tushare",
    data_root: str = "data",
    parallel: int = 1,
) -> dict[str, object]:
    """
    扫描并修补数据空洞流程。

    该流程会：
    1. 获取日历中的所有交易日
    2. 对比已摄取日期，找出空洞
    3. 回补空洞日期

    Args:
        dataset: 数据集名称
        source: 数据源名称
        data_root: DataHub 根目录
        parallel: 并行度

    Returns:
        修补结果字典

    """
    from ditto_datahub import DataHub  # noqa: PLC0415

    from ditto_server.ingestion.services.backfill import (  # noqa: PLC0415
        BackfillManager,
    )
    from ditto_server.ingestion.services.coordinator import (  # noqa: PLC0415
        IngestionCoordinator,
    )

    hub = DataHub(data_root=data_root)

    try:
        # 获取数据源
        data_source = hub.sources.get(source)

        # 创建协调器
        coordinator = IngestionCoordinator(
            hub=hub,
            source=data_source,
            source_name=source,
        )

        # 创建回补管理器
        backfill_manager = BackfillManager(
            coordinator=coordinator,
            calendar_store=hub.calendar_store,
            ingestion_log_store=hub.ingestion_log,
        )

        # 回补缺失数据
        result = backfill_manager.backfill_missing(
            dataset=dataset,
            parallel=parallel,
        )

        return {
            "dataset": result.dataset,
            "holes_count": result.total_dates,
            "repaired_count": result.success_count,
            "failed_count": result.failed_count,
            "message": (
                f"修补完成: {result.success_count}/{result.total_dates} 个空洞已修补"
                if result.total_dates > 0
                else "没有发现空洞"
            ),
        }
    finally:
        hub.close()


@flow(name="daily-repair", description="每日修补流程")
def daily_repair_flow(  # noqa: PLR0913
    datasets: list[str] | None = None,
    max_attempts: int = 3,
    retry_limit: int = 10,
    source: str = "tushare",
    data_root: str = "data",
    parallel: int = 1,
) -> dict[str, object]:
    """
    每日修补流程。

    该流程运行两个步骤：
    1. 重试失败的任务
    2. 扫描并修补数据空洞

    适合每日凌晨运行。

    Args:
        datasets: 要修补的数据集列表，默认为 None（所有数据集）
        max_attempts: 重试的最大尝试次数
        retry_limit: 重试的最大任务数
        source: 数据源名称
        data_root: DataHub 根目录
        parallel: 并行度

    Returns:
        修补结果汇总

    """
    from ditto_datahub import DataHub  # noqa: PLC0415

    hub = DataHub(data_root=data_root)

    try:
        # 默认数据集列表
        if datasets is None:
            datasets = ["etf_daily", "stock_daily", "adj_factor", "fund_adj"]

        retry_results = {}
        holes_results = {}

        for dataset in datasets:
            # 1. 重试失败任务
            retry_result = retry_failed_flow(
                dataset=dataset,
                max_attempts=max_attempts,
                limit=retry_limit,
                source=source,
                data_root=data_root,
            )
            retry_results[dataset] = retry_result

            # 2. 修补空洞
            holes_result = repair_holes_flow(
                dataset=dataset,
                source=source,
                data_root=data_root,
                parallel=parallel,
            )
            holes_results[dataset] = holes_result

        # 汇总结果
        total_retried = sum(r.get("retried_count", 0) for r in retry_results.values())
        total_repaired = sum(r.get("repaired_count", 0) for r in holes_results.values())

        return {
            "retry_result": retry_results,
            "holes_result": holes_results,
            "summary": {
                "datasets": datasets,
                "total_retried": total_retried,
                "total_repaired": total_repaired,
                "message": (
                    f"修补完成: 重试 {total_retried} 个任务, "
                    f"修补 {total_repaired} 个空洞"
                ),
            },
        }
    finally:
        hub.close()
