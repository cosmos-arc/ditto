# runtime

**版本**: v0.6.0
**最后更新**: 2026-04-04
**状态**: ✅ 稳定

## 概要

数据层领域特定运行时组件 — Instrument ID 分配、数据版本管理、SQL 引擎。

> **注意**: 通用基础设施组件（SQLite 连接池 `SQLitePool`、文件锁 `FileLockManager`）已迁移至
> `ditto_infra.foundation`（`db` 和 `concurrency` 子模块）。本模块仅保留数据层特有的运行时辅助组件。

## 核心功能

提供数据存储所需的领域特定运行时基础设施，包括 Instrument ID 标识分配和数据版本管理。

## 包含文件

| 文件 | 功能 |
|------|------|
| `instrument_id_allocator.py` | Instrument ID 分配器，管理内部唯一 ID |
| `freeze_manager.py` | 轻量级数据版本管理 (SHA-256 checksum) |
| `sql_engine.py` | SQL 引擎，提供跨数据库查询能力 |

## 使用示例

```python
from ditto_infra.foundation.db import SQLitePool  # 连接池来自 infra
from ditto_data.runtime import InstrumentIdAllocator, FreezeManager

# Instrument ID 分配（依赖 infra 层的 SQLitePool）
sqlite_pool = SQLitePool(db_path="data/meta.db")
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
