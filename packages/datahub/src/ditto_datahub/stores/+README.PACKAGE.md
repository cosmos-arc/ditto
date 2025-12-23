# stores

> 数据存储层 - SQLite 与 Parquet 双存储实现

## 一、核心功能

提供 SQLite (事务型) 和 Parquet (年分区分析型) 两种存储的统一访问接口。

## 二、包含文件

| 文件 | 功能 |
|------|------|
| `sqlite_client.py` | SQLite 客户端封装，提供统一的 CRUD 接口 |
| `security_store.py` | 证券主数据 + PIT 映射存储 |
| `calendar_store.py` | 交易日历存储 (内存缓存优化) |
| `pipeline_store.py` | Pipeline 运行状态 + DQ 异常记录 |
| `bars_store.py` | K线数据 Parquet 年分区存储 |
| `adj_factor_store.py` | 复权因子 Parquet 年分区存储 |

## 三、使用示例

```python
from pathlib import Path
from ditto_datahub.stores import (
    SQLiteClient,
    SecurityStore,
    BarsStore,
    AdjFactorStore,
)

# SQLite 客户端
client = SQLiteClient(Path("data/ditto.db"))

# 证券存储
security_store = SecurityStore(client)
sid = security_store.resolve_sid("510300.SH", source="tushare")

# K线存储
bars_store = BarsStore(Path("data"))
df = bars_store.read("etf_daily", sids=[sid], start_date="2024-01-01")

# 复权因子存储
adj_store = AdjFactorStore(Path("data"))
adj_df = adj_store.read("adj_factor", sids=[sid])
```
