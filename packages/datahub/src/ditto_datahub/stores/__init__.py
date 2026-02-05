"""
Data stores module.

注意：大部分 store 已迁移至 domains/ 或 runtime/ 目录。
本模块只保留基础设施和仍在使用的 store。
"""

# 基础抽象
from ditto_datahub.stores.base import BaseStore

# 仍在使用的 store
from ditto_datahub.stores.parquet_store_base import ParquetStoreBase
from ditto_datahub.stores.sqlite_client import SQLiteClient
from ditto_datahub.stores.universe_store import UniverseStore

# 已迁移（注释保留作为记录）:
# IndexWeightStore → domains/market/index/weight/
# IngestionLogStore → runtime/ingestion/ingestion_log_store.py
# QuarantineStore → runtime/quality/quarantine_store.py
# ComparisonStore → runtime/quality/comparison_store.py
# CalendarStore → domains/metadata/calendar/calendar_store.py
# AdjFactorStore → domains/market/*/adj/adj_factor_store.py
# BarsStore → domains/market/*/bars/bars_store.py

__all__ = [
    "BaseStore",
    "ParquetStoreBase",
    "SQLiteClient",
    "UniverseStore",
]
