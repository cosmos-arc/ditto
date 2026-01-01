"""
Prefect flows for data ingestion.

该模块提供数据摄取的 Prefect Flows：
- daily_ingestion_flow: 每日增量摄取（新版）
- backfill_flow: 全量回补
- backfill_missing_flow: 回补缺失数据
- retry_failed_flow: 重试失败任务
- repair_holes_flow: 修补数据空洞
- daily_repair_flow: 每日修补流程
- daily_ingest_flow: 每日摄取（旧版，向后兼容）
- scheduled_daily_ingest_flow: 定时调度摄取
- create_weekday_schedule: 创建工作日调度
"""

# 新版 flows（基于 IngestionCoordinator）
from ditto_server.ingestion.flows.backfill import (
    backfill_flow,
    backfill_missing_flow,
)
from ditto_server.ingestion.flows.daily import daily_ingestion_flow

# 旧版 flows（向后兼容）
from ditto_server.ingestion.flows.daily_ingest import (
    daily_ingest_flow as daily_ingest_flow_old,
)
from ditto_server.ingestion.flows.repair import (
    daily_repair_flow,
    repair_holes_flow,
    retry_failed_flow,
)
from ditto_server.ingestion.flows.scheduled_ingest import (
    create_weekday_schedule,
    scheduled_daily_ingest_flow,
)

__all__ = [
    "backfill_flow",
    "backfill_missing_flow",
    "create_weekday_schedule",
    "daily_ingest_flow_old",
    "daily_ingestion_flow",
    "daily_repair_flow",
    "repair_holes_flow",
    "retry_failed_flow",
    "scheduled_daily_ingest_flow",
]
