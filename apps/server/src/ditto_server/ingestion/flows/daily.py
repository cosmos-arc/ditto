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

使用 Prefect 原生依赖机制（@task + wait_for）实现声明式编排。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from prefect import flow, task

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
    pass


@task(name="check_trading_day")
def check_trading_day(trade_date: str, data_root: str) -> bool:
    """
    检查指定日期是否为交易日。

    Args:
        trade_date: 交易日期 (YYYY-MM-DD)
        data_root: DataHub 根目录

    Returns:
        是否为交易日

    """
    from ditto_datahub import DataHub  # noqa: PLC0415

    hub = DataHub(data_root=data_root)
    try:
        return hub.calendar.is_trading_day(trade_date)
    finally:
        hub.close()


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

    使用 Prefect 原生依赖机制（@task + wait_for）实现声明式编排。

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
    # 1. 检查交易日
    is_trading = check_trading_day(trade_date=trade_date, data_root=data_root)

    # 如果非交易日，直接返回
    if not is_trading:
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

    # 2. 提交 T0 任务（并行执行）
    t0_datasets = get_datasets_by_tier(TaskTier.T0_META)
    t0_futures = []
    for dataset in t0_datasets:
        t0_task = create_ingest_task_t0(dataset)  # type: ignore[assignment, attr-defined]
        future = t0_task.submit(
            trade_date=trade_date,
            source=source,
            data_root=data_root,
            force=force,
        )
        t0_futures.append(future)

    # 3. 提交 T1 任务（并行执行，等待 T0 完成）
    t1_datasets = get_datasets_by_tier(TaskTier.T1_INCREMENTAL)
    t1_futures = []

    # T1 日行情任务
    for dataset in t1_datasets:
        t1_task = create_ingest_task_t1_bars(dataset)  # type: ignore[assignment, attr-defined]
        future = t1_task.submit(
            trade_date=trade_date,
            source=source,
            data_root=data_root,
            force=force,
            wait_for=t0_futures,  # 等待所有 T0 任务完成
        )
        t1_futures.append(future)

    # T1 复权因子任务
    adj_datasets = [Dataset.ADJ_FACTOR, Dataset.FUND_ADJ]
    for dataset in adj_datasets:
        t1_adj_task = create_ingest_task_t1_adj(dataset)  # type: ignore[assignment, attr-defined]
        future = t1_adj_task.submit(
            trade_date=trade_date,
            source=source,
            data_root=data_root,
            force=force,
            wait_for=t0_futures,  # 等待所有 T0 任务完成
        )
        t1_futures.append(future)

    # 4. 收集结果
    t0_results = {}
    for future in t0_futures:
        result = future.result()
        dataset_name = result.get("dataset", "unknown")
        t0_results[dataset_name] = result

    t1_results = {}
    for future in t1_futures:
        result = future.result()
        dataset_name = result.get("dataset", "unknown")
        t1_results[dataset_name] = result

    # 5. 触发 DQC（TODO: 待实现）
    dqc_results = {
        "trade_date": trade_date,
        "status": "skipped",
        "message": "DQC 检查待实现",
    }

    # 6. 汇总统计
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
