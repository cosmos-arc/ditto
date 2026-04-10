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

from __future__ import annotations

# 新版 flows（基于 IngestionCoordinator）
from ditto_interfaces.jobs.flows.backfill import (
    BackfillFlowConfig,
    backfill_flow,
    backfill_missing_flow,
)
from ditto_interfaces.jobs.flows.daily import daily_ingestion_flow
from ditto_interfaces.jobs.flows.materialization import (
    certify_publication_flow,
    daily_materialization_flow,
    deprecate_publication_flow,
    promote_publication_flow,
    repair_from_invalidation_flow,
    rollback_publication_flow,
    shadow_compare_flow,
    shadow_publish_flow,
)
from ditto_interfaces.jobs.flows.repair import (
    daily_repair_flow,
    repair_holes_flow,
    retry_failed_flow,
)
from ditto_interfaces.jobs.flows.research import research_dataset_build_flow

__all__ = [
    "BackfillFlowConfig",
    "backfill_flow",
    "backfill_missing_flow",
    "certify_publication_flow",
    "daily_ingestion_flow",
    "daily_materialization_flow",
    "daily_repair_flow",
    "deprecate_publication_flow",
    "promote_publication_flow",
    "repair_from_invalidation_flow",
    "repair_holes_flow",
    "research_dataset_build_flow",
    "retry_failed_flow",
    "rollback_publication_flow",
    "shadow_compare_flow",
    "shadow_publish_flow",
]
