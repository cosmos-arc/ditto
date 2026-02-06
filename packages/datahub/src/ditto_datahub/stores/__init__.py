"""
Data stores module.

本模块只保留基础设施和仍在使用的 store。

架构：
- stores/base/: 基础抽象和通用存储实现（BaseStore, ParquetStore, SQLiteStore）
- sqlite_client.py: SQLite 客户端封装

已迁移（注释保留作为记录）:
- IndexWeightStore → domains/market/index/weight/
- UniverseStore → domains/metadata/universe/
- IngestionLogStore → runtime/ingestion/ingestion_log_store.py
- QuarantineStore → runtime/quality/quarantine_store.py
- ComparisonStore → runtime/quality/comparison_store.py
- CalendarStore → domains/metadata/calendar/calendar_store.py
- AdjFactorStore → domains/market/*/adj/adj_factor_store.py
- BarsStore → domains/market/*/bars/bars_store.py
- ParquetStoreBase → 已合并到 base/parquet_store.py
"""

# 基础抽象
from ditto_datahub.stores.base import BaseStore, MergeResult, ParquetStore

# 仍在使用的 store
from ditto_datahub.stores.sqlite_client import SQLiteClient

__all__ = [
    "BaseStore",
    "MergeResult",
    "ParquetStore",
    "SQLiteClient",
]
