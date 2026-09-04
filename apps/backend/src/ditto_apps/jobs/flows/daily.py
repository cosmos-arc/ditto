"""
每日增量摄取 Flow。

该模块实现 T0 → T1 → T3 的依赖编排：
- T0: 元数据任务（calendar, stock_basic, etf_basic）
- T1: 增量任务（etf_daily, stock_daily, stock_status, adj_factor, fund_adj）
- T3: 数据质量检查（覆盖所有有 DQ 规则的数据集）

Flow 功能：
- 非交易日跳过逻辑
- 汇总所有结果
- 触发 DQC 检查

使用 Prefect 原生依赖机制（@task + wait_for）实现声明式编排。
"""

from __future__ import annotations

from collections.abc import Iterable
from itertools import chain
from typing import Any, cast

from ditto_application.config import (
    IngestionScope,
    TaskTier,
    get_datasets_by_tier,
    get_parallel_datasets,
    resolve_ingestion_scope,
)
from ditto_application.processes.ingestion.result_handler import count_results
from prefect import flow, task
from prefect.futures import PrefectFuture

from ditto_apps.jobs.tasks import (
    create_ingest_task_t0,
    create_ingest_task_t1_adj,
    create_ingest_task_t1_bars,
    dq_batch_check,
)
from ditto_apps.jobs.tasks.dq_batch import run_dq_batch_check
from ditto_apps.jobs.tasks.t0_meta import run_ingest_dataset
from ditto_apps.registry import create_ingestion_bundle


def _collect_results(
    futures: list[PrefectFuture[dict[str, object]]],
) -> dict[str, dict[str, object]]:
    """
    从 Prefect futures 收集结果字典。

    Args:
        futures: Prefect Future 对象列表

    Returns:
        以数据集名称为键的结果字典。如果结果中没有 'dataset' 字段，
        则使用 'unknown' 作为键。

    """
    return _index_results(future.result() for future in futures)


def _index_results(
    raw_results: Iterable[dict[str, object]],
) -> dict[str, dict[str, object]]:
    """按 dataset 统一索引同步结果与 Prefect future 结果。"""
    results: dict[str, dict[str, object]] = {}
    for result in raw_results:
        dataset_name = cast(str, result.get("dataset", "unknown"))
        results[dataset_name] = result
    return results


def _dataset_value(dataset: object) -> str:
    value = getattr(dataset, "value", None)
    return value if isinstance(value, str) else ""


def _daily_ingestion_scope(
    required_datasets: tuple[str, ...] | None,
) -> IngestionScope:
    """Select the full daily registry or one dependency-closed strategy scope."""
    if required_datasets is not None:
        return resolve_ingestion_scope(required_datasets)
    return IngestionScope(
        t0_datasets=tuple(get_datasets_by_tier(TaskTier.T0_META)),
        t1_levels=tuple(
            tuple(level) for level in get_parallel_datasets(TaskTier.T1_INCREMENTAL)
        ),
    )


def run_check_trading_day(trade_date: str) -> bool:
    """执行交易日判断业务，供 Prefect task 与同步 CLI 共用。"""
    with create_ingestion_bundle() as bundle:
        return bundle.metadata_facade.is_trading_day(trade_date)


@task(name="check_trading_day")
def check_trading_day(trade_date: str) -> bool:
    """
    检查指定日期是否为交易日。

    Args:
        trade_date: 交易日期 (YYYY-MM-DD)

    Returns:
        是否为交易日

    """
    return run_check_trading_day(trade_date)


def _skipped_ingestion_result(trade_date: str) -> dict[str, object]:
    """构造非交易日稳定结果。"""
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


def _completed_ingestion_result(
    *,
    trade_date: str,
    t0_results: dict[str, dict[str, object]],
    t1_results: dict[str, dict[str, object]],
    dqc_results: dict[str, Any],
) -> dict[str, object]:
    """由同一业务结果构造同步与 Prefect 返回契约。"""
    all_results = {**t0_results, **t1_results}
    counts = count_results(all_results)
    return {
        "trade_date": trade_date,
        "skipped": False,
        "reason": None,
        "t0_results": t0_results,
        "t1_results": t1_results,
        "dqc_results": dqc_results,
        "summary": {
            "trade_date": trade_date,
            "total_tasks": len(all_results),
            "success_count": counts.success,
            "failed_count": counts.failed,
            "skipped_count": counts.skipped,
        },
    }


def run_daily_ingestion(
    trade_date: str,
    source: str = "tushare",
    force: bool = False,
    required_datasets: tuple[str, ...] | None = None,
) -> dict[str, object]:
    """顺序执行每日摄取业务，可限制为策略依赖闭包。"""
    if not run_check_trading_day(trade_date):
        return _skipped_ingestion_result(trade_date)

    scope = _daily_ingestion_scope(required_datasets)
    t0_results = _index_results(
        run_ingest_dataset(
            dataset=dataset,
            trade_date=trade_date,
            source=source,
            force=force,
        )
        for dataset in scope.t0_datasets
    )

    t1_results = _index_results(
        run_ingest_dataset(
            dataset=dataset,
            trade_date=trade_date,
            source=source,
            force=force,
        )
        for level in scope.t1_levels
        for dataset in level
    )
    ingestion_results = {**t0_results, **t1_results}
    dqc_results = run_dq_batch_check(
        trade_date=trade_date,
        datasets=list(ingestion_results),
        market_wide=True,
        ingestion_results=ingestion_results,
    )
    return _completed_ingestion_result(
        trade_date=trade_date,
        t0_results=t0_results,
        t1_results=t1_results,
        dqc_results=dqc_results,
    )


@flow(name="daily-ingestion", description="每日增量数据摄取流程")
def daily_ingestion_flow(
    trade_date: str,
    source: str = "tushare",
    force: bool = False,
    required_datasets: tuple[str, ...] | None = None,
) -> dict[str, object]:
    """
    每日增量数据摄取流程。

    该流程实现 T0 → T1 → T3 的依赖编排：
    1. 验证交易日
    2. 执行 T0 元数据任务（并行）
    3. 执行 T1 增量任务（并行，依赖 T0）
    4. 触发 T3 数据质量检查（覆盖所有有 DQ 规则的数据集）

    使用 Prefect 原生依赖机制（@task + wait_for）实现声明式编排。

    Args:
        trade_date: 交易日期 (YYYY-MM-DD)
        source: 数据源名称
        force: 是否强制重新摄取
        required_datasets: 显式策略依赖；提供时仅执行其依赖闭包。

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
    is_trading = check_trading_day(trade_date=trade_date)

    # 如果非交易日，直接返回
    if not is_trading:
        return _skipped_ingestion_result(trade_date)

    scope = _daily_ingestion_scope(required_datasets)

    # 2. 提交 T0 任务（并行执行）
    t0_futures: list[PrefectFuture[dict[str, object]]] = []
    for dataset in scope.t0_datasets:
        t0_task = create_ingest_task_t0(dataset)
        future = t0_task.submit(
            trade_date=trade_date,
            source=source,
            force=force,
        )
        t0_futures.append(future)

    # 3. 提交 T1 任务（按依赖层级并行执行）
    # T1 数据集按依赖关系分层：
    # - Level 0: etf_daily, stock_daily (只依赖 T0)
    # - Level 1: stock_status/adj_factor/fund_adj (依赖日行情数据)
    t1_futures: list[PrefectFuture[dict[str, object]]] = []
    level_futures: list[list[PrefectFuture[dict[str, object]]]] = []

    for level_idx, level in enumerate(scope.t1_levels):
        # 确定等待的任务：第一层等待 T0，后续层等待前面所有层
        if level_idx == 0:
            wait_for_futures = t0_futures
        else:
            # 收集前面所有层的 futures
            wait_for_futures = list(chain.from_iterable(level_futures))

        current_level_futures: list[PrefectFuture[dict[str, object]]] = []
        for dataset in level:
            # 根据数据集类型选择对应的 task 创建函数
            if _dataset_value(dataset) in {"adj_factor", "fund_adj"}:
                task = create_ingest_task_t1_adj(dataset)
            else:
                task = create_ingest_task_t1_bars(dataset)

            future = task.submit(
                trade_date=trade_date,
                source=source,
                force=force,
                wait_for=wait_for_futures,
            )
            current_level_futures.append(future)
            t1_futures.append(future)

        # 记录本层的 futures，供后续层依赖
        level_futures.append(current_level_futures)

    # 4. 收集结果
    t0_results = _collect_results(t0_futures)
    t1_results = _collect_results(t1_futures)
    ingestion_results = {**t0_results, **t1_results}

    # 5. 触发 DQC（等待 T1 任务完成）
    dqc_future: PrefectFuture[dict[str, Any]] = dq_batch_check.submit(  # pyright: ignore[reportCallIssue, reportUnknownMemberType, reportUnknownVariableType]
        trade_date=trade_date,
        datasets=list(ingestion_results),
        market_wide=True,
        ingestion_results=ingestion_results,
        wait_for=t1_futures,
    )
    dqc_results = cast(
        dict[str, Any],
        dqc_future.result(),  # pyright: ignore[reportUnknownMemberType]
    )

    # 6. 汇总统计
    return _completed_ingestion_result(
        trade_date=trade_date,
        t0_results=t0_results,
        t1_results=t1_results,
        dqc_results=dqc_results,
    )
