---
name: polars-guide
description: |
  【必读】Polars DataFrame 开发规范。
  触发条件: 写 polars 代码、DataFrame、LazyFrame、rolling、with_columns、group_by、filter、join、over、agg、sort、select、cast。
  核心规则: closed="left" 防止 PIT 泄露，LazyFrame 优先，禁止 pandas。
globs:
  - "**/*.py"
---

# Polars 开发指南

## LazyFrame 优先

```python
# ✅ 推荐：LazyFrame
result = (
    pl.scan_parquet("data.parquet")
    .filter(pl.col("date") >= start_date)
    .group_by("code")
    .agg(pl.col("close").mean())
    .collect()
)

# ❌ 避免：DataFrame 链式操作大数据
df = pl.read_parquet("data.parquet")
df = df.filter(...)  # 每步都物化
```

---

## Rolling 必须 closed="left"

```python
# ✅ PIT 安全
pl.col("close").rolling_mean(20, closed="left").over("code")

# ❌ 未来泄露
pl.col("close").rolling_mean(20).over("code")
```

---

## 常用模式

### 分组排序

```python
df.sort(["code", "trade_date"]).with_columns(
    pl.col("close").pct_change().over("code").alias("return")
)
```

### 条件表达式

```python
pl.when(pl.col("signal") > 0)
  .then(pl.lit("buy"))
  .when(pl.col("signal") < 0)
  .then(pl.lit("sell"))
  .otherwise(pl.lit("hold"))
```

### 窗口函数

```python
# 分组内排名
pl.col("factor").rank().over("trade_date")

# 分组内累计
pl.col("return").cum_sum().over("code")
```

---

## 类型处理

```python
# 日期
pl.col("date").cast(pl.Date)
pl.col("date").str.to_date("%Y-%m-%d")

# 数值
pl.col("price").cast(pl.Float64)
pl.col("volume").cast(pl.Int64)
```

---

## 禁止

| 禁止 | 替代 |
|------|------|
| `import pandas` | `import polars as pl` |
| `rolling_mean(20)` | `rolling_mean(20, closed="left")` |
| `df.apply(lambda...)` | 向量化表达式 |
| 循环处理行 | `with_columns` / `group_by` |
