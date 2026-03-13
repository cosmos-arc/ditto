# 算子参考手册

本文档详细定义了 Ditto 因子引擎支持的所有算子，包括语法、语义、属性和实现说明。

## 算子分类体系

```
算子分类
├── TS (Time Series)      - 时序算子，按 instrument_id 分组
├── CS (Cross Sectional)  - 截面算子，按 trade_date 分组
├── SCALAR                - 标量算子，不涉及分组
└── AGGREGATE             - 聚合算子，多行聚单值
```

## 属性说明

每个算子定义包含以下属性：

| 属性 | 说明 |
|------|------|
| `scope` | 作用域：TS / CS / SCALAR |
| `lookback` | 回溯窗口需求（默认 0） |
| `requires_full_day` | 是否需要完整日线数据 |
| `null_propagation` | 空值传播策略 |
| `incremental_complexity` | 增量计算复杂度 |

---

## P0 核心算子（32个）

### 1. 时序算子（TS）

#### ts_ref
```python
ts_ref(x, n: int) -> x.shift(n)
```
**语义**：引用 n 天前的值

| 属性 | 值 |
|------|-----|
| scope | TS |
| lookback | n |
| requires_full_day | false |
| incremental_complexity | O(1) |

**示例**：`ts_ref(close, 5)` - 5 天前的收盘价

---

#### ts_delta
```python
ts_delta(x, n: int) -> x - x.shift(n)
```
**语义**：与 n 天前的差值

| 属性 | 值 |
|------|-----|
| scope | TS |
| lookback | n |
| requires_full_day | false |
| incremental_complexity | O(1) |

**示例**：`ts_delta(close, 5)` - 5 天涨跌点数

---

#### ts_pct_change
```python
ts_pct_change(x, n: int) -> (x - x.shift(n)) / x.shift(n)
```
**语义**：与 n 天前的涨跌幅

| 属性 | 值 |
|------|-----|
| scope | TS |
| lookback | n |
| requires_full_day | false |
| incremental_complexity | O(1) |

**示例**：`ts_pct_change(close, 20)` - 20 日涨跌幅

---

#### ts_mean
```python
ts_mean(x, n: int) -> x.rolling_mean(n, closed="left")
```
**语义**：n 天滑动平均（`closed="left"` 避免数据泄漏）

| 属性 | 值 |
|------|-----|
| scope | TS |
| lookback | n - 1 |
| requires_full_day | false |
| incremental_complexity | O(1) |

**示例**：`ts_mean(close, 20)` - 20 日均线

---

#### ts_std
```python
ts_std(x, n: int) -> x.rolling_std(n, closed="left")
```
**语义**：n 天滑动标准差（`closed="left"` 避免数据泄漏）

| 属性 | 值 |
|------|-----|
| scope | TS |
| lookback | n - 1 |
| requires_full_day | false |
| incremental_complexity | O(1) |

**示例**：`ts_std(close, 20)` - 20 日波动率

---

#### ts_sum
```python
ts_sum(x, n: int) -> x.rolling_sum(n, closed="left")
```
**语义**：n 天滚动求和（`closed="left"` 避免数据泄漏）

| 属性 | 值 |
|------|-----|
| scope | TS |
| lookback | n - 1 |
| requires_full_day | false |
| incremental_complexity | O(1) |

**示例**：`ts_sum(volume, 5)` - 5 日成交量总和

---

#### ts_max
```python
ts_max(x, n: int) -> x.rolling_max(n, closed="left")
```
**语义**：n 天滚动最大值（`closed="left"` 避免数据泄漏）

| 属性 | 值 |
|------|-----|
| scope | TS |
| lookback | n - 1 |
| requires_full_day | false |
| incremental_complexity | O(log n) - 需要 deque |

**示例**：`ts_max(high, 20)` - 20 日最高价

---

#### ts_min
```python
ts_min(x, n: int) -> x.rolling_min(n, closed="left")
```
**语义**：n 天滚动最小值（`closed="left"` 避免数据泄漏）

| 属性 | 值 |
|------|-----|
| scope | TS |
| lookback | n - 1 |
| requires_full_day | false |
| incremental_complexity | O(log n) - 需要 deque |

**示例**：`ts_min(low, 20)` - 20 日最低价

---

#### ts_rank
```python
ts_rank(x, n: int) -> rank in window / window_size
```
**语义**：时序排名（归一化到 0-1）

| 属性 | 值 |
|------|-----|
| scope | TS |
| lookback | n - 1 |
| requires_full_day | false |
| incremental_complexity | O(log n) - sortedcontainers |

**示例**：`ts_rank(close, 20)` - 20 日内排名位置

---

#### ts_corr
```python
ts_corr(x, y, n: int) -> rolling_correlation(x, y, n)
```
**语义**：n 天滚动相关系数

| 属性 | 值 |
|------|-----|
| scope | TS |
| lookback | n - 1 |
| requires_full_day | false |
| incremental_complexity | O(1) |

**示例**：`ts_corr(close, volume, 20)` - 价量相关性

---

#### ts_cov
```python
ts_cov(x, y, n: int) -> rolling_covariance(x, y, n)
```
**语义**：n 天滚动协方差

| 属性 | 值 |
|------|-----|
| scope | TS |
| lookback | n - 1 |
| requires_full_day | false |
| incremental_complexity | O(1) |

---

#### ts_argmax
```python
ts_argmax(x, n: int) -> position of max in window
```
**语义**：窗口内最大值的位置（距今天数）

| 属性 | 值 |
|------|-----|
| scope | TS |
| lookback | n - 1 |
| requires_full_day | false |
| incremental_complexity | O(n) |

**示例**：`ts_argmax(high, 20)` - 20 日内最高价距今天数

---

#### ts_argmin
```python
ts_argmin(x, n: int) -> position of min in window
```
**语义**：窗口内最小值的位置（距今天数）

| 属性 | 值 |
|------|-----|
| scope | TS |
| lookback | n - 1 |
| requires_full_day | false |
| incremental_complexity | O(n) |

---

### 2. 截面算子（CS）

#### cs_rank
```python
cs_rank(x) -> x.rank() over date
```
**语义**：截面排名（归一化到 0-1）

| 属性 | 值 |
|------|-----|
| scope | CS |
| lookback | 0 |
| requires_full_day | **true** |
| incremental_complexity | N/A - 整日重算 |

**示例**：`cs_rank(close)` - 当日收盘价排名

---

#### cs_zscore
```python
cs_zscore(x) -> (x - mean) / std over date
```
**语义**：截面标准化

| 属性 | 值 |
|------|-----|
| scope | CS |
| lookback | 0 |
| requires_full_day | **true** |
| incremental_complexity | N/A - 整日重算 |

**示例**：`cs_zscore(pe_ratio)` - 市盈率截面标准化

---

#### cs_demean
```python
cs_demean(x) -> x - mean(x) over date
```
**语义**：截面去均值

| 属性 | 值 |
|------|-----|
| scope | CS |
| lookback | 0 |
| requires_full_day | **true** |
| incremental_complexity | N/A - 整日重算 |

---

#### cs_scale
```python
cs_scale(x, scale: float = 1.0) -> x / sum(abs(x)) * scale
```
**语义**：截面缩放到目标和

| 属性 | 值 |
|------|-----|
| scope | CS |
| lookback | 0 |
| requires_full_day | **true** |
| incremental_complexity | N/A - 整日重算 |

---

### 3. 分组截面算子

#### group_rank
```python
group_rank(x, group) -> x.rank() over (date, group)
```
**语义**：组内排名

| 属性 | 值 |
|------|-----|
| scope | CS |
| lookback | 0 |
| requires_full_day | **true** |
| incremental_complexity | N/A - 整日重算 |

**示例**：`group_rank(pe_ratio, industry)` - 行业内排名

---

#### group_zscore
```python
group_zscore(x, group) -> (x - group_mean) / group_std
```
**语义**：组内标准化

| 属性 | 值 |
|------|-----|
| scope | CS |
| lookback | 0 |
| requires_full_day | **true** |
| incremental_complexity | N/A - 整日重算 |

---

### 4. 标量函数

#### 数学函数
```python
abs(x)        # 绝对值
sign(x)       # 符号函数 (-1, 0, 1)
log(x)        # 自然对数
log10(x)      # 以10为底对数
log2(x)       # 以2为底对数
exp(x)        # e的幂
sqrt(x)       # 平方根
power(x, a)   # 幂运算
floor(x)      # 向下取整
ceil(x)       # 向上取整
round(x, n=0) # 四舍五入
```

| 属性 | 值 |
|------|-----|
| scope | SCALAR |
| lookback | 0 |
| requires_full_day | false |
| incremental_complexity | O(1) |

#### 三角函数
```python
sin(x)   # 正弦
cos(x)   # 余弦
tan(x)   # 正切
asin(x)  # 反正弦
acos(x)  # 反余弦
atan(x)  # 反正切
sinh(x)  # 双曲正弦
cosh(x)  # 双曲余弦
tanh(x)  # 双曲正切
```

#### 条件函数
```python
if(cond, then, else)  # 三元条件
coalesce(x, y, ...)   # 返回第一个非空值
```

---

## P1 增强算子（12个）

### 高级时序

#### ts_decay_linear
```python
ts_decay_linear(x, n: int) -> weighted_sum with linear decay
```
**语义**：线性衰减加权平均

| 属性 | 值 |
|------|-----|
| scope | TS |
| lookback | n - 1 |
| incremental_complexity | O(1) |

**权重**：`[n, n-1, ..., 1] / sum(1..n)`

---

#### ts_decay_exp
```python
ts_decay_exp(x, n: int, factor: float = 0.5) -> EMA
```
**语义**：指数衰减加权平均

| 属性 | 值 |
|------|-----|
| scope | TS |
| lookback | n - 1 (or infinite for pure EMA) |
| incremental_complexity | O(1) |

---

#### ts_skewness
```python
ts_skewness(x, n: int) -> rolling_skewness
```
**语义**：滚动偏度

---

#### ts_kurtosis
```python
ts_kurtosis(x, n: int) -> rolling_kurtosis
```
**语义**：滚动峰度

---

#### ts_quantile
```python
ts_quantile(x, n: int, q: float) -> rolling_quantile
```
**语义**：滚动分位数

---

### 中性化

#### neutralize
```python
neutralize(x, group) -> residual of regression against dummies
```
**语义**：行业/板块中性化（正交化）

| 属性 | 值 |
|------|-----|
| scope | CS |
| requires_full_day | **true** |
| incremental_complexity | N/A - 整日重算 |

---

#### winsorize
```python
winsorize(x, lower: float = 0.01, upper: float = 0.99)
```
**语义**：缩尾处理

| 属性 | 值 |
|------|-----|
| scope | CS |
| requires_full_day | **true** |

---

## P2 高级算子（8个）

### 多周期

#### ts_product
```python
ts_product(x, n: int) -> product of window
```
**语义**：窗口连乘

---

#### ts_count_null
```python
ts_count_null(x, n: int) -> null count in window
```
**语义**：窗口内空值计数

---

#### ts_count_true
```python
ts_count_true(cond, n: int) -> true count in window
```
**语义**：窗口内条件成立次数

---

### 复杂聚合

#### ts_median
```python
ts_median(x, n: int) -> rolling_median
```
**语义**：滚动中位数

| 属性 | 值 |
|------|-----|
| incremental_complexity | O(n) - 需要 skip list |

---

#### ts_mode
```python
ts_mode(x, n: int) -> most frequent value
```
**语义**：滚动众数

---

## 算子属性速查表

| 算子 | scope | lookback | full_day | 增量复杂度 |
|------|-------|----------|----------|-----------|
| ts_ref | TS | n | No | O(1) |
| ts_delta | TS | n | No | O(1) |
| ts_mean | TS | n-1 | No | O(1) |
| ts_std | TS | n-1 | No | O(1) |
| ts_sum | TS | n-1 | No | O(1) |
| ts_max | TS | n-1 | No | O(log n) |
| ts_min | TS | n-1 | No | O(log n) |
| ts_rank | TS | n-1 | No | O(log n) |
| ts_corr | TS | n-1 | No | O(1) |
| ts_argmax | TS | n-1 | No | O(n) |
| ts_argmin | TS | n-1 | No | O(n) |
| cs_rank | CS | 0 | **Yes** | N/A |
| cs_zscore | CS | 0 | **Yes** | N/A |
| cs_demean | CS | 0 | **Yes** | N/A |
| group_rank | CS | 0 | **Yes** | N/A |
| neutralize | CS | 0 | **Yes** | N/A |

## 嵌套规则

### 属性传播

1. **lookback 传播**：`lookback(parent) = max(lookback(children)) + intrinsic_lookback(parent)`
2. **requires_full_day 传播**：任意子表达式为 true 则父表达式为 true
3. **scope 传播**：
   - TS + TS → TS
   - CS + CS → CS
   - TS + CS → MIXED (需分阶段执行)

### 嵌套示例

```python
# ts_rank(cs_rank(close), 10)
# - cs_rank: scope=CS, full_day=true
# - ts_rank: scope=TS, full_day=inherits true
# - 结果: scope=TS, full_day=true, lookback=9
```
