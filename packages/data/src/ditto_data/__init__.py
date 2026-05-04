"""Ditto 数据模块 — 数据层统一入口."""

# Data Facade 已在 v0.15.0 移除
# App 层现在直接注入 Domain Services

# 导出 Data Provider Protocol（从 ditto-data 合并）
from ditto_data.events import DataIngested, QualityCheckCompleted
from ditto_data.provider import BarQuery, DataProvider, InstrumentQuery

__all__ = [
    "BarQuery",
    "DataIngested",
    "DataProvider",
    "InstrumentQuery",
    "QualityCheckCompleted",
]
