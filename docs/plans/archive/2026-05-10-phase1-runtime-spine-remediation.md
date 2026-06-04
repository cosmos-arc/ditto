# Phase 1 Runtime Spine 收尾修复

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 修复审计发现的 3 处不足，使 Runtime Spine 实现与计划完全对齐。

**Architecture:** 统一时钟路径到 Synchronizer（消除 EngineOptions.clock），澄清 start_date 双重过滤的职责分工，更新计划文档。

**Tech Stack:** Python 3.12+ / basedpyright / ruff / pytest

---

## 概述

> Sprint: Phase 1 收尾 | 基线: `docs/plans/2026-05-10-phase1-runtime-spine-plan.md`
> 创建: 2026-05-10

### 问题清单

| # | 问题 | 评级 | 修复策略 |
|---|------|------|---------|
| 1 | 双时钟路径：`options.clock` + `synchronizer.clock()` 并存 | 偏偷工减料 | 移除 `EngineOptions.clock`，统一到 Synchronizer |
| 3 | start_date 双重过滤：BacktestSynchronizer + EngineLoop 各自过滤 | 文档缺失 | 添加注释澄清各过滤器的职责分工 |
| 5 | 计划文档 checkbox 未更新：Wave 3 实际已完成但标记为 `[ ]` | 文档疏漏 | 更新 Wave 3 + 最终验证 checkbox |

---

## Task R1: 移除 EngineOptions.clock — 统一时钟到 Synchronizer `[M]`

### 问题

`EngineLoop` 同时持有两条时钟路径：
1. `self._clock = options.clock` → Steps 通过 `StepDeps.clock` 消费
2. `self._synchronizer.clock()` → `run()` 中 `advance_to()` 推进

如果 `options.clock` 和 `synchronizer.clock()` 不是同一实例，Steps 读到的时间戳会是未推进的旧值。
当前 runtime builder 传入同一对象所以不会触发，但架构语义不清。

### 修复策略

- 从 `EngineOptions` 移除 `clock: Clock` 字段
- 从 `EngineLoop` 移除 `self._clock = options.clock`
- `EngineLoop._build_steps()` 改为 `clock=self._synchronizer.clock()`
- Steps 接口不变（仍通过 `StepDeps.clock` 获取时钟，只是来源变了）
- 所有测试中 `EngineOptions(clock=clock, ...)` 移除 `clock=` 参数

### 文件影响

**生产代码（4 文件）**:

| 文件 | 变更 |
|------|------|
| `packages/backtest/src/ditto_backtest/engine_steps.py` | `EngineOptions`: 移除 `clock: Clock` 字段 + docstring 更新 |
| `packages/backtest/src/ditto_backtest/engine.py` | 移除 `self._clock`；`_build_steps()` 中 `StepDeps(clock=...)` 改为 `self._synchronizer.clock()` |
| `packages/application/src/ditto_application/processes/execution/backtest_process.py` | `_build_engine_options()`: 移除 `clock=clock`；`_execute_backtest()`: 移除从 options 取 clock 的逻辑 |

**测试代码（~15 文件，~37 处 EngineOptions 构造）**:

| 文件 | 构造数 | 说明 |
|------|--------|------|
| `packages/backtest/tests/unit/test_engine_loop_unit.py` | ~15 | 含 `_make_engine_loop` helper + 直接构造 |
| `packages/backtest/tests/integration/conftest.py` | 5 | 集成测试 fixture |
| `packages/backtest/tests/unit/test_engine_events_unit.py` | 2 | |
| `packages/backtest/tests/unit/test_backtest_contracts_unit.py` | 1 | |
| `packages/backtest/tests/unit/test_post_trade_unit.py` | 1 | |
| `packages/backtest/tests/integration/test_risk_integration.py` | 1 | |
| `packages/backtest/tests/integration/test_backtest_e2e_smoke.py` | 1 | |
| `packages/backtest/tests/integration/test_golden_baseline.py` | 1 | |
| `packages/backtest/tests/integration/test_reproducibility.py` | 2 | |
| `packages/backtest/tests/integration/test_backtest_invariants.py` | 3 | |
| `packages/strategy/tests/integration/alpha/conftest.py` | 1 | |
| `packages/strategy/tests/integration/alpha/test_stock_sector_rotation_snapshot.py` | 1 | |
| `packages/application/tests/integration/test_backtest_service_integration.py` | 3 | |

> **注意**: 测试文件中保留 clock 变量创建（synchronizer mock 需要），仅从 EngineOptions 构造中移除。

### Step 1: 修改 EngineOptions — 移除 clock 字段

**文件**: `packages/backtest/src/ditto_backtest/engine_steps.py`

```python
# BEFORE (line 55-84):
@dataclass(frozen=True)
class EngineOptions:
    """..."""
    clock: Clock              # ← 删除此行
    fee_model: FeeModel | None = None
    ...

# AFTER:
@dataclass(frozen=True)
class EngineOptions:
    """
    引擎可选组件 — 将可选依赖打包以减少构造参数数量。

    时钟由 Synchronizer 提供（options 不再持有 clock）。

    Attributes:
        fee_model: 手续费模型 (用于 PreTrade 估算, None = 不使用独立费率)
        ...
    """
    fee_model: FeeModel | None = None
    ...
```

同时移除 `from ditto_kernel.clock import Clock` 导入（如果 `StepDeps` 和 `build_steps` 仍需，则保留）。

> `StepDeps.clock` 字段保留（Step 构建仍需时钟，来源从 `options.clock` 改为 `synchronizer.clock()`）。

### Step 2: 修改 EngineLoop — 统一时钟来源

**文件**: `packages/backtest/src/ditto_backtest/engine.py`

```python
# BEFORE (line 120-122):
        self._data_feed = data_feed
        self._synchronizer = synchronizer
        self._clock = options.clock          # ← 删除此行

# AFTER:
        self._data_feed = data_feed
        self._synchronizer = synchronizer
```

```python
# BEFORE (_build_steps, line 156-180):
    def _build_steps(self) -> tuple[TradingStep, ...]:
        return build_steps(
            StepDeps(
                ...
                clock=self._clock,            # ← 改为 self._synchronizer.clock()
                ...
            ),
        )

# AFTER:
    def _build_steps(self) -> tuple[TradingStep, ...]:
        return build_steps(
            StepDeps(
                ...
                clock=self._synchronizer.clock(),
                ...
            ),
        )
```

### Step 3: 修改 backtest_process — 移除 options.clock

**文件**: `packages/application/src/ditto_application/processes/execution/backtest_process.py`

```python
# BEFORE (_execute_backtest, line 243-252):
        # 构造 Synchronizer + EngineLoop
        clock = options.clock
        if not isinstance(clock, SimulatedClock):
            msg = "Backtest requires SimulatedClock"
            raise AppProcessError(msg)
        synchronizer = BacktestSynchronizer(
            data_feed=self._data_feed,
            clock=clock,
            start_date=self._config.start_date,
        )

# AFTER:
        # 构造 Synchronizer（clock 在 _build_engine_options 中创建）
        clock = self._build_clock()
        synchronizer = BacktestSynchronizer(
            data_feed=self._data_feed,
            clock=clock,
            start_date=self._config.start_date,
        )
```

```python
# BEFORE (_build_engine_options, line 337-347):
        return EngineOptions(
            clock=clock,
            event_bus=SimpleEventBus(),
            ...
        )

# AFTER:
        return EngineOptions(
            event_bus=SimpleEventBus(),
            ...
        )
```

需要将 clock 创建提取为独立方法（或内联在 `_execute_backtest` 中）：

```python
    def _build_clock(self) -> SimulatedClock:
        """构造回测模拟时钟。"""
        _start = date.fromisoformat(self._config.start_date)
        return SimulatedClock(
            initial=datetime(_start.year, _start.month, _start.day, tzinfo=UTC),
        )
```

### Step 4: 更新所有测试 — 移除 EngineOptions(clock=...)

**机械操作**：所有 `EngineOptions(clock=clock, ...)` 和 `EngineOptions(clock=..., ...)` 构造中移除 `clock=` 参数。

**典型变更**:

```python
# BEFORE:
options=EngineOptions(clock=clock, fee_model=fee_model)

# AFTER:
options=EngineOptions(fee_model=fee_model)
```

```python
# BEFORE (只有 clock 的):
options=EngineOptions(clock=clock)

# AFTER:
options=EngineOptions()
```

**涉及文件列表**（37 处构造）:
- `packages/backtest/tests/unit/test_engine_loop_unit.py` (~15 处)
- `packages/backtest/tests/integration/conftest.py` (5 处)
- `packages/backtest/tests/unit/test_engine_events_unit.py` (2 处)
- `packages/backtest/tests/unit/test_backtest_contracts_unit.py` (1 处)
- `packages/backtest/tests/unit/test_post_trade_unit.py` (1 处)
- `packages/backtest/tests/integration/test_risk_integration.py` (1 处)
- `packages/backtest/tests/integration/test_backtest_e2e_smoke.py` (1 处)
- `packages/backtest/tests/integration/test_golden_baseline.py` (1 处)
- `packages/backtest/tests/integration/test_reproducibility.py` (2 处)
- `packages/backtest/tests/integration/test_backtest_invariants.py` (3 处)
- `packages/strategy/tests/integration/alpha/conftest.py` (1 处)
- `packages/strategy/tests/integration/alpha/test_stock_sector_rotation_snapshot.py` (1 处)
- `packages/application/tests/integration/test_backtest_service_integration.py` (3 处)

> **注意**: clock 变量本身保留（synchronizer mock 仍需要），只从 EngineOptions 构造中移除。

### Step 5: 运行验证

```bash
# 类型检查
pixi run -e dev type packages/backtest/src packages/application/src

# 单元测试
pixi run -e dev pytest packages/backtest/tests/unit -q

# 集成测试（含 golden baseline）
pixi run -e dev pytest packages/backtest/tests/integration -q
pixi run -e dev pytest packages/strategy/tests/integration/alpha -q
pixi run -e dev pytest packages/application/tests/integration -q

# 架构检查
pixi run -e dev arch-check
```

**验收标准**:
- [ ] `rg "clock" packages/backtest/src/ditto_backtest/engine_steps.py` — EngineOptions 无 clock 字段
- [ ] `rg "self\._clock" packages/backtest/src/ditto_backtest/engine.py` — 零匹配
- [ ] `rg "options\.clock" packages/ --type py` — 零匹配
- [ ] Golden baseline 3 passed
- [ ] 36/36 arch contracts kept

### Step 6: 提交

```bash
git add -A
git commit -m "refactor(backtest): unify clock to Synchronizer — remove EngineOptions.clock"
```

---

## Task R2: start_date 双重过滤 — 文档澄清 `[S]`

### 问题

`BacktestSynchronizer.stream()` 和 `EngineLoop.run()` 都按 `start_date` 过滤交易日。
这不是冗余——两个过滤器服务于不同目的：

1. **BacktestSynchronizer**: 控制迭代范围（Synchronizer 抽象边界 — 决定产出哪些 TimeSlice）
2. **EngineLoop**: 构建 `trading_days` 索引用于 `is_rebalance_day()` 计算（业务逻辑 — 第一个交易日 idx=0 触发调仓）

### 修复策略

添加注释澄清职责分工。不做代码变更。

### Step 1: 注释 BacktestSynchronizer 过滤

**文件**: `packages/backtest/src/ditto_backtest/synchronizer.py:42-44`

```python
    def stream(self) -> Iterator[TimeSlice]:
        for date_str in self._feed.trading_days():
            # Synchronizer 过滤: 控制迭代范围（决定产出哪些 TimeSlice）
            # EngineLoop 也按 start_date 过滤 trading_days（用于 is_rebalance_day 索引）
            if date_str < self._start_date:
                continue
```

### Step 2: 注释 EngineLoop 过滤

**文件**: `packages/backtest/src/ditto_backtest/engine.py:193-196`

```python
        # 构建 trading_days 索引 — 用于 is_rebalance_day() 计算
        # 注: BacktestSynchronizer 也按 start_date 过滤（控制迭代范围），
        # 此处的过滤是为 is_rebalance_day 提供正确的日期索引（首个交易日 idx=0 触发调仓）
        days = self._data_feed.trading_days()
        trading_days = [d for d in days if d >= self._config.start_date]
```

### Step 3: 提交

```bash
git add -A
git commit -m "docs(backtest): clarify dual start_date filter responsibilities"
```

---

## Task R3: 更新计划文档 checkbox `[S]`

### Step 1: 更新 Wave 3 checkbox

**文件**: `docs/plans/2026-05-10-phase1-runtime-spine-plan.md`

将 Wave 3 (T3.1-T3.4) 和最终验证 checklist 中所有 `[ ]` 改为 `[x]`。

Wave 3 迁移检查清单（15 处 backtest 层 + 3 处 application 层）全部标记为 `[x]`。

### Step 2: 更新最终验证 checklist

```markdown
**门禁清单**:
- [x] basedpyright 类型检查通过
- [x] ruff 检查通过
- [x] 全部测试通过（单元 + 集成）
- [x] 36/36 arch contracts kept
- [x] Golden baseline 无回归
- [x] `rg "ctx\.date" packages/ --type py` = 零匹配
```

### Step 3: 提交

```bash
git add docs/plans/2026-05-10-phase1-runtime-spine-plan.md
git commit -m "docs: update Phase 1 Runtime Spine plan checkboxes — Wave 3 complete"
```

---

## 最终验证（全部完成后）

```bash
# 完整检查
pixi run -e dev check          # lint + fmt + type + test --fast
pixi run -e dev arch-check     # 36/36 arch contracts

# Golden baseline 回归
pixi run -e dev pytest packages/backtest/tests/integration -k "golden" -q

# 确认零残留
rg "options\.clock" packages/ --type py    # 零匹配
rg "self\._clock" packages/backtest/src/ --type py  # 零匹配
rg "ctx\.date[^_]" packages/ --type py     # 零匹配（Wave 3 遗留确认）
```

**门禁清单**:
- [ ] `pixi run -e dev check` 全部通过
- [ ] 36/36 arch contracts kept
- [ ] Golden baseline 无回归
- [ ] `options.clock` 零残留
- [ ] `self._clock` 零残留（engine.py）

## 风险与缓解

| 风险 | 严重度 | 缓解 |
|------|--------|------|
| 移除 clock 后测试 mock 不兼容 | 🟡 中 | unit test helper 已创建 synchronizer mock with clock，无需额外改动 |
| backtest_process 时钟提取影响集成测试 | 🟡 中 | 集成测试验证 golden baseline 等价 |
| ~37 处测试 EngineOptions 漏改 | 🟢 低 | `pixi run -e dev type` 会立即捕获遗漏 |

## 工作量估计

| Task | 复杂度 | 生产文件 | 测试文件 | 估计 |
|------|--------|---------|---------|------|
| R1: 统一时钟 | M | 3 修改 | ~15 修改 | 1-1.5h |
| R2: 文档澄清 | S | 2 修改 | 0 | 10min |
| R3: checkbox 更新 | S | 1 修改 | 0 | 5min |
| **合计** | — | **6 修改** | **~15 修改** | **1.5-2h** |
