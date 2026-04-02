# Helpers - 纯函数工具模块

**版本**: v0.5.0
**最后更新**: 2026-02-06
**状态**: ✅ 稳定

## 概要

提供无副作用的纯函数工具，用于复权计算和 PIT（Point-in-Time）查询支持。

## 核心职责

- **纯函数实现**：无状态、可预测、易于测试
- **复权计算**：前复权（QFQ）和后复权（HFQ）公式
- **PIT 支持**：时点安全的数据过滤逻辑

## 可用模块

| 模块 | 描述 | 主要函数 |
|------|------|----------|
| `adjustment.py` | 复权计算工具 | `apply_qfq_adj()`, `apply_hfq_adj()` |
| `pit.py` | PIT 查询工具 | `parse_asof_date()`, `filter_by_knowledge_date()` |

## adjustment.py - 复权计算

### 前复权（QFQ）

```python
from datetime import date
from ditto_data.helpers.adjustment import apply_qfq_adj

# 前复权调整（当前价格 × 当前因子 / 最新因子）
df_adj = apply_qfq_adj(
    df=bars_with_factor,  # 已关联 adj_factor 的 K线数据
    adj_df=adj_factor_df,  # 调整因子数据
    asof=date(2024, 6, 30),  # 可选：PIT 日期
)

# Tushare QFQ 公式：
# adj_price = orig_price * cur_factor / latest_factor
```

### 后复权（HFQ）

```python
from ditto_data.helpers.adjustment import apply_hfq_adj

# 后复权调整（当前价格 × 当前因子）
df_adj = apply_hfq_adj(
    df=bars_with_factor,
    adj_df=adj_factor_df,
)

# HFQ 公式：
# adj_price = orig_price * cur_factor
```

### 注意事项

- `pre_close` 字段不需要复权调整（Tushare 已处理）
- 只对 `open/high/low/close` 进行复权
- 缺失因子值使用 `1.0`（返回原始价格）

## pit.py - PIT 查询

### 解析日期

```python
from ditto_data.helpers.pit import parse_asof_date

# 解析 asof 参数
dt = parse_asof_date("2024-06-30")  # str -> date
dt = parse_asof_date(date(2024, 6, 30))  # date -> date
```

### PIT 安全过滤

```python
from ditto_data.helpers.pit import filter_by_knowledge_date

# 根据 knowledge_date 过滤数据
df_filtered = filter_by_knowledge_date(
    df=df,
    pit_dt=date(2024, 6, 30),
    date_column="knowledge_date",  # 默认值
)

# 优先使用 knowledge_date，fallback 到 trade_date（会记录警告）
```

### PIT 安全原则

- **knowledge_date**: 数据已知日期（推荐）
- **trade_date**: 数据发生日期（非 PIT 安全）

## 设计模式

### 纯函数优势

```
┌─────────────────┐
│   Application   │
├─────────────────┤
│     Helpers     │  ← 纯函数工具（无状态）
├─────────────────┤
│     Store       │  ← 数据访问层
└─────────────────┘
```

| 特性 | 说明 |
|------|------|
| 无状态 | 不依赖外部状态，输入确定则输出确定 |
| 可测试 | 易于编写单元测试 |
| 可组合 | 可以自由组合使用 |

## 使用示例

### MarketService 中的使用

```python
from ditto_data.helpers.adjustment import apply_qfq_adj, apply_hfq_adj
from ditto_data.helpers.pit import filter_by_knowledge_date

# 1. PIT 过滤复权因子
adj_df = filter_by_knowledge_date(
    df=self._adj_factor_store.read(...),
    pit_dt=asof,
)

# 2. 应用复权调整
if adj_type == AdjType.QFQ:
    df = apply_qfq_adj(df, adj_df, asof)
elif adj_type == AdjType.HFQ:
    df = apply_hfq_adj(df, adj_df)
```

## 相关文档

- [PIT 查询设计](../../../../../docs/design/07_pit_query_design.md)
- [Market 域文档](../domains/market/README.md)
