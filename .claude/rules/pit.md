---
paths: packages/datahub/**/*.py
---

# PIT (Point-in-Time) 安全规范

## 核心原则

**时间点 T 只能用 T 之前已知的数据**

## knowledge_date 规则

| 数据类型 | knowledge_date |
|----------|----------------|
| 日行情 | trade_date + 1 |
| 财报 | 公告日期 |
| 指数成分 | 生效日期 |

## Rolling 窗口安全

**绝对禁止**：rolling 操作不指定 `closed="left"`（会导致未来数据泄露）

```python
# ✅ PIT 安全 - 窗口 [T-20, T-1]
pl.col("close").rolling_mean(20, closed="left").over("code")

# ❌ 未来泄露 - 窗口 [T-19, T]
pl.col("close").rolling_mean(20).over("code")
```

| closed | 窗口范围 | 安全 |
|--------|----------|------|
| "left" | [T-20, T-1] | ✅ |
| "right" | [T-19, T] | ❌ |

## As-Of Join

```python
result = signals.join_asof(
    prices,
    left_on="decision_date",
    right_on="knowledge_date",
    by="code",
    strategy="backward",
)
```

## 信号执行规则

**T日信号 → T+1执行**

```python
Signal(
    generated_at=decision_date,
    execute_at=decision_date + timedelta(days=1),
)
```

## 禁止事项

| 禁止 | 替代 |
|------|------|
| 用 trade_date 查询 | 用 knowledge_date |
| T日信号T日执行 | T+1执行 |
| rolling 不指定 closed | closed="left" |
| 手动计算 trade_date + 1 | `auto_knowledge_date=True` |

## 知识日期使用

| ✅ 正确 | ❌ 错误 |
|---------|---------|
| `hub.bars.get(auto_knowledge_date=True)` | 手动计算 trade_date + 1 |
| `@traced("data.read")` | 无追踪装饰器 |

## Polars LazyFrame 优先

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

## 常用 Polars 模式

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

## 测试标记

| 测试类型 | 标记 | 运行命令 |
|----------|------|----------|
| PIT 验证 | @pytest.mark.pit | pytest -m pit |
| 数据摄入 | @pytest.mark.ingestion | pytest -m ingestion |
| 集成测试 | @pytest.mark.integration | pytest -m integration |
