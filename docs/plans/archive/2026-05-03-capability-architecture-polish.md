# Capability Architecture Polish Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 补齐能力包架构重构审计中发现的 5 个待完善项，使所有评审维度达到 100 分。

**Architecture:** 纯文档和测试归类修复，不涉及生产代码变更。6 个空壳 `__init__.py` 补齐占位 docstring；1 个重复测试类从 strategy 删除（backtest 已有更完整的覆盖）；1 个 CLAUDE.md 格式对齐。

**Tech Stack:** Python 3.13, ruff, basedpyright, pytest, import-linter。

---

## Execution Rules

1. 每个 task 单独提交，提交前运行 task 内指定验证命令。
2. 不修改生产代码，只修改文档、占位 `__init__.py` 和测试文件。
3. 每个 task 改动范围 ≤ 5 文件。

## Global Verification Commands

```bash
pixi run -e dev lint
pixi run -e dev type
pixi run -e dev test --fast
pixi run -e dev arch-check
pixi run -e dev check
```

---

### Task 1: Unify Empty Shell `__init__.py` Docstrings `[S]`

**Files:**
- Modify: `packages/strategy/src/ditto_strategy/audit/__init__.py`
- Modify: `packages/execution/src/ditto_execution/broker/gateways/__init__.py`
- Modify: `packages/analysis/src/ditto_analysis/reports/__init__.py`
- Modify: `packages/analysis/src/ditto_analysis/diagnostics/__init__.py`
- Modify: `packages/analysis/src/ditto_analysis/experiments/__init__.py`
- Modify: `packages/analysis/src/ditto_analysis/screeners/__init__.py`

**Context:** 这 6 个 `__init__.py` 文件为空（0 字节），而另外 7 个占位目录的 `__init__.py` 已有描述性 docstring。需统一格式。

**参考模板**（以 `packages/portfolio/src/ditto_portfolio/holdings/__init__.py` 为标准）：

```python
"""
Holdings — 持仓快照与追踪。

管理当前持仓状态、目标持仓 vs 实际持仓对比、
持仓历史快照等。与 accounting/position 不同，
holdings 侧重于持仓的快照式查询和跨周期追踪。

此模块为占位符，定义了未来能力扩展的目标结构。
当前不应删除 — 由能力包架构计划保留。
"""
```

**Step 1: Write placeholder docstrings**

每个文件写入与领域匹配的描述性 docstring：

`packages/strategy/src/ditto_strategy/audit/__init__.py`:
```python
"""
Audit — 策略审计追踪。

记录策略运行过程中的关键决策、信号变化和执行偏差。
支持策略回溯审计和合规检查，确保策略行为可追溯。

此模块为占位符，定义了未来能力扩展的目标结构。
当前不应删除 — 由能力包架构计划保留。
"""
```

`packages/execution/src/ditto_execution/broker/gateways/__init__.py`:
```python
"""
Gateways — 券商网关实现。

提供与具体券商（如 QMT、XTP）的适配器实现。
每个网关实现 BrokerGateway Protocol，
由 apps 层 composition root 按环境注入。

此模块为占位符，定义了未来能力扩展的目标结构。
当前不应删除 — 由能力包架构计划保留。
"""
```

`packages/analysis/src/ditto_analysis/reports/__init__.py`:
```python
"""
Reports — 分析报告生成。

提供策略回测报告、绩效归因报告、风险报告等标准化报告模板。
支持 HTML/PDF 输出和自定义报告扩展。

此模块为占位符，定义了未来能力扩展的目标结构。
当前不应删除 — 由能力包架构计划保留。
"""
```

`packages/analysis/src/ditto_analysis/diagnostics/__init__.py`:
```python
"""
Diagnostics — 诊断分析工具。

提供策略健康检查、数据质量诊断、模型偏差检测等工具。
用于研发阶段的快速问题定位，不参与生产路径。

此模块为占位符，定义了未来能力扩展的目标结构。
当前不应删除 — 由能力包架构计划保留。
"""
```

`packages/analysis/src/ditto_analysis/experiments/__init__.py`:
```python
"""
Experiments — 实验性分析。

提供因子探索、参数敏感性分析、策略对比实验等研究工具。
实验结果仅用于研究参考，不影响生产决策。

此模块为占位符，定义了未来能力扩展的目标结构。
当前不应删除 — 由能力包架构计划保留。
"""
```

`packages/analysis/src/ditto_analysis/screeners/__init__.py`:
```python
"""
Screeners — 证券筛选器。

提供多维度选股筛选、条件组合过滤、动态 universe 构建等工具。
筛选结果可作为策略 universe 输入。

此模块为占位符，定义了未来能力扩展的目标结构。
当前不应删除 — 由能力包架构计划保留。
"""
```

**Step 2: Verify**

Run:

```bash
pixi run -e dev lint
pixi run -e dev type
pixi run -e dev test --fast
```

Expected: all pass. Docstring-only changes should not affect any test or type check.

**Step 3: Commit**

```bash
git add packages/strategy/src/ditto_strategy/audit/__init__.py packages/execution/src/ditto_execution/broker/gateways/__init__.py packages/analysis/src/ditto_analysis/reports/__init__.py packages/analysis/src/ditto_analysis/diagnostics/__init__.py packages/analysis/src/ditto_analysis/experiments/__init__.py packages/analysis/src/ditto_analysis/screeners/__init__.py
git commit -m "docs: unify placeholder docstrings for skeleton directories"
```

---

### Task 2: Remove Duplicate TestRebalanceFreq from Strategy `[S]`

**Files:**
- Modify: `packages/strategy/tests/unit/alpha/test_stock_selection_trend_unit.py`

**Context:** `TestRebalanceFreq` 类（行 405-475）测试的是 `ditto_backtest.engine.EngineLoop._is_rebalance_day()`，属于 backtest 包的行为。Backtest 包已有更完整的 `TestIsRebalanceDay`（10 个测试方法）在 `packages/backtest/tests/unit/test_engine_loop_unit.py` 中，完全覆盖了 `TestRebalanceFreq` 的 6 个场景。同时需要移除文件头部对 `ditto_backtest` 的 import（行 12-13），以及 docstring 中"EngineConfig rebalance_freq"的描述。

**Step 1: Read the current file**

Read `packages/strategy/tests/unit/alpha/test_stock_selection_trend_unit.py` fully to understand the import structure and test class boundaries.

**Step 2: Remove TestRebalanceFreq class and backtest imports**

Remove lines 12-13 (backtest imports):
```python
from ditto_backtest.config import EngineConfig
from ditto_backtest.engine import EngineLoop, EngineOptions
```

Remove the entire `TestRebalanceFreq` class (lines 405-475), including the preceding comment block (lines 405-408):
```python
# ---------------------------------------------------------------------------
# EngineConfig rebalance_freq
# ---------------------------------------------------------------------------
```

Update the module docstring (line 5) to remove "and EngineConfig rebalance_freq" from:
```python
"""Tests for stock_selection_trend strategy template.

Covers StockSelectionTrendConfig, validate_config, get_param_constraints,
MultiFactorSignalStage, build_stock_selection_trend_pipeline, E2E pipeline,
and EngineConfig rebalance_freq.
"""
```

Change to:
```python
"""Tests for stock_selection_trend strategy template.

Covers StockSelectionTrendConfig, validate_config, get_param_constraints,
MultiFactorSignalStage, build_stock_selection_trend_pipeline, and E2E pipeline.
"""
```

**Step 3: Verify**

Run:

```bash
pixi run -e dev pytest packages/strategy/tests/unit/alpha/test_stock_selection_trend_unit.py -q
pixi run -e dev pytest packages/backtest/tests/unit/test_engine_loop_unit.py -q
pixi run -e dev type
```

Expected: strategy test passes without backtest imports; backtest test passes unchanged; type check passes.

**Step 4: Commit**

```bash
git add packages/strategy/tests/unit/alpha/test_stock_selection_trend_unit.py
git commit -m "test: remove duplicate TestRebalanceFreq from strategy (covered by backtest)"
```

---

### Task 3: Normalize Strategy CLAUDE.md Format `[S]`

**Files:**
- Modify: `packages/strategy/CLAUDE.md`

**Context:** Strategy CLAUDE.md 使用单一 `## 依赖` 章节加行内 emoji 标注，与其他 6 个包的 `## 允许依赖` / `## 禁止依赖` 分离格式不一致。同时缺少 `ditto_platform` 的依赖声明（storage/sqlite 层使用了 `ditto_platform.foundation` 的 `SQLitePool`/`logger`/`traced`）。

**Step 1: Rewrite the dependency sections**

将当前的 `## 依赖` + `## 技术债务` 替换为标准的 `## 允许依赖` + `## 禁止依赖` 格式：

Replace the current `## 依赖` section (lines 12-22):

```markdown
## 依赖

```
ditto_strategy → ditto_kernel ✅
ditto_strategy → ditto_data ✅ (DataProvider Protocol)
ditto_strategy → ditto_features ✅
ditto_strategy 禁止 → ditto_portfolio ❌
ditto_strategy 禁止 → ditto_apps ❌
ditto_strategy 禁止 → ditto_application ❌
ditto_strategy 禁止 → ditto_execution ❌
```

## 技术债务

strategy 模板当前直接引用 portfolio 的 allocation/constraints 类型。
长期演进方向：策略只产信号，分配方案由 application 层独立配置。
参见 LEAN 架构的 AlphaModel → PortfolioConstructionModel 解耦模式。
```

With:

```markdown
## 允许依赖

```
ditto_strategy → ditto_kernel ✅
ditto_strategy → ditto_data ✅ (DataProvider Protocol)
ditto_strategy → ditto_features ✅
ditto_strategy → ditto_platform ✅ (storage/sqlite: SQLitePool, logger, traced)
```

外部依赖：polars, orjson

**技术债务**：strategy 模板当前直接引用 portfolio 的 allocation/constraints 类型（仅 runtime_builder 和集成测试）。长期演进方向：策略只产信号，分配方案由 application 层独立配置。参见 LEAN 架构的 AlphaModel → PortfolioConstructionModel 解耦模式。

## 禁止依赖

```
ditto_strategy → ditto_portfolio ❌ (技术债务豁免：runtime_builder / 集成测试)
ditto_strategy → ditto_execution ❌
ditto_strategy → ditto_backtest ❌
ditto_strategy → ditto_analysis ❌
ditto_strategy → ditto_application ❌
ditto_strategy → ditto_apps ❌
```
```

**Step 2: Update directory tree to include new subdirectories**

在 `## 内部目录职责` 的目录树中补充缺失的子目录：

```text
ditto_strategy/
├── alpha/              # Alpha pipeline（从 engine 提取）
│   ├── builtins/       # 内置 Stage（Universe/Signal/Scoring/Selection/Filtering/Regime）
│   ├── templates/      # 策略模板（ETF轮动/趋势摆动/选股/行业轮动）
│   ├── pipeline.py     # StrategyPipeline + StrategyInputBundle
│   ├── protocols.py    # DecisionStage Protocol + DecisionFrame
│   ├── context.py      # StrategyContext（风险锁/持仓/冷却）
│   ├── models.py       # StrategyRun/Template/Version/SignalSnapshot/TargetPortfolio
│   ├── specs.py        # StrategySpec + CostModel/Execution/Constraint/Scorer/Selector
│   ├── frame.py        # FrameCol 常量 + validate_frame
│   ├── seeds.py        # 预定义 StrategySpec
│   └── validation.py   # validate_spec_params
├── signals/            # 信号契约（Protocol 定义）
│   ├── store.py        # SignalStore Protocol
│   └── models.py       # 信号模型
├── storage/            # 策略持久化
│   └── sqlite/         # SQLite 存储
│       ├── strategy_spec_store.py
│       ├── strategy_run_store.py
│       ├── strategy_artifact_store.py
│       └── services/   # 策略目录/运行/工件服务
├── runs/               # 策略运行模型
│   └── models.py
├── audit/              # 审计追踪（待扩展）
├── di/                 # 依赖注入
│   └── storage.py
├── contracts.py        # 包级公共契约
├── errors.py           # StrategyError 异常层级
└── models.py           # 策略域模型
```

**Step 3: Verify no other format issues**

Run:

```bash
pixi run -e dev lint
pixi run -e dev type
```

Expected: pass.

**Step 4: Commit**

```bash
git add packages/strategy/CLAUDE.md
git commit -m "docs: normalize strategy CLAUDE.md format and document ditto-platform dependency"
```

---

### Task 4: Final Verification `[S]`

**Files:**
- No file changes expected unless verification fails.

**Step 1: Run full gate**

Run:

```bash
pixi run -e dev check
```

Expected:

```text
ruff check . -> All checks passed
basedpyright --warnings -> 0 errors, 0 warnings
pytest --fast -> all pass
import-linter -> all contracts kept
architecture smell check passed
```

**Step 2: Run stale reference check**

Run:

```bash
rg -n "ditto_engine|ditto_analytics|ditto_app|ditto_infra|ditto_interfaces|packages/engine|packages/analytics|packages/app|packages/infra|interfaces/src" AGENTS.md CLAUDE.md .claude .factory -g '*.md' -g '*.py'
```

Expected: no active stale references (only historical/archive hits if any).

**Step 3: Verify test count consistency**

Run:

```bash
pixi run -e dev pytest packages/strategy/tests/unit -q --co -q | tail -1
pixi run -e dev pytest packages/backtest/tests/unit -q --co -q | tail -1
```

Expected: strategy test count reduced by 6 (TestRebalanceFreq had 6 test methods); backtest test count unchanged.

**Step 4: Commit any final fixes**

Only if verification reveals issues:

```bash
git add -A
git commit -m "fix: address verification findings"
```

---

## Implementation Notes

### What this plan does NOT do

- **Runtime directory**: `packages/application/src/ditto_application/runtime/` stays as placeholder per YAGNI decision.
- **Runtime builder location**: `builders/runtime_builder.py` stays in builders/ — no business need to move it.
- **DI refactoring for strategy→platform**: The dependency is documented as allowed, not refactored away.
- **Filling skeleton modules with Protocols**: Only docstrings are unified; no code is added to empty directories.

### Commit Cadence

3 substantive commits (Tasks 1-3) + 1 verification commit (Task 4, conditional).

Plan complete. Use `superpowers:executing-plans` in the implementation session and execute one task at a time.
