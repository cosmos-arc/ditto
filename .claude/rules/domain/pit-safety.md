---
paths: paths: {packages/core,packages/foundation}/**/*.py
---

# Point-in-Time 数据安全规范

> 量化交易系统最关键的约束：防止未来数据泄露

## 核心原则

**任何时刻 t 的决策，只能使用 t 时刻及之前已公开的信息。**

违反此原则会导致：
- 回测结果虚高，无法复现
- 实盘亏损，策略失效
- 本质上是「作弊」

## 常见泄露场景

### 1. 财务数据泄露

```python
# ❌ Bad: 使用报告期作为数据日期
# 2024Q1财报（报告期3月31日）实际5月15日才披露
df.filter(pl.col("report_period") <= "2024-04-01")  # 4月1日就用了Q1数据！

# ✅ Good: 使用实际披露日期
df.filter(pl.col("announce_date") <= "2024-04-01")  # 只用已披露的数据
```

### 2. 复权因子泄露

```python
# ❌ Bad: 使用最新复权因子
adj_close = close * latest_adj_factor  # 最新因子包含未来除权信息

# ✅ Good: 使用历史复权因子
adj_close = close * historical_adj_factor[date]  # 当时已知的因子
```

### 3. Rolling 计算泄露

```python
# ❌ Bad: 默认 rolling 包含当前行
df.with_columns([
    pl.col("close").rolling_mean(20).alias("ma20")  # 包含「未来」的今日数据
])

# ✅ Good: 明确排除当前行
df.with_columns([
    pl.col("close").rolling_mean(20, closed="left").alias("ma20"),
    # 或
    pl.col("close").rolling_mean(20).shift(1).alias("ma20_lagged"),
])
```

### 4. 收益率计算泄露

```python
# ❌ Bad: 用收盘价计算当日收益率后作为当日信号输入
signal = df.with_columns([
    (pl.col("close") / pl.col("close").shift(1) - 1).alias("return")
])
# 然后用这个 return 生成当日信号——但当日收盘价要收盘后才知道！

# ✅ Good: 信号使用前一日数据
signal = df.with_columns([
    (pl.col("close").shift(1) / pl.col("close").shift(2) - 1).alias("prev_return")
])
# 或者信号在收盘后生成，次日开盘执行
```

## 数据字段规范

### 必须字段

所有因子/指标数据表必须包含：

| 字段 | 含义 | 说明 |
|------|------|------|
| `trade_date` | 数据对应的交易日 | 因子「描述」的日期 |
| `knowledge_date` | 数据可知日期 | 因子「可用」的日期，≥ trade_date |

```python
# 示例：PE 因子
# 2024-03-31 的 PE 值，实际 2024-05-15 才披露
{
    "code": "510300",
    "trade_date": "2024-03-31",      # 报告期
    "knowledge_date": "2024-05-15",  # 披露日
    "pe_ttm": 12.5,
}
```

### 查询规范

```python
# ✅ Good: 使用 knowledge_date 过滤
def get_factors_pit(
    conn: duckdb.DuckDBPyConnection,
    as_of_date: date,
    factor_name: str,
) -> pl.DataFrame:
    """获取 PIT 安全的因子数据"""
    return conn.execute(
        """
        SELECT code, trade_date, factor_value
        FROM factors
        WHERE factor_name = $1
          AND knowledge_date <= $2  -- PIT 安全！
        ORDER BY code, trade_date
        """,
        [factor_name, as_of_date],
    ).pl()


# ❌ Bad: 忽略 knowledge_date
def get_factors_unsafe(conn, as_of_date, factor_name):
    return conn.execute(
        """
        SELECT * FROM factors
        WHERE factor_name = $1
          AND trade_date <= $2  -- 危险！可能包含未披露数据
        """,
        [factor_name, as_of_date],
    ).pl()
```

## 时间序列操作规范

### As-of Join（推荐）

```python
# 股价数据 join 财务因子，保证 PIT 安全
result = prices.join_asof(
    factors,
    left_on="trade_date",
    right_on="knowledge_date",  # 关键：用 knowledge_date
    by="code",
    strategy="backward",  # 只取历史数据
)
```

### Rolling 计算

```python
# 所有 rolling 必须显式指定 closed 参数
df.with_columns([
    # 方式1: closed="left" 排除当前行
    pl.col("close")
      .rolling_mean(window_size=20, closed="left")
      .alias("ma20"),

    # 方式2: shift 实现滞后
    pl.col("close")
      .rolling_std(window_size=20)
      .shift(1)
      .alias("volatility"),

    # 方式3: 分组内 rolling
    pl.col("close")
      .rolling_mean(window_size=20, closed="left")
      .over("code")
      .alias("ma20_by_code"),
])
```

### 信号生成时间线

```
Day T-1 收盘后:
  ├── 获取 T-1 收盘价
  ├── 计算 T-1 因子（使用 T-2 及之前数据）
  └── 生成 T 日信号

Day T 开盘:
  └── 执行 T 日信号（买入/卖出）

Day T 收盘:
  └── T 日收益率确定
```

## 回测框架要求

### 数据对齐检查

```python
def validate_pit_safety(
    signals: pl.DataFrame,
    prices: pl.DataFrame,
) -> None:
    """验证信号没有使用未来数据"""

    # 检查1: 信号日期必须 < 执行日期
    assert (signals["signal_date"] < signals["execution_date"]).all()

    # 检查2: 因子数据的 knowledge_date 必须 <= signal_date
    for row in signals.iter_rows(named=True):
        factor_date = get_factor_knowledge_date(row["factor_values"])
        assert factor_date <= row["signal_date"], (
            f"PIT violation: factor from {factor_date} used for signal on {row['signal_date']}"
        )
```

### 回测引擎约束

```python
class BacktestEngine:
    def __init__(self):
        self._current_date: date | None = None

    def _get_available_data(self, as_of: date) -> pl.DataFrame:
        """只返回 as_of 日期可用的数据"""
        return self._data.filter(
            pl.col("knowledge_date") <= as_of
        )

    def step(self, date: date) -> None:
        """推进一天"""
        # 确保时间只向前
        if self._current_date and date <= self._current_date:
            raise ValueError("Cannot go back in time")

        self._current_date = date
        available = self._get_available_data(date)
        # ... 使用 available 数据生成信号
```

## 测试要求

### 必须的 PIT 测试

每个因子/数据处理模块必须包含 PIT 安全测试：

```python
class TestPITSafety:
    """PIT 安全测试套件"""

    def test_factor_uses_knowledge_date(self, factor_engine):
        """验证因子计算使用 knowledge_date"""
        # 准备：一个在 5/15 才披露的 3/31 数据
        data = pl.DataFrame({
            "code": ["510300"],
            "trade_date": [date(2024, 3, 31)],
            "knowledge_date": [date(2024, 5, 15)],
            "pe": [12.5],
        })

        # 4/1 查询不应该看到这个数据
        result_apr = factor_engine.get_factors(as_of=date(2024, 4, 1))
        assert len(result_apr.filter(pl.col("trade_date") == date(2024, 3, 31))) == 0

        # 5/16 查询应该能看到
        result_may = factor_engine.get_factors(as_of=date(2024, 5, 16))
        assert len(result_may.filter(pl.col("trade_date") == date(2024, 3, 31))) == 1

    def test_rolling_excludes_current(self):
        """验证 rolling 计算排除当前行"""
        df = pl.DataFrame({
            "date": pl.date_range(date(2024, 1, 1), date(2024, 1, 10), eager=True),
            "value": list(range(10)),
        })

        result = df.with_columns([
            pl.col("value").rolling_mean(3, closed="left").alias("ma3")
        ])

        # 第4行(idx=3, value=3)的 ma3 应该是 (0+1+2)/3 = 1.0，不包含3
        assert result["ma3"][3] == pytest.approx(1.0)

    def test_backtest_no_lookahead(self, backtest_engine):
        """验证回测无前视偏差"""
        # 准备：已知结果的历史数据
        result = backtest_engine.run(
            start=date(2024, 1, 1),
            end=date(2024, 6, 30),
        )

        # 验证：每日决策只使用该日之前的数据
        for daily in result.daily_results:
            factors_used = daily.factors_snapshot
            for factor in factors_used:
                assert factor["knowledge_date"] <= daily["date"]
```

### 测试标记

```python
# 标记 PIT 相关测试
@pytest.mark.pit
def test_pit_safety():
    ...

# 运行所有 PIT 测试
# pytest -m pit
```

## 审查清单

代码审查时必须检查：

- [ ] 财务数据是否使用 `announce_date` / `knowledge_date` 而非 `report_period`
- [ ] Rolling 计算是否指定 `closed="left"` 或使用 `shift()`
- [ ] Join 操作是否使用 `join_asof` 并指定正确的时间列
- [ ] 因子表是否包含 `knowledge_date` 字段
- [ ] 查询是否使用 `knowledge_date` 过滤
- [ ] 是否有对应的 PIT 安全测试

## 禁止清单

| 禁止 | 原因 | 替代方案 |
|------|------|----------|
| 用 `report_period` 过滤财务数据 | 未来泄露 | 用 `announce_date` |
| 不指定 `closed` 的 rolling | 可能包含当前 | 显式 `closed="left"` |
| 用最新复权因子算历史价格 | 未来泄露 | 用历史复权因子 |
| 当日收盘价生成当日信号 | 未来泄露 | 信号次日执行 |
| 因子表无 `knowledge_date` | 无法做 PIT 检查 | 必须添加 |
