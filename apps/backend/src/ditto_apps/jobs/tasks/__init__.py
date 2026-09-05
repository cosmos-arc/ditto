"""
Prefect Tasks for data ingestion.

该模块提供数据摄取的 Prefect 任务，使用工厂函数模式。
"""

from __future__ import annotations

from ditto_apps.jobs.tasks.aliases import (
    create_ingest_task_t1_adj,
    create_ingest_task_t1_bars,
)

# DQ 检查任务
from ditto_apps.jobs.tasks.dq_batch import dq_batch_check, dq_completeness_check

# 监控任务
from ditto_apps.jobs.tasks.monitoring import monitor_ingestion_quality

# T0/T1 任务工厂
from ditto_apps.jobs.tasks.t0_meta import (
    create_ingest_task as create_ingest_task_t0,
)

__all__ = [
    # 任务工厂
    "create_ingest_task_t0",
    "create_ingest_task_t1_adj",
    "create_ingest_task_t1_bars",
    # DQ 检查
    "dq_batch_check",
    "dq_completeness_check",
    # 监控任务
    "monitor_ingestion_quality",
]
