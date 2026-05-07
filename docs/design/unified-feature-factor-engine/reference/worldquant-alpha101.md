> **⚠️ Historical Document**: 本文档撰写于旧架构（engine/analytics/infra/interfaces）时期。
> 当前架构请参考 `CLAUDE.md` 和 `docs/architecture/` 下的活跃文档。
# WorldQuant Alpha101 算子参考

## 概述

WorldQuant Alpha101 是业界广泛使用的因子表达式库，包含 101 个经过验证的 alpha 因子公式。这些公式使用特定的 DSL 语法，是 Ditto 表达式引擎设计的重要参考。

## 语法规范

### 基础算子

| 算子 | 语法 | 说明 |
|------|------|------|
| `rank` | `rank(x)` | 截面排名（0-1） |
| `ts_rank` | `ts_rank(x, d)` | 时序排名 |
| `delay` | `delay(x, d)` | 延迟 d 天的值 |
| `delta` | `delta(x, d)` | 与 d 天前的差值 |
| `scale` | `scale(x)` | 标准化到 [-1, 1] |
| `sign` | `sign(x)` | 符号函数 |

### 时序算子

| 算子 | 语法 | 说明 |
|------|------|------|
| `ts_mean` | `ts_mean(x, d)` | d 天均值 |
| `ts_std` | `ts_std(x, d)` | d 天标准差 |
| `ts_sum` | `ts_sum(x, d)` | d 天求和 |
| `ts_max` | `ts_max(x, d)` | d 天最大值 |
| `ts_min` | `ts_min(x, d)` | d 天最小值 |
| `ts_argmax` | `ts_argmax(x, d)` | 最大值位置 |
| `ts_argmin` | `ts_argmin(x, d)` | 最小值位置 |

### 统计算子

| 算子 | 语法 | 说明 |
|------|------|------|
| `correlation` | `correlation(x, y, d)` | d 天相关系数 |
| `covariance` | `covariance(x, y, d)` | d 天协方差 |
| `ts_regression` | `ts_regression(x, y, d)` | d 天回归系数 |

### 数学函数

| 函数 | 语法 | 说明 |
|------|------|------|
| `abs` | `abs(x)` | 绝对值 |
| `log` | `log(x)` | 自然对数 |
| `power` | `power(x, a)` | 幂函数 |
| `sign` | `sign(x)` | 符号 |

## 典型因子示例

### Alpha#1
```
rank(ts_delta(log(volume), 1))
```
含义：成交量变化的排名

### Alpha#2
```
-1 * correlation(rank(delta(log(volume), 2)), rank(((close - open) / open)), 6)
```
含义：成交量变化与日内波动的负相关

### Alpha#3
```
-1 * correlation(rank(open), rank(volume), 10)
```
含义：开盘价与成交量的负相关

### Alpha#6
```
-1 * correlation(open, volume, 10)
```
含义：开盘价与成交量的负相关

### Alpha#53
```
-1 * delta((((close - low) - (high - close)) / (high - low)) * volume, 1)
```
含义：日内买卖压力变化的反向

## 嵌套模式分析

统计 WorldQuant Alpha101 中的嵌套模式：

| 嵌套类型 | 数量 | 占比 | 示例 |
|---------|------|------|------|
| TS(CS(x)) | 45 | 45% | `ts_rank(rank(x), 9)` |
| CS(TS(x)) | 38 | 38% | `rank(ts_delta(x, 20))` |
| TS(CS(x), CS(y)) | 12 | 12% | `correlation(rank(x), rank(y), 10)` |
| 纯 TS | 5 | 5% | `ts_mean(x, 10)` |

**关键发现**：80% 的因子需要 TS/CS 混合嵌套，这是 Ditto 选择支持任意嵌套的核心原因。

## 窗口参数分布

| 窗口大小 | 频次 | 占比 |
|---------|------|------|
| 1-5 | 35 | 35% |
| 6-10 | 40 | 40% |
| 11-20 | 18 | 18% |
| 21+ | 7 | 7% |

**设计影响**：
- 默认 lookback 阈值设为 60 天可覆盖 95%+ 场景
- 长周期算子需要独立优化

## Ditto 适配

### 命名映射

| WorldQuant | Ditto | 说明 |
|------------|-------|------|
| `rank` | `cs_rank` | 显式 CS 前缀 |
| `ts_rank` | `ts_rank` | 保持一致 |
| `delay` | `ts_ref` | 更语义化 |
| `delta` | `ts_delta` | 统一 TS 前缀 |

### 扩展算子

Ditto 在 WorldQuant 基础上扩展：

| 算子 | 说明 |
|------|------|
| `cs_zscore` | 截面标准化 |
| `group_rank` | 组内排名 |
| `group_zscore` | 组内标准化 |
| `neutralize` | 行业/市值中性化 |

## 参考链接

- WorldQuant Brain Platform: https://platform.worldquantbrain.com/
- Alpha101 论文: "101 Formulaic Alphas" by Zura Kakushadze
