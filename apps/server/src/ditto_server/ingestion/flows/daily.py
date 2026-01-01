"""
每日增量摄取 Flow。

该模块实现 T0 → T1 → T3 的依赖编排：
- T0: 元数据任务（calendar, stock_basic, etf_basic）
- T1: 增量任务（etf_daily, stock_daily, adj_factor, fund_adj）
- T3: 数据质量检查

Flow 功能：
- 非交易日跳过逻辑
- 汇总所有结果
- 触发 DQC 检查
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from prefect import flow

from ditto_server.ingestion.config.datasets import (
    Dataset,
    TaskTier,
    get_datasets_by_tier,
)
from ditto_server.ingestion.tasks import (
    create_ingest_task_t0,
    create_ingest_task_t1_adj,
    create_ingest_task_t1_bars,
)

if TYPE_CHECKING:
    from collections.abc import Callable


@flow(name="daily-ingestion", description="每日增量数据摄取流程")
def daily_ingestion_flow(
    trade_date: str,
    source: str = "tushare",
    data_root: str = "data",
    force: bool = False,
) -> dict[str, object]:
    """
    每日增量数据摄取流程。

    该流程实现 T0 → T1 → T3 的依赖编排：
    1. 验证交易日
    2. 执行 T0 元数据任务（并行）
    3. 执行 T1 增量任务（并行，依赖 T0）
    4. 触发 T3 数据质量检查

    Args:
        trade_date: 交易日期 (YYYY-MM-DD)
        source: 数据源名称
        data_root: DataHub 根目录
        force: 是否强制重新摄取

    Returns:
        摄取结果字典，包含：
        - trade_date: 交易日期
        - skipped: 是否跳过（非交易日）
        - reason: 跳过原因
        - t0_results: T0 任务结果
        - t1_results: T1 任务结果
        - dqc_results: DQC 检查结果
        - summary: 汇总统计

    """
    from ditto_datahub import DataHub  # noqa: PLC0415

    # 1. 验证交易日
    hub = DataHub(data_root=data_root)
    try:
        if not hub.calendar.is_trading_day(trade_date):
            return {
                "trade_date": trade_date,
                "skipped": True,
                "reason": "非交易日",
                "t0_results": {},
                "t1_results": {},
                "dqc_results": {},
                "summary": {
                    "trade_date": trade_date,
                    "total_tasks": 0,
                    "success_count": 0,
                    "failed_count": 0,
                    "skipped_count": 0,
                },
            }
    finally:
        hub.close()

    # 2. 执行 T0 任务（并行）
    t0_datasets = get_datasets_by_tier(TaskTier.T0_META)
    t0_results = _execute_tier_tasks(
        datasets=t0_datasets,
        trade_date=trade_date,
        source=source,
        data_root=data_root,
        force=force,
        task_factory=create_ingest_task_t0,
    )

    # 3. 执行 T1 任务（并行，依赖 T0）
    t1_datasets = get_datasets_by_tier(TaskTier.T1_INCREMENTAL)
    t1_results = _execute_tier_tasks(
        datasets=t1_datasets,
        trade_date=trade_date,
        source=source,
        data_root=data_root,
        force=force,
        task_factory=create_ingest_task_t1_bars,
    )

    # 执行 adj_factor 和 fund_adj（T1）
    adj_datasets = [Dataset.ADJ_FACTOR, Dataset.FUND_ADJ]
    for dataset in adj_datasets:
        task = create_ingest_task_t1_adj(dataset)
        try:
            result = task(
                trade_date=trade_date,
                source=source,
                data_root=data_root,
                force=force,
            )
            t1_results[dataset.value] = result
        except Exception as e:
            t1_results[dataset.value] = {
                "status": "failed",
                "error": str(e),
            }

    # 4. 触发 DQC 检查
    dqc_results = _trigger_dqc(trade_date=trade_date)

    # 5. 汇总结果
    all_results = {**t0_results, **t1_results}
    success_count = sum(1 for r in all_results.values() if r.get("status") == "success")
    failed_count = sum(1 for r in all_results.values() if r.get("status") == "failed")
    skipped_count = sum(1 for r in all_results.values() if r.get("status") == "skipped")

    summary = {
        "trade_date": trade_date,
        "total_tasks": len(all_results),
        "success_count": success_count,
        "failed_count": failed_count,
        "skipped_count": skipped_count,
    }

    return {
        "trade_date": trade_date,
        "skipped": False,
        "reason": None,
        "t0_results": t0_results,
        "t1_results": t1_results,
        "dqc_results": dqc_results,
        "summary": summary,
    }


def _execute_tier_tasks(  # noqa: PLR0913
    datasets: list[Dataset],
    trade_date: str,
    source: str,
    data_root: str,
    force: bool,
    task_factory: Callable[[Dataset], Any],
) -> dict[str, Any]:
    """
    执行指定层级的所有任务。

    Args:
        datasets: 数据集列表
        trade_date: 交易日期
        source: 数据源
        data_root: 数据根目录
        force: 是否强制
        task_factory: 任务工厂函数

    Returns:
        数据集名称到结果的映射

    """
    results = {}

    for dataset in datasets:
        task = task_factory(dataset)
        try:
            result = task(
                trade_date=trade_date,
                source=source,
                data_root=data_root,
                force=force,
            )
            results[dataset.value] = result
        except Exception as e:
            results[dataset.value] = {
                "status": "failed",
                "error": str(e),
            }

    return results


def _trigger_dqc(trade_date: str) -> dict[str, object]:
    """
    触发数据质量检查。

    Args:
        trade_date: 交易日期

    Returns:
        DQC 检查结果

    """
    # TODO: 实现 DQC 检查逻辑
    # 目前返回占位符
    return {
        "trade_date": trade_date,
        "status": "skipped",
        "message": "DQC 检查待实现",
    }
