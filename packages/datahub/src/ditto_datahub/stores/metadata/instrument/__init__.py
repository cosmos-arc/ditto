"""
Instrument 子域 - 证券主数据（重构后命名）.

命名映射：
- Python 代码使用 instrument/source_ticker
- 数据库表/列保持 instrument/source_ticker（避免数据迁移）

CQRS 模式：
- InstrumentReader - 查询接口（支持 PIT + DataCache + 扩展信息）
- InstrumentWriter - 写入接口（自动缓存失效 + 扩展信息自动路由）

扩展表模式：
- 使用 Protocol 定义扩展信息接口
- 根据资产类型自动路由到对应的扩展表
"""

from ditto_datahub.models.metadata import (
    ETFExtension,
    IndexExtension,
    InstrumentExtension,
    InstrumentRegistration,
    StockExtension,
)
from ditto_datahub.stores.metadata.instrument.instrument_reader import (
    InstrumentReader,
)
from ditto_datahub.stores.metadata.instrument.instrument_writer import (
    InstrumentWriter,
)
from ditto_datahub.stores.metadata.instrument.name_history_reader import (
    NameHistoryReader,
)
from ditto_datahub.stores.metadata.instrument.name_history_writer import (
    NameHistoryWriter,
)

__all__ = [
    "ETFExtension",
    "IndexExtension",
    "InstrumentExtension",
    "InstrumentReader",
    "InstrumentRegistration",
    "InstrumentWriter",
    "NameHistoryReader",
    "NameHistoryWriter",
    "StockExtension",
]
