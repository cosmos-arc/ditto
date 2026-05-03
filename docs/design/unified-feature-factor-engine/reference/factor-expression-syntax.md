> **⚠️ Historical Document**: 本文档撰写于旧架构（engine/analytics/infra/interfaces）时期。
> 当前架构请参考 `CLAUDE.md` 和 `docs/architecture/` 下的活跃文档。
# 因子表达式语法参考

## 1. 基础语法

### 1.1 字面量

```python
42          # 整数
3.14        # 浮点数
"string"    # 字符串
true/false  # 布尔值
null        # 空值
```

### 1.2 列引用

```python
close               # 市场数据列
volume              # 成交量
$close              # 显式市场域
$$net_income        # 基本面数据（PIT）
```

### 1.3 算术运算

```python
close + open        # 加法
close - open        # 减法
close * volume      # 乘法
close / volume      # 除法
close % 100         # 取模
close ** 2          # 幂运算
```

### 1.4 比较运算

```python
close > open        # 大于
close >= open       # 大于等于
close < open        # 小于
close <= open       # 小于等于
close == open       # 等于
close != open       # 不等于
```

### 1.5 逻辑运算

```python
cond1 and cond2     # 逻辑与
cond1 or cond2      # 逻辑或
not cond            # 逻辑非
```

### 1.6 条件表达式

```python
if(cond, then, else)    # 三元条件
```

## 2. 时序算子（TS）

### 2.1 基础时序

| 算子 | 语法 | 说明 |
|------|------|------|
| `ts_ref` | `ts_ref(x, n)` | 引用 n 天前的值 |
| `ts_delta` | `ts_delta(x, n)` | 与 n 天前的差值 |
| `ts_pct_change` | `ts_pct_change(x, n)` | 与 n 天前的涨跌幅 |

### 2.2 滑动窗口

| 算子 | 语法 | 说明 |
|------|------|------|
| `ts_mean` | `ts_mean(x, n)` | n 天均值 |
| `ts_std` | `ts_std(x, n)` | n 天标准差 |
| `ts_sum` | `ts_sum(x, n)` | n 天求和 |
| `ts_max` | `ts_max(x, n)` | n 天最大值 |
| `ts_min` | `ts_min(x, n)` | n 天最小值 |
| `ts_median` | `ts_median(x, n)` | n 天中位数 |

### 2.3 排名与分位数

| 算子 | 语法 | 说明 |
|------|------|------|
| `ts_rank` | `ts_rank(x, n)` | 时序排名（0-1） |
| `ts_argmax` | `ts_argmax(x, n)` | 最大值位置 |
| `ts_argmin` | `ts_argmin(x, n)` | 最小值位置 |
| `ts_quantile` | `ts_quantile(x, n, q)` | 分位数 |

### 2.4 统计相关

| 算子 | 语法 | 说明 |
|------|------|------|
| `ts_corr` | `ts_corr(x, y, n)` | n 天相关系数 |
| `ts_cov` | `ts_cov(x, y, n)` | n 天协方差 |
| `ts_skewness` | `ts_skewness(x, n)` | 偏度 |
| `ts_kurtosis` | `ts_kurtosis(x, n)` | 峰度 |

### 2.5 技术指标

| 算子 | 语法 | 说明 |
|------|------|------|
| `ts_decay_linear` | `ts_decay_linear(x, n)` | 线性衰减加权 |
| `ts_decay_exp` | `ts_decay_exp(x, n, factor)` | 指数衰减 |
| `ts_product` | `ts_product(x, n)` | 连乘 |

## 3. 截面算子（CS）

### 3.1 基础截面

| 算子 | 语法 | 说明 |
|------|------|------|
| `cs_rank` | `cs_rank(x)` | 截面排名（0-1） |
| `cs_zscore` | `cs_zscore(x)` | 截面标准化 |
| `cs_demean` | `cs_demean(x)` | 截面去均值 |
| `cs_scale` | `cs_scale(x, scale)` | 截面缩放 |

### 3.2 分组截面

| 算子 | 语法 | 说明 |
|------|------|------|
| `group_rank` | `group_rank(x, group)` | 组内排名 |
| `group_zscore` | `group_zscore(x, group)` | 组内标准化 |
| `group_demean` | `group_demean(x, group)` | 组内去均值 |
| `group_mean` | `group_mean(x, group)` | 组内均值 |

### 3.3 中性化

| 算子 | 语法 | 说明 |
|------|------|------|
| `neutralize` | `neutralize(x, industry)` | 行业中性化 |
| `neutralize_mcap` | `neutralize_mcap(x)` | 市值中性化 |

## 4. 数学函数

### 4.1 基础数学

```python
abs(x)          # 绝对值
sign(x)         # 符号函数
log(x)          # 自然对数
log10(x)        # 以10为底对数
log2(x)         # 以2为底对数
exp(x)          # e的幂
sqrt(x)         # 平方根
power(x, a)     # 幂运算
```

### 4.2 取整函数

```python
floor(x)        # 向下取整
ceil(x)         # 向上取整
round(x, n)     # 四舍五入
truncate(x)     # 截断
```

### 4.3 三角函数

```python
sin(x)          # 正弦
cos(x)          # 余弦
tan(x)          # 正切
asin(x)         # 反正弦
acos(x)         # 反余弦
atan(x)         # 反正切
```

## 5. 聚合函数

```python
sum(x)          # 求和
mean(x)         # 均值
std(x)          # 标准差
var(x)          # 方差
max(x)          # 最大值
min(x)          # 最小值
count(x)        # 计数
count_null(x)   # 空值计数
```

## 6. 类型转换

```python
cast_int(x)     # 转整数
cast_float(x)   # 转浮点
cast_bool(x)    # 转布尔
cast_str(x)     # 转字符串
```

## 7. 空值处理

```python
is_null(x)              # 判断是否为空
is_not_null(x)          # 判断是否非空
fill_null(x, value)     # 填充空值
drop_null(x)            # 删除空值
coalesce(x, y, ...)     # 返回第一个非空值
```

## 8. 嵌套规则

### 8.1 允许的嵌套

```python
# TS(CS(x)) - 允许
ts_mean(cs_rank(close), 5)

# CS(TS(x)) - 允许
cs_rank(ts_delta(close, 5))

# 多层嵌套 - 允许
ts_rank(cs_rank(ts_mean(close, 10)), 5)
```

### 8.2 约束条件

- 嵌套深度建议不超过 10 层
- CS(CS(x)) 会产生警告但允许
- 复杂表达式编译期会有性能警告

## 9. 注释

```python
# 单行注释
close + volume  # 行尾注释

# 多行表达式
ts_mean(
    close,      # 收盘价
    20          # 20日窗口
)
```

## 10. 完整示例

```python
# 动量因子
momentum_20 = ts_pct_change(close, 20)
momentum_rank = cs_rank(momentum_20)

# 波动率因子
volatility = ts_std(log(close / ts_ref(close, 1)), 20)
volatility_rank = cs_rank(volatility)

# 复合因子
composite = 0.6 * momentum_rank - 0.4 * volatility_rank

# 行业中性化
factor = neutralize(composite, industry)
```
