# ADR-007: 算子完整清单

**状态**: 已决策（2026-03-04）

---

## P0 核心算子（Phase 0 必须实现）

### TS 滚动聚合（8 个）

| 算子 | 签名 | 说明 | lookback |
|------|------|------|----------|
| `ts_mean` | `ts_mean(x, n)` | 滚动均值 | n |
| `ts_sum` | `ts_sum(x, n)` | 滚动求和 | n |
| `ts_std` | `ts_std(x, n)` | 滚动标准差 | n |
| `ts_var` | `ts_var(x, n)` | 滚动方差 | n |
| `ts_max` | `ts_max(x, n)` | 滚动最大值 | n |
| `ts_min` | `ts_min(x, n)` | 滚动最小值 | n |
| `ts_count` | `ts_count(x, n)` | 滚动计数 | n |
| `ts_median` | `ts_median(x, n)` | 滚动中位数 | n |

### TS 延迟/变化（4 个）

| 算子 | 签名 | 说明 | lookback |
|------|------|------|----------|
| `ts_delay` | `ts_delay(x, n)` | n 期延迟 | n |
| `ts_delta` | `ts_delta(x, n)` | n 期变化 | n |
| `ts_pct_change` | `ts_pct_change(x, n)` | n 期变化率 | n |
| `ts_diff` | `ts_diff(x, n)` | 差分 | 1 |

### TS 排名（3 个）

| 算子 | 签名 | 说明 | lookback |
|------|------|------|----------|
| `ts_rank` | `ts_rank(x, n)` | 窗口内排名 | n |
| `ts_argmax` | `ts_argmax(x, n)` | 最大值位置 | n |
| `ts_argmin` | `ts_argmin(x, n)` | 最小值位置 | n |

### TS 相关（2 个）

| 算子 | 签名 | 说明 | lookback |
|------|------|------|----------|
| `ts_corr` | `ts_corr(x, y, n)` | 滚动相关系数 | n |
| `ts_cov` | `ts_cov(x, y, n)` | 滚动协方差 | n |

### CS 排名/标准化（5 个）

| 算子 | 签名 | 说明 | requires_full_day |
|------|------|------|-------------------|
| `cs_rank` | `cs_rank(x)` | 截面排名 | True |
| `cs_scale` | `cs_scale(x)` | 截面缩放到 [0,1] | True |
| `cs_zscore` | `cs_zscore(x)` | 截面标准化 | True |
| `cs_demean` | `cs_demean(x)` | 截面去均值 | True |
| `cs_winsorize` | `cs_winsorize(x, lower, upper)` | 截面缩尾 | True |

### 标量-数学（6 个）

| 算子 | 签名 | 说明 |
|------|------|------|
| `abs` | `abs(x)` | 绝对值 |
| `log` | `log(x)` | 自然对数 |
| `exp` | `exp(x)` | 指数 |
| `sqrt` | `sqrt(x)` | 平方根 |
| `sign` | `sign(x)` | 符号 |
| `power` | `power(x, n)` | 幂运算 |

### 标量-比较/逻辑（4 个）

| 算子 | 签名 | 说明 |
|------|------|------|
| `max2` | `max2(x, y)` | 两数最大 |
| `min2` | `min2(x, y)` | 两数最小 |
| `clip` | `clip(x, lower, upper)` | 裁剪 |
| `if_else` | `if_else(cond, x, y)` | 条件选择 |

**P0 总计**: 32 个算子

---

## P1 增强算子（Phase 1 实现）

### TS 加权（4 个）

| 算子 | 签名 | 说明 | lookback |
|------|------|------|----------|
| `ts_ema` | `ts_ema(x, n)` | 指数移动平均 | n * 2 |
| `ts_wma` | `ts_wma(x, n)` | 加权移动平均 | n |
| `ts_decay_linear` | `ts_decay_linear(x, n)` | 线性衰减加权 | n |
| `ts_decay_exp` | `ts_decay_exp(x, n)` | 指数衰减加权 | n |

### TS 分位数（3 个）

| 算子 | 签名 | 说明 | lookback |
|------|------|------|----------|
| `ts_quantile` | `ts_quantile(x, n, q)` | 滚动分位数 | n |
| `ts_qtlu` | `ts_qtlu(x, n, q)` | 滚动上分位数 | n |
| `ts_qtld` | `ts_qtld(x, n, q)` | 滚动下分位数 | n |

### TS 高阶统计（2 个）

| 算子 | 签名 | 说明 | lookback |
|------|------|------|----------|
| `ts_skew` | `ts_skew(x, n)` | 滚动偏度 | n |
| `ts_kurt` | `ts_kurt(x, n)` | 滚动峰度 | n |

### CS 分组（3 个）

| 算子 | 签名 | 说明 | requires_full_day |
|------|------|------|-------------------|
| `group_rank` | `group_rank(x, group)` | 组内排名 | True |
| `group_zscore` | `group_zscore(x, group)` | 组内标准化 | True |
| `group_demean` | `group_demean(x, group)` | 组内去均值 | True |

**P1 总计**: 12 个算子

---

## P2 高级算子（Phase 2 实现）

### TS 复杂聚合（4 个）

| 算子 | 签名 | 说明 | lookback |
|------|------|------|----------|
| `ts_prod` | `ts_prod(x, n)` | 滚动乘积 | n |
| `ts_av_diff` | `ts_av_diff(x, n)` | 与均值差 | n |
| `ts_mean_return` | `ts_mean_return(x, n, lag)` | 平均收益 | n + lag |
| `ts_regression` | `ts_regression(y, x, n)` | 滚动回归 | n |

### CS 复杂操作（4 个）

| 算子 | 签名 | 说明 | requires_full_day |
|------|------|------|-------------------|
| `cs_regression` | `cs_regression(y, x)` | 截面回归残差 | True |
| `cs_neutralize` | `cs_neutralize(x, groups)` | 多组中性化 | True |
| `cs_normalize` | `cs_normalize(x)` | L2 归一化 | True |
| `cs_percentile` | `cs_percentile(x)` | 百分位排名 | True |

**P2 总计**: 8 个算子

---

## 算子总计

| 优先级 | 数量 | 说明 |
|--------|------|------|
| P0 | 32 | Phase 0 核心，支持基础因子计算 |
| P1 | 12 | Phase 1 增强，支持 Alpha101 |
| P2 | 8 | Phase 2 高级，支持复杂策略 |
| **合计** | **52** | 全功能覆盖 |
