"""
Prefect Tasks for data ingestion.

该模块提供数据摄取的 Prefect 任务，使用工厂函数模式。
"""

# 新式任务工厂
from ditto_port.jobs.tasks.monitoring import monitor_ingestion_quality
from ditto_port.jobs.tasks.t0_meta import (
    create_ingest_task as create_ingest_task_t0,
)
from ditto_port.jobs.tasks.t1_adj_factor import (
    create_ingest_task as create_ingest_task_t1_adj,
)
from ditto_port.jobs.tasks.t1_bars import (
    create_ingest_task as create_ingest_task_t1_bars,
)

__all__ = [
    # 新式任务工厂
    "create_ingest_task_t0",
    "create_ingest_task_t1_adj",
    "create_ingest_task_t1_bars",
    # 监控任务
    "monitor_ingestion_quality",
]
