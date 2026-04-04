"""
Prefect Tasks for data ingestion.

该模块提供数据摄取的 Prefect 任务，使用工厂函数模式。
"""

# DQ 检查任务
from ditto_interfaces.jobs.tasks.dq_batch import dq_batch_check, dq_completeness_check

# 新式任务工厂
from ditto_interfaces.jobs.tasks.monitoring import monitor_ingestion_quality

# T1 任务工厂别名
# 直接从 t0_meta 导入 create_ingest_task，为 T1 数据集创建别名
# 这样可以避免创建空的 wrapper 文件
from ditto_interfaces.jobs.tasks.t0_meta import create_ingest_task
from ditto_interfaces.jobs.tasks.t0_meta import (
    create_ingest_task as create_ingest_task_t0,
)

create_ingest_task_t1_adj = create_ingest_task
create_ingest_task_t1_bars = create_ingest_task

__all__ = [
    # 新式任务工厂
    "create_ingest_task_t0",
    "create_ingest_task_t1_adj",
    "create_ingest_task_t1_bars",
    # DQ 检查
    "dq_batch_check",
    "dq_completeness_check",
    # 监控任务
    "monitor_ingestion_quality",
]
