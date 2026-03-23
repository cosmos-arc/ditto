# Phase 0 Part 5: Housekeeping

> **Status: DONE** (2026-03-21) | Branch: `phase0/01-housekeeping` | Commits: `e5c810ea`, `b63f6c75`

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 归档旧 README.md (R10)、更新 Core CLAUDE.md 模块结构、清理占位 __init__.py

**Architecture:** 无架构变更，纯清理工作。

**Design Doc:** v3 §11.1 Phase 0 (R10 归档旧文档)

**前置依赖:** 无

---

## Task 1: 归档旧 README.md `[S]` ✅

> **R10**: 旧设计文档（v0.2 README）与 v3 设计冲突，需归档到 `docs/archive/`。

**Files:**
- Archive: `packages/core/src/ditto_core/strategy/README.md` → `docs/archive/v02-strategy-readme.md`
- Archive: `packages/core/src/ditto_core/portfolio/README.md` → `docs/archive/v02-portfolio-readme.md`

**Step 1: 创建 archive 目录**

```bash
mkdir -p docs/archive
```

**Step 2: 归档 README 文件**

```bash
git mv packages/core/src/ditto_core/strategy/README.md docs/archive/v02-strategy-readme.md
git mv packages/core/src/ditto_core/portfolio/README.md docs/archive/v02-portfolio-readme.md
```

**Step 3: Commit**

```bash
git add docs/archive/
git commit -m "chore: archive v0.2 strategy/portfolio READMEs (R10)"
```

---

## Task 2: 更新 Core CLAUDE.md 模块结构 `[S]` ✅

**Files:**
- Modify: `packages/core/CLAUDE.md`

**Step 1: 更新模块结构**

将 `packages/core/CLAUDE.md` 中的模块结构从：

```
ditto_core/
├── quality/           # 数据质量引擎（已实现）
├── engine/            # 核心引擎（Phase 1 已实现）
├── portfolio/         # 组合管理（待实现）
└── strategy/          # 策略框架（待实现）
```

更新为：

```
ditto_core/
├── quality/           # 数据质量引擎（已实现）
├── engine/            # 核心引擎（Phase 1 已实现）
├── accounting/        # 共享账户契约层（Phase 0）
├── execution/         # 执行层类型定义（Phase 0）
├── strategy/          # 策略决策层类型定义（Phase 0）
└── portfolio/         # 组合管理（待实现）
```

**Step 2: 添加 accounting/execution/strategy 子领域说明**

在 `## 子领域规范` 部分补充：

```markdown
### Accounting（共享账户契约层）

**职责**：Position / CashBook / OrderBook / Account / AccountView / BuyingPowerModel

**关键点**：
- 纯数据结构层，frozen dataclass + Protocol
- Account 是唯一可变对象（内部替换 frozen 引用）
- AccountView 是只读快照，供上层安全消费
- 详见 v3 设计文档 §3.1-§3.6

### Execution（执行层类型定义）

**职责**：三层规则 (R6)、FillOutcome (F4)

**关键点**：
- InstrumentDefinition / TradingRuleSet / FeeSchedule 是 frozen dataclass
- TradingRuleSet 和 FeeSchedule 通过 PIT 基础设施版本化
- FillOutcome 是显式联合类型（Filled / NoFill）
- 详见 v3 设计文档 §4.3, §5.1

### Strategy（策略决策层）

**职责**：StrategySpec / StrategyRun / StrategyContext / DecisionStage Protocol

**关键点**：
- StrategySpec 是策略的完整语义契约
- DecisionStage 是 Protocol，Pipeline 通过它分发
- 详见 v3 设计文档 §2, §6.1
```

**Step 3: Commit**

```bash
git add packages/core/CLAUDE.md
git commit -m "docs(core): update CLAUDE.md with Phase 0 module structure"
```

---

## Task 3: Housekeeping 验证 `[S]` ✅

```bash
pixi run -e dev check
```
