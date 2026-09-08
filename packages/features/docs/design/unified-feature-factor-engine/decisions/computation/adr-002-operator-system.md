> **⚠️ Historical Document**: 本文档撰写于旧架构（engine/analytics/infra/interfaces）时期。
> 当前架构请参考 `CLAUDE.md` 和 `docs/architecture/` 下的活跃文档。
# ADR-002: 算子体系设计

**状态**: 已决策（2026-03-04）

---

## 决策

### 1. 命名风格

WorldQuant 风格（前缀区分 TS/CS）：
- TS 算子: `ts_mean`, `ts_rank`, `ts_delta`, `ts_corr`
- CS 算子: `cs_rank`, `cs_zscore`, `cs_demean`
- 标量算子: `abs`, `log`, `sign`, `power`

### 2. 首批算子范围

全功能（P0 + P1 + P2），约 50+ 个算子：
- 目标：完整支持 WorldQuant Alpha101 + 常用技术指标
- 优先级：P0 核心必选 → P1 增强能力 → P2 高级能力

### 3. 分组中性化支持

首批支持：
- `group_rank(x, group)` - 组内排名
- `group_zscore(x, group)` - 组内标准化
- `group_demean(x, group)` - 组内去均值
- 需要：行业分类数据关联

---

## 首批算子清单

| 类别 | 算子 | 说明 |
|------|------|------|
| **TS 滚动聚合** | `ts_mean`, `ts_sum`, `ts_std`, `ts_var`, `ts_max`, `ts_min`, `ts_count`, `ts_prod`, `ts_med` | 窗口聚合 |
| **TS 延迟/变化** | `ts_delay`, `ts_delta`, `ts_pct_change` | 时间序列基础 |
| **TS 排名** | `ts_rank`, `ts_argmax`, `ts_argmin` | 窗口内排名 |
| **TS 相关** | `ts_corr`, `ts_cov` | 滚动相关/协方差 |
| **TS 分位数** | `ts_quantile`, `ts_qtlu`, `ts_qtld` | 分位数操作 |
| **TS 加权** | `ts_wma`, `ts_ema`, `ts_decay_linear` | 加权移动平均 |
| **TS 高阶** | `ts_skew`, `ts_kurt` | 高阶统计量 |
| **CS 排名** | `cs_rank`, `cs_scale` | 截面排名/缩放 |
| **CS 标准化** | `cs_zscore`, `cs_demean`, `cs_winsorize` | 截面标准化 |
| **CS 分组** | `group_rank`, `group_zscore`, `group_demean` | 组内操作 |
| **标量-数学** | `abs`, `log`, `exp`, `sqrt`, `sign`, `power` | 数学函数 |
| **标量-比较** | `max2`, `min2`, `clip` | 比较函数 |
| **标量-逻辑** | `if_else`, `and`, `or`, `not` | 逻辑函数 |
| **技术指标** | `rsi`, `atr`, `macd`, `boll`, `kdj` | 复合技术指标 |
