# Phase 1: Runtime Spine 实施计划

> Sprint: Phase 1 | 基线: `docs/plans/2026-05-10-phase1-runtime-spine-design.md`
> 创建: 2026-05-10

## 概述

建立回测/实盘切换的核心抽象层：Synchronizer + TimeContext + 事件增强。完成后 Paper Trading 可立即启动。

**设计确认**：
- EngineLoop 重构后**保留 DataFeed 引用**（仅用于 `get_history()` 历史查询）
- StepContext **保留 `slice_` 字段**（`benchmark_close` 等附加数据继续通过 Slice 获取）

## 代码假设验证摘要

| 假设 | 结果 |
|------|------|
| EngineLoop 持有 DataFeed + Clock | ✅ 确认 |
| 主循环 `for date in trading_days` | ✅ 确认 |
| StepContext 有 `date: str` | ✅ 确认 |
| Slice 有 `step_time`, `trade_date`, `bars` + `benchmark_close` | ✅ 确认 |
| Account.apply_fill() 不发布事件 | ✅ 确认 |
| kernel `__all__` = 30 | ⚠️ 实际 **26**（4 个余量） |
| ctx.date 迁移范围 | ⚠️ **21 处**（18 生产 + 3 测试），跨 10 文件 |
| Golden baseline 测试存在 | ✅ `backtest/tests/integration/test_golden_baseline.py`（inline-snapshot） |

## 执行 Waves

```
Wave 1: Kernel 抽象（无依赖）
  │
  ├── T1.1 TimeContext + T1.2 Synchronizer Protocol + T1.3 测试
  │
  ├──────────────────────────────────────────┐
  │                                          │
Wave 2: Backtest 实现                    Wave 4: 事件增强（并行）
  │                                          │
  ├── T2.1 BacktestSynchronizer             ├── T4.1 EventName + Account 事件
  │                                          │
Wave 3: EngineLoop 重构（最高风险）     Wave 5: Paper 骨架（并行）
  │                                          │
  ├── T3.1 Baseline 快照                   ├── T5.1 PaperSynchronizer 骨架
  ├── T3.2 核心重构 + 全量迁移
  ├── T3.3 DataFetchStep 简化
  └── T3.4 Baseline 等价验证
```

**并行策略**：Wave 1 完成后，Wave 2/4/5 可并行。Wave 3 依赖 Wave 2 且风险最高，放在最后。

---

## Wave 1: Kernel 抽象

### T1.1: TimeContext 值对象 `[S]`

**文件**: `packages/kernel/src/ditto_kernel/time_context.py`（新增）

**内容**: `TimeContext` frozen dataclass — `decision_time`, `knowledge_date`, `trade_date` + `pit_cutoff` property

**验收**:
- [x] `from ditto_kernel.time_context import TimeContext` 可用
- [x] frozen dataclass，零外部依赖
- [x] `pit_cutoff` 属性返回 `datetime.combine(knowledge_date, time.min)`
- [x] 不加入 `__init__.py` barrel（从叶模块导入）
- [x] kernel CLAUDE.md 模块结构更新

### T1.2: Synchronizer Protocol + TimeSlice `[S]`

**文件**: `packages/kernel/src/ditto_kernel/synchronizer.py`（新增）

**内容**: `TimeSlice` frozen dataclass（`time_context` + `bars`）+ `Synchronizer` Protocol（`stream()` + `clock()`）

**依赖**: T1.1（TimeContext）、kernel 内部类型（Clock, InstrumentId, MarketSnapshot）

**验收**:
- [x] `from ditto_kernel.synchronizer import Synchronizer, TimeSlice` 可用
- [x] `TimeSlice` frozen dataclass，`bars` 类型为 `dict[InstrumentId, MarketSnapshot]`
- [x] `Synchronizer` Protocol 有 `stream() -> Iterator[TimeSlice]` 和 `clock() -> Clock`
- [x] 不加入 `__init__.py` barrel
- [x] kernel CLAUDE.md 模块结构更新

### T1.3: Kernel 抽象单元测试 `[S]`

**文件**:
- `packages/kernel/tests/unit/test_time_context_unit.py`（新增）
- `packages/kernel/tests/unit/test_synchronizer_unit.py`（新增）

**覆盖**:
- `TimeContext`: 构造、frozen 语义、`pit_cutoff` 计算正确性
- `TimeSlice`: 构造、frozen 语义
- `Synchronizer`: Protocol 满足性验证（`BacktestSynchronizer` 实现后由 T2.1 覆盖）

**验收**:
- [x] 分支覆盖率 ≥ 90%（实际 100%）
- [x] `pixi run -e dev test --unit -p ditto-kernel` 通过
- [x] `pixi run -e dev type -p ditto-kernel` 通过

---

## Wave 2: Backtest 实现

### T2.1: BacktestSynchronizer 实现 + 测试 `[M]`

**文件**:
- `packages/backtest/src/ditto_backtest/synchronizer.py`（新增）
- `packages/backtest/tests/unit/test_backtest_synchronizer_unit.py`（新增）

**实现**:
- 封装 `DataFeed` + `SimulatedClock`，日历驱动迭代
- `stream()`: 遍历 `data_feed.trading_days()` → `get_slice()` → 转换为 `TimeSlice`
- `clock()`: 返回 `SimulatedClock` 实例
- `knowledge_lag_days` 参数（默认 1）

**关键注意**:
- `start_date` 过滤逻辑从 `EngineLoop.run()` 迁移过来
- `Slice` → `TimeSlice` 转换：`slice_.step_time` → `decision_time`，`slice_.step_time.date() - lag` → `knowledge_date`
- `Slice` 保留（`benchmark_close` 等附加数据由 StepContext.slice_ 承载）

**测试**:
- `stream()` 产出 `TimeSlice` 序列（数量、顺序、内容）
- `clock()` 返回 `SimulatedClock`
- `knowledge_date = decision_time.date() - knowledge_lag_days`
- `start_date` 过滤逻辑
- 空 trading_days 边界情况

**验收**:
- [x] `BacktestSynchronizer` 满足 `Synchronizer` Protocol（结构化子类型）
- [x] 分支覆盖率 ≥ 90%（实际 100%）
- [x] `pixi run -e dev test --unit -p ditto-backtest` 通过

---

## Wave 3: EngineLoop 重构（最高风险）

### T3.1: Golden baseline 快照捕获 `[S]`

**动作**: 重构前运行 golden baseline 测试，确认当前结果

```bash
pixi run -e dev test --integration -p ditto-backtest -k "golden"
```

**验收**:
- [x] 现有 golden baseline 测试全部通过
- [x] 记录当前快照值（inline-snapshot 已锁定）

### T3.2: EngineLoop + StepContext 核心重构 + ctx.date 全量迁移 `[L]`

> **风险**: 最高 — 21 处 ctx.date 引用跨 10 文件（含 application 层）
> **缓解**: Golden baseline 验证 + `rg "ctx\.date"` 全量搜索确认零遗漏

**修改文件**:

| 文件 | 变更 |
|------|------|
| [engine.py](packages/backtest/src/ditto_backtest/engine.py) | 接受 `Synchronizer` + 保留 `DataFeed`（history）；主循环改为 `for time_slice in sync.stream()`；`start_date` 过滤移除（已迁入 BacktestSynchronizer） |
| [steps/types.py](packages/backtest/src/ditto_backtest/steps/types.py) | `StepContext.date: str` → `StepContext.time_context: TimeContext`；新增 `bars` 字段 |
| [engine_steps.py](packages/backtest/src/ditto_backtest/engine_steps.py) | `ctx.date` → `ctx.time_context.trade_date`（1 处） |
| [steps/data_fetch.py](packages/backtest/src/ditto_backtest/steps/data_fetch.py) | 简化：bars 已由 Synchronizer 提供，改为从 `ctx.bars` 获取 |
| [steps/audit.py](packages/backtest/src/ditto_backtest/steps/audit.py) | `ctx.date` → `ctx.time_context.trade_date`（1 处） |
| [steps/planning.py](packages/backtest/src/ditto_backtest/steps/planning.py) | `ctx.date` → `ctx.time_context.trade_date`（3 处） |
| [steps/strategy.py](packages/backtest/src/ditto_backtest/steps/strategy.py) | `ctx.date` → `ctx.time_context.trade_date`（1 处） |
| [steps/risk_scan.py](packages/backtest/src/ditto_backtest/steps/risk_scan.py) | `ctx.date` → `ctx.time_context.trade_date`（2 处） |
| [steps/execution.py](packages/backtest/src/ditto_backtest/steps/execution.py) | `ctx.date` → `ctx.time_context.trade_date`（1 处） |
| [steps/pre_trade.py](packages/backtest/src/ditto_backtest/steps/pre_trade.py) | `ctx.date` → `ctx.time_context.trade_date`（1 处） |
| [backtest_process.py](packages/application/src/ditto_application/processes/execution/backtest_process.py) | `ctx.date` → `ctx.time_context.trade_date`（3 处） |

**EngineLoop.__init__ 签名变更**:
```python
# 变更后
def __init__(
    self,
    ...,
    synchronizer: Synchronizer,  # 新增：替代 DataFeed 的主数据流
    data_feed: DataFeed,         # 保留：仅用于 get_history()
    options: EngineOptions,
) -> None:
```

**EngineLoop.run() 变更**:
```python
# 变更后
def run(self) -> EngineResult:
    for time_slice in self._synchronizer.stream():
        self._synchronizer.clock().advance_to(
            time_slice.time_context.decision_time
        )
        self._step(time_slice)
```

**StepContext 变更**:
```python
# 变更后
@dataclass
class StepContext:
    time_context: TimeContext                           # 替代 date: str
    is_rebalance_day: bool
    bars: dict[InstrumentId, MarketSnapshot]            # 新增：来自 Synchronizer
    slice_: Slice | None = None                         # 保留：benchmark_close 等
    # ... 其余字段不变 ...
```

**迁移检查清单（21 处 ctx.date → ctx.time_context.trade_date）**:

backtest 层（15 处）:
- [x] engine.py:288 — StepContext 构造（flush 延迟信号）
- [x] engine.py:317 — StepContext 构造（单日步骤）
- [x] engine_steps.py:200 — bundle builder
- [x] steps/audit.py:46 — record_account_view
- [x] steps/planning.py:62 — rule_ref_collector.observe
- [x] steps/planning.py:68 — trade_date
- [x] steps/planning.py:90 — get_rules
- [x] steps/strategy.py:73 — trade_date
- [x] steps/data_fetch.py:51 — get_slice（**简化为从 ctx.bars 取**）
- [x] steps/data_fetch.py:62 — bar_fingerprints
- [x] steps/data_fetch.py:65 — clear_locks
- [x] steps/risk_scan.py:60 — record
- [x] steps/risk_scan.py:63 — trade_date
- [x] steps/execution.py:44 — trade_date
- [x] steps/pre_trade.py:91 — trade_date

application 层（3 处）:
- [x] backtest_process.py:440 — market_rows trade_date
- [x] backtest_process.py:445 — get_history as_of_date
- [x] backtest_process.py:466 — StrategyInputBundle trade_date

**最终验证**:
```bash
rg "ctx\.date" packages/ --type py
# 预期结果：零匹配（测试中的 ctx.date 引用也需更新）
```

**测试更新**:
- [x] `backtest/tests/unit/test_step_types_unit.py:47` — `ctx.date` 断言更新
- [x] `application/tests/unit/process/execution/test_factor_backtest_integration.py:55` — mock 更新

**验收**:
- [x] `EngineLoop.__init__` 同时接受 `Synchronizer` + `DataFeed`
- [x] 主循环为 `for time_slice in self._synchronizer.stream()`
- [x] 时钟推进为 `synchronizer.clock().advance_to()`
- [x] `ctx.date` 零残留（`rg "ctx\.date" packages/ --type py` = 空）
- [x] Golden baseline 测试结果不变（T3.4 验证）

### T3.3: DataFetchStep 简化 `[S]`

**文件**: [steps/data_fetch.py](packages/backtest/src/ditto_backtest/steps/data_fetch.py)

**变更**: bars 数据已由 Synchronizer 通过 `StepContext.bars` 提供，`DataFetchStep.execute()` 不再调用 `data_feed.get_slice()`。

**保留职责**:
- 获取账户快照（`account_view`）
- 清除冻结量（`clear_locks`）
- 记录 bar 指纹（从 `ctx.bars` 而非 `slice_.bars`）

**移除职责**:
- ~~调用 `data_feed.get_slice(ctx.date)`~~（已由 Synchronizer 完成）

**注意**: `StepContext.slice_` 仍需设置（用于 `benchmark_close`），但 Slice 内容需通过其他方式获取。考虑 BacktestSynchronizer 在 TimeSlice 之外保留原始 Slice 引用，或在 StepContext 中添加 `slice_: Slice | None` 由 EngineLoop 设置。

**验收**:
- [x] DataFetchStep 不再调用 `data_feed.get_slice()`
- [x] bars 数据从 `ctx.bars` 获取
- [x] `slice_.benchmark_close` 仍可访问

### T3.4: Golden baseline 等价验证 `[M]`

**动作**: 重构后运行完整回测测试套件，验证行为等价

```bash
# Golden baseline 回归
pixi run -e dev test --integration -p ditto-backtest -k "golden"

# 可复现性验证
pixi run -e dev test --integration -p ditto-backtest -k "reproducibility"

# 不变量保持
pixi run -e dev test --integration -p ditto-backtest -k "invariants"

# 架构契约
pixi run -e dev arch-check
```

**验收**:
- [x] Golden baseline inline-snapshot 无变化
- [x] 可复现性测试通过
- [x] 不变量测试通过
- [x] 36/36 arch contracts kept
- [x] `pixi run -e dev check` 全部通过

---

## Wave 4: 事件增强（可与 Wave 2-3 并行）

### T4.1: EventName 补全 + Account 事件发布 + 测试 `[M]`

**修改文件**:

| 文件 | 变更 |
|------|------|
| [kernel/events.py](packages/kernel/src/ditto_kernel/events.py) | `EventName` 新增 `ACCOUNT_UPDATED`、`STRATEGY_SIGNAL_GENERATED` |
| [portfolio/accounting/account.py](packages/portfolio/src/ditto_portfolio/accounting/account.py) | `__init__` 接受可选 `event_bus: EventBus`；`apply_fill()` 末尾发布 `PositionChanged` |

**新增测试**:
- `packages/portfolio/tests/unit/test_account_events_unit.py`（新增）

**实现细节**:
- `Account.__init__` 新增 `event_bus: EventBus | None = None`
- `apply_fill()` 末尾：`if self._event_bus is not None: self._event_bus.publish(PositionChanged(...))`
- 事件注入路径：回测通过 `EngineOptions.event_bus` → `BacktestBrokerage` → `Account`

**测试覆盖**:
- `apply_fill()` 在 `event_bus` 可用时发布 `PositionChanged`
- `apply_fill()` 在 `event_bus=None` 时不发布（向后兼容）
- 发布事件包含正确的 instrument_id、direction、quantity、price

**验收**:
- [x] `EventName` 新增 2 个常量
- [x] `Account.apply_fill()` 在有 event_bus 时发布 `PositionChanged`
- [x] 现有测试不受影响（`event_bus=None` 默认值）
- [x] 分支覆盖率 ≥ 90%（实际 100%）
- [x] `pixi run -e dev test --unit -p ditto-portfolio` 通过（398 passed）

---

## Wave 5: Paper 骨架（可与 Wave 2-4 并行）

### T5.1: PaperSynchronizer 骨架 + 测试 `[S]`

**文件**:
- `packages/application/src/ditto_application/runtime/__init__.py`（更新：移除占位符 docstring，添加模块导出）
- `packages/application/src/ditto_application/runtime/synchronizer.py`（新增）
- `packages/application/tests/unit/test_paper_synchronizer_unit.py`（新增）

**实现**:
- `PaperSynchronizer` 满足 `Synchronizer` Protocol
- `stream()` 方法 raise `NotImplementedError("Paper Trading implementation pending")`
- `clock()` 返回 `RealtimeClock()`

**验收**:
- [x] `from ditto_application.runtime.synchronizer import PaperSynchronizer` 可用
- [x] `PaperSynchronizer` 满足 `Synchronizer` Protocol
- [x] `clock()` 返回 `RealtimeClock` 实例
- [x] `pixi run -e dev check` 通过（6395 passed, 36/36 arch contracts）

---

## 最终验证（全部完成后）

```bash
pixi run -e dev check          # lint + fmt + type + test --fast
pixi run -e dev arch-check     # 36/36 arch contracts
```

**门禁清单**:
- [x] basedpyright 类型检查通过
- [x] ruff 检查通过
- [x] 全部测试通过（单元 + 集成）
- [x] 36/36 arch contracts kept
- [x] Golden baseline 无回归
- [x] `rg "ctx\.date" packages/ --type py` = 零匹配

## 风险与缓解

| 风险 | 严重度 | 缓解 |
|------|--------|------|
| T3.2 重构破坏回测结果 | 🔴 高 | T3.1 快照先行 + T3.4 等价验证 |
| T3.2 ctx.date 迁移遗漏 | 🟡 中 | `rg "ctx\.date"` 全量搜索 + CI 门禁 |
| T3.3 benchmark_close 丢失 | 🟡 中 | StepContext 保留 `slice_` 字段 |
| T4.1 事件发布影响性能 | 🟢 低 | event_bus=None 零开销 |
| kernel barrel 增长 | 🟢 低 | 当前 26/26 实际容量，新类型从叶模块导入 |

## 工作量估计

| Wave | 任务数 | 新增文件 | 修改文件 | 估计 |
|------|--------|---------|---------|------|
| Wave 1 | 3 | 4 | 0 | 0.5h |
| Wave 2 | 1 | 2 | 0 | 1h |
| Wave 3 | 4 | 0 | 11 | 3-4h |
| Wave 4 | 1 | 1 | 2 | 1-1.5h |
| Wave 5 | 1 | 2 | 1 | 0.5h |
| **合计** | **10** | **9** | **14** | **6-8h** |
