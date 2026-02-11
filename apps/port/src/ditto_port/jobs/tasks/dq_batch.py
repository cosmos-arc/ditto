"""L3 统计异常检测的 DQ 批量检查任务."""

from typing import Any, Literal

from ditto_core.quality.spec import DQIssue
from ditto_datahub.services.market_service import MarketBarsQuery
from ditto_foundation import M, logger
from prefect import task

from ditto_port.jobs.context import (
    create_dq_and_metadata_context,
)
from ditto_port.services.ingestion.quality import L3BatchService


@task(
    name="dq-batch-check",
    description="批量数据质量检查(L3 统计异常)",
    tags=["dq", "batch", "l3"],
)
async def dq_batch_check(  # noqa: C901 - 端到端业务流程，保持单一函数以维持可读性
    trade_date: str | None = None,
    datasets: list[str] | None = None,
    market_wide: bool = False,
) -> dict[str, Any]:
    """
    执行 L3 批量检查任务。

    这是一个完整的端到端业务流程，包括：
    1. 初始化服务和上下文
    2. 遍历数据集执行检查
    3. 汇总结果和指标
    4. 发送告警通知

    拆分为子函数会：
    - 增加状态传递复杂性
    - 降低流程可读性
    - 分散相关逻辑

    Args:
        trade_date: 交易日期(YYYY-MM-DD)，默认为最后一个交易日
        datasets: 要检查的数据集列表，默认为常用数据集
        market_wide: 是否使用全市场查询模式

    Returns:
        检查结果摘要

    """
    logger.info(
        "Starting DQ batch check",
        event="dq_batch_start",
        trade_date=trade_date,
        datasets=datasets,
        market_wide=market_wide,
    )

    with create_dq_and_metadata_context() as (engine, metadata_service, market_service):
        # 获取最后一个交易日
        if trade_date is None:
            trade_date = metadata_service.get_last_trading_day()
            logger.info(
                "Using last trading day",
                event="dq_batch_date_resolved",
                trade_date=trade_date,
            )

        # 类型收窄：确保 trade_date 不是 None（用于后续类型检查）
        if trade_date is None:
            raise ValueError("Failed to resolve trade_date")

        # 默认数据集
        if datasets is None:
            datasets = ["etf_daily", "index_daily", "stock_daily", "adj_factor"]

        # 初始化 L3 Batch Service
        l3_service = L3BatchService(
            engine=engine,
            market_service=market_service,
            metadata_service=metadata_service,
        )

        all_issues: list[DQIssue] = []
        results_by_dataset: dict[str, dict[str, Any]] = {}

        # 定义 dataset 到 asset_class 的映射
        dataset_asset_class: dict[str, Literal["stock", "etf", "index"]] = {
            "stock_daily": "stock",
            "etf_daily": "etf",
            "index_daily": "index",
            "adj_factor": "stock",
            "fund_adj": "etf",
        }

        # 执行 L3 检查
        for dataset in datasets:
            try:
                # 推断 asset_class
                asset_class = dataset_asset_class.get(dataset)
                if asset_class is None:
                    raise ValueError(f"Unknown dataset: {dataset}")

                result = l3_service.check_dataset(
                    dataset=dataset,
                    trade_date=trade_date,
                    asset_class=asset_class,
                    market_wide=market_wide,
                )

                results_by_dataset[dataset] = {
                    "passed": result["passed"],
                    "issue_count": result.get("issue_count", 0),
                    "alert_count": result.get("alert_count", 0),
                }

                # 收集 issues（如果有）
                if "issues" in result:
                    all_issues.extend(result["issues"])

                if result.get("alert_count", 0) > 0:
                    logger.warning(
                        "L3 DQ issues found",
                        event="dq_batch_issues",
                        dataset=dataset,
                        count=result.get("issue_count", 0),
                    )

            except (ValueError, TypeError, KeyError, AttributeError) as e:
                # 已知的数据处理异常
                logger.warning(
                    "dq_batch_known_error",
                    event="dq_batch_error",
                    dataset=dataset,
                    error_type=type(e).__name__,
                    error=str(e),
                )
            except Exception as e:
                # 未知异常
                logger.exception(
                    "dq_batch_unknown_error",
                    event="dq_batch_error",
                    dataset=dataset,
                    error_type=type(e).__name__,
                )
                results_by_dataset[dataset] = {
                    "passed": False,
                    "issue_count": 0,
                    "alert_count": 0,
                    "error": str(e),
                }

        # 汇总结果
        total_issues = len(all_issues)
        alert_count = sum(1 for i in all_issues if i.severity.value == "alert")

        summary = {
            "trade_date": trade_date,
            "datasets_checked": datasets,
            "total_issues": total_issues,
            "alert_count": alert_count,
            "results_by_dataset": results_by_dataset,
        }

        logger.info(
            "DQ batch check complete",
            event="dq_batch_complete",
            **summary,
        )

        # 如果有告警，发送通知
        if alert_count > 0:
            _send_dq_alert(trade_date, all_issues)

        # 记录指标
        M.dq_batch_checks.add(1.0, {"trade_date": trade_date})
        M.dq_batch_issues.add(float(total_issues), {"trade_date": trade_date})
        M.dq_batch_alerts.add(float(alert_count), {"trade_date": trade_date})

        return summary


def _send_dq_alert(trade_date: str, issues: list[Any]) -> None:
    """
    发送 DQ 告警通知。

    Args:
        trade_date: 交易日期
        issues: 问题列表

    """
    # TODO: 实现告警发送逻辑(邮件、钉钉、企业微信等)
    logger.warning(
        "DQ alert notification",
        event="dq_alert",
        trade_date=trade_date,
        issue_count=len(issues),
        issues=[
            {"level": i.level.value, "rule": i.rule_name, "message": i.message}
            for i in issues
        ],
    )


@task(
    name="dq-completeness-check",
    description="数据完整性检查",
    tags=["dq", "completeness"],
)
def dq_completeness_check(
    trade_date: str,
    dataset: str,
    expected_sids: list[int] | None = None,
    market_wide: bool = False,
) -> dict[str, Any]:
    """
    检查数据完整性。

    Args:
        trade_date: 交易日期
        dataset: 数据集名称
        expected_sids: 预期的 Instrument ID 列表
        market_wide: 是否使用全市场查询模式

    Returns:
        完整性检查结果

    """
    with create_dq_and_metadata_context() as (
        _engine,
        _metadata_service,
        market_service,
    ):
        # 读取实际数据
        query = MarketBarsQuery(
            start=trade_date,
            end=trade_date,
            market_wide=market_wide,
        )
        df = market_service.query(query)

        actual_sids = (
            df["instrument_id"].unique().to_list() if not df.is_empty() else []
        )

        # 计算缺失
        missing_sids: set[int]
        extra_sids: set[int]
        if expected_sids:
            missing_sids = set(expected_sids) - set(actual_sids)
            extra_sids = set(actual_sids) - set(expected_sids)
        else:
            missing_sids = set()
            extra_sids = set()

        result = {
            "trade_date": trade_date,
            "dataset": dataset,
            "expected_count": len(expected_sids) if expected_sids else None,
            "actual_count": len(actual_sids),
            "missing_count": len(missing_sids),
            "missing_sids": sorted(missing_sids),
            "extra_count": len(extra_sids),
            "extra_sids": sorted(extra_sids),
            "is_complete": len(missing_sids) == 0,
        }

        logger.info(
            "Completeness check complete",
            event="dq_completeness_complete",
            **result,
        )

        return result
