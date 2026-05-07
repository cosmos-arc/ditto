# Architecture Polish: 完善能力包遗漏与偷工减料

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 修复能力包架构迁移审计中发现的遗漏和偷工减料——错误层级形式主义、模式复制粘贴、缺失的契约/错误定义、无用的 `__version__`。

**Architecture:** 不改变包结构或依赖图，仅在现有 12 包内部完善契约、错误层级和代码质量。

**Tech Stack:** Python 3.13, pixi, ruff, basedpyright, pytest, import-linter, polars.

---

## 审计发现摘要

| # | 问题 | 类型 | 严重度 |
|---|------|------|--------|
| 1 | 29 个自定义错误仅 4 个被 raise；34+ 处 ValueError 硬编码 | 偷工减料 | HIGH |
| 2 | Strategy/Execution 错误 `details` dict __init__ 完全复制粘贴 | 偷工减料 | MEDIUM |
| 3 | Backtest 无 errors.py 和 contracts.py | 遗漏 | HIGH |
| 4 | Analysis 无顶层 contracts.py | 遗漏 | MEDIUM |
| 5 | `__version__` 12 包中 2 包缺失，kernel 有冗余 `_version.py` | 不一致 | LOW |
| 6 | Risk 定义 4 个错误但 0 个被 raise | 死代码 | MEDIUM |
| 7 | `StrategySpecError` 多继承 `(StrategyError, ValueError)` | 反模式 | LOW |

---

## Execution Rules

1. 每个 task 单独提交，提交前运行 `pixi run -e dev check`。
2. 不引入新依赖或改变包间依赖图。
3. 错误替换只改 raise 点和 catch 点，不改业务逻辑。
4. 输入验证类 ValueError（参数范围检查）保留不改；领域逻辑错误替换为领域异常。
5. 每个 task 有独立的验证命令。

---

### Task 1: 删除 `__version__` 和 `_version.py` [S]

**Files:**
- Modify: `packages/kernel/src/ditto_kernel/__init__.py` — 删除 `__version__` 行
- Delete: `packages/kernel/src/ditto_kernel/_version.py`
- Modify: `packages/platform/src/ditto_platform/__init__.py` — 已无 `__version__`（确认）
- Modify: `packages/data/src/ditto_data/__init__.py` — 已无 `__version__`（确认）
- Modify: `packages/features/src/ditto_features/__init__.py` — 删除 `__version__` 行
- Modify: `packages/strategy/src/ditto_strategy/__init__.py` — 删除 `__version__` 行
- Modify: `packages/portfolio/src/ditto_portfolio/__init__.py` — 删除 `__version__` 行
- Modify: `packages/risk/src/ditto_risk/__init__.py` — 删除 `__version__` 行
- Modify: `packages/execution/src/ditto_execution/__init__.py` — 删除 `__version__` 行
- Modify: `packages/backtest/src/ditto_backtest/__init__.py` — 删除 `__version__` 行
- Modify: `packages/analysis/src/ditto_analysis/__init__.py` — 删除 `__version__` 行
- Modify: `packages/application/src/ditto_application/__init__.py` — 删除 `__version__` 行
- Modify: `packages/apps/src/ditto_apps/__init__.py` — 删除 `__version__` 行
- Modify: `pyproject.toml` — 删除 `[tool.commitizen] version_files` 整段
- Rewrite: `packages/strategy/tests/unit/test_import_ditto_strategy_unit.py` — 改为 import boundary 测试
- Rewrite: `packages/portfolio/tests/unit/test_import_ditto_portfolio_unit.py` — 改为 import boundary 测试

**Step 1:** 删除所有 `__version__ = "0.1.0"` 行

```bash
rg -n '__version__' packages/*/src/ditto_*/__init__.py
```

逐文件删除 `__version__ = "0.1.0"` 行。

**Step 2:** 删除 kernel `_version.py`

```bash
git rm packages/kernel/src/ditto_kernel/_version.py
```

同时删除 `__init__.py` 中对 `_version` 的引用（如有 `from ._version import __version__`）。

**Step 3:** 删除 commitizen version_files

在 `pyproject.toml` 中删除 `[tool.commitizen]` 下的 `version_files` 列表。

**Step 4:** 重写 import 测试

将 strategy 和 portfolio 的 skeleton import 测试改为 import boundary 测试（与其他包一致）：

```python
# packages/strategy/tests/unit/test_import_ditto_strategy_unit.py
def test_strategy_imports_without_execution_or_data() -> None:
    """Strategy must not depend on execution or data at import time."""
    import sys

    import ditto_strategy  # noqa: F401

    loaded = {k for k in sys.modules if k.startswith("ditto_")}
    assert "ditto_execution" not in loaded
    assert "ditto_data" not in loaded
```

```python
# packages/portfolio/tests/unit/test_import_ditto_portfolio_unit.py
def test_portfolio_imports_without_strategy_or_data() -> None:
    """Portfolio must not depend on strategy or data at import time."""
    import sys

    import ditto_portfolio  # noqa: F401

    loaded = {k for k in sys.modules if k.startswith("ditto_")}
    assert "ditto_strategy" not in loaded
    assert "ditto_data" not in loaded
```

**Step 5:** 验证

```bash
pixi run -e dev type
pixi run -e dev test --fast
pixi run -e dev arch-check
```

**Step 6:** 提交

```bash
git add packages pyproject.toml
git commit -m "chore: remove unused __version__ from all packages"
```

---

### Task 2: 统一错误基类模式 — details dict 上推到 DittoError [M]

**问题:** `StrategyError` 和 `ExecutionError` 各自实现了完全相同的 `details: dict` + `**kwargs` 合并模式。`DataError` 也有类似但不完全相同的实现。应统一到 `DittoError` 基类。

**Files:**
- Modify: `packages/kernel/src/ditto_kernel/exceptions.py`
- Modify: `packages/strategy/src/ditto_strategy/errors.py`
- Modify: `packages/execution/src/ditto_execution/errors.py`
- Modify: `packages/portfolio/src/ditto_portfolio/errors.py` — 补齐 details 支持
- Modify: `packages/risk/src/ditto_risk/errors.py` — 补齐 details 支持
- Modify: `packages/analysis/src/ditto_analysis/errors.py` — 补齐 details 支持
- Modify: 对应测试文件

**Step 1:** 在 DittoError 中添加 details dict 支持

```python
# kernel/exceptions.py
class DittoError(Exception):
    """全局异常根。"""

    def __init__(self, message: str, *, details: dict | None = None, **kwargs: object) -> None:
        super().__init__(message)
        self.details: dict = {**(details or {}), **kwargs}
```

**Step 2:** 简化 DataError / DerivedError

移除 `DataError.__init__` 中的 `self.details = details or {}` 行，改为继承 DittoError 的 details。调整 `DerivedError` 同理。

**Step 3:** 简化 StrategyError / ExecutionError

移除两者中完全重复的 `details` dict 初始化代码，改为依赖 DittoError 基类。

**Step 4:** 补齐 PortfolioError / RiskError / AnalysisError

使这三个错误根类也传递 details 给 DittoError：

```python
class PortfolioError(DittoError):
    """Portfolio domain error."""
```

（无需自定义 `__init__`，DittoError 基类已处理 details。）

**Step 5:** 更新所有子类构造函数

确保子类如 `ConstraintViolationError`、`StateTransitionError` 等通过 `super().__init__` 正确传递 details。

**Step 6:** 更新测试

检查 `packages/kernel/tests/unit/test_exceptions_unit.py` 是否覆盖 DittoError.details。
检查 strategy/execution 错误测试是否需要调整。

**Step 7:** 验证

```bash
pixi run -e dev type
pixi run -e dev test --fast
pixi run -e dev arch-check
```

**Step 8:** 提交

```bash
git add packages/kernel packages/strategy packages/execution packages/portfolio packages/risk packages/analysis
git commit -m "refactor: unify error details pattern into DittoError base class"
```

---

### Task 3: 添加 Backtest 错误层级和契约文件 [M]

**问题:** backtest 是唯一没有 `errors.py` 的能力包（5 处 ValueError 硬编码），
且用 `protocol.py` 而非 `contracts.py` 命名契约。

**Files:**
- Create: `packages/backtest/src/ditto_backtest/errors.py`
- Create: `packages/backtest/src/ditto_backtest/contracts.py`
- Modify: `packages/backtest/src/ditto_backtest/__init__.py` — 更新 `__all__`
- Delete or Keep: `packages/backtest/src/ditto_backtest/protocol.py` — 视情况合并或保留
- Create: `packages/backtest/tests/unit/test_backtest_errors_unit.py`
- Create: `packages/backtest/tests/unit/test_backtest_contracts_unit.py`

**Step 1:** 创建 errors.py

```python
"""Backtest domain errors."""

from __future__ import annotations

from ditto_kernel.exceptions import DittoError

__all__ = [
    "BacktestError",
    "EngineConfigError",
    "ReplayError",
    "SimulationError",
]


class BacktestError(DittoError):
    """Backtest domain error."""


class EngineConfigError(BacktestError):
    """回测引擎配置错误。"""


class ReplayError(BacktestError):
    """数据回放错误。"""


class SimulationError(BacktestError):
    """模拟交易错误（策略执行/盘前检查/订单规划）。"""
```

**Step 2:** 创建 contracts.py

将 `protocol.py` 中的 `TradingLoop` Protocol 迁移到 `contracts.py`。
如果 `protocol.py` 除了 `TradingLoop` 无其他内容，则删除 `protocol.py` 并更新所有 import。

```python
"""Backtest capability contracts."""

from __future__ import annotations

from typing import Protocol

__all__ = ["TradingLoop"]

if TYPE_CHECKING:
    from ditto_backtest.engine import EngineResult


class TradingLoop(Protocol):
    """回测交易循环的抽象接口。"""

    def run(self) -> EngineResult: ...
```

**Step 3:** 更新 `__init__.py` 的 `__all__`

确保 errors 和 contracts 的公开名称被正确导出。

**Step 4:** 更新引用 `protocol.py` 的 import

```bash
rg -n "from ditto_backtest.protocol import" packages/ --include="*.py"
```

将 `ditto_backtest.protocol` 改为 `ditto_backtest.contracts`。

**Step 5:** 编写测试

`test_backtest_errors_unit.py` — 验证错误层级结构和 details dict：
```python
def test_backtest_error_hierarchy() -> None:
    from ditto_backtest.errors import (
        BacktestError,
        EngineConfigError,
        ReplayError,
        SimulationError,
    )

    assert issubclass(BacktestError, DittoError)
    assert issubclass(EngineConfigError, BacktestError)
    assert issubclass(ReplayError, BacktestError)
    assert issubclass(SimulationError, BacktestError)
```

`test_backtest_contracts_unit.py` — 验证 TradingLoop 是 Protocol：
```python
from typing import Protocol

from ditto_backtest.contracts import TradingLoop


def test_trading_loop_is_protocol() -> None:
    assert issubclass(TradingLoop, Protocol)
```

**Step 6:** 验证

```bash
pixi run -e dev pytest packages/backtest/tests/unit -q
pixi run -e dev type
pixi run -e dev arch-check
```

**Step 7:** 提交

```bash
git add packages/backtest
git commit -m "refactor: add backtest error hierarchy and contracts"
```

---

### Task 4: 添加 Analysis contracts.py [S]

**问题:** analysis 是唯一没有顶层 `contracts.py` 的能力包。
虽然 Protocols 已存在于 `research/catalog_service.py`，但顶层缺少统一的契约入口。

**Files:**
- Create: `packages/analysis/src/ditto_analysis/contracts.py`
- Create: `packages/analysis/tests/unit/test_analysis_contracts_unit.py`
- Modify: `packages/analysis/src/ditto_analysis/__init__.py` — 更新 `__all__`

**Step 1:** 创建 contracts.py

提取 `research/catalog_service.py` 中已有的 Protocol 接口作为顶层契约：

```python
"""Analysis capability contracts."""

from __future__ import annotations

__all__ = [
    "ResearchCatalogReader",
    "ResearchCatalogWriter",
]

from typing import Protocol

from ditto_analysis.research.catalog_service import (
    ResearchCatalogReaderProtocol,
    ResearchCatalogWriterProtocol,
)

# Re-export protocols under canonical contract names
ResearchCatalogReader = ResearchCatalogReaderProtocol
ResearchCatalogWriter = ResearchCatalogWriterProtocol
```

**备选方案:** 如果 re-export 违反"禁止跨包 re-export"规则，
则在 contracts.py 中直接定义 Protocol，让 catalog_service.py 引用 contracts。

选择哪种方案取决于现有 Protocol 的使用范围。如果仅 analysis 内部使用，re-export 可接受；
如果外部包需要引用，应将 Protocol 定义移到 contracts.py。

**Step 2:** 编写测试

```python
from typing import Protocol

from ditto_analysis.contracts import ResearchCatalogReader, ResearchCatalogWriter


def test_research_catalog_reader_is_protocol() -> None:
    assert issubclass(ResearchCatalogReader, Protocol)


def test_research_catalog_writer_is_protocol() -> None:
    assert issubclass(ResearchCatalogWriter, Protocol)
```

**Step 3:** 验证

```bash
pixi run -e dev pytest packages/analysis/tests/unit -q
pixi run -e dev type
pixi run -e dev arch-check
```

**Step 4:** 提交

```bash
git add packages/analysis
git commit -m "refactor: add analysis capability contracts"
```

---

### Task 5: 消灭死代码 — 连通 Risk 错误定义到 raise 点 [S]

**问题:** Risk 定义了 4 个自定义错误，但 0 个被 raise。5 处 ValueError 硬编码。

**ValueError 位置分析:**

| 文件 | 行 | 当前 | 替换为 |
|------|---|------|--------|
| `_validation.py` | 9 | `raise ValueError(f"{name} must be in (0, 1]")` | **保留** — 输入验证 |
| `exposure/rules.py` | 82 | `raise ValueError(f"threshold must be positive")` | **保留** — 输入验证 |
| `drawdown/rules.py` | 35 | `raise ValueError("thresholds must be non-negative")` | **保留** — 输入验证 |
| `drawdown/rules.py` | 41 | `raise ValueError(msg)` (threshold validation) | **保留** — 输入验证 |
| `drawdown/rules.py` | 117 | `raise ValueError(f"threshold must be positive")` | **保留** — 输入验证 |

**判断:** Risk 包中所有 ValueError 都是**输入参数验证**（阈值范围检查），不是领域逻辑错误。
自定义错误（`ConstraintViolationError`、`ExposureLimitError`、`DrawdownThresholdError`）设计用于
运行时风控规则违反（如持仓超限、回撤超阈值），但目前风控检查逻辑以返回值形式报告违规
（返回 `RiskAction` 而非抛异常），所以这些错误类是**为未来扩展预留的**。

**Files:**
- Keep: `packages/risk/src/ditto_risk/errors.py` — 不改动，错误是合理的未来扩展点
- Add docstring: 在每个错误类添加注释说明预期使用场景

**Step 1:** 为 Risk 错误类添加使用场景注释

```python
class ConstraintViolationError(RiskError):
    """持仓约束违反（如集中度超限、板块超配）。由 PostTradeGuard 扫描触发。"""
```

**Step 2:** 验证

```bash
pixi run -e dev type
pixi run -e dev test --fast
```

**Step 3:** 提交

```bash
git add packages/risk
git commit -m "docs: clarify risk error usage intent"
```

---

### Task 6: 消灭死代码 — 连通 Execution 错误定义到 raise 点 [S]

**问题:** Execution 定义了 6 个自定义错误，仅 1 个被 raise。2 处 ValueError 硬编码。

**ValueError 位置分析:**

| 文件 | 行 | 当前 | 替换为 |
|------|---|------|--------|
| `storage/sqlite/legacy/_sql.py` | 88 | `raise ValueError("SignalRecord required")` | `OrderSubmitError` |
| `storage/sqlite/legacy/_sql.py` | 94 | `raise ValueError("FillRecord required")` | `FillProcessingError` |

**Files:**
- Modify: `packages/execution/src/ditto_execution/storage/sqlite/legacy/_sql.py`
- Modify: 对应测试（如有 catch ValueError 的断言需更新）

**Step 1:** 替换 ValueError 为领域错误

在 `_sql.py` 中：
```python
from ditto_execution.errors import FillProcessingError, OrderSubmitError

# 替换
raise OrderSubmitError("SignalRecord required for order submission")
raise FillProcessingError("FillRecord required for fill processing")
```

**Step 2:** 更新测试中的 catch 断言

检查是否有测试 `pytest.raises(ValueError)` 对应这两行：

```bash
rg -n "ValueError" packages/execution/tests/ --include="*.py"
```

如有则更新为对应领域错误。

**Step 3:** 验证

```bash
pixi run -e dev pytest packages/execution/tests/unit -q
pixi run -e dev type
```

**Step 4:** 提交

```bash
git add packages/execution
git commit -m "refactor: replace ValueError with domain errors in execution storage"
```

---

### Task 7: 消灭死代码 — 连通 Strategy 错误定义到 raise 点 [M]

**问题:** Strategy 定义了 5 个自定义错误，仅 1 个被 raise。19 处 ValueError 硬编码。

**ValueError 位置分类:**

| 类别 | 数量 | 处理 |
|------|------|------|
| alpha/specs.py — StrategySpec 字段验证 | 8 处 | 用 `StrategySpecError` 替换 |
| alpha/templates/*.py — 模板参数验证 | 11 处 | 用 `StrategySpecError` 替换 |
| alpha/frame.py — DecisionFrame 列校验 | 1 处 | 保留（数据验证，非策略逻辑） |

**注意:** `StrategySpecError` 同时继承 `StrategyError` 和 `ValueError`（多重继承），
这允许 catch `ValueError` 的代码继续工作。保留这个设计以保持向后兼容。

**Files:**
- Modify: `packages/strategy/src/ditto_strategy/alpha/specs.py`
- Modify: `packages/strategy/src/ditto_strategy/alpha/templates/stock_selection_trend.py`
- Modify: `packages/strategy/src/ditto_strategy/alpha/templates/stock_sector_rotation.py`
- Modify: 对应测试文件

**Step 1:** 在 specs.py 中替换

```python
from ditto_strategy.errors import StrategySpecError

# 将:
raise ValueError(f"StrategySpec.{field_name} must be non-empty")
# 替换为:
raise StrategySpecError(f"StrategySpec.{field_name} must be non-empty")
```

**Step 2:** 在模板文件中替换

每个模板的参数验证 ValueError 替换为 `StrategySpecError`。

**Step 3:** 更新测试

```bash
rg -n "raises.*ValueError" packages/strategy/tests/ --include="*.py"
```

检查是否有测试 catch `ValueError` 对应被替换的行。由于 `StrategySpecError` 继承 `ValueError`，
这些测试应继续通过，但应更新为更精确的 `StrategySpecError`。

**Step 4:** 验证

```bash
pixi run -e dev pytest packages/strategy/tests/unit -q
pixi run -e dev type
```

**Step 5:** 提交

```bash
git add packages/strategy
git commit -m "refactor: replace ValueError with StrategySpecError in strategy validation"
```

---

### Task 8: 消灭死代码 — 连通 Backtest 错误定义到 raise 点 [S]

**问题:** Backtest 目前有 5 处 ValueError 硬编码，刚创建的错误层级未被使用。

**ValueError 位置分析:**

| 文件 | 行 | 替换为 |
|------|---|--------|
| `engine.py` | 155 | `EngineConfigError` |
| `replay.py` | 216 | `ReplayError` |
| `steps/planning.py` | 87 | `SimulationError` |
| `steps/pre_trade.py` | 140 | `SimulationError` |
| `steps/strategy.py` | 69 | `SimulationError` |

**Files:**
- Modify: `packages/backtest/src/ditto_backtest/engine.py`
- Modify: `packages/backtest/src/ditto_backtest/replay.py`
- Modify: `packages/backtest/src/ditto_backtest/steps/planning.py`
- Modify: `packages/backtest/src/ditto_backtest/steps/pre_trade.py`
- Modify: `packages/backtest/src/ditto_backtest/steps/strategy.py`
- Modify: 对应测试文件

**Step 1:** 替换所有 ValueError 为领域错误

```python
from ditto_backtest.errors import EngineConfigError, ReplayError, SimulationError
```

**Step 2:** 更新测试 catch 断言

```bash
rg -n "raises.*ValueError" packages/backtest/tests/ --include="*.py"
```

更新为对应的领域错误类型。

**Step 3:** 验证

```bash
pixi run -e dev pytest packages/backtest/tests/unit -q
pixi run -e dev type
```

**Step 4:** 提交

```bash
git add packages/backtest
git commit -m "refactor: replace ValueError with domain errors in backtest"
```

---

### Task 9: 最终验证 [S]

**Step 1:** 运行全量检查

```bash
pixi run -e dev check
```

Expected:
```
ruff check . -> All checks passed
basedpyright --warnings -> 0 errors, 0 warnings
pytest --fast -> all pass
import-linter -> all contracts kept
architecture smell check passed
```

**Step 2:** 验证错误使用率

```bash
rg -rn "raise ValueError" packages/*/src/ --include="*.py" | wc -l
```

Expected: 显著减少（输入验证类 ValueError 保留，领域逻辑类已替换为领域错误）。

**Step 3:** 验证无死错误

```bash
for pkg in strategy portfolio risk execution backtest analysis; do
    echo "=== $pkg ==="
    errors=$(grep -rn "class.*Error" packages/$pkg/src/ditto_$pkg/errors.py 2>/dev/null | wc -l)
    raises=$(grep -rn "raise.*Error\|raise.*$pkg" packages/$pkg/src/ --include="*.py" 2>/dev/null | wc -l)
    echo "  defined: $errors, raised: $raises"
done
```

Expected: 每个包至少有 1 个自定义错误被 raise。

**Step 4:** 提交最终修复（如有）

```bash
git add -A
git commit -m "chore: architecture polish final verification"
```

---

## Implementation Notes

### 输入验证 vs 领域错误的判断标准

- **保留 ValueError**：函数入口参数范围检查（如 `threshold must be positive`、`name must be non-empty`）。
  这是编程错误（precondition violation），不是领域逻辑错误。
- **替换为领域错误**：业务流程中的语义错误（如"策略配置不完整"、"回测引擎配置无效"、
  "存储层收到非法记录类型"）。这些是运行时领域状态违反。

### 执行顺序

Task 1 → Task 2 → Task 3（依赖 Task 2 的新 DittoError 基类）→ Task 4（独立）
→ Task 5-8（可并行，都是替换 ValueError）→ Task 9

Task 5 和 Task 6-8 之间无依赖关系，但建议按序执行以控制变更范围。

### 不在本次范围

- 填充 skeleton 占位符目录（holdings/positions/gateways/reports 等）— 这是未来功能开发
- 扩展 analysis/reports/diagnostics/experiments/screeners — 待需求驱动
- apps pyproject.toml 补齐 portfolio/risk/backtest 声明 — apps 不直接导入这些包，声明正确

---

Plan complete. Use `superpowers:executing-plans` in the implementation session and execute one task at a time.
