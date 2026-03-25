# 策略引擎 Phase 1 实施计划 — 主计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 实现决策 Pipeline 闭环 — 输入 bundle → Pipeline → TargetPortfolio

**Architecture:** Phase 1 是纯计算阶段，产出 `strategy/pipeline.py`、`strategy/builtins/`、`portfolio/` 三个 Core 子模块。所有代码为纯函数 / 无状态类，无 I/O。Pipeline 通过 Polars DataFrame 向量化计算，DecisionStage Protocol（Phase 0）分发阶段。

**Tech Stack:** Python 3.13, Polars, dataclass(frozen=True), Protocol, pytest

**Design Doc:** `docs/plans/2026-03-21-strategy-engine-system-design-v3.md` §1-2, §6.1, §9.1

**Prerequisite:** Phase 0 Part 01-04 DONE; Part 05 (DataHub) 不阻塞 Phase 1（可并行）

---

## Phase 1 范围

```
输入: StrategyInputBundle（市场数据 + 策略配置 + 参数覆盖）
  ↓
Pipeline Runner 编排:
  Universe → Signal → Score → Filter → Select → Allocate → Constraint
  ↓
输出: TargetPortfolio + SignalSnapshot
```

**包含：**
- Pipeline Runner（StrategyPipeline 类，顺序编排 DecisionStage）
- 内置 stage 实现（Universe / Signal / Scoring / Filtering / Selection）
- WeightAllocator（equal_weight / score_weight）
- ConstraintCheck（priority 排序执行）
- RiskLockFilter（R4）
- etf_rotation 模板端到端验证
- StrategyInputBundle 组装

**不包含（后续 Phase）：**
- EngineLoop / 日历步进（Phase 2）
- ExecutionPlanner / Brokerage（Phase 2）
- A 股完整交易规则（Phase 3）
- PreTradeRiskCheck / PostTradeRiskGuard（Phase 4）
- 多策略模板扩展（Phase 5）

---

## 子计划索引（按执行顺序）

| # | 子计划 | 范围 | 复杂度 | 依赖 |
|---|--------|------|--------|------|
| 01 | [pipeline-runner](2026-03-21-strategy-engine-phase1-01-pipeline-runner.md) | StrategyPipeline + DecisionFrame schema + StrategyInputBundle | M | Phase 0 |
| 02 | [builtin-stages](2026-03-21-strategy-engine-phase1-02-builtin-stages.md) | UniverseStage / SignalStage / ScoringStage / FilteringStage / SelectionStage | L | Part 1 |
| 03 | [portfolio-construction](2026-03-21-strategy-engine-phase1-03-portfolio-construction.md) | WeightAllocator / ConstraintChecker / AllocationStage / ConstraintStage | L | Part 1 |
| 04 | [risklock-template-e2e](2026-03-21-strategy-engine-phase1-04-risklock-template-e2e.md) | RiskLockFilter + etf_rotation 模板 + E2E RECOMMENDATION 测试 | L | Part 2 + Part 3 |

## 执行顺序

```
01 Pipeline Runner (M) ──── 无依赖，Phase 0 完成即可
02 Built-in Stages (L) ─── 依赖 01（需要 Pipeline 来测试 Stage）
03 Portfolio Construction (L) ─ 依赖 01（需要 TargetPortfolio 输出）
04 RiskLock + Template + E2E (L) ─ 依赖 02 + 03（需要全部 Stage 就绪）
```

推荐路径：**01 → 02 → 03 → 04**（02 和 03 可并行加速）

## Phase 1 交付物清单

### Core 层新增模块

```
ditto_core/
├── strategy/                    # [已有] Phase 0 类型定义
│   ├── pipeline.py              # [Part 1] StrategyPipeline + DecisionFrame schema
│   ├── builtins/                # [Part 2] 内置 Stage 实现
│   │   ├── __init__.py
│   │   ├── universe.py          #     UniverseStage
│   │   ├── signal.py            #     SignalStage
│   │   ├── scoring.py           #     ScoringStage
│   │   ├── filtering.py         #     FilteringStage
│   │   └── selection.py         #     SelectionStage
│   └── templates/               # [Part 4] 策略模板
│       ├── __init__.py
│       └── etf_rotation.py      #     etf_rotation 模板配置
│
├── portfolio/                   # [Part 3] 组合构建层（新增模块）
│   ├── __init__.py
│   ├── allocation.py            #     WeightAllocator Protocol + EqualWeight / ScoreWeight
│   └── constraints.py           #     ConstraintChecker（priority 排序）
```

### 测试

```
packages/core/tests/
├── unit/strategy/
│   ├── test_pipeline_unit.py        # [Part 1] Pipeline Runner
│   ├── test_stages_unit.py          # [Part 2] 内置 Stages
│   ├── test_allocation_unit.py      # [Part 3] WeightAllocator
│   ├── test_constraints_unit.py     # [Part 3] ConstraintChecker
│   └── test_template_unit.py        # [Part 4] etf_rotation 模板
│
└── integration/strategy/
    └── test_etf_rotation_e2e.py     # [Part 4] 端到端 RECOMMENDATION
```

## 质量门禁

每个子计划完成后执行：

```bash
pixi run -e dev check          # lint + fmt + type + test --fast
```

Phase 1 全部完成后执行：

```bash
pixi run -e dev ci             # CI 完整检查
```

## 里程碑

**Phase 1 完成标志：** ETF 轮动策略 RECOMMENDATION 闭环 — 给定输入数据 + 策略配置，Pipeline 输出合法的 TargetPortfolio，且 RiskLockFilter 能正确过滤锁定标的。

## 注意事项

1. **纯计算**：所有 Phase 1 代码无 I/O，无网络，无文件系统访问
2. **Polars 向量化**：Stage 内部使用 Polars DataFrame 操作，不逐行循环
3. **frozen dataclass**：新增数据结构遵循 Phase 0 约定
4. **DecisionFrame 不强制 schema**：Pipeline 通过列名约定流转数据，不做运行时 schema 校验
5. **Phase 0 Part 05 (DataHub) 不阻塞**：InstrumentRuleProvider 等 DataHub 组件在 Phase 2 才需要
