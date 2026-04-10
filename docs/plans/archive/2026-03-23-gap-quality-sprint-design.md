# Gap 补齐 + 质量加固 Sprint 设计

**日期**: 2026-03-23
**状态**: Done (Wave 1 ✅, Wave 2 ✅, Wave 3 ✅, Wave 4 ✅)
**范围**: `packages/core/src/ditto_core/` + `packages/data/src/ditto_data/`
**前置文档**:
- `docs/plans/2026-03-21-strategy-engine-system-design-v3.md`（v3 系统设计）
- `docs/plans/2026-03-23-strategy-engine-v3-completion-analysis.md`（完成分析）

---

## 背景

Phase 0-5 全部完成（v3 引擎总完成度 ~97%），105 文件已暂存未提交。代码质量评级 A-，类型注解满分，主要问题集中在字符串字面量类型、中英文 docstring 混用、少量冗余代码。测试整体质量高，最大盲区在 `statistics.py`。

本 Sprint 目标：**质量先行，后补 Gap**——先清理现有代码建立规范，再在干净基础上补齐功能缺失。

---

## Sprint 结构

```
Wave 1: 代码审查与重构 (Part 01-03)
Wave 2: 测试加固 (Part 04-06)
Wave 3: Gap 补齐 (Part 07-09)
Wave 4: 文档同步 (Part 10-11)
```

---

## Wave 1: 代码审查与重构 ✅

基于代码审查报告的 11 项发现，分 3 Part 串行执行。**已完成** (2026-03-23)。

### Part 01: 类型安全加固 ✅

**优先级**: P0
**范围**: `execution/planner.py`, `backtest/risk/pre_trade.py`, `strategy/protocols.py`

| 改动 | 详情 |
|------|------|
| `OrderCheckResult.decision` → StrEnum | `"accept" \| "reject" \| "resize"` → `Decision` 枚举（`pre_trade.py:167`） |
| `BlockedOrder.severity` → StrEnum | `"block" \| "defer"` → `BlockSeverity` 枚举（`planner.py:72`） |
| 清理 `@runtime_checkable` | 移除 `DecisionStage` 上的 `@runtime_checkable`（`protocols.py:14`），与另外 9 个 Protocol 保持一致 |
| 统一 `slots=True` | `_DiffResult` 移除 `slots=True`（`planner.py:39`），与项目其他 frozen dataclass 保持一致 |

**验证**: 所有引用处更新为枚举比较，`pixi run -e dev check` 通过

### Part 02: 代码清理 ✅

**优先级**: P1
**范围**: `accounting/account.py`, `execution/trade_builder.py`, `execution/planner.py`, `execution/trade_builder.py`

| 改动 | 详情 |
|------|------|
| 删除 `_calc_nav()` 冗余 | `account.py:51` 定义但从未被调用，`get_view()` 已内联相同逻辑 |
| 删除 `FifoTradeBuilder.method` 未使用参数 | `trade_builder.py:121` 构造后未使用于逻辑分支 |
| 统一中英文 docstring | `_DiffResult`、`_OpenEntry`、`TradeMatchingMethod`、`TradeBuilder` Protocol → 中文 |

**验证**: `pixi run -e dev check` 通过，无 dead code

### Part 03: 文档完整性 ✅

**优先级**: P2
**范围**: 多文件

| 改动 | 详情 |
|------|------|
| 补齐 Attributes 列表 | `CostModelSpec`、`ScorerSpec`、`SelectorSpec`（specs.py）；`OrderEvent`、`OrderTicket`（order_book.py）；`ProcessInput`（brokerage.py）；`OrderCheckResult`（pre_trade.py） |
| 补齐私有方法 docstring | `_calc_exposure`、`_calc_pending_buy_value`（account.py）；`_calc_avg`（order_book.py） |
| 补齐 `EngineConfig.rebalance_freq` | engine.py Attributes 列表缺失该字段 |

**规则**: frozen dataclass 字段 > 2 个时，应提供 Attributes 列表；非平凡私有方法（逻辑 > 3 行）应添加 docstring

---

## Wave 2: 测试加固 ✅

基于测试审查报告，分 3 Part 执行。**已完成** (2026-03-23)。

### Part 04: statistics.py 加固 ✅

**优先级**: P1（最大测试盲区）
**范围**: `backtest/statistics.py` + `tests/unit/backtest/test_audit_collector_unit.py`

| 改动 | 详情 |
|------|------|
| 7 个数值辅助函数独立测试 | 新增 `test_statistics_helpers_unit.py`，62 个精确值验证测试 |
| NAV=0 边界 | `TestNavZeroBoundary` 4 个测试：全零 NAV、零→正、正→零、单快照 |
| benchmark 长度不匹配 | `TestBenchmarkLengthMismatch` 4 个测试：过长、过短、None、等长 |

**新增文件**: `tests/unit/backtest/test_statistics_helpers_unit.py`（62 tests）

### Part 05: 边界/异常路径 ✅

**优先级**: P2
**范围**: 全模块

| 改动 | 详情 |
|------|------|
| RiskLockFilter 边界 | 5 个测试：无锁定、部分锁定、全锁定、空 frame、frozen |
| FilteringStage 边界 | 5 个测试：空 frame、全过滤、矛盾条件、仅 null 排除、frozen |
| ScoringStage 边界 | 4 个测试：空 frame 参数化（RAW/RANK/ZSCORE）、单行 RAW/RANK/ZSCORE |
| ConstraintChecker 边界 | 8 个测试：空 frame、max_positions=0、max_weight=0、min_weight=1、单行、全零权重、负权重保留、组合约束 |
| EqualWeight 边界 | 4 个测试：cash_target=0/1/-0.1、100 instruments |
| ScoreWeight 边界 | 5 个测试：空 frame、同分、null+valid 混合、cash_target 削减、min_weight 超出 |

**覆盖率提升**: `filtering.py` 100%、`allocation.py` 100%、`constraints.py` 100%

### Part 06: 集成测试扩展 ✅

**优先级**: P2

**确认已覆盖**: `test_planner_unit.py` 现有 22 个测试已完整覆盖 T+1（3）、涨跌停（5）、停牌（3）、手数取整（5）、100+1 取整（5）、组合场景（3）。无需新增测试。

**验证结果**: 3763 tests passed, 0 errors, 0 warnings

---

## Wave 3: Gap 补齐 ✅

基于完成分析的 9 项 gap（排除 RiskSizer → Phase 8）。**已完成** (2026-03-23)。

### Part 07: `strategy/builtins/regime.py`

**优先级**: 中
**范围**: `strategy/builtins/regime.py`（新文件）

**设计要点**:
- 实现 `DecisionStage` Protocol
- 基于均线/波动率等指标判断市场状态（牛/熊/震荡）
- 输入: DecisionFrame 含价格列
- 输出: DecisionFrame 新增 `regime` 列（`"bull"` / `"bear"` / `"neutral"`）
- 参数: 均线周期、波动率阈值等，通过 `StrategySpec.params` 传入
- 作为可选 stage，不影响现有 Pipeline

**测试**: 单元测试（已知输入 → 预期 regime）+ snapshot 测试

### Part 08: DataHub 控制面

**优先级**: 中（v3 R10 唯一未完全落地项）
**范围**: `datahub/services/strategy/` + `datahub/stores/metadata/`

| 新文件 | 职责 |
|--------|------|
| `strategy_catalog_service.py` | 策略 spec CRUD + DRAFT/PUBLISHED 状态治理 |
| `strategy_artifact_service.py` | artifact 生命周期管理（创建/查询/归档） |

**设计要点**:
- PIT 版本化存储（复用 `_pit_base.py` 基类）
- Service 层 Protocol 定义在 core 包，实现在 datahub 包
- v3 spec 9.3 DataHub Greenfield 要求

**测试**: 单元测试 + 集成测试（CRUD 全流程）

### Part 09: 7 项低优先级 gap

**优先级**: 低
**范围**: 多文件

| Gap | 处理方式 |
|-----|---------|
| `strategy/validation.py` | StrategySpec 参数校验独立入口 |
| `models.py: RebalancePlan` | 调仓计划数据对象（含调仓日期、目标权重、执行状态） |
| `SignalSnapshot.valid_until` | 信号有效期字段 |
| `DecisionFrame` 类型别名 | `pl.DataFrame` 的语义化类型别名 |
| `execution/orders.py` | 从 accounting/order_book.py 迁移 Order 相关类型 |
| `Account._cash` 私有化 | `._cash` → property 访问，保护内部状态 |
| `order_book.py` 非dataclass注释 | 添加注释说明选择普通 class 的原因 |

---

## Wave 4: 文档同步 ✅

**已完成** (2026-03-23)。

### Part 10: CLAUDE.md + README

| 改动 | 文件 |
|------|------|
| 新增策略引擎模块说明 | `packages/core/CLAUDE.md` |
| 更新包 README | `packages/core/README.md`, `packages/data/README.md` |
| 更新 memory 索引 | `MEMORY.md`（新增本次 Sprint 记录） |

### Part 11: 模块 docstring

| 改动 | 范围 |
|------|------|
| `__init__.py` 导出列表与 `__all__` 一致 | `accounting/`, `strategy/`, `execution/`, `backtest/`, `portfolio/` |
| 包级 docstring 反映最终模块结构 | 各 `__init__.py` |

---

## 执行约束

1. **每个 Part 独立可验证**: 完成后运行 `pixi run -e dev check`
2. **TDD 模式**: Wave 1-2 重构类任务先补测试再改代码；Wave 3 严格 RED → GREEN → REFACTOR
3. **依赖关系**: Wave 1 → Wave 2（重构后测试更准确）；Wave 3 各 Part 之间无依赖可并行
4. **不引入新依赖**: 所有实现使用现有技术栈
5. **分支策略**: 在当前 `phase4/02-post-trade-risk` 分支继续，完成后统一提交
