# runtime

> 运行时支持组件 - 连接池、SID 分配、数据质量检查

## 一、核心功能

提供数据存储所需的运行时基础设施，包括连接池管理、SID 标识分配、并发控制和数据质量检查。

## 二、包含文件

| 文件 | 功能 |
|------|------|
| `sqlite_pool.py` | SQLite 连接池，线程安全的连接管理 |
| `sid_allocator.py` | SID 分配器，管理内部唯一 ID (100M-299M for ETF) |
| `file_lock.py` | 跨平台文件锁，防止并发写入冲突 |
| `dq_checker.py` | 数据质量检查引擎 |
| `dq_rules.py` | DQ 规则定义 (主键、OHLC、涨跌停等) |

## 三、使用示例

```python
from ditto_datahub.runtime import SidAllocator, DQChecker
import polars as pl

# SID 分配
allocator = SidAllocator()
etf_sid = allocator.get_or_allocate_sid("510300.SH", "etf")
print(f"Allocated SID: {etf_sid}")

# 数据质量检查
checker = DQChecker()
df = pl.DataFrame({
    "sid": [100000001],
    "trade_date": [date(2024, 1, 2)],
    "close": [10.5],
    "high": [11.0],
    "low": [10.0],
    "open": [10.2],
    "volume": [1000000],
})
result = checker.check(df, dataset_id="test")
print(f"DQ Passed: {result.passed}")
```
