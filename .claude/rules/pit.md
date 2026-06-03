---
paths:
  - packages/data/**/*.py
---

# PIT (Point-in-Time) 安全规范

## 核心原则

**时间点 T 只能用 T 之前已知的数据**

## effective_from / effective_to 语义

### 字段定义

| 字段 | 说明 | 示例 |
|------|------|------|
| `effective_from` | 版本生效日期（含） | 数据从该日期起可用 |
| `effective_to` | 版本失效日期（不含） | 该日期起数据不再有效，NULL 表示当前版本 |

### 边界语义

**`effective_to` 表示"失效日期（不含）"**，即：
- 如果 `effective_to = 2024-01-15`，则该版本在 2024-01-15 起不再有效
- 查询 `as_of_date = 2024-01-15` 时，该版本**不包含**
- 查询 `as_of_date = 2024-01-14` 时，该版本**包含**

### PIT 查询条件

```python
# 标准 PIT 查询条件
df.filter(
    (pl.col("effective_from") <= as_of_date) &  # 版本已生效
    (
        (pl.col("effective_to").is_null()) |     # NULL = 当前版本
        (pl.col("effective_to") > as_of_date)    # 未失效（注意 > 而非 >=）
    )
)
```

| as_of_date | effective_from | effective_to | 结果 |
|-------------|----------------|--------------|------|
| 2024-01-14 | 2024-01-01 | 2024-01-15 | ✅ 包含 |
| 2024-01-15 | 2024-01-01 | 2024-01-15 | ❌ 不包含 |
| 2024-01-16 | 2024-01-01 | NULL | ✅ 包含 |

### 重要说明

**为什么使用 `>` 而非 `>=`？**
- `effective_to` 是"失效日期"，表示该日期**起**不再有效
- 这与 `trade_date` 的语义一致（T 日数据在 T 日收盘后可知）
- 因此 `effective_to > as_of_date` 表示"在 as_of_date 时刻版本仍然有效"

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

**注意**：Polars Expr 级别 `.rolling_*()` 方法（如 `.rolling_mean()`、`.rolling_sum()`）
不支持 `closed` 参数（仅 `DataFrame.rolling()` 支持）。在 Expr 上下文中，必须使用
`shift(1)` 作为替代方案来实现等价的 PIT 安全窗口：

```python
# ✅ Expr 上下文中的 PIT 安全写法（表达式引擎使用此模式）
pl.col("close").shift(1).rolling_mean(20).over("code")
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
| `service.get_bars(query)`（MarketService 自动处理 knowledge_date） | 手动计算 trade_date + 1 |
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
| 集成测试 | @pytest.mark.integration | pytest -m integration |

## 表达式引擎 rolling 语义

表达式编译器 (`codegen.py`) 中所有 rolling 函数通过 `shift(1)` 预防数据泄漏：

```python
shifted = argument.shift(1)
return builder(shifted, window).over(entity_keys)
```

**窗口语义**: `shift(1) + rolling(window)` 使用 `[T-window, T-1]` 范围的数据，
与 `rolling(window, closed="left")` 等价（都是 window 个历史数据点，不含当日 T）。

**用户代码规范**: 在策略代码中直接调用 polars API 时，必须使用 `closed="left"` 或 `shift(1)`。
表达式引擎已从编译器层面保证 PIT 安全，用户无需额外处理。
