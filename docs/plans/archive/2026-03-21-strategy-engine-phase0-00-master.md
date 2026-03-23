# 策略引擎 Phase 0 实施计划 — 主计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 建立策略引擎的数据契约层与基础设施，为后续 Phase 1-5 提供共享类型基础

**Architecture:** Phase 0 是纯数据结构定义阶段，产出 accounting/、execution/rules、execution/fills、strategy/specs 四个 Core 模块，以及 DataHub 层的 PIT 存储和 Service。所有 Core 代码为纯数据结构 + Protocol，无 I/O、无业务逻辑。

**Tech Stack:** Python 3.13, dataclass(frozen=True), StrEnum, Protocol, pytest

**Design Doc:** `docs/plans/2026-03-21-strategy-engine-system-design-v3.md`

---

## 子计划索引（按执行顺序）

| # | 子计划 | 范围 | 复杂度 | 依赖 |
|---|--------|------|--------|------|
| 01 | [housekeeping](2026-03-21-strategy-engine-phase0-01-housekeeping.md) | 归档旧 README (R10)、更新 CLAUDE.md | S | 无 |
| 02 | [accounting](2026-03-21-strategy-engine-phase0-02-accounting.md) | Position / CashBook / OrderBook / Account / AccountView / BuyingPowerModel | L | 无 |
| 03 | [strategy-specs](2026-03-21-strategy-engine-phase0-03-strategy-specs.md) | StrategySpec / StrategyRun / StrategyTemplate / StrategyVersion / ParamConstraint / DecisionStage | L | 无 |
| 04 | [execution-rules](2026-03-21-strategy-engine-phase0-04-execution-rules.md) | InstrumentDefinition / TradingRuleSet / FeeSchedule / FillOutcome | L | Part 2 |
| 05 | [datahub](2026-03-21-strategy-engine-phase0-05-datahub.md) | InstrumentRuleProvider / PIT stores / TradingRuleStore / FeeScheduleStore | L | Part 2 + Part 4 |

## 执行顺序

```
01 housekeeping (S) ────── 可最先执行，无依赖
02 accounting (L)   ────── 最底层，无依赖
03 strategy-specs (L) ──── 无 Core 依赖，可与 02 并行
04 execution-rules (L) ─── 依赖 02（Order/Account 类型引用）
05 datahub (L)      ────── 依赖 02 + 04
```

推荐路径：**01 → 02 → 03 → 04 → 05**（02 和 03 可并行加速）

## Phase 0 交付物清单

### Core 层新增模块

```
ditto_core/
├── accounting/               # [Part 1] 共享账户契约层
│   ├── __init__.py
│   ├── position.py           #   Position (frozen)
│   ├── cash.py               #   CashBook (frozen, R6)
│   ├── order_book.py         #   OrderBook / OrderTicket (frozen, F5) / OrderEvent / OrderBookReadOnly
│   ├── account.py            #   Account / AccountView
│   └── buying_power.py       #   BuyingPowerModel Protocol / CashAccountBuyingPower
│
├── execution/                # [Part 2] 执行层类型定义
│   ├── __init__.py
│   ├── orders.py             #   Order / OrderType / OrderDirection
│   ├── fills.py              #   FillOutcome (F4) / FillEvent / Filled / NoFill
│   └── rules.py              #   InstrumentDefinition / TradingRuleSet / FeeSchedule
│
└── strategy/                 # [Part 3] 策略决策层类型定义
    ├── __init__.py
    ├── specs.py              #   StrategySpec / StrategyTemplate / StrategyVersion
    ├── models.py             #   StrategyRun / SignalSnapshot / TargetPortfolio
    ├── context.py            #   StrategyContext
    └── protocols.py          #   DecisionStage Protocol
```

### DataHub 层新增

```
ditto_datahub/
├── stores/metadata/
│   ├── trading_rule_reader.py    # [Part 4] PIT 查询
│   ├── trading_rule_writer.py    # [Part 4] PIT 写入
│   ├── fee_schedule_reader.py    # [Part 4] PIT 查询
│   └── fee_schedule_writer.py    # [Part 4] PIT 写入
│
├── services/strategy/
│   ├── instrument_rule_provider.py   # [Part 4] 三层规则组装
│   └── __init__.py
│
└── models/strategy.py          # [Part 4] 控制表 ORM 更新
```

### 测试

```
packages/core/tests/
├── unit/accounting/            # [Part 1] 不变量测试
│   ├── test_position_unit.py
│   ├── test_cash_book_unit.py
│   ├── test_order_book_unit.py
│   ├── test_account_unit.py
│   └── test_buying_power_unit.py
│
├── unit/execution/             # [Part 2] 场景矩阵测试
│   ├── test_orders_unit.py
│   ├── test_fills_unit.py
│   └── test_rules_unit.py
│
└── unit/strategy/              # [Part 3] Spec 校验测试
    ├── test_specs_unit.py
    └── test_models_unit.py
```

## 质量门禁

每个子计划完成后执行：

```bash
pixi run -e dev check          # lint + fmt + type + test --fast
```

Phase 0 全部完成后执行：

```bash
pixi run -e dev ci             # CI 完整检查
```
