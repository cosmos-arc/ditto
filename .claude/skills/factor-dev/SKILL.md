---
name: factor-dev
description: 因子开发指南。当开发量化因子时使用。
---

# 因子开发指南

## 因子类别

| 类别 | 示例 |
|------|------|
| MOMENTUM | N日收益率、相对强度 |
| VOLATILITY | 历史波动率 |
| VOLUME | 换手率、量比 |
| VALUE | PE、PB |

---

## 因子定义

```python
@dataclass
class FactorDefinition:
    name: str
    category: FactorCategory
    compute_fn: Callable
    higher_is_better: bool = True
    required_columns: set[str] = {"close"}
    min_periods: int = 20
```

---

## 示例因子

```python
# 动量（注意 closed="left"）
def momentum(data: pl.DataFrame, window: int = 20) -> pl.Series:
    return (
        pl.col("close") / pl.col("close").shift(window) - 1
    ).over("code")

# 波动率
def volatility(data: pl.DataFrame, window: int = 20) -> pl.Series:
    return (
        pl.col("close")
          .pct_change()
          .rolling_std(window, closed="left")
          .over("code")
    )
```

---

## 因子处理

### 去极值

```python
lower = pl.col(name).quantile(0.01)
upper = pl.col(name).quantile(0.99)
pl.col(name).clip(lower, upper)
```

### 标准化

```python
# Z-score
(pl.col(name) - pl.col(name).mean()) / pl.col(name).std()

# Rank
pl.col(name).rank() / pl.col(name).count()
```

---

## IC 分析

```python
def compute_ic(factor_data: pl.DataFrame, factor_name: str) -> float:
    return factor_data.select(
        pl.corr(
            pl.col(factor_name).rank(),
            pl.col("forward_return").rank()
        )
    )[0, 0]
```

---

## 禁止

| 禁止 | 替代 |
|------|------|
| 不用 closed="left" | 显式指定 |
| 不处理空值 | 明确 null 处理 |
| 不做标准化 | 统一标准化 |
