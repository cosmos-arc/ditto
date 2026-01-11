"""
T1 复权因子摄取任务工厂.

该模块提供 T1 层级（复权因子数据）摄取任务的工厂函数。
任务是轻量 wrapper，真正逻辑在 IngestionCoordinator。
"""

from __future__ import annotations

from ditto_port.ingestion.tasks.t0_meta import create_ingest_task

__all__ = ["create_ingest_task"]

# 直接从 t0_meta 导入工厂函数
# 所有数据集使用相同的工厂模式，只是配置不同
