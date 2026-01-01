"""
Prefect Tasks for data ingestion.

该模块提供数据摄取的 Prefect 任务，包括：
- 旧式任务：直接实现逻辑的任务（向后兼容）
- 新式任务：工厂函数生成的轻量 wrapper（推荐）
"""

# 新式任务工厂（推荐使用）
# 旧式任务（向后兼容，已废弃）
from ditto_server.ingestion.tasks.adj_factor import ingest_adj_factor, ingest_fund_adj
from ditto_server.ingestion.tasks.bars import ingest_etf_bars
from ditto_server.ingestion.tasks.monitoring import monitor_ingestion_quality
from ditto_server.ingestion.tasks.stock import ingest_stock_basic, ingest_stock_daily
from ditto_server.ingestion.tasks.t0_meta import (
    create_ingest_task as create_ingest_task_t0,
)
from ditto_server.ingestion.tasks.t1_adj_factor import (
    create_ingest_task as create_ingest_task_t1_adj,
)
from ditto_server.ingestion.tasks.t1_bars import (
    create_ingest_task as create_ingest_task_t1_bars,
)

__all__ = [
    # 新式任务工厂
    "create_ingest_task_t0",
    "create_ingest_task_t1_adj",
    "create_ingest_task_t1_bars",
    # 旧式任务（已废弃）
    "ingest_adj_factor",
    "ingest_etf_bars",
    "ingest_fund_adj",
    "ingest_stock_basic",
    "ingest_stock_daily",
    "monitor_ingestion_quality",
]
