---
paths:
  - ./**/*.py
---

# Polars 规范

## LazyFrame vs DataFrame 决策

| 场景 | 选择 | 原因 |
|------|------|------|
| 文件读取（parquet/csv） | `pl.scan_parquet()` / `pl.scan_csv()` | 查询优化、内存高效 |
| 已有小数据集（<10K行） | `pl.DataFrame()` | 小数据开销可忽略 |
| 需要立即查看结果 | `.collect()` 后转 DataFrame | LazyFrame 不可迭代 |
| 链式变换后输出 | 全链 Lazy → 最终 `.collect()` | 最大化查询优化 |

**核心原则**：I/O 边界用 LazyFrame，最终输出时 `.collect()`。

```python
# ✅ 推荐：全链 Lazy
result = (
    pl.scan_parquet("data.parquet")
    .filter(pl.col("date") >= start_date)
    .group_by("code")
    .agg(pl.col("close").mean())
    .collect()
)
```

## 常用模式

### 分组与排序

```python
# 分组排序 + 计算变化率
df.sort(["code", "trade_date"]).with_columns(
    pl.col("close").pct_change().over("code").alias("return")
)

# 分组内排名
pl.col("factor").rank().over("trade_date")
```

### 条件表达式

```python
pl.when(pl.col("signal") > 0).then(pl.lit("buy"))
  .when(pl.col("signal") < 0).then(pl.lit("sell"))
  .otherwise(pl.lit("hold"))
```

### Join 模式

```python
# 等值 join
left.join(right, on=["code", "date"], how="left")

# As-of join（PIT 安全）
result = signals.join_asof(
    prices,
    left_on="decision_date",
    right_on="knowledge_date",
    by="code",
    strategy="backward",
)
```

### Null 处理

```python
# 填充 null（明确策略）
df.with_columns(pl.col("value").fill_null(strategy="forward"))  # 前向填充
df.with_columns(pl.col("value").fill_null(0))                   # 默认值填充
df.filter(pl.col("value").is_not_null())                        # 过滤 null

# ❌ 禁止：静默忽略 null
df.drop_nulls()  # 不明确指定 subset — 可能丢失有效行
```

### Schema 约定

```python
# ✅ 明确指定 schema 读取
pl.scan_parquet(path, schema={"date": pl.Date, "code": pl.Utf8, "close": pl.Float64})

# ✅ 断言输出 schema
assert result.schema["close"] == pl.Float64

# ✅ cast 显式指定 strict=False（允许溢出截断）
df.with_columns(pl.col("value").cast(pl.Float64, strict=False))
```

### with_columns vs select

```python
# with_columns: 保留原列 + 添加新列
df.with_columns(pl.col("close").mean().over("code").alias("avg_close"))

# select: 只保留选择的列
df.select(["code", "date", "close"])
```

## Rolling 窗口

**PIT 安全要求**：所有 rolling 操作必须指定 `closed="left"`。

```python
# ✅ PIT 安全 - 窗口 [T-20, T-1]
pl.col("close").rolling_mean(20, closed="left").over("code")

# ❌ 未来泄露 - 窗口 [T-19, T]
pl.col("close").rolling_mean(20).over("code")
```

详见 [pit.md](.claude/rules/pit.md)。

## 禁止

| 禁止 | 替代 | 原因 |
|------|------|------|
| `import pandas` | `import polars as pl` | 项目统一 |
| `df.apply(lambda...)` | 向量化表达式 | 性能 |
| `pl.read_parquet()` 大文件 | `pl.scan_parquet()` | 内存 |
| `rolling_mean(n)` 无 `closed` | `rolling_mean(n, closed="left")` | 数据泄露 |
| `.iterrows()` | `.rows()` 或向量化 | 性能 |
| `df.to_pandas()` | 原生 polars 操作 | 避免 pandas |
