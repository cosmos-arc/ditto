"""
Prefect flows for data ingestion.

该模块提供数据摄取的 Prefect Flows：
- daily_ingestion_flow: 每日增量摄取
- backfill_flow: 全量回补
- backfill_missing_flow: 回补缺失数据
- retry_failed_flow: 重试失败任务
- repair_holes_flow: 修补数据空洞
- daily_repair_flow: 每日修补流程
"""

# 新版 flows（基于 IngestionCoordinator）
from ditto_port.jobs.flows.backfill import (
    backfill_flow,
    backfill_missing_flow,
)
from ditto_port.jobs.flows.daily import daily_ingestion_flow
from ditto_port.jobs.flows.repair import (
    daily_repair_flow,
    repair_holes_flow,
    retry_failed_flow,
)

__all__ = [
    "backfill_flow",
    "backfill_missing_flow",
    "daily_ingestion_flow",
    "daily_repair_flow",
    "repair_holes_flow",
    "retry_failed_flow",
]
