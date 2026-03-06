# API Review 修复设计

基于 PR #57 的 review建议，修复以下问题：

## 1. P1-1: 非法 pairs/symbols 静默过滤，返回空 200

### 当前行为
- 请求 `/fx/bars` 传入 `pairs=["USDCNH.FXCM", "EURUSD.FXCM"]`
- 路由静默过滤非法值
- 如果全部非法，返回空 `[]`

- 用户可能以为是是没有数据，实际上是参数错误

- 调用方无法知道哪些值被忽略了

### 修复方案
**采用严格模式**: 遇到任何非法值直接返回 400 错误。

同时进行参数重命名：
- `pairs` → `currency_pairs`
- `symbols` → `commodity_codes`

### 变更清单

| 文件 | 变更内容 |
|------|------|---------|
| `models/fx.py` | `FxQuery.pairs` → `FxQuery.currency_pairs` |
| `models/fx.py` | `FxBar.pair` → `FxBar.currency_pair` |
| `routes/fx.py` | 参数校验逻辑 + 命名更新 |
| `models/commodity.py` | `CommodityQuery.symbols` → `CommodityQuery.commodity_codes` |
| `models/commodity.py` | `CommodityBar.symbol` → `CommodityBar.commodity_code` |
| `routes/commodity.py` | 参数校验逻辑 + 命名更新 |

## 2. P1-2: limit 未下推查询

### 当前行为
- 查询全部数据到 DataFrame
- 转换为 Python 对象列表
- 在内存中切片
- 数据量大时性能放大

### 修复方案

**将 limit 参数下推到 Store 层的 Parquet 查询**， 利用 Polars 的 `head()` 方法在读取后立即截断。

```python
# ParquetStore.read() 添加 limit 参数
df = store.read(
    ...,
    limit=limit,  # 下推 limit
)
```

### 变更范围
| 层级 | 文件 | 变更内容 |
|------|------|---------|
| Store 层 | `ParquetStore.read()` | 添加 `limit` 参数 |
| Store 层 | `MarketBarsStoreBase.read()` | 添加 `limit` 参数并传递 |
| Service 层 | `MarketService.list_bars()` | 添加 `limit` 参数 |
| Service 层 | `MarketBarsQuery` | 添加 `limit` 字段 |
| API 层 | 路由中传递 `limit` 并在 DataFrame 层应用 |

### 示例代码
```python
# Store 层
def read(
    self,
    dataset: str,
    instrument_ids: list[int] | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int | None = None,
) -> pl.DataFrame:
    # 应用 limit
    if limit is not None:
        return df
    return df.head(limit)  # 抛弃多余数据
```

**注意**：limit 下推需要修改 ParquetStore，但这会带来额外的复杂度。对于当前的数据量，可以简化实现：先不添加 limit 参数到 Store 层。

## 3. P2-1 修复设计 - trade_date_utc 字段语义

### 当前问题
```python
# fx.py 第 80 行
pl.col("trade_date_utc").dt.date().cast(pl.String).alias("trade_date_utc")
```

**问题**：字段名是 `trade_date_utc`，暗示是 UTC 时区时时点，但被 `dt.date()` 截断为日期（丢失时区信息)。

### 修复建议
将字段名改为 `trade_date`，如果确认是时区信息需要保留，则使用 `trade_date_utc`。

### 变更清单
| 文件 | 变更内容 |
|------|------|---------|
| `models/fx.py` | `FxBar.trade_date_utc` → `FxBar.trade_date` (或保留 utc) |
| `models/commodity.py` | `CommodityBar.trade_date_utc` → `CommodityBar.trade_date` (或保留 utc) |
| `routes/fx.py` | 移除 `dt.date()` 截断 |
| `routes/commodity.py` | 移除 `dt.date()` 截断 |

---

## 4. P2-2 修复设计 - Bond Yield 日期解析

### 当前问题
```python
# bond_yield.py 第 75-88 行
def _parse_trade_date(trade_date: object) -> date | None:
    try:
        date_str = str(trade_date)
        if len(date_str) == _DATE_STR_LENGTH:
            return date_str
        elif isinstance(trade_date, (int, float)):
            date_val = str(int(trade_date))  # 浮点数 20240101.5 → "20240101"
        else:
            return None
```

**问题**：浮点数 `20240101.5` 被静默截断为合法日期 `20240101`，可能掩盖数据质量问题。

### 修复方案
**增加校验**: 拒绝带小数的浮点数，只接受整数值或 `.0` 后缀的值。

```python
def _parse_trade_date(trade_date: object) -> date | None:
    try:
        date_str = str(trade_date)
        if len(date_str) == _DATE_STR_LENGTH:
            return date_str
        elif isinstance(trade_date, (int, float)):
            # 检查是否为整数值或有小数
            if isinstance(trade_date, float) and not trade_date.is_integer():
                logger.warning(
                    "Invalid trade_date with decimal, skipping",
                    event="bond_yield_invalid_date",
                    trade_date=trade_date,
                )
                return None
            date_val = str(int(trade_date))
        else:
            return None
```

### 变更清单
| 文件 | 变更内容 |
|------|------|---------|
| `bond_yield.py` | 添加浮点数校验逻辑 |

---

## 宱. 完整设计文档

现在让我保存并呈现给用户确认。
