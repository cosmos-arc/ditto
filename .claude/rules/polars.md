---
paths: ./**/*.py
---

# Polars 规范

## LazyFrame 优先

```python
# ✅ 推荐
result = (
    pl.scan_parquet("data.parquet")
    .filter(pl.col("date") >= start_date)
    .group_by("code")
    .agg(pl.col("close").mean())
    .collect()
)
```

## 常用模式

```python
# 分组排序
df.sort(["code", "trade_date"]).with_columns(
    pl.col("close").pct_change().over("code").alias("return")
)

# 条件表达式
pl.when(pl.col("signal") > 0).then(pl.lit("buy"))
  .when(pl.col("signal") < 0).then(pl.lit("sell"))
  .otherwise(pl.lit("hold"))

# 分组内排名
pl.col("factor").rank().over("trade_date")
```

## 禁止

| 禁止 | 替代 |
|------|------|
| `import pandas` | `import polars as pl` |
| `df.apply(lambda...)` | 向量化表达式 |

**注意**: Rolling 窗口的 PIT 安全规则详见 [pit.md](.claude/rules/pit.md)
