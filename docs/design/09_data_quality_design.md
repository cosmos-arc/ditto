# Ditto 数据质量设计

**版本：v1.1**

**日期：2025-12-28**

---

## 变更记录

| 版本 | 日期 | 变更内容 |
|------|------|----------|
| v1.1 | 2025-12-28 | Phase 1 实现完成：采用 YAML + Pydantic 多文件配置架构 |
| v1.0 | 2025-12-25 | 初始设计 |

---

## 1. 设计原则

### 1.1 核心理念

参考业界最佳实践（Great Expectations / dbt / Data Contract）：

1. **规则定义收敛**：所有 DQ 规则定义在 DataHub 的 YAML 配置中
2. **执行时机分离**：写入时同步执行 vs 定时批量执行
3. **分层校验**：技术校验 → 业务规则 → 统计异常

### 1.2 不做双源校验

Phase 0-1 阶段**不实现双源校验**（Tushare vs AkShare），原因：

| 维度 | 分析 |
|------|------|
| 复杂度 | 需维护两套适配器，增加 50% 工作量 |
| 收益 | ETF 数据来自交易所，错误概率极低 |
| 替代方案 | 时序异常检测 + Golden Dataset 人工核验更实用 |

AkShare 保留作为**降级备选**，而非校验对比源。

---

## 2. 规则分层

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              DQ 规则分层                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ L1: 技术校验（Technical）                                            │   │
│  │                                                                      │   │
│  │ - 非空检查：sid, trade_date, close 必填                              │   │
│  │ - 主键唯一：(sid, trade_date) 不重复                                 │   │
│  │ - 类型检查：数值字段为数值类型                                        │   │
│  │ - 外键存在：sid 存在于 security 表                                   │   │
│  │                                                                      │   │
│  │ 执行时机：写入时同步                                                  │   │
│  │ 失败处理：硬失败，阻断写入，数据进隔离区                              │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ L2: 业务规则（Business）                                             │   │
│  │                                                                      │   │
│  │ - OHLC 一致性：high >= low, high >= max(open, close)                │   │
│  │ - 正数检查：open, high, low, close, volume >= 0                     │   │
│  │ - 涨跌幅限制：|pct_change| <= 11%（含 ST/新股容差）                  │   │
│  │ - 量额匹配：volume > 0 时 amount > 0                                 │   │
│  │                                                                      │   │
│  │ 执行时机：写入时同步                                                  │   │
│  │ 失败处理：软失败，记录警告，允许写入                                  │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ L3: 统计异常（Statistical）                                          │   │
│  │                                                                      │   │
│  │ - 成交量 Z-score：60 日滚动窗口，|zscore| > 5 告警                   │   │
│  │ - 完整性检查：Universe 标的数据完整率 >= 95%                         │   │
│  │ - 时序断点：检测连续缺失 > 3 天的标的                                │   │
│  │ - 趋势异常：数据量较上周同期下降 > 10%                               │   │
│  │                                                                      │   │
│  │ 执行时机：定时批量（每日收盘后）                                      │   │
│  │ 失败处理：生成报告，发送告警，不阻断                                  │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. 配置方式（YAML + Pydantic）

### 3.1 架构决策

Phase 1 实现采用了**多文件 YAML + Pydantic 验证**的架构，而非单一 YAML 文件：

| 方案 | 优势 | 劣势 | 采用 |
|------|------|------|------|
| 单一 YAML 文件 | 集中管理 | 文件过长、diff 冲突多 | ❌ |
| **多文件 YAML + Pydantic** | **模块化、类型安全、易审计** | **稍多文件** | ✅ |
| 纯 Python 代码 | IDE 友好 | 不透明、不易审计 | ❌ |

### 3.2 配置文件结构

```
packages/datahub/
└── config/
    └── dq_rules/
        ├── etf_daily.yml       # ETF 日频数据规则
        ├── index_daily.yml     # 指数日频数据规则
        ├── market_daily.yml    # 股票日频数据规则
        ├── index_weight.yml    # 指数权重规则
        └── adj_factor.yml      # 复权因子规则
```

### 3.3 规则文件示例（etf_daily.yml）

```yaml
dataset: etf_daily
description: "ETF 日 K 线数据"

# L1: 技术校验（写入时强制）
l1_technical:
  - rule: not_null
    columns: [sid, trade_date, open, high, low, close]
    message: "必填字段不能为空"

  - rule: unique
    columns: [sid, trade_date]
    message: "主键重复"

# L2: 业务规则（写入时警告）
l2_business:
  - rule: positive
    columns: [open, high, low, close]
    message: "价格必须为正"

  - rule: expression
    name: ohlc_consistency
    expr: "high >= low AND high >= open"
    message: "OHLC 关系不一致"

# L3: 统计异常（定时批量）
l3_statistical:
  - rule: zscore
    name: volume_spike
    column: volume
    window: 60
    threshold: 5
    message: "成交量异常波动"
```

### 3.4 规则类型说明

| 规则类型 | 层级 | 参数 | 说明 |
|----------|------|------|------|
| `not_null` | L1 | columns | 指定列不能为空 |
| `unique` | L1 | columns | 指定列组合唯一 |
| `foreign_key` | L1 | column, reference | 外键存在性检查 |
| `positive` | L2 | columns | 值必须 > 0 |
| `non_negative` | L2 | columns | 值必须 >= 0 |
| `expression` | L2 | expr | 自定义 Polars 表达式 |
| `zscore` | L3 | column, window, threshold | 滚动 Z-score 异常检测 |
| `completeness` | L3 | universe, threshold | Universe 覆盖率检查 |
| `continuity` | L3 | max_gap_days | 时序连续性检查 |

---

## 4. 执行引擎（DataHub）

### 4.1 目录结构

```
packages/datahub/
├── config/
│   └── dq_rules/              # YAML 规则文件目录
│       ├── etf_daily.yml
│       ├── index_daily.yml
│       ├── market_daily.yml
│       ├── index_weight.yml
│       └── adj_factor.yml
│
└── src/ditto_datahub/
    └── dq/                     # DQ 模块
        ├── __init__.py
        ├── models.py           # Pydantic 规则模型 ✅
        ├── engine.py           # DQ 执行引擎 ✅
        ├── result.py           # 校验结果模型 ✅
        ├── report.py           # 报告生成器 ✅
        └── checkers/           # 规则检查器实现
            ├── __init__.py
            ├── technical.py    # L1 技术校验 ✅
            ├── business.py     # L2 业务规则 ✅
            └── statistical.py  # L3 统计异常 ✅
```

> ✅ = Phase 1 已实现

### 4.2 DQEngine 实现 ✅

详见 `src/ditto_datahub/dq/engine.py`

---

## 5. Repository 集成（Phase 3 待实现）

> **注意**：此部分（Task 1.8）已延后到 Phase 3 实现，原因：
> 1. 需要在真实写入流程中集成验证
> 2. 需要与数据摄入增强功能协同
> 3. 需要完整的数据流测试覆盖

---

## 6. Server 批量检查任务 ✅

L3 批量 DQ 检查任务已实现：
`apps/server/src/ditto_server/ingestion/tasks/dq_batch.py`

---

## 7. 隔离区机制 ✅

SQLite 隔离区存储已实现：
`src/ditto_datahub/stores/quarantine_store.py`

---

## 8. 报告生成 ✅

DQ 报告生成器已实现：
`src/ditto_datahub/dq/report.py`

---

## 9. Phase 1 实现状态

### 9.1 完成情况

| Task | 描述 | 状态 | 说明 |
|------|------|------|------|
| 1.1 | YAML 规则配置文件 | ✅ | 5 个数据集规则文件 |
| 1.2 | Pydantic 规则模型 | ✅ | models.py 完整实现 |
| 1.3 | DQEngine 核心 | ✅ | 引擎 + 规则加载 |
| 1.4 | TechnicalChecker（L1） | ✅ | not_null, unique, foreign_key |
| 1.5 | BusinessChecker（L2） | ✅ | positive, expression 检查 |
| 1.6 | StatisticalChecker（L3） | ✅ | 框架实现，Z-score/completeness 待完善 |
| 1.7 | 隔离区机制 | ✅ | QuarantineStore + SQLite 表 |
| 1.8 | Repository 集成 | ⏸️ | **延后到 Phase 3** |
| 1.9 | Server L3 任务 | ✅ | dq_batch_check Prefect task |
| 1.10 | DQ 报告生成 | ✅ | Markdown + HTML 报告 |

### 9.2 测试覆盖

```bash
# Phase 1 DQ 测试（53 个测试全部通过）
✅ test_models.py         - Pydantic 模型验证
✅ test_engine.py         - 引擎和规则加载
✅ test_checkers.py       - 三层检查器
✅ test_result.py         - 结果模型
✅ test_report.py         - 报告生成
✅ test_quarantine_store.py - 隔离区存储
```

### 9.3 文件结构

```
packages/datahub/
├── config/dq_rules/
│   ├── etf_daily.yml       ✅
│   ├── index_daily.yml     ✅
│   ├── market_daily.yml    ✅
│   ├── index_weight.yml    ✅
│   └── adj_factor.yml      ✅
│
├── src/ditto_datahub/
│   ├── dq/
│   │   ├── __init__.py     ✅
│   │   ├── models.py       ✅
│   │   ├── engine.py       ✅
│   │   ├── result.py       ✅
│   │   ├── report.py       ✅
│   │   └── checkers/
│   │       ├── __init__.py         ✅
│   │       ├── technical.py        ✅
│   │       ├── business.py         ✅
│   │       └── statistical.py      ✅
│   │
│   └── stores/
│       └── quarantine_store.py     ✅
│
└── tests/unit/dq/
    ├── test_models.py              ✅
    ├── test_engine.py              ✅
    ├── test_checkers.py            ✅
    ├── test_result.py              ✅
    ├── test_report.py              ✅
    └── test_quarantine_store.py    ✅
```

---

## 10. 总结

### 设计对比

| 维度 | 原方案（v1.0） | 实现方案（v1.1） |
|------|----------------|------------------|
| 规则定义 | 单一 `dq_rules.yaml` | **多文件 YAML + Pydantic** |
| 配置验证 | 运行时解析 | **类型安全的 Pydantic 模型** |
| 文件组织 | 单一文件 | **按数据集分离** |
| 执行引擎 | 统一 `DQEngine` | ✅ 按设计实现 |
| 双源校验 | 不实现 | ✅ 按设计不实现 |

### 三层规则

| 层级 | 检测内容 | 执行时机 | 失败处理 | 状态 |
|------|----------|----------|----------|------|
| L1 | 非空、唯一、外键 | 写入时 | **阻断写入** | ✅ |
| L2 | OHLC、涨跌幅 | 写入时 | **警告记录** | ✅ |
| L3 | Z-score、完整性 | 定时批量 | **告警通知** | ✅ 框架 |

### Phase 3 待办

1. **Task 1.8**：Repository 集成 DQEngine
   - L1 失败阻断写入
   - L2 警告记录日志
   - 隔离区数据保存

2. **L3 统计检测完善**：
   - Z-score 计算实现
   - 完整性检查实现
   - 时序连续性检查

3. **真实数据验证**：
   - 使用历史数据测试
   - 验证误报率
   - 调优阈值参数
