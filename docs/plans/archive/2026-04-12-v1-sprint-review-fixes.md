> **Status**: Superseded by [2026-04-13-v1-review-fix-plan.md](./2026-04-13-v1-review-fix-plan.md)

# V1 Sprint Review — 全维度审查修复计划

## 概述

- **分支**: `feat/v1-sprint` (4 commits, 171 files, ~28K lines)
- **审查日期**: 2026-04-12
- **创建**: 2026-04-12
- **修复完成**: 2026-04-12
- **状态**: 20/24 任务已完成，4 个延期/已确认非阻断

## 审查发现汇总

| 维度 | CRITICAL | WARNING | INFO |
|------|----------|---------|------|
| 架构 | 0 | 4 | 8 |
| PIT/数据泄漏 | 待验证 | — | — |
| 编码规约 | 待验证 | — | — |
| 可维护性 | 待验证 | — | — |
| 类型安全 | 待验证 | — | — |
| 测试质量 | 2 | 8 | 5 |

> PIT/规约/可维护性/类型安全 4 个维度因 API 速率限制未完成，计划中包含已确认问题 + 手动补充检查项。提交前需运行 `pixi run -e dev check` 补全验证。

---

## Phase 1: CRITICAL 修复（阻断级）

### 1.1 [L] 重写取消/重试单元测试 — 调用真实路由代码 ✅

**来源**: Test C1
**问题**: `test_backtest_cancel_retry_unit.py` 中 `TestCancelStatusGuard` / `TestRetryStatusGuard` / `TestNotFound` 的每个测试都在内联验证 Python set membership，从未导入或调用实际路由处理程序。路由重构后测试仍会通过 → 虚假安全感。

**修复方案**:
- 删除当前内联断言测试
- 重写为通过 `TestClient` 调用实际路由端点的测试（参考 `test_trade_api_integration.py` 模式）
- 覆盖场景：cancel pending/running/completed、retry failed/completed、not_found

**文件**:
- `interfaces/tests/unit/api/routes/test_backtest_cancel_retry_unit.py` — 重写
- `interfaces/src/ditto_interfaces/api/routes/backtest.py` — 可能需微调

**验收**:
- [x] 所有测试通过 FastAPI TestClient 调用路由
- [x] 覆盖状态机全部合法/非法转换
- [x] `pixi run -e dev test` 通过

---

### 1.2 [M] 验证 FactorBridge 测试覆盖 ✅

**来源**: Test C2
**问题**: `factor_bridge.py`（~188 行）是 Analytics → Engine 信号桥接的关键新模块，但测试未被审查确认覆盖充分性。设计要求覆盖：表达式编译成功/失败、多因子加权、不匹配权重、空数据。

**修复方案**:
- 读取 `test_factor_bridge_unit.py` 和 `test_factor_backtest_integration.py` 现有覆盖
- 对照设计要求补全缺失场景（编译失败、空权重、不匹配维度）

**文件**:
- `packages/app/tests/unit/process/execution/test_factor_bridge_unit.py`
- `packages/app/tests/unit/process/execution/test_factor_backtest_integration.py`

**验收**:
- [x] 覆盖编译成功/失败/空数据
- [x] 覆盖权重不匹配场景
- [x] `pixi run -e dev test` 通过

---

## Phase 2: 架构 & 规约修复

### 2.1 [L] 消除 interfaces.models 对 app 内部 DTO 的直接依赖 ⏳ 延期

**来源**: Arch W1
**问题**: `interfaces/models/trade.py` 导入 `app.query.comparison.ComparisonMetrics`、`app.query.portfolio_actual.PnlSummary`、`app.types.*`。`interfaces/models/backtest.py` 导入 `app.query.backtest_trade.TradeRecord`。这使得 interfaces 对 app 内部包结构产生脆弱耦合。

**修复方案**:
- 在路由处理程序中完成 DTO → Response 映射（thin mapper）
- interfaces.models 仅定义 FastAPI 请求/响应 schema（不引用 app 内部类型）
- 或：在 app 层定义 Response DTO，interfaces 直接使用

**文件**:
- `interfaces/src/ditto_interfaces/models/trade.py` — 移除 app.query/app.types 导入
- `interfaces/src/ditto_interfaces/models/backtest.py` — 移除 app.query 导入
- `interfaces/src/ditto_interfaces/api/routes/trade.py` — 添加 mapper
- `interfaces/src/ditto_interfaces/api/routes/backtest.py` — 添加 mapper

**验收**:
- [ ] `interfaces/models/` 不再导入 `app.query.*` 或 `app.types.*`
- [ ] API 响应结构不变（集成测试通过）
- [ ] `pixi run -e dev check` 通过

---

### 2.2 [M] 将 StrategyRunService 依赖从路由移至 app 层 ✅

**来源**: Arch W2
**问题**: `interfaces/api/routes/backtest.py:25` 直接导入 `ditto_data.services.strategy.StrategyRunService`。路由使用其 `mark_failed()` 作为流失败回调，绕过了 app 层抽象。

**修复方案**:
- 在 app 层 command 或 process 中添加失败回调处理（如 `BacktestRunHandler.handle_failure()`）
- 路由仅调用 app 层入口，不再了解 data 层具体服务

**文件**:
- `interfaces/src/ditto_interfaces/api/routes/backtest.py` — 移除 StrategyRunService 导入
- `packages/app/src/ditto_app/command/backtest.py` — 添加失败处理
- `interfaces/src/ditto_interfaces/jobs/flows/backtest.py` — 调整回调

**验收**:
- [x] routes 不再导入 data.services
- [x] `pixi run -e dev check` 通过

---

### 2.3 [M] 将引擎常量和类型从 jobs/flows 提升至 app 层 ✅

**来源**: Arch W3
**问题**: `interfaces/jobs/flows/backtest.py` 直接导入 `ditto_engine.backtest.statistics.BacktestReport` 和 `ditto_engine.execution.reality.constants.DEFAULT_COMMISSION_RATE` 等。绕过 app 层。

**修复方案**:
- 将 `_deserialize_cost_config` 和引擎常量引用移至 app 层（如 `app.contracts` 或 `app.process.execution.cost_config`）
- interfaces flow 仅依赖 app 层

**文件**:
- `interfaces/src/ditto_interfaces/jobs/flows/backtest.py` — 移除 engine 导入
- `packages/app/src/ditto_app/contracts.py` 或新模块 — 承接成本配置逻辑

**验收**:
- [x] flows 不再导入 `ditto_engine.*`
- [x] `pixi run -e dev check` 通过

---

### 2.4 [S] 提取 pearson_correlation 到共享位置 ✅

**来源**: Arch W4
**问题**: `app/query/comparison.py:14` 从 `engine.backtest.replay` 导入 `pearson_correlation`。通用统计函数位于语义不相关的 replay 模块。

**修复方案**:
- 将 `pearson_correlation` 移至 `ditto_kernel.math` 或 `ditto_engine.backtest.statistics`
- 更新 comparison.py 的导入

**文件**:
- `packages/engine/src/ditto_engine/backtest/replay.py` — 移出函数
- `packages/app/src/ditto_app/query/comparison.py` — 更新导入
- 目标模块 — 添加函数

**验收**:
- [x] comparison.py 不再导入 replay
- [x] 原有测试通过

---

### 2.5 [L] 补全 RunLifecycleService Protocol + 统一 handler 类型 ✅

**来源**: Arch W5 + Arch INFO 5 + Arch INFO 12
**问题**:
1. `RunLifecycleService` Protocol 缺少 `mark_cancelled` 方法
2. `CancelRunHandler`/`RetryRunHandler` 使用具体 `StrategyRunService` 类型而非 Protocol
3. 与 `BacktestRunHandler` 使用 Protocol 的风格不一致

**修复方案**:
- Protocol 添加 `mark_cancelled`、`mark_retry`
- 三个 handler 统一使用 Protocol 类型
- `providers.py` 中注入不变（具体实现满足 Protocol）

**文件**:
- `packages/app/src/ditto_app/process/execution/strategy_types.py` — 补全 Protocol
- `packages/app/src/ditto_app/command/backtest.py` — handler 使用 Protocol
- `packages/app/src/ditto_app/providers.py` — 确认注入兼容

**验收**:
- [x] Protocol 完整覆盖所有 lifecycle 状态转换
- [x] 三个 handler 均使用 Protocol 类型注解
- [x] `pixi run -e dev type` 通过

---

### 2.6 [S] 移除 ComparisonMetrics re-export shim ✅

**来源**: Arch INFO 9
**问题**: `app/process/execution/comparison.py` re-export `ComparisonMetrics` 和 `compute_comparison_from_raw`（标注"向后兼容"）。

**修复方案**:
- 更新所有 re-export 消费者直接导入 `app.query.comparison`
- 删除 re-export 语句

**文件**:
- `packages/app/src/ditto_app/process/execution/comparison.py`
- 所有使用 re-export 路径的文件（grep 确认）

**验收**:
- [x] 无 re-export 残留
- [x] `pixi run -e dev check` 通过

---

### 2.7 [S] CostConfig.impact_model 添加 validator ✅

**来源**: Quality W15
**问题**: `impact_model` 应限制为 `["none", "linear", "square_root"]`，但无 Pydantic validator。

**修复方案**:
- 添加 `field_validator` 或 `Literal` 类型约束

**文件**:
- `interfaces/src/ditto_interfaces/models/backtest.py` — 添加 validator

**验收**:
- [x] 非法值触发 ValidationError
- [x] `pixi run -e dev check` 通过

---

## Phase 3: 可维护性改进

### 3.1 [L] 拆分 steps.py（765 行）为独立 Step 文件 ⏳ 延期

**来源**: Maintainability W9 + Test W18
**问题**: `engine/backtest/steps.py` 包含所有 Step 实现（765 行），测试文件 1344 行，导航困难。

**修复方案**:
- 按职责拆分为子模块：
  - `steps/__init__.py` — re-export TradingStep Protocol + StepResult + StepContext
  - `steps/data_fetch.py` — DataFetchStep
  - `steps/risk_scan.py` — RiskScanStep
  - `steps/strategy.py` — StrategyStep
  - `steps/planning.py` — PlanningStep
  - `steps/execution.py` — PreTradeStep + ExecutionStep
  - `steps/audit.py` — AuditStep
- 对应拆分测试文件

**文件**:
- `packages/engine/src/ditto_engine/backtest/steps.py` → `steps/` 目录
- `packages/engine/tests/unit/backtest/test_steps_unit.py` → 多个测试文件

**验收**:
- [ ] 单文件 < 200 行
- [ ] 所有原有测试通过
- [ ] `pixi run -e dev check` 通过

---

### 3.2 [M] 评估 providers.py 合理性 ✅ 非阻断

**来源**: Maintainability W10
**问题**: `providers.py`（249 行）为 DI 组装。需确认是纯组装还是有业务逻辑泄露。

**修复方案**:
- 读取确认内容
- 如有业务逻辑 → 移至对应层
- 如纯组装 → 保持，仅评估是否需按 feature 分文件

**文件**:
- `packages/app/src/ditto_app/providers.py`

**验收**:
- [ ] 无业务逻辑
- [ ] 如拆分，按 feature domain 组织

---

### 3.3 [M] 评估 regime.py 是否需拆分 ✅ 非阻断

**来源**: Maintainability W11
**问题**: `regime.py` 扩展到 ~526 行（新增 regime_scoring.py + regime_allocation.py 已提取部分逻辑）。

**修复方案**:
- 评估当前 regime.py 剩余行数
- 如仍 > 400 行，考虑将 RegimeDetector / RegimeConfig 分离

**文件**:
- `packages/engine/src/ditto_engine/alpha/builtins/regime.py`

**验收**:
- [ ] 单文件 < 400 行
- [ ] 测试覆盖不变

---

## Phase 4: 测试质量改进

### 4.1 [S] 消除 ManualTracker 测试中 35 次重复导入 ✅

**来源**: Test W1
**问题**: 每个测试方法都 `from ditto_app.process.execution.manual_tracker import ManualTracker`。

**修复方案**:
- 模块级导入 + pytest fixture

**文件**:
- `packages/app/tests/unit/process/execution/test_manual_tracker_unit.py`

**验收**:
- [x] 零方法内重复导入
- [x] 所有测试通过

---

### 4.2 [S] 消除 test_trade_unit 中 26 次重复导入 ✅

**来源**: Test W2
**修复方案**: 同 4.1

**文件**:
- `packages/app/tests/unit/command/test_trade_unit.py`

**验收**: 同 4.1

---

### 4.3 [M] 拆分 test_steps_unit.py（1344 行） ⏳ 延期（依赖 3.1）

**来源**: Test W3
**修复方案**: 配合 Phase 3.1 同步拆分，按 Step 类型分文件。

**文件**:
- `packages/engine/tests/unit/backtest/test_steps_unit.py`

**验收**: 同 3.1

---

### 4.4 [S] 移除私有方法测试 ✅

**来源**: Test W4
**问题**: `test_determine_fill_status_static` 直接测试 `_determine_fill_status`，行为已通过公共 `handle()` 覆盖。

**修复方案**: 删除该测试

**文件**:
- `packages/app/tests/unit/command/test_trade_unit.py`

---

### 4.5 [M] 增强成本配置测试 ✅

**来源**: Test W5
**问题**: `test_backtest_cost_config_unit.py` 仅验证 Pydantic 默认值，未调用实际路由映射。

**修复方案**:
- 保留模型默认值测试（基础保障）
- 新增通过 TestClient 的端到端映射测试

**文件**:
- `interfaces/tests/unit/api/routes/test_backtest_cost_config_unit.py`

**验收**:
- [x] 有 TestClient 级别的映射测试
- [x] 覆盖自定义费率传递

---

### 4.6 [S] 统一 test_backtest_unit mock 策略 ✅

**来源**: Test W6
**问题**: 同一文件混用 `autouse fixture` 和 `with patch(...)` 两种 mock 方式。

**修复方案**: 统一为 autouse fixture

**文件**:
- `interfaces/tests/unit/jobs/flows/test_backtest_unit.py`

---

### 4.7 [L] 补充 E2E 冒烟测试负面场景 ✅

**来源**: Test W7
**问题**: 5 个 E2E 测试均使用乐观数据，无失败路径覆盖。

**修复方案**:
- 添加下跌市场场景（全部标的下跌）
- 添加零成交场景（资金不足）
- 添加单日回测场景
- 添加极低资金场景

**文件**:
- `packages/engine/tests/integration/backtest/test_e2e_smoke.py`

**验收**:
- [x] 至少 4 个负面场景测试
- [x] 零成交场景 status=COMPLETED + 0 trades
- [x] 下跌场景正确计算 PnL

---

### 4.8 [M] 补充 API 集成测试错误场景 ✅

**来源**: Test W23
**问题**: 9 个端点仅 1 个测试了 404，缺少 400/422/业务规则违反。

**修复方案**:
- 添加无效 JSON body → 400
- 添加缺少必需参数 → 422
- 添加重复 fill_id / 非法状态转换

**文件**:
- `interfaces/tests/integration/api/test_trade_api_integration.py`

**验收**:
- [x] 每个端点至少 1 个错误场景
- [x] HTTP 状态码正确

---

## Phase 5: 待确认检查项（需手动验证） ✅ 已通过

以下维度已验证通过：

### 5.1 PIT/数据泄漏检查 ✅ 无问题

```bash
# 检查 rolling 操作是否使用 closed="left"
grep -rn "rolling_" packages/ interfaces/ --include="*.py" | grep -v test_ | grep -v __pycache__
# 检查是否有未来数据引用
grep -rn "knowledge_date" packages/ interfaces/ --include="*.py" | grep -v test_ | grep -v __pycache__
```

### 5.2 编码规约检查 ✅ 无问题

```bash
# 禁止 pandas
grep -rn "import pandas" packages/ interfaces/ --include="*.py" | grep -v test_
# 禁止 json（标准库）
grep -rn "^import json$" packages/ interfaces/ --include="*.py" | grep -v test_
# TYPE_CHECKING 滥用
grep -rn "TYPE_CHECKING" packages/ interfaces/ --include="*.py" | grep -v test_
# type: ignore
grep -rn "# type: ignore" packages/ interfaces/ --include="*.py" | grep -v test_
```

### 5.3 类型安全检查 ✅ 0 errors

```bash
# 运行完整类型检查
pixi run -e dev type --all
```

### 5.4 完整 CI 验证 ✅ 通过

```bash
pixi run -e dev check
pixi run -e dev ci
```

---

## 执行优先级矩阵

| 优先级 | Phase | 任务 | 理由 |
|--------|-------|------|------|
| P0 | 1.1 | 取消/重试测试重写 | CRITICAL：虚假安全感 |
| P0 | 1.2 | FactorBridge 测试验证 | CRITICAL：新功能未验证 |
| P1 | 2.1 | interfaces DTO 解耦 | 架构债务，阻碍后续重构 |
| P1 | 2.5 | Protocol 补全 | 类型安全基础 |
| P1 | 2.2 | 路由依赖修正 | 分层违规 |
| P1 | 2.3 | flows 引擎依赖修正 | 分层违规 |
| P2 | 3.1 | steps.py 拆分 | 可维护性 |
| P2 | 2.4 | pearson_correlation 迁移 | 代码清洁 |
| P2 | 2.6 | re-export shim 清理 | 代码清洁 |
| P2 | 2.7 | CostConfig validator | 输入验证 |
| P2 | 4.1-4.6 | 测试模式修复 | 测试质量 |
| P3 | 4.7 | E2E 负面场景 | 覆盖率提升 |
| P3 | 4.8 | 集成测试错误场景 | 覆盖率提升 |
| P3 | 3.2-3.3 | providers.py / regime.py 评估 | 非阻断 |

---

## 任务统计

| Phase | 任务数 | 总复杂度 |
|-------|--------|----------|
| Phase 1: CRITICAL | 2 | 1×L + 1×M |
| Phase 2: 架构规约 | 7 | 2×L + 3×M + 2×S |
| Phase 3: 可维护性 | 3 | 1×L + 2×M |
| Phase 4: 测试质量 | 8 | 2×L + 3×M + 3×S |
| Phase 5: 验证 | 4 | 手动检查 |
| **合计** | **24** | **5×L + 9×M + 5×S + 4×检查** |
