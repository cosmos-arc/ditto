"""
修补 Flow。

该模块实现数据修补功能：
- 重试失败任务
- 扫描并修补数据空洞
- 每日修补流程
"""

from __future__ import annotations

from typing import cast

from ditto_application.processes.ingestion.sparse_recovery_models import (
    SparsePITReattestationRequest,
)
from prefect import flow

from ditto_apps.registry import create_ingestion_bundle

__all__ = [
    "daily_repair_flow",
    "repair_holes_flow",
    "retry_failed_flow",
    "run_sparse_pit_reattestation",
    "sparse_pit_reattestation_flow",
]


def run_sparse_pit_reattestation(
    *,
    dataset: str,
    signal_date: str,
    source: str = "tushare",
) -> dict[str, object]:
    """Run application-owned full-history sparse PIT recovery synchronously."""
    with create_ingestion_bundle(source=source) as bundle:
        result = bundle.sparse_pit_reattestation.run(
            SparsePITReattestationRequest(
                dataset=dataset,
                source=source,
                signal_date=signal_date,
            )
        )
    return result.to_dict()


@flow(
    name="sparse-pit-reattestation",
    description="全量重摄取稀疏 PIT 历史并重建可验证 L1/L2 证据",
)
def sparse_pit_reattestation_flow(
    dataset: str,
    signal_date: str,
    source: str = "tushare",
) -> dict[str, object]:
    """Schedule the same sparse recovery used by the synchronous ops CLI."""
    result = run_sparse_pit_reattestation(
        dataset=dataset,
        signal_date=signal_date,
        source=source,
    )
    if result.get("passed") is not True:
        error = result.get("error")
        error_code = error if isinstance(error, str) else "SPARSE_REATTEST_FAILED"
        raise RuntimeError(error_code)
    return result


@flow(name="retry-failed", description="重试失败任务")
def retry_failed_flow(
    dataset: str,
    max_attempts: int = 3,
    limit: int = 10,
    source: str = "tushare",
) -> dict[str, object]:
    """
    重试失败任务流程。

    Args:
        dataset: 数据集名称（如 "stock_daily"）
        max_attempts: 最大尝试次数筛选条件
        limit: 重试的最大任务数量
        source: 数据源名称

    Returns:
        重试结果字典

    """
    with create_ingestion_bundle(source=source) as bundle:
        # 执行重试
        result = bundle.retry_manager.retry_failed(
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
            "message": (
                f"重试完成: {result.success_count}/{result.retried_count} 成功"
            ),
        }


@flow(name="repair-holes", description="扫描并修补数据空洞")
def repair_holes_flow(
    dataset: str,
    source: str = "tushare",
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
        parallel: 并行度

    Returns:
        修补结果字典

    """
    with create_ingestion_bundle(source=source) as bundle:
        # 回补缺失数据
        result = bundle.backfill_manager.backfill_missing(
            dataset=dataset,
            source=source,
            parallel=parallel,
        )

        return {
            "dataset": result.dataset,
            "holes_count": result.total_dates,
            "repaired_count": result.success_count,
            "failed_count": result.failed_count,
            "message": (
                f"修补完成: {result.success_count} 个空洞已修补"
                if result.total_dates > 0
                else "没有发现空洞"
            ),
        }


@flow(name="daily-repair", description="每日修补流程")
def daily_repair_flow(
    datasets: list[str] | None = None,
    max_attempts: int = 3,
    retry_limit: int = 10,
    source: str = "tushare",
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
        parallel: 并行度

    Returns:
        修补结果汇总

    """
    # 默认数据集列表
    if datasets is None:
        datasets = ["etf_daily", "stock_daily", "adj_factor", "fund_adj"]

    retry_results: dict[str, dict[str, object]] = {}
    holes_results: dict[str, dict[str, object]] = {}

    for dataset in datasets:
        # 1. 重试失败任务
        retry_result = retry_failed_flow(
            dataset=dataset,
            max_attempts=max_attempts,
            limit=retry_limit,
            source=source,
        )
        retry_results[dataset] = retry_result

        # 2. 修补空洞
        holes_result = repair_holes_flow(
            dataset=dataset,
            source=source,
            parallel=parallel,
        )
        holes_results[dataset] = holes_result

    # 汇总结果
    total_retried = sum(
        cast(int, r.get("retried_count", 0)) for r in retry_results.values()
    )
    total_repaired = sum(
        cast(int, r.get("repaired_count", 0)) for r in holes_results.values()
    )

    return {
        "retry_result": retry_results,
        "holes_result": holes_results,
        "summary": {
            "datasets": datasets,
            "total_retried": total_retried,
            "total_repaired": total_repaired,
            "message": (
                f"修补完成: 重试 {total_retried} 个任务, 修补 {total_repaired} 个空洞"
            ),
        },
    }
