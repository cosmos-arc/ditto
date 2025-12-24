# meta

> 元数据定义 - Polars Schema 常量

## 一、核心功能

定义 Parquet 文件的 Schema 结构，用于数据验证和类型一致性保障。

## 二、包含文件

| 文件 | 功能 |
|------|------|
| `schemas.py` | Polars Schema 定义 |

## 三、定义的 Schema

- `STOCK_DAILY_SCHEMA`: 股票日线数据结构
- `ETF_DAILY_SCHEMA`: ETF 日线数据结构
- `INDEX_DAILY_SCHEMA`: 指数日线数据结构
- `ADJ_FACTOR_SCHEMA`: 复权因子数据结构

## 四、使用示例

```python
from ditto_datahub.meta.schemas import ETF_DAILY_SCHEMA
import polars as pl

# 验证 DataFrame 符合 Schema
df = pl.DataFrame({
    "sid": [200000001],
    "trade_date": [date(2024, 1, 2)],
    "open": [4.0],
    "high": [4.1],
    "low": [3.9],
    "close": [4.05],
    "volume": [1000000],
    "amount": [4050000.0],
})

# Schema 验证
for col in df.columns:
    assert col in ETF_DAILY_SCHEMA
```
