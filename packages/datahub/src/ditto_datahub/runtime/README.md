# runtime

**版本**: v0.5.0
**最后更新**: 2026-01-23
**状态**: ✅ 稳定

## 概要

运行时支持组件 - 连接池、Instrument ID 分配、版本管理，提供数据存储所需的运行时基础设施。

## 核心功能

提供数据存储所需的运行时基础设施，包括连接池管理、Instrument ID 标识分配、并发控制和数据版本管理。

## 二、包含文件

| 文件 | 功能 |
|------|------|
| `sqlite_pool.py` | SQLite 连接池，线程安全的连接管理 |
| `instrument_id_allocator.py` | Instrument ID 分配器，管理内部唯一 ID |
| `file_lock.py` | 跨平台文件锁，防止并发写入冲突 |
| `freeze_manager.py` | 轻量级数据版本管理 (SHA-256 checksum) |
| `sql_engine.py` | SQL 引擎，提供跨数据库查询能力 |

## 三、使用示例

```python
from ditto_datahub.runtime import InstrumentIdAllocator, FreezeManager

# Instrument ID 分配
allocator = InstrumentIdAllocator(sqlite_pool)
etf_instrument_id = allocator.allocate("etf")
print(f"Allocated instrument_id: {etf_instrument_id}")

# Freeze 数据版本管理
manager = FreezeManager(data_root="data")
manifest = manager.create(
    freeze_id="freeze_20240101",
    description="2024-01-01 数据快照",
    datasets=["etf_daily", "stock_daily"],
)
print(f"Freeze created: {manifest.freeze_id}")
```
