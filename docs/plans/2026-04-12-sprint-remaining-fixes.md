> **Status**: Superseded by [2026-04-13-v1-review-fix-plan.md](./2026-04-13-v1-review-fix-plan.md)

# V1 Sprint Remaining Fixes — 剩余问题修复计划

## 概述

- **分支**: `feat/v1-sprint`
- **前置**: `2026-04-12-v1-sprint-review-fixes.md`（20/24 已完成）
- **创建**: 2026-04-12
- **范围**: 4 个待修复任务 + 1 个前置验证

## 剩余问题清单

| # | 任务 | 复杂度 | 来源 | 依赖 |
|---|------|--------|------|------|
| 1 | interfaces.models DTO 解耦 | L | Review Phase 2.1 | 无 |
| 2 | steps.py 拆分（766 行 → steps/ 目录） | L | Review Phase 3.1 | 无 |
| 3 | test_steps_unit.py 拆分（1344 行） | M | Review Phase 4.3 | #2 |
| 4 | TradeService DI 注册缺失 | S | Pre-existing test failures | 无 |

---

## 技术方案

### 问题 1: interfaces.models DTO 解耦

**现状**: `interfaces/models/` 中 3 个文件直接导入 `ditto_app` 内部类型，用于 `to_*_response()` 转换函数。

| 文件 | 导入 |
|------|------|
| `models/trade.py` | `ComparisonMetrics`, `PnlSummary`, `ActualPositionSnapshot`, `ManualExecutionFill`, `TradeIntent` |
| `models/backtest.py` | `TradeRecord` |
| `models/identifier.py` | `MetadataQueryFacade` |

**方案**: 将 `to_*_response()` 转换函数从 `models/` 移至对应 `routes/` 文件。`models/` 仅保留 Pydantic schema 定义（纯数据结构，无 app 依赖）。

**影响分析**:
- `routes/trade.py` 已经导入 app 层 handler/facade，移入 mapper 不会新增依赖方向
- `routes/backtest.py` 已有 `_to_cost_config()` mapper 模式，保持一致
- `identifier.py` 的 `resolve_instrument_identifier()` 需移至 `routes/` 或独立 utility

### 问题 2: steps.py 拆分

**现状**: `ditto_engine/backtest/steps.py` 766 行，含 10 个类。

**方案**: 按职责拆分为 `steps/` 包：

```
steps/
├── __init__.py      # Re-export: TradingStep, StepResult, StepContext, 所有 Step 类
├── types.py         # StepResult, StepContext (共享数据类型)
├── data_fetch.py    # DataFetchStep (~54 行)
├── risk_scan.py     # RiskScanStep (~81 行)
├── strategy.py      # StrategyStep (~92 行)
├── planning.py      # PlanningStep (~74 行)
├── pre_trade.py     # PreTradeStep (~148 行)
├── execution.py     # ExecutionStep (~53 行)
└── audit.py         # AuditStep (~46 行)
```

**关键决策**:
- `TradingStep` Protocol 放在 `types.py`（与 StepResult/StepContext 一起作为公共接口）
- `__init__.py` re-export 所有公共符号，确保 `from ditto_engine.backtest.steps import X` 不中断
- `PreTradeStep` 虽然 148 行，但逻辑内聚，不进一步拆分

### 问题 3: test_steps_unit.py 拆分

**现状**: 1344 行，12 个 test class，50 个测试方法。依赖 `steps.py` 结构。

**方案**: 配合问题 2 同步拆分：

```
tests/unit/backtest/
├── test_step_types_unit.py       # TestStepResult + TestStepContext + TestTradingStepProtocol
├── test_data_fetch_step.py       # TestDataFetchStep
├── test_risk_scan_step.py        # TestRiskScanStep
├── test_strategy_step.py         # TestStrategyStep
├── test_planning_step.py         # TestPlanningStep
├── test_pre_trade_step.py        # TestPreTradeStep
├── test_execution_step.py        # TestExecutionStep
└── test_audit_step.py            # TestAuditStep
```

### 问题 4: TradeService DI 注册缺失

**现状**: `RecordFillHandler` 和 `UpdateIntentStatusHandler` 均依赖 `TradeService`（来自 `ditto_data.services.trade_service`），但 Data 层 8 个 DI Provider 均未注册 `TradeService`。导致 `test_providers_unit.py` 和 `test_derived_provider_unit.py` 中 7 个测试失败。

**方案**: 在 Data 层 DI 中注册 `TradeService`。需要确认注册位置（可能是新建 `TradeProvider` 或添加到现有 `RuntimeProvider`）。

---

## 任务清单

### Phase A: DTO 解耦（独立，可先行）

- [x] **A1. trade.py mapper 移至 routes** `[L]` ✅
  - 5 个 mapper 函数移至 `routes/trade.py`，`models/trade.py` 仅保留 Pydantic 模型
  - 验收: 0 个 `ditto_app` 导入 ✅

- [x] **A2. backtest.py mapper 移至 routes** `[S]` ✅
  - `to_trade_response` 移至 `routes/backtest.py`，`models/backtest.py` 移除 `TradeRecord` 导入
  - 验收: 0 个 `ditto_app` 导入 ✅

- [x] **A3. identifier.py 删除** `[S]` ✅
  - 确认为死代码（无任何引用），直接删除整个文件
  - 验收: 文件已删除，`models/__init__.py` 已更新 ✅

- [x] **A4. DTO 解耦验证** `[S]` ✅
  - `pixi run -e dev check` 通过 ✅
  - 30 个 trade API 集成测试全部通过 ✅

### Phase B: steps.py 拆分（独立，可与 Phase A 并行）

- [x] **B1. 创建 steps/ 包 + 迁移共享类型** `[M]` ✅
  - `steps/` 包已创建，`types.py` 包含 `StepResult`, `StepContext`, `TradingStep` Protocol
  - `__init__.py` re-export 所有 10 个公共符号
  - 验收: `from ditto_engine.backtest.steps import TradingStep, StepResult, StepContext` 正常 ✅
    - `packages/engine/src/ditto_engine/backtest/steps/types.py` — 新建
    - `packages/engine/src/ditto_engine/backtest/steps.py` → 删除（移入包）

- [ ] **B2. 迁移 7 个 Step 实现类** `[M]`
  - 按方案拆分到 7 个子模块
  - 每个文件 `< 200 行`
  - `__init__.py` re-export 所有 Step 类
  - 验收: 所有 `from ditto_engine.backtest.steps import X` 不中断
  - 文件:
    - `packages/engine/src/ditto_engine/backtest/steps/data_fetch.py` — 新建
    - `packages/engine/src/ditto_engine/backtest/steps/risk_scan.py` — 新建
    - `packages/engine/src/ditto_engine/backtest/steps/strategy.py` — 新建
    - `packages/engine/src/ditto_engine/backtest/steps/planning.py` — 新建
    - `packages/engine/src/ditto_engine/backtest/steps/pre_trade.py` — 新建
    - `packages/engine/src/ditto_engine/backtest/steps/execution.py` — 新建
    - `packages/engine/src/ditto_engine/backtest/steps/audit.py` — 新建

- [x] **B3. 更新外部导入** `[S]` ✅
  - 所有外部导入路径通过 `__init__.py` re-export 保持兼容
  - 验收: `pixi run -e dev lint` All checks passed ✅

- [x] **B4. 拆分测试文件** `[M]` ✅
  - `test_steps_unit.py` (1345行) 拆分为 8 个测试文件 + conftest.py
  - 共享 fixture 提取到 `conftest.py`
  - 验收: 408 个 backtest 测试全部通过 ✅

- [x] **B5. steps 拆分验证** `[S]` ✅
  - `pixi run -e dev check` 通过 ✅

### Phase C: TradeService DI 修复（独立，可先行）

- [x] **C1. 注册 TradeService 到 DI 容器** `[S]` ✅
  - `TradeProvider()` 添加到 `test_providers_unit.py` 和 `test_derived_provider_unit.py` 的容器构建
  - 验收: 10 + 6 tests passed ✅

- [x] **C2. DI 修复验证** `[S]` ✅
  - `pixi run -e dev pytest packages/app/tests/unit/test_providers_unit.py --no-cov` — 10 passed ✅
  - `pixi run -e dev pytest interfaces/tests/registry/test_derived_provider_unit.py --no-cov` — 6 passed ✅

### Phase D: 最终验证

- [x] **D1. 全量检查** `[S]` ✅
  - `pixi run -e dev lint` — All checks passed ✅
  - `pixi run -e dev fmt --check` — 1238 files already formatted ✅
  - `pixi run -e dev type` — 0 errors, 0 warnings, 0 notes ✅
  - `pixi run -e dev test --fast --no-cov` — **5138 passed**, 25 skipped ✅

---

## 执行顺序

```
Phase A (DTO 解耦)     ─┐
Phase B (steps 拆分)    ─┼─→ Phase D (最终验证)
Phase C (TradeService)  ─┘

Phase B 内部: B1 → B2 → B3 → B4 → B5 (严格顺序)
Phase A 内部: A1 → A2 → A3 → A4 (严格顺序)
Phase C 内部: C1 → C2 (严格顺序)
```

Phase A/B/C 之间无依赖，可并行执行。

## 任务统计

| Phase | 任务数 | 总复杂度 |
|-------|--------|----------|
| Phase A: DTO 解耦 | 4 | 1×L + 2×S + 1×S |
| Phase B: steps 拆分 | 5 | 2×M + 2×S + 1×S |
| Phase C: DI 修复 | 2 | 2×S |
| Phase D: 验证 | 1 | 1×S |
| **合计** | **12** | **1×L + 2×M + 7×S** |
