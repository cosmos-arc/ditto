"""
Instrument 子域 - 证券主数据（重构后命名）.

命名映射：
- Python 代码使用 instrument/source_ticker
- 数据库表/列保持 instrument/source_ticker（避免数据迁移）

CQRS 模式：
- InstrumentReader - 查询接口（支持 PIT + DataCache）
- InstrumentWriter - 写入接口（自动缓存失效）
"""

from ditto_datahub.models.metadata.instrument import InstrumentRegistration
from ditto_datahub.stores.metadata.instrument.instrument_reader import (
    InstrumentReader,
)
from ditto_datahub.stores.metadata.instrument.instrument_writer import (
    InstrumentWriter,
)

__all__ = [
    "InstrumentReader",
    "InstrumentRegistration",
    "InstrumentWriter",
]
