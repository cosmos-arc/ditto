"""
Prefect flows for data ingestion.

该模块提供数据摄取的 Prefect Flows：
- daily_ingestion_flow: 每日增量摄取
- eod_flow: EOD 编排（摄取 -> 物化 -> 策略）
- backfill_flow: 全量回补
- repair_holes_flow: 修补数据空洞
- daily_repair_flow: 每日修补流程
- retry_failed_flow: 重试失败任务
"""

from __future__ import annotations

from ditto_interfaces.jobs.flows.backfill import backfill_flow
from ditto_interfaces.jobs.flows.daily import daily_ingestion_flow
from ditto_interfaces.jobs.flows.eod import eod_flow
from ditto_interfaces.jobs.flows.repair import (
    daily_repair_flow,
    repair_holes_flow,
    retry_failed_flow,
)

__all__ = [
    "backfill_flow",
    "daily_ingestion_flow",
    "daily_repair_flow",
    "eod_flow",
    "repair_holes_flow",
    "retry_failed_flow",
]
