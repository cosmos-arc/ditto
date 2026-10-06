"""
例行 adj_factor 跨源对账任务（#515 A3）.

对账能力（#438）此前只有 CLI 手动入口（`ditto ops reconcile`）；本任务把
adj_factor 对账接入每日 T3 质量链：daily flow 在 dq_batch_check 之后提交，
无事件日正常通过（skip_reason=no_adjustment_events，见 handler），dump
缺失/陈旧、辅源未配置等无法对账的情形显式 skip 并留日志，不拖垮摄取
flow——辅源 fuyao 属可选数据源，其缺席降级为对账不可用，而非摄取失败。
"""

from __future__ import annotations

from typing import Any, cast

from ditto_application.commands.quality_reconciliation import (
    ReconcileSourcesCommand,
    ReconcileSourcesHandler,
)
from ditto_application.processes.quality.types import ReconciliationResult
from ditto_application.queries.market import MarketQueryFacade
from ditto_platform.foundation import logger
from prefect import task

from ditto_apps.jobs.context import create_prefect_host


def _run_reconciliation(trade_date: str) -> ReconciliationResult | None:
    """构建容器并执行对账；主源无存量返回 None（无可对账对象）。"""
    with create_prefect_host() as container:
        handler = container.get(ReconcileSourcesHandler)
        market = container.get(MarketQueryFacade)
        primary = market.get_adj_factors(
            start=trade_date,
            end=trade_date,
            allow_experimental_data=True,
        )
        if primary.is_empty():
            return None
        return handler.handle(
            ReconcileSourcesCommand(
                primary_df=primary,
                trade_date=trade_date,
                dataset="adj_factor",
            )
        )


def _serialize(
    reconciliation: ReconciliationResult,
) -> dict[str, Any]:
    """
    ReconciliationResult.to_dict 的例行链规范化.

    to_dict 的遗留形状把 ``skipped`` 映射成 skip_reason 字符串（非布尔、
    无独立键）；例行链结果键保持 ``skipped: bool`` + ``skip_reason: str``
    的显式形状，便于 flow 结果与日志消费。
    """
    payload = reconciliation.to_dict()
    payload["skipped"] = reconciliation.skipped
    payload["skip_reason"] = reconciliation.skip_reason
    return cast(dict[str, Any], payload)


def _skip_result(
    trade_date: str,
    *,
    passed: bool,
    reason: str,
) -> dict[str, Any]:
    """以 ReconciliationResult 为唯一契约形状构造 skip 结果."""
    return _serialize(
        ReconciliationResult(
            trade_date=trade_date,
            dataset="adj_factor",
            passed=passed,
            issue_count=0,
            skipped=True,
            skip_reason=reason,
        )
    )


def run_dq_reconcile_adj_factor(trade_date: str) -> dict[str, Any]:
    """Invoke the adj_factor reconciliation and serialize its result."""
    try:
        reconciliation = _run_reconciliation(trade_date)
    except Exception as error:
        # 例行链上的对账失败（辅源未配置/dump 缺失或陈旧、读取失败等）不
        # 拖垮摄取 flow：显式 skip 留痕，由告警/日志跟进
        logger.exception(
            "adj_factor reconciliation failed",
            event="dq_reconcile_failed",
            trade_date=trade_date,
            error_type=type(error).__name__,
        )
        return _skip_result(
            trade_date,
            passed=False,
            reason=f"{type(error).__name__}: {error!s}",
        )
    if reconciliation is None:
        # 目标日无因子存量（未摄取/非交易日）＝对账不可运行，非对账失败：
        # 缺数日告警由 dq_batch 的 adj_factor completeness（frame=historical）
        # 承担，这里只显式 skip 留痕。
        logger.info(
            "adj_factor reconciliation skipped: no primary data",
            event="dq_reconcile_skipped",
            trade_date=trade_date,
        )
        return _skip_result(
            trade_date,
            passed=True,
            reason="no_primary_data",
        )

    if reconciliation.passed:
        logger.info(
            "adj_factor reconciliation passed",
            event="dq_reconcile_complete",
            trade_date=trade_date,
            skipped=reconciliation.skipped,
            skip_reason=reconciliation.skip_reason,
            diff_count=reconciliation.diff_count,
        )
    else:
        logger.warning(
            "adj_factor reconciliation not passed",
            event="dq_reconcile_not_passed",
            trade_date=trade_date,
            comparable=reconciliation.comparable,
            diff_count=reconciliation.diff_count,
            issue_count=reconciliation.issue_count,
        )
    return _serialize(reconciliation)


@task(
    name="dq-reconcile-adj-factor",
    description="例行 adj_factor 跨源对账(主源 Tushare 因子 vs fuyao 事件)",
    tags=["dq", "reconcile", "adj-factor"],
)
async def dq_reconcile_adj_factor(trade_date: str) -> dict[str, Any]:
    """Prefect wrapper for :func:`run_dq_reconcile_adj_factor`."""
    return run_dq_reconcile_adj_factor(trade_date)
