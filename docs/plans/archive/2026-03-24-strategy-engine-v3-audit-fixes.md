# 策略引擎 v3 审计修复计划

> **SUPERSEDED** — 本计划中的修复项（EngineLoop 接入 AuditCollector、死代码接入、BacktestReport 补齐等）已在治理收口计划 (`2026-03-24-strategy-engine-v3-governance-closeout-plan.md`) 的 Task 1-7 中全部完成。

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 修复 v3 设计审计发现的功能断裂（统计报告管道）和 11 项遗漏

**Architecture:** EngineLoop._step() 末尾接入 AuditCollector（record_fill + record_account_view + record_closed_trade via TradeBuilder），打通 EngineLoop → Collector → BacktestReport 完整管道。同步补齐死代码接入、缺失测试、质量加固项。

**Tech Stack:** Python 3.12+, polars, pytest, basedpyright, ruff

---

## 概述

- Sprint: Phase 4 收尾 | 范围: P0 + P1 + P2
- 创建: 2026-03-24
- 基于: v3 设计审计发现（engine → collector 管道断裂 + 11 项遗漏）

### 关键发现

1. **EngineLoop 不记录任何审计数据** — `record_fill()`、`record_account_view()`、`record_closed_trade()` 从未被调用，导致 `build_report()` 产出空壳 BacktestReport
2. **测试通过是假象** — `test_reproducibility.py` 使用 `_AuditedEngineLoop` 子类补偿，但该子类也不记录 fills/closed_trades，只记录 account_view
3. **`validate_spec_params` 是死代码** — 定义完整但运行时从未调用
4. **3 个 v3 §10.6 必要测试完全缺失**

### 剩余任务全景

| 优先级 | 任务 | 复杂度 | 依赖 |
|--------|------|--------|------|
| P0 | T-1: EngineLoop 接入 AuditCollector | M | 无 |
| P1 | T-2: validate_spec_params 接入运行时 | S | 无 |
| P1 | T-3: 缺失测试（exit_order_rules + rule_refs_preserved + suspended E2E） | S | T-1 |
| P2 | T-4: valid_until 信号过期检查 | S | 无 |
| P2 | T-5: ArtifactKind 枚举 | S | 无 |
| P2 | T-6: FillModel 参数化场景矩阵 | S | 无 |
| P2 | T-7: PortfolioStatistics 不变量测试 | S | 无 |

---

## 技术方案

### 1. EngineLoop 接入 AuditCollector（P0 核心修复）

**问题**：`engine.py:334-337` 在 `process_pending` 后直接结束，不记录任何审计数据。

**方案**：在 `EngineOptions` 新增 `trade_builder` 字段，`_step()` 末尾新增审计记录逻辑：

```python
# _step() 末尾（process_pending 之后）
step_fills = self._brokerage.process_pending(process_input)
self._fills.extend(step_fills)

# ── 审计记录（R3: 使用成交后快照） ──
if self._audit_collector is not None:
    account_view = self._brokerage.get_account()
    self._audit_collector.record_account_view(date, account_view)
    for fill in step_fills:
        self._audit_collector.record_fill(fill)
    if self._trade_builder is not None:
        for fill in step_fills:
            self._trade_builder.on_fill(fill, account_view)
        for trade in self._trade_builder.get_closed_trades():
            self._trade_collector.record_closed_trade(trade)
            self._trade_builder.clear_closed()
```

**TradeBuilder 生命周期**：
- EngineLoop 根据 `config.trade_matching` 创建对应 TradeBuilder 实例
- 存储在 `self._trade_builder` 中
- `run()` 结束时调用 `flush()` 记录未平仓交易

**关键设计决策**：
- TradeBuilder 由 EngineLoop 持有和驱动，不放在 EngineOptions 中（避免外部误配）
- `get_closed_trades()` 返回后立即清除，避免重复记录
- TradeBuilder 依赖 `AccountView`，在 `process_pending` 后刷新

### 2. validate_spec_params 接入

在 `StrategyRunService.run()` 调用 Pipeline 前校验 spec 参数，校验失败抛出 `ValueError`。

### 3. _AuditedEngineLoop 清理

修复 EngineLoop 后，`test_reproducibility.py` 中的 `_AuditedEngineLoop` 子类不再需要。清理为直接使用 base EngineLoop，并补充 fills/closed_trades 的验证断言。

---

## 任务清单

### Phase 1: P0 核心修复（阻塞所有下游功能）

- [x] **T-1: EngineLoop 接入 AuditCollector** `[M]` ✅
  - 验收: `_step()` 末尾调用 `record_fill` + `record_account_view`；`run()` 结束时调用 `trade_builder.flush()` + `record_closed_trade`；`build_report()` 产出非空 `nav_series` + `fill_log` + `trade_log`
  - 文件:
    - `packages/core/src/ditto_core/backtest/engine.py`（修改 _step + run + 新增 TradeBuilder 创建）
  - 测试:
    - `packages/core/tests/integration/backtest/test_reproducibility.py`（清理 _AuditedEngineLoop，改用 base EngineLoop + 验证 fill_log 非空）
  - 风险: 涉及引擎主循环（+1 级 Kill Switch）；需要同步更新所有依赖 EngineLoop 的测试 fixture

**T-1 详细步骤：**

**Step 1: 修改 EngineOptions 新增 trade_builder 依赖说明**

在 `engine.py` 的 `EngineOptions` 注释中说明 TradeBuilder 由 EngineLoop 内部管理，不需要外部传入。

**Step 2: EngineLoop.__init__ 创建 TradeBuilder**

在 `__init__` 中根据 `config.trade_matching` 创建对应的 TradeBuilder：

```python
from ditto_core.execution.trade_builder import (
    FifoTradeBuilder,
    FlatToFlatTradeBuilder,
    TradeMatchingMethod,
    TradeBuilder,
)

# 在 __init__ 中:
if config.trade_matching == TradeMatchingMethod.FLAT_TO_FLAT:
    self._trade_builder: TradeBuilder | None = FlatToFlatTradeBuilder()
else:
    self._trade_builder = FifoTradeBuilder()
```

**Step 3: 修改 _step() 末尾添加审计记录**

在 `process_pending` 之后、方法结束之前添加：

```python
# 处理成交
process_input = self._build_process_input(date, slice_)
step_fills = self._brokerage.process_pending(process_input)
self._fills.extend(step_fills)

# ── 审计记录（R3: 使用成交后快照） ──
if self._audit_collector is not None:
    account_view = self._brokerage.get_account()
    self._audit_collector.record_account_view(date, account_view)
    for fill in step_fills:
        self._audit_collector.record_fill(fill)
    if self._trade_builder is not None:
        for fill in step_fills:
            self._trade_builder.on_fill(fill, account_view)
        # 记录本轮新平仓交易并清除
        for trade in self._trade_builder.get_closed_trades():
            self._audit_collector.record_closed_trade(trade)
```

注意：`get_closed_trades()` 在 FifoTradeBuilder/FlatToFlatTradeBuilder 中返回已关闭交易后不会自动清除。需要确认 TradeBuilder 的 `get_closed_trades()` 语义——如果返回后不清除，需要跟踪已记录的 trade_id 避免重复。或者新增 `drain_closed_trades()` 方法。

**Step 4: 修改 run() 末尾 flush TradeBuilder**

在 `run()` 方法的 return 之前：

```python
# flush 未平仓交易
if self._trade_builder is not None and self._audit_collector is not None:
    for trade in self._trade_builder.flush():
        self._audit_collector.record_closed_trade(trade)
```

**Step 5: 更新 test_reproducibility.py — 清理 _AuditedEngineLoop**

删除 `_AuditedEngineLoop` 子类，所有测试直接使用 base `EngineLoop`。更新 `two_identical_engine_loops` fixture 和 `_build_audited_engine_loop` helper。

添加 fill_log 非空断言：

```python
assert len(report1.fill_log) > 0, "fill_log should not be empty"
```

**Step 6: 运行回归测试**

```bash
pixi run -e dev test --unit
pixi run -e dev test --integration
```

**Step 7: 提交**

```bash
git add packages/core/src/ditto_core/backtest/engine.py
git add packages/core/tests/integration/backtest/test_reproducibility.py
git commit -m "fix: EngineLoop 接入 AuditCollector — 打通统计报告管道 (R3)"
```

---

### Phase 2: P1 功能完善（无阻塞依赖，可并行）

- [x] **T-2: validate_spec_params 接入运行时** `[S]` ✅
  - 验收: `StrategyRunService.run()` 在调用 Pipeline 前校验参数；无效参数抛出 `ValueError` 并包含具体错误信息
  - 文件:
    - `apps/port/src/ditto_port/services/strategy/strategy_run_service.py`（添加校验调用）
    - `apps/port/tests/unit/services/strategy/test_strategy_run_service_unit.py`（新增校验失败测试）
  - 测试: 单元测试（无效类型、越界、非法枚举值 → ValueError）

**T-2 详细步骤：**

**Step 1: 写失败测试**

在 `test_strategy_run_service_unit.py` 新增：

```python
class TestParamValidation:
    def test_invalid_param_type_raises(self):
        """参数类型不匹配 → ValueError。"""
        spec = StrategySpec(
            strategy_id="test",
            name="Test",
            template="etf_rotation",
            param_constraints=(
                ParamConstraint(name="lookback", dtype="int", min_value=1),
            ),
            params={"lookback": "abc"},  # 错误类型
        )
        service = StrategyRunService(
            config=StrategyRunServiceConfig(strategy_id="test"),
            assembler=Mock(spec=StrategyInputAssembler),
            pipeline=Mock(spec=StrategyPipeline),
        )
        with pytest.raises(ValueError, match="类型错误"):
            service._validate_params(spec)

    def test_param_out_of_range_raises(self):
        """参数值越界 → ValueError。"""
        spec = StrategySpec(
            strategy_id="test",
            name="Test",
            template="etf_rotation",
            param_constraints=(
                ParamConstraint(name="lookback", dtype="int", min_value=1, max_value=100),
            ),
            params={"lookback": 200},
        )
        # ... 类似测试
```

**Step 2: 运行测试确认失败**

```bash
pixi run -e dev pytest apps/port/tests/unit/services/strategy/test_strategy_run_service_unit.py::TestParamValidation -v
```

**Step 3: 实现 _validate_params 方法**

在 `StrategyRunService` 中添加私有方法：

```python
from ditto_core.strategy.validation import validate_spec_params

def _validate_params(self, spec: StrategySpec) -> None:
    """校验策略参数约束。"""
    errors = validate_spec_params(spec)
    if errors:
        raise ValueError(f"策略参数校验失败: {'; '.join(errors)}")
```

在 `run()` 方法中调用：

```python
if self._spec is not None:
    self._validate_params(self._spec)
```

**Step 4: 运行测试确认通过**

```bash
pixi run -e dev pytest apps/port/tests/unit/services/strategy/test_strategy_run_service_unit.py -v
```

**Step 5: 提交**

```bash
git add apps/port/src/ditto_port/services/strategy/strategy_run_service.py
git add apps/port/tests/unit/services/strategy/test_strategy_run_service_unit.py
git commit -m "feat: validate_spec_params 接入 StrategyRunService 运行时校验"
```

---

- [x] **T-3: 补齐 3 个缺失测试** `[S]` ✅
  - 验收: `test_exit_order_has_rules`、`test_rule_refs_all_versions_preserved`、`test_no_fill_event_on_suspended` E2E 通过
  - 文件:
    - `packages/core/tests/integration/backtest/test_backtest_invariants.py`（新增 3 个测试）
  - 测试: 集成测试
  - 依赖: T-1（需要 EngineLoop 正确记录审计数据）

**T-3 详细步骤：**

**Step 1: 写 test_exit_order_has_rules**

在 `test_backtest_invariants.py` 中新增，验证退出标（当前持仓但不在 target 中的标的）的卖出订单正确加载三层规则。

**Step 2: 写 test_rule_refs_all_versions_preserved**

在 `test_reproducibility.py` 中新增，使用 `InMemoryRuleProvider` 提供跨日期变化的规则，验证 manifest 保留所有版本。

**Step 3: 写 test_no_fill_event_on_suspended E2E**

在 `test_backtest_invariants.py` 中新增，创建 `is_suspended=True` 的 MarketSnapshot，验证完整引擎管道产生 NoFill 且无 FillEvent。

**Step 4: 运行测试**

```bash
pixi run -e dev pytest packages/core/tests/integration/backtest/ -v -k "exit_order or rule_refs_preserved or suspended"
```

**Step 5: 提交**

```bash
git add packages/core/tests/integration/backtest/test_backtest_invariants.py
git add packages/core/tests/integration/backtest/test_reproducibility.py
git commit -m "test: 补齐 exit_order_rules + rule_refs_preserved + suspended E2E 测试"
```

---

### Phase 3: P2 质量加固（独立，可并行）

- [x] **T-4: valid_until 信号过期检查** `[S]` ✅
  - 验收: `StrategyInputAssembler` 在组装 bundle 时过滤 `valid_until < trade_date` 的信号
  - 文件:
    - `apps/port/src/ditto_port/services/strategy/input_assembler.py`（添加过滤逻辑）
    - `apps/port/tests/unit/services/strategy/test_input_assembler_unit.py`（新增过期信号测试）
  - 测试: 单元测试

**T-4 详细步骤：**

**Step 1: 写失败测试**

```python
def test_expired_signals_filtered(self):
    """valid_until < trade_date 的信号应被过滤。"""
    signals = {"ETF-001": 0.05, "ETF-002": -0.03}
    assembler = StrategyInputAssembler(...)
    # valid_until 设为昨天
    bundle = assembler.assemble(
        date="2026-01-06",
        bars={"ETF-001": ..., "ETF-002": ...},
        signals=signals,
        valid_until="2026-01-05",  # 已过期
    )
    # 验证 signal_values 为空或信号被过滤
```

**Step 2: 实现过滤逻辑**

在 `assemble()` 方法中添加 `valid_until` 检查。

**Step 3: 运行测试 + 提交**

---

- [x] **T-5: ArtifactKind 枚举** `[S]` ✅
  - 验收: `ArtifactKind` StrEnum 定义在 `packages/data/src/ditto_data/models/strategy.py`；`StrategyArtifactRecord.artifact_type` 类型从 `str` 改为 `ArtifactKind`
  - 文件:
    - `packages/data/src/ditto_data/models/strategy.py`（新增枚举，更新字段类型）
    - `packages/data/tests/unit/services/test_strategy_artifact_service_unit.py`（更新测试）
  - 测试: 单元测试

**T-5 详细步骤：**

**Step 1: 定义 ArtifactKind 枚举**

```python
class ArtifactKind(StrEnum):
    # Pipeline 输出
    DECISION_FRAME = "decision_frame"
    SIGNAL_SNAPSHOT = "signal_snapshot"
    TARGET_PORTFOLIO = "target_portfolio"
    REBALANCE_PLAN = "rebalance_plan"
    # 执行层输出
    ORDER_LOG = "order_log"
    FILL_LOG = "fill_log"
    # 统计层输出
    NAV = "nav"
    TRADE_LOG = "trade_log"
    BACKTEST_REPORT = "backtest_report"
    # 审计日志
    RISK_LOG = "risk_log"
    PRE_TRADE_LOG = "pre_trade_log"
    # 诊断
    DIAGNOSTICS = "diagnostics"
```

**Step 2: 更新 StrategyArtifactRecord.artifact_type 类型**

从 `str` 改为 `ArtifactKind`，保持向后兼容（StrEnum 是 str 子类）。

**Step 3: 更新引用处 + 测试 + 提交**

---

- [x] **T-6: FillModel 参数化场景矩阵** `[S]` ✅
  - 验收: `A_SHARE_FILL_SCENARIOS` 数据结构定义；现有独立测试方法保留但新增参数化矩阵测试
  - 文件:
    - `packages/core/tests/unit/execution/test_fill_model_unit.py`（新增参数化测试）
  - 测试: 单元测试

**T-6 详细步骤：**

**Step 1: 定义场景数据结构**

```python
@dataclass(frozen=True)
class FillScenario:
    name: str
    order_type: OrderType
    direction: OrderDirection
    is_suspended: bool
    limit_up: float | None
    limit_down: float | None
    order_price: float | None
    should_fill: bool
    expected_reason: str | None = None
    expected_can_retry: bool = True
```

**Step 2: 创建场景矩阵覆盖所有组合**

覆盖 v3 §5.3 表格中的 6 个核心场景 + 边界场景（suspended+SELL, LIMIT at boundaries）。

**Step 3: 写参数化测试**

```python
@pytest.mark.parametrize("scenario", A_SHARE_FILL_SCENARIOS)
def test_fill_scenario(scenario: FillScenario):
    outcome = fill_model.try_fill(...)
    if scenario.should_fill:
        assert isinstance(outcome, Filled)
    else:
        assert isinstance(outcome, NoFill)
        assert outcome.reason == scenario.expected_reason
```

**Step 4: 运行测试 + 提交**

---

- [x] **T-7: PortfolioStatistics 不变量测试** `[S]` ✅
  - 验收: NAV > 0、max_drawdown <= 0、annualized_return 与 total_return 一致性、turnover >= 0 等不变量测试
  - 文件:
    - `packages/core/tests/unit/backtest/test_statistics_helpers_unit.py`（新增不变量测试）
  - 测试: 单元测试（手写边界值 + 不变量断言，不引入 hypothesis）

**T-7 详细步骤：**

**Step 1: 写不变量测试**

```python
class TestPortfolioStatisticsInvariants:
    def test_max_drawdown_non_positive(self):
        """任何场景下 max_drawdown <= 0。"""
        stats = compute_portfolio_statistics(...)  # 使用构造的 snapshot 数据
        for s in stats:
            assert s.max_drawdown <= 0.0

    def test_nav_positive(self):
        """NAV 不为负。"""
        stats = compute_portfolio_statistics(...)
        for s in stats:
            assert s.nav >= 0.0

    def test_total_return_consistency(self):
        """total_return 与 initial/final NAV 一致。"""
        # 手工计算 vs compute_portfolio_statistics 结果一致

    def test_turnover_non_negative(self):
        """换手率不为负。"""
```

**Step 2: 运行测试 + 提交**

---

## 执行顺序 & 依赖图

```
Phase 1 (P0 核心修复)
─────────────────────
T-1 EngineLoop 接入 AuditCollector

Phase 2 (P1 功能完善)        Phase 3 (P2 质量加固)
─────────────────────        ──────────────────────
T-2 validate_spec_params       T-4 valid_until 过期检查
T-3 缺失测试 (依赖 T-1)       T-5 ArtifactKind 枚举
                               T-6 FillModel 场景矩阵
                               T-7 PortfolioStatistics 不变量
```

### 关键路径

```
T-1 → T-3（最长链，但 T-2/T-4/T-5/T-6/T-7 可完全并行）
```

### 并行机会

- T-2, T-4, T-5, T-6, T-7 与 T-1 完全可并行
- T-3 依赖 T-1 完成

---

## 验收门禁

每个 Phase 完成后运行：

```bash
pixi run -e dev check          # lint + fmt + type + test --fast
pixi run -e dev arch-check     # 分层边界检查
```

### 最终验收标准

- [x] basedpyright 类型检查 0 errors
- [x] ruff 检查 All checks passed
- [x] 全量测试通过（3959 passed）
- [x] 分支覆盖率 ≥ 80%（core unit 84.43%）
- [x] `build_report()` 产出非空 `nav_series` + `fill_log` + `trade_log`
- [x] `validate_spec_params` 在运行时被调用
- [x] 3 个缺失测试通过
