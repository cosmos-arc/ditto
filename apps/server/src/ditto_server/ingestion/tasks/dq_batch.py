"""DQ batch check tasks for L3 statistical anomaly detection."""

from pathlib import Path
from typing import Any

import ditto_datahub
from ditto_datahub import DataHub
from ditto_datahub.dq import DQEngine
from ditto_foundation import M, logger
from prefect import task


def get_default_dq_config_path() -> str:
    """
    获取默认 DQ 规则配置路径。

    Returns:
        指向 packages/datahub/config/dq_rules 的绝对路径字符串

    """
    package_root = Path(ditto_datahub.__file__).parent.parent.parent
    return str(package_root / "config" / "dq_rules")


@task(
    name="dq-batch-check",
    description="批量数据质量检查(L3 统计异常)",
    tags=["dq", "batch", "l3"],
)
def dq_batch_check(
    trade_date: str | None = None,
    datasets: list[str] | None = None,
    config_path: str | None = None,
) -> dict[str, Any]:
    """
    执行 L3 批量检查任务。

    Args:
        trade_date: 交易日期(YYYY-MM-DD)，默认为最后一个交易日
        datasets: 要检查的数据集列表，默认为常用数据集
        config_path: DQ 规则配置目录路径

    Returns:
        检查结果摘要

    """
    logger.info(
        "Starting DQ batch check",
        event="dq_batch_start",
        trade_date=trade_date,
        datasets=datasets,
    )

    hub = DataHub()

    # 获取最后一个交易日
    if trade_date is None:
        trade_date = hub.calendar.get_last_trading_day()
        logger.info(
            "Using last trading day",
            event="dq_batch_date_resolved",
            trade_date=trade_date,
        )

    # 默认数据集
    if datasets is None:
        datasets = ["etf_daily", "index_daily", "market_daily", "adj_factor"]

    # 初始化 DQ 引擎
    if config_path is None:
        config_path = get_default_dq_config_path()

    engine = DQEngine(config_path=config_path)

    all_issues = []
    results_by_dataset = {}

    # 执行 L3 检查
    for dataset in datasets:
        try:
            result = engine.check_statistical(
                dataset=dataset,
                trade_date=trade_date,
                hub=hub,
            )

            results_by_dataset[dataset] = {
                "passed": result.passed,
                "issue_count": len(result.issues),
                "alert_count": result.alert_count,
            }

            all_issues.extend(result.issues)

            if result.issues:
                logger.warning(
                    "L3 DQ issues found",
                    event="dq_batch_issues",
                    dataset=dataset,
                    count=len(result.issues),
                )

        except Exception as e:
            logger.error(
                "L3 DQ check failed",
                event="dq_batch_error",
                dataset=dataset,
                error=str(e),
            )
            results_by_dataset[dataset] = {
                "error": str(e),
            }

    # 汇总结果
    summary = {
        "trade_date": trade_date,
        "datasets_checked": datasets,
        "total_issues": len(all_issues),
        "alert_count": sum(1 for i in all_issues if i.severity.value == "alert"),
        "results_by_dataset": results_by_dataset,
    }

    logger.info(
        "DQ batch check complete",
        event="dq_batch_complete",
        **summary,
    )

    # 如果有告警，发送通知
    if summary["alert_count"] > 0:
        _send_dq_alert(trade_date, all_issues)

    # 记录指标
    M.dq_batch_checks.increment()
    M.dq_batch_issues.add(summary["total_issues"], {"trade_date": trade_date})
    M.dq_batch_alerts.add(summary["alert_count"], {"trade_date": trade_date})

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
) -> dict[str, Any]:
    """
    检查数据完整性。

    Args:
        trade_date: 交易日期
        dataset: 数据集名称
        expected_sids: 预期的 SID 列表

    Returns:
        完整性检查结果

    """
    hub = DataHub()

    # 读取实际数据
    df = hub.bars.get(
        start=trade_date,
        end=trade_date,
    )

    actual_sids = df["sid"].unique().to_list() if not df.is_empty() else []

    # 计算缺失
    if expected_sids:
        missing_sids = set(expected_sids) - set(actual_sids)
        extra_sids = set(actual_sids) - set(expected_sids)
    else:
        missing_sids = []
        extra_sids = []

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
