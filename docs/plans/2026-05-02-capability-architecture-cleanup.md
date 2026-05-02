# 能力包架构收尾 — 残留耦合清理与一致性补齐

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 消除能力包架构重构的残留耦合（data↔capability 反向依赖、risk→execution 被压制的违规），补齐包结构一致性缺失，使 importlinter 所有合约零 ignore_imports 通过。

**Architecture:** 当前 architecture-refactor 分支已将 12 个能力包骨架就位。核心问题：data 包的 DI 层仍充当 execution/features/analysis 的 composition root，导致依赖方向倒挂；risk→execution 的违规通过 ignore_imports 压制而非解决。

**Tech Stack:** Python 3.13, pixi, Dishka DI, import-linter, basedpyright, ruff, pytest。

---

## Execution Rules

1. 每个 task 单独提交，提交前运行 task 内指定验证命令。
2. 不引入长期 backward compatibility；临时 shim 必须在同一 task 内删除。
3. 不用 `TYPE_CHECKING` 延迟导入解决循环依赖。
4. 每次 import 改动后先 `rg` 定位引用，再改，再跑 `pixi run -e dev type` + `arch-check`。
5. 当前 staged changes（DI storage 模块等）视为已完成的基线。

## Global Verification Commands

```bash
pixi run -e dev lint
pixi run -e dev type
pixi run -e dev test --fast
pixi run -e dev arch-check
pixi run -e dev check
```

---

## Task 1: 迁移 FeeModel Protocol 到 kernel `[L]` ✅ DONE (dd0915ee)

**问题：** `ditto_risk.pre_trade` 为获取 `FeeModel` Protocol 被迫依赖 `ditto_execution`，违反 `risk-no-execution` 硬性约束。当前通过 `.importlinter` 的 `ignore_imports` 压制。

**根因：** `FeeModel` Protocol + 值对象 `FeeSchedule` 应同居 kernel。`FeeSchedule` 已在 `ditto_kernel.trading`，但 `FeeModel` 遗漏在 `ditto_execution.reality.fee`。

**关键决策：** `FeeModel` 方法签名引用 `Order`（来自 `ditto_portfolio.accounting.order_book`）。迁移方案：

- **Protocol 定义** → `ditto_kernel.trading`（使用 `from __future__ import annotations`，`Order` 作为前向引用字符串）
- **具体实现** `SimpleFeeModel`、`AShareFeeModel` → 保留在 `ditto_execution.reality.fee`（运行时需要真实 `Order`）
- `execution/reality/fee.py` → 从 kernel re-export `FeeModel`，本地保留实现类

**Files:**
- Modify: `packages/kernel/src/ditto_kernel/trading.py` — 添加 `FeeModel` Protocol
- Modify: `packages/execution/src/ditto_execution/reality/fee.py` — 删除 Protocol 定义，从 kernel re-export
- Modify: `packages/execution/src/ditto_execution/reality/__init__.py` — 更新 re-export
- Modify: `packages/risk/src/ditto_risk/pre_trade.py` — `from ditto_kernel.trading import FeeModel`
- Modify: `packages/risk/pyproject.toml` — 删除 `ditto-execution` 依赖
- Modify: `packages/risk/CLAUDE.md` — 更新允许依赖列表
- Modify: `.importlinter` risk-boundary — 删除 `ignore_imports` 行
- Modify: `packages/backtest/src/ditto_backtest/engine.py` — 更新 import 来源
- Modify: `packages/backtest/src/ditto_backtest/steps/pre_trade.py` — 更新 import 来源
- Modify: `packages/application/src/ditto_application/builders/service_factory.py` — 更新 import
- Modify: `packages/application/src/ditto_application/processes/execution/fee_override.py` — 更新 import
- Update ~8 test files referencing `FeeModel`

**Step 1: 添加 FeeModel Protocol 到 kernel**

在 `ditto_kernel.trading` 顶部添加 `from __future__ import annotations`，然后在 `FeeSchedule` 之后定义：

```python
class FeeModel(Protocol):
    """交易费用计算协议 — 盘前估算与盘后结算共享。"""

    def calculate(
        self,
        order: Order,
        fill_price: float,
        fill_quantity: int,
        fee_schedule: FeeSchedule,
    ) -> float: ...

    def estimate(
        self,
        order: Order,
        estimated_price: float,
        fee_schedule: FeeSchedule,
    ) -> float: ...
```

**Step 2: 更新 execution 的 fee.py**

删除 `FeeModel` class 定义，改为从 kernel re-export：

```python
from ditto_kernel.trading import FeeModel  # re-export

__all__ = ["FeeModel", "SimpleFeeModel", "AShareFeeModel"]
```

**Step 3: 批量更新所有 FeeModel import 来源**

```bash
rg -n "from ditto_execution.reality import FeeModel|from ditto_execution.reality.fee import FeeModel" packages/ --include="*.py"
```

生产代码中以下文件直接 import `FeeModel`，需改为 `from ditto_kernel.trading import FeeModel`：

- `packages/risk/src/ditto_risk/pre_trade.py`
- `packages/backtest/src/ditto_backtest/engine.py`
- `packages/backtest/src/ditto_backtest/steps/pre_trade.py`
- `packages/application/src/ditto_application/builders/service_factory.py`
- `packages/application/src/ditto_application/processes/execution/fee_override.py`

注意：`fee_override.py` 和 `service_factory.py` 也 import `AShareFeeModel`，这些具体类仍从 `ditto_execution.reality` import，保持不变。只改 `FeeModel` Protocol 的 import 来源。

**Step 4: 删除 risk→execution 依赖**

- `packages/risk/pyproject.toml`: 移除 `"ditto-execution"` 行
- `packages/risk/CLAUDE.md`: 移除 `ditto_risk → ditto_execution ✅` 行
- `.importlinter` risk-boundary: 删除 `ignore_imports = ditto_risk.pre_trade -> ditto_execution.reality`

**Step 5: 验证**

```bash
pixi run -e dev pytest packages/risk/tests/unit -q
pixi run -e dev pytest packages/kernel/tests/unit -q
pixi run -e dev type
pixi run -e dev arch-check
```

Expected: risk 测试通过；type 通过；risk-boundary 合约零 ignore_imports 通过。

**Step 6: Commit**

```bash
git add packages/kernel packages/risk packages/execution packages/backtest packages/application .importlinter
git commit -m "refactor: move FeeModel protocol to kernel, remove risk→execution dependency"
```

---

## Task 2: 迁移 data/di/trade.py 到 execution/di/ `[L]` ✅ DONE (a70ec403)

**问题：** `data/di/trade.py` 注册 execution 域的全部 DI（TradeService、DDL schema、readers/writers），导致 data 包硬依赖 `ditto-execution`。依赖方向倒挂。

**依赖链：** `data/di/trade.py` → `ditto_execution.storage.sqlite.legacy`（14 个符号）+ `ditto_execution.storage.sqlite.trade`（TradeService）

**Files:**
- Modify: `packages/execution/src/ditto_execution/di/storage.py` — 合并 trade DI providers
- Modify: `packages/execution/src/ditto_execution/di/__init__.py` — 更新 exports
- Delete: `packages/data/src/ditto_data/di/trade.py`
- Modify: `packages/data/src/ditto_data/di/__init__.py` — 移除 TradeProvider
- Modify: `packages/data/src/ditto_data/di/_factory.py` — 移除 TradeProvider
- Modify: `packages/data/src/ditto_data/services/deps.py` — 移除 ExecutionReaders/ExecutionWriters re-export
- Modify: `packages/apps/src/ditto_apps/registry/container.py` — 更新 provider 组装
- Modify: `.importlinter` data-boundary — 移除 trade 相关 ignore_imports
- Modify: `packages/data/pyproject.toml` — 移除 `ditto-execution`（如果无其他 execution 引用）

**Step 1: 分析 trade.py 的完整依赖**

```bash
cat packages/data/src/ditto_data/di/trade.py
rg -n "from ditto_data.di.trade|from ditto_data.services.deps.*Execution" packages/ --include="*.py"
```

确认 `data/di/trade.py` 的所有 import 和 consumer。

**Step 2: 将 trade providers 合并到 execution/di/storage.py**

`execution/di/storage.py` 已有 `ExecutionStorageProvider`（提供 `ExecutionAuditService`）。需要增加：

- Signal/Fill/Position 的 readers/writers providers
- DDL schema initialization provider
- TradeService provider
- ExecutionReaders/ExecutionWriters 聚合 providers

关键变更：`data/di/trade.py` 使用 `SQLiteClient`（from `ditto_data.storage.sqlite_client`），需切换为 `SQLitePool`（from `ditto_platform.foundation`），因为 execution 不依赖 data。strategy/di 和现有 execution/di 已使用 `SQLitePool` 模式。

**Step 3: 清理 data 包**

```bash
# 删除 trade DI
rm packages/data/src/ditto_data/di/trade.py

# 更新 data/di/__init__.py — 移除 TradeProvider
# 更新 data/di/_factory.py — 移除 TradeProvider 引用
# 更新 data/services/deps.py — 移除 ExecutionReaders/ExecutionWriters re-export
```

**Step 4: 更新 composition root**

`packages/apps/src/ditto_apps/registry/container.py` 已 import `get_execution_providers`。确认 trade 相关 provider 通过此函数提供，data 的 `get_data_providers()` 不再包含 trade。

**Step 5: 收紧 importlinter**

`.importlinter` data-boundary 合约中移除：
```ini
ignore_imports =
    ditto_data.di.trade -> ditto_execution.**
    ditto_data.services.deps -> ditto_execution.storage.deps
```

**Step 6: 验证 data 包可脱离 execution**

```bash
rg -n "ditto_execution" packages/data/src/ --include="*.py"
```

Expected: 零命中（除 `di/runtime.py` 如果 runtime 仍有桥接则保留对应 ignore_imports）。

```bash
pixi run -e dev pytest packages/execution/tests/unit -q
pixi run -e dev pytest packages/data/tests/unit -q
pixi run -e dev type
pixi run -e dev arch-check
```

**Step 7: Commit**

```bash
git add packages/execution packages/data packages/apps .importlinter
git commit -m "refactor: migrate trade DI from data to execution package"
```

---

## Task 3: 拆分 data/di/runtime.py 中的 features/analysis 桥接 `[M]` ✅ DONE (7f01ba95)

**问题：** `data/di/runtime.py` 仍实例化 `ditto_features` 和 `ditto_analysis` 的服务（DerivedQueryService、ResearchArtifactService），是 data→features/analysis 反向依赖的残留。

**现状（staged changes 后）：** strategy 相关 providers 已迁出。runtime.py 保留两个桥接方法：
- `research_artifact_service()` — 构建 `ResearchArtifactService`（from analysis）
- `derived_query_service()` — 构建 `DerivedQueryService`（from features）

**Files:**
- Modify: `packages/features/src/ditto_features/di/storage.py` — 添加 derived_query_service provider
- Modify: `packages/analysis/src/ditto_analysis/di/storage.py` — 添加 research_artifact_service provider
- Modify: `packages/data/src/ditto_data/di/runtime.py` — 删除 features/analysis 桥接
- Modify: `packages/data/src/ditto_data/services/__init__.py` — 移除 features re-exports
- Modify: `.importlinter` — 更新 data-boundary 和 layered-architecture 的 ignore_imports
- Modify: `packages/data/pyproject.toml` — 评估能否移除 ditto-features/ditto-analysis/ditto-strategy

**Step 1: 审计 data 包中所有 features/analysis/strategy 引用**

```bash
rg -n "ditto_features|ditto_analysis|ditto_strategy" packages/data/src/ --include="*.py"
```

确认迁移 trade.py（Task 2）后 data 残留的 capability 包引用。

**Step 2: 将 derived_query_service 迁入 features/di/**

`derived_query_service` 依赖 `DerivedCatalogService`（由 `FeaturesStorageProvider` 提供）和 `DerivedArtifactReader`。通过 Dishka 的依赖注入，`features/di/storage.py` 可以声明依赖 `DerivedCatalogService` 并组合 `DerivedQueryService`。

**Step 3: 将 research_artifact_service 迁入 analysis/di/**

`ResearchArtifactService` 只需要 `data_root` 路径配置。将其迁入 `analysis/di/storage.py`，从 settings 获取路径。

**Step 4: 清理 data/services/__init__.py re-exports**

staged changes 已将 import 来源从 data 本地改为直接从 features 包 import，但 data 的公共 API 仍暴露这些符号。所有消费者应改为直接从 `ditto_features.services` import。

```bash
rg -n "from ditto_data.services import.*Derived|from ditto_data.services import.*Research" packages/ --include="*.py"
```

逐个更新消费者。

**Step 5: 更新 importlinter**

移除 layered-architecture 和 data-boundary 中的：
```ini
ditto_data.di.runtime -> ditto_features.**
ditto_data.di.runtime -> ditto_analysis.**
ditto_data.services -> ditto_features.**
ditto_data.providers.** -> ditto_features.**
```

**Step 6: 验证 data 包依赖最小化**

```bash
rg -n "ditto_features|ditto_analysis|ditto_strategy|ditto_execution" packages/data/src/ --include="*.py"
```

Expected: 零命中。data 只依赖 kernel + platform。

```bash
pixi run -e dev pytest packages/data/tests/unit packages/features/tests/unit packages/analysis/tests/unit -q
pixi run -e dev type
pixi run -e dev arch-check
```

**Step 7: Commit**

```bash
git add packages/data packages/features packages/analysis .importlinter
git commit -m "refactor: remove data→features/analysis DI bridging"
```

---

## Task 4: 移除 strategy 死依赖 `[S]` ✅ DONE (38a2ecd7)

**问题：** `packages/strategy/pyproject.toml` 声明 `ditto-portfolio` 依赖，但源码中零 `from ditto_portfolio` 导入。

**Files:**
- Modify: `packages/strategy/pyproject.toml` — 删除 `ditto-portfolio`
- Modify: `packages/strategy/CLAUDE.md` — 更新依赖声明

**Step 1: 确认无 portfolio 引用**

```bash
rg -n "ditto_portfolio" packages/strategy/src/ --include="*.py"
```

Expected: 零命中。

**Step 2: 移除依赖**

`packages/strategy/pyproject.toml`: 删除 `"ditto-portfolio"` 行。
`packages/strategy/CLAUDE.md`: 移除 `ditto_strategy → ditto_portfolio` 相关说明，或标注为"未来演进方向"。

**Step 3: 验证**

```bash
pixi run -e dev pytest packages/strategy/tests/unit -q
pixi run -e dev type
pixi run -e dev arch-check
```

**Step 4: Commit**

```bash
git add packages/strategy
git commit -m "chore: remove unused ditto-portfolio dependency from strategy"
```

---

## Task 5: 补齐缺失的 errors.py `[S]` ✅ DONE (38a2ecd7)

**问题：** `analysis` 缺少 `errors.py`，直接借用 `ditto_data.errors` 和 `ditto_features.errors.AnalyticsError`。这违反了"analysis 不被生产路径依赖"原则的反面 — analysis 也不应依赖 production 包的错误类型。

**Files:**
- Create: `packages/analysis/src/ditto_analysis/errors.py`
- Modify: `packages/analysis/src/ditto_analysis/research/domain.py` — 使用本地 error
- Modify: `packages/analysis/src/ditto_analysis/__init__.py` — export error
- Modify: `.importlinter` analysis-no-production-dependency — 移除 `ditto_data.errors` 和 `ditto_features.errors` 的 ignore_imports（如果 analysis 不再需要这些引用）

**Step 1: 定义 analysis 本地 error hierarchy**

```python
"""Analysis — 研究分析错误定义。"""

from ditto_kernel.exceptions import DittoError

__all__ = ["AnalysisError", "ResearchDatasetError"]


class AnalysisError(DittoError):
    """分析层基础错误。"""


class ResearchDatasetError(AnalysisError):
    """研究数据集操作错误。"""
```

**Step 2: 更新 analysis 内部引用**

`packages/analysis/src/ditto_analysis/research/domain.py`:
- `LateArrivalError` 改为继承 `AnalysisError`（本地）而非 `AnalyticsError`（features）
- 如果 `DerivedNotImplementedError`/`DerivedValidationError` 在 analysis 语义中被使用，考虑改为 `ResearchDatasetError` 或保留 data.errors 的 import（如果语义确实属于 data 域）

**Step 3: 评估 features.errors.AnalyticsError 命名**

`features/errors.py` 中的 `AnalyticsError` 名称属于 analysis 语义域但定义在 features 中。两个选择：
- **保持现状**（`AnalyticsError` 是历史命名，改名影响面大）
- **重命名** 为 `FeaturesError`（正确但需要更新所有消费者）

建议保持现状，仅在 analysis 中定义自己的 `AnalysisError` 作为 analysis 域的根。

**Step 4: 更新 importlinter**

如果 analysis 不再 import `ditto_data.errors` 和 `ditto_features.errors`：
```ini
# 移除
ditto_analysis.** -> ditto_data.errors
ditto_analysis.** -> ditto_features.errors
```

**Step 5: 验证**

```bash
pixi run -e dev pytest packages/analysis/tests/unit -q
pixi run -e dev type
pixi run -e dev arch-check
```

**Step 6: Commit**

```bash
git add packages/analysis .importlinter
git commit -m "refactor: add analysis error hierarchy, decouple from features/data errors"
```

---

## Task 6: 最终验证与文档同步 `[S]` ✅ DONE

**Files:**
- Modify: `packages/data/CLAUDE.md` — 更新依赖声明（移除 capability 包引用）
- Modify: `CLAUDE.md` — 确认架构描述准确
- Modify: `docs/plans/2026-04-29-capability-package-architecture-implementation-plan.md` — 标记所有残留项完成

**Step 1: 运行完整验证**

```bash
pixi run -e dev check
```

Expected: lint/type/test/arch-check 全部通过。

**Step 2: 确认 importlinter 零 ignore_imports（或仅剩余合理的豁免）**

```bash
grep -c "ignore_imports" .importlinter
```

逐条审查每个 ignore_imports 是否合理。以下豁免可接受：
- `ditto_platform.exceptions -> ditto_kernel.exceptions`（PlatformError 继承 DittoError）
- `ditto_data.storage.** -> ditto_data.models.**`（storage 与 model 的类型注解耦合）
- Registry 豁免（composition root 允许直接依赖）

以下必须已清除：
- ~~`ditto_risk.pre_trade -> ditto_execution.reality`~~ → Task 1
- ~~`ditto_data.di.trade -> ditto_execution.**`~~ → Task 2
- ~~`ditto_data.di.runtime -> ditto_features.**`~~ → Task 3
- ~~`ditto_data.di.runtime -> ditto_analysis.**`~~ → Task 3

**Step 3: 更新 CLAUDE.md 和包级文档**

确认 `CLAUDE.md` 架构原则中：
- data 依赖仅 kernel + platform
- risk 不依赖 execution
- 所有 capability 包的 CLAUDE.md 与 pyproject.toml 一致

**Step 4: 标记实施计划完成**

在实施计划文档中标注所有残留项为 DONE。

**Step 5: Commit**

```bash
git add CLAUDE.md docs packages/*/CLAUDE.md .importlinter
git commit -m "docs: finalize capability package architecture documentation"
```

---

## Implementation Notes

### 执行顺序

严格按 Task 1→2→3→4→5→6 顺序：
- Task 1（FeeModel → kernel）独立，可先做
- Task 2（trade DI 迁移）依赖 Task 1 无关，但应在 Task 3 前（Task 3 需要确认 data 包的完整依赖图）
- Task 3（runtime 桥接拆分）依赖 Task 2（确认 data 包清理后的完整状态）
- Task 4（死依赖）独立，可穿插
- Task 5（errors 补齐）独立
- Task 6（最终验证）必须最后

### 风险点

1. **FeeModel → kernel 的 Order 类型引用**：Protocol 方法签名引用 `Order` from `ditto_portfolio`。使用 `from __future__ import annotations` 使其成为前向引用。basedpyright 在 strict 模式下可能报告未解析类型。如果报错，需将 `Order` dataclass 也迁入 kernel 或定义最小 Protocol 替代。

2. **trade.py 的 SQLiteClient → SQLitePool 切换**：`data/di/trade.py` 使用 `SQLiteClient`（data 包），迁移到 execution 后需切换为 `SQLitePool`（platform 包）。两者 API 可能不同，需确认行为一致。

3. **data/services/__init__.py re-export 移除的消费者影响**：外部代码可能通过 `from ditto_data.services import DerivedQueryService` 引用 features 的服务。需全量搜索并更新。

---

Plan complete. Use `superpowers:executing-plans` in the implementation session and execute one task at a time.
