---
paths: packages/**/*.py
---

# Polars 规范

> 高性能数据处理，替代 Pandas

## 核心原则

1. **LazyFrame 优先**：延迟计算，最后 `.collect()`
2. **表达式 API**：避免 `.apply()` 和 Python UDF
3. **链式调用**：单一数据流，避免中间变量
4. **PIT 安全**：时间序列操作必须防止未来数据泄露

## 推荐模式

### 基本链式操作

```python
# Good: 链式 + LazyFrame
result = (
    df.lazy()
    .filter(pl.col("date") >= start_date)
    .with_columns([
        pl.col("close").pct_change().alias("returns"),
        pl.col("volume").rolling_mean(20).alias("vol_ma20"),
    ])
    .group_by("sector")
    .agg([
        pl.col("returns").mean().alias("avg_returns"),
        pl.col("volume").sum().alias("total_volume"),
    ])
    .sort("avg_returns", descending=True)
    .collect()
)

# Bad: 多次赋值 + Eager
df["returns"] = df["close"].pct_change()
df["vol_ma20"] = df["volume"].rolling_mean(20)
result = df.groupby("sector").agg(...)
```

### 列选择与重命名

```python
# Good: 表达式选择
df.select([
    pl.col("date"),
    pl.col("close").alias("price"),
    pl.col("volume"),
])

# Good: 批量选择
df.select([
    pl.col("^ohlcv_.*$"),  # 正则匹配
    pl.exclude("temp_col"),  # 排除列
])

# Bad: 字符串索引
df[["date", "close", "volume"]]
```

### 条件表达式

```python
# Good: when-then-otherwise
df.with_columns([
    pl.when(pl.col("returns") > 0)
      .then(pl.lit("up"))
      .when(pl.col("returns") < 0)
      .then(pl.lit("down"))
      .otherwise(pl.lit("flat"))
      .alias("direction")
])

# Bad: apply + lambda
df.with_columns([
    pl.col("returns").apply(
        lambda x: "up" if x > 0 else "down" if x < 0 else "flat"
    ).alias("direction")
])
```

## 时间序列操作

### 排序（必须）

```python
# 时间序列操作前必须排序
df = df.sort("trade_date")

# 分组内排序
df = df.sort(["code", "trade_date"])
```

### Rolling 计算（PIT 安全）

```python
# Good: 明确指定 closed，防止未来泄露
df.with_columns([
    # closed="left" 表示不包含当前行
    pl.col("close")
      .rolling_mean(window_size=20, closed="left")
      .alias("ma20_prev"),

    # 或者用 shift 实现同样效果
    pl.col("close")
      .rolling_mean(window_size=20)
      .shift(1)
      .alias("ma20_lagged"),
])

# Bad: 默认包含当前行，可能导致 lookahead bias
df.with_columns([
    pl.col("close").rolling_mean(20).alias("ma20")  # 危险！
])
```

### 分组窗口计算

```python
# Good: over() 分组计算
df.with_columns([
    pl.col("returns")
      .mean()
      .over("sector")
      .alias("sector_avg_returns"),

    pl.col("close")
      .rank()
      .over(["sector", "date"])
      .alias("sector_rank"),
])
```

### 时间窗口

```python
# 按时间窗口聚合
df.group_by_dynamic(
    "trade_date",
    every="1w",
    closed="left",
    label="left",
).agg([
    pl.col("returns").sum().alias("weekly_returns"),
    pl.col("volume").mean().alias("avg_daily_volume"),
])
```

## Join 操作

### 安全 Join

```python
# Good: 检查 Join 结果
before_count = df.height
df = df.join(other, on="code", how="left")
after_count = df.height

assert before_count == after_count, (
    f"Join changed row count: {before_count} -> {after_count}"
)

# Good: 处理重复列名
df = df.join(
    other.select(["code", "name"]),
    on="code",
    how="left",
    suffix="_other",
)
```

### As-of Join（时间序列专用）

```python
# 用于 PIT 安全的时间对齐
result = prices.join_asof(
    financials,
    left_on="trade_date",
    right_on="knowledge_date",  # 使用数据可知日期
    by="code",
    strategy="backward",  # 只取已知的历史数据
)
```

## 性能优化

### 列类型优化

```python
# 在读取时指定类型
df = pl.read_parquet(
    "data.parquet",
    columns=["date", "code", "close"],  # 只读需要的列
)

# 或转换类型减少内存
df = df.with_columns([
    pl.col("code").cast(pl.Categorical),
    pl.col("volume").cast(pl.UInt32),
])
```

### 避免的操作

```python
# Bad: 转 Pandas 再转回
pdf = df.to_pandas()
pdf["new_col"] = pdf["col"].apply(some_func)
df = pl.from_pandas(pdf)

# Bad: 逐行遍历
for row in df.iter_rows():
    process(row)

# Bad: 多次 collect
df1 = df.lazy().filter(...).collect()
df2 = df1.lazy().with_columns(...).collect()  # 应该一次 collect
```

## 与 DuckDB 交互

```python
import duckdb

# Polars → DuckDB
conn = duckdb.connect("ditto.db")
conn.register("prices", df)
result = conn.execute("SELECT * FROM prices WHERE date > '2024-01-01'").pl()

# DuckDB → Polars
df = conn.execute("SELECT * FROM etf_daily").pl()
```

## 测试数据构造

```python
# 测试用的 DataFrame 工厂
def make_ohlcv(
    n_rows: int = 100,
    start_date: str = "2024-01-01",
) -> pl.DataFrame:
    dates = pl.date_range(
        pl.lit(start_date).str.to_date(),
        eager=True,
    )[:n_rows]

    return pl.DataFrame({
        "trade_date": dates,
        "open": np.random.uniform(100, 110, n_rows),
        "high": np.random.uniform(110, 120, n_rows),
        "low": np.random.uniform(90, 100, n_rows),
        "close": np.random.uniform(100, 110, n_rows),
        "volume": np.random.randint(1000000, 5000000, n_rows),
    })
```

## 禁止清单

| 禁止 | 原因 | 替代方案 |
|------|------|----------|
| `df.apply(lambda)` | 极慢，破坏向量化 | 用表达式 API |
| `df.to_pandas()` | 性能损失，类型丢失 | 保持 Polars |
| `for row in df` | O(n) 循环 | 向量化操作 |
| 未排序的 rolling | 结果不确定 | 先 `.sort()` |
| 无 `closed` 的 rolling | PIT 泄露风险 | 指定 `closed="left"` |
