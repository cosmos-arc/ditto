"""
Data stores module - CQRS Reader/Writer 模式.

本模块提供数据访问层的基础设施。

架构：
- stores/base/: 通用存储实现（ParquetStore, SQLiteStore）
- stores/metadata/: 元数据子域，采用 CQRS Reader/Writer 模式
  - calendar/: 交易日历 (CalendarReader/CalendarWriter)
  - instrument/: 证券标识 (InstrumentReader/InstrumentWriter)
  - industry/: 行业分类 (IndustryMappingReader/IndustryMappingWriter, etc.)
  - universe/: 证券集合 (UniverseReader/UniverseWriter)
- stores/market/: 市场数据子域
  - stock/: 股票数据 (StockBarsReader/StockBarsWriter, etc.)
  - etf/: ETF 数据 (EtfBarsReader/EtfBarsWriter, etc.)
  - index/: 指数数据 (IndexBarsReader/IndexBarsWriter, etc.)
- sqlite_client.py: SQLite 客户端封装

CQRS 迁移历史：
- CalendarStore → CalendarReader/CalendarWriter
- InstrumentStore → InstrumentReader/InstrumentWriter
- IdentityStore → IdentityReader/IdentityWriter
- UniverseStore → UniverseReader/UniverseWriter
- IndustryBasicStore → IndustryBasicReader/IndustryBasicWriter
- IndustryMappingStore → IndustryMappingReader/IndustryMappingWriter
- 各种 BarsStore → BarsReader/BarsWriter
- 各种 AdjFactorStore → AdjFactorReader/AdjFactorWriter
"""

from ditto_data.storage.sqlite_client import SQLiteClient

__all__ = [
    "SQLiteClient",
]
