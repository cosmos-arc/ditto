# Hybrid Plane v2 第二阶段迁移 — 实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 补全 Hybrid Plane V2 迁移遗留的结构性缺口——Analytics 补全、Engine 重组、datahub→data 完整迁移、App command + DomainEvent——使源码与设计目标完全对齐。

**Architecture:** 4 Wave 串行执行，每 Wave 独立可验证。Strangler 模式迁移，每个 PR 独立通过 `pixi run -e dev check` + `arch-check`。

**Tech Stack:** Python import 路径迁移、目录重命名、importlinter 规则维护、Dishka DI

---

## 背景与决策

基于 2026-04-02 源码级审计（审计报告见 `~/.claude/plans/typed-wishing-raven.md`），第一轮收尾（PR1-PR3）已完成配置路径修正 + shim 清理 + 文档同步。本轮解决结构性缺口：

| 决策 | 选择 | 理由 |
|------|------|------|
| datahub → data | 完整迁移 | 用户明确要求 |
| TradingOrchestrator | 无限期推迟 | EngineLoop 满足当前需求 |
| Analytics 补全 | 本轮迁移 | 减少 engine 职责过载 |
| Engine 小项 | 全部执行 | strategy→alpha + risk 提取 + command + DomainEvent |

---

## 执行波浪与依赖

```
Wave 1: Analytics补全 ──────────────────────────┐
  (6 PRs, engine/engine/ → analytics/)          │
                                                 │
Wave 2: Engine内部重组 ──── 依赖 Wave 1 ────────┤
  (3 PRs, alpha/risk/namespace)                  │
                                                 │
Wave 3: datahub → data ──── 独立 ───────────────┤
  (6 PRs, 包重命名 + 子域重组)                    │
                                                 │
Wave 4: App + 收尾 ──────── 依赖 Wave 1-3 ──────┘
  (5 PRs, command/DomainEvent/文档)
```

> Wave 1 和 Wave 3 操作不同文件，理论上可并行。但建议串行以控制风险。

---

## Wave 1: Analytics 补全

> 目标：将 engine/engine/ 下的 analytics 模块迁移至 analytics/ 包，消除 analytics → engine 依赖

### PR1: factors/ 迁移 `[L]`
- **操作**: `ditto_engine.engine.factors/` (6 文件: alpha, fundamental, primitives, spec, technical, __init__) → `ditto_analytics.factors/`
- **消费者**: 0 外部（仅 engine 内部 + 2 个测试）
- **Re-export shim**: `ditto_engine.engine.factors` re-export from `ditto_analytics.factors`
- **验收**:
  - `pixi run -e dev check` 通过
  - `ditto_analytics.factors` 含计算逻辑
  - `ditto_engine.engine.factors` 为 re-export shim
- **文件**:
  - `packages/analytics/src/ditto_analytics/factors/` (新建 6 文件)
  - `packages/core/src/ditto_engine/engine/factors/` (改为 shim)
  - `packages/core/tests/unit/engine/test_factors_*.py` (更新 import)

### PR2: evaluation/ 迁移 `[L]`
- **操作**: `ditto_engine.engine.evaluation/` (7 文件: evaluator, report, metrics/*) → `ditto_analytics.evaluation/`
- **消费者**: 3 外部
  - `ditto_app.query.evaluation` (evaluator, FactorEvaluationReport)
  - `ditto_app.process.materialization` (orthogonalize)
  - 1 interfaces 测试文件
- **Re-export shim**: `ditto_engine.engine.evaluation` re-export from `ditto_analytics.evaluation`
- **验收**:
  - `pixi run -e dev check` 通过
  - 3 个外部消费者更新 import（或通过 shim 兼容）
- **文件**:
  - `packages/analytics/src/ditto_analytics/evaluation/` (新建 7 文件)
  - `packages/core/src/ditto_engine/engine/evaluation/` (改为 shim)
  - `packages/app/src/ditto_app/query/evaluation.py` (更新 import)
  - `packages/app/src/ditto_app/process/materialization.py` (更新 import)

### PR3: research + publication_safety 迁移 `[M]`
- **操作**:
  - `ditto_engine.engine.research.py` → `ditto_analytics.research.domain.py` (领域逻辑)
  - `ditto_engine.engine.publication_safety.py` → `ditto_analytics.publication_safety.py`
- **消费者**:
  - research: 3 外部 (1 app, 2 interfaces 测试)
  - publication_safety: 6 外部 (1 app, 5 interfaces)
- **验收**:
  - `pixi run -e dev check` 通过
  - analytics 已有 `models/research.py`（元数据），新增 `research/domain.py`（领域逻辑）
- **文件**:
  - `packages/analytics/src/ditto_analytics/research/` (新建)
  - `packages/analytics/src/ditto_analytics/publication_safety.py` (新建)
  - `packages/core/src/ditto_engine/engine/research.py` (改为 shim)
  - `packages/core/src/ditto_engine/engine/publication_safety.py` (改为 shim)

### PR4: specs 清理 + analytics→engine 依赖断开 `[M]`
- **操作**:
  - 将 `validate_derived_spec()` 从 `ditto_engine.engine.specs` 移至 `ditto_kernel` 或 `ditto_analytics`
  - 更新 `compiler.py` (analytics) 不再依赖 engine
  - 清理 `ditto_engine.engine.specs` re-export shim
- **当前违规**: `ditto_analytics.expression.compiler` → `ditto_engine.engine.specs.validate_derived_spec`
- **消费者**: specs 18 外部消费者（1 analytics, 2 app, 10 interfaces, 5 datahub）
- **验收**:
  - analytics-no-datahub-import 规则 remove ignore_imports 中的 engine.specs 豁免
  - analytics 对 engine 零依赖
  - `pixi run -e dev check` + `arch-check` 通过
- **文件**:
  - `packages/analytics/src/ditto_analytics/expression/compiler.py` (更新 import)
  - `packages/kernel/src/ditto_kernel/specs.py` (可能新增 validate_derived_spec)
  - `.importlinter` analytics-no-datahub-import 规则 (移除 ignore)

### PR5: Re-export shim 清理 `[S]` ✅ DONE
- **操作**: 删除 Wave 1 PR1-PR3 创建的 re-export shim（engine/engine/factors, evaluation, research, publication_safety）
- **前提**: 所有消费者已直接从 analytics 导入
- **验收**:
  - ✅ `ditto_engine.engine.factors` 等目录完全删除
  - ✅ grep 零残留引用
  - ✅ arch-check 15 KEPT, 0 BROKEN
  - ✅ 2274 单元测试全部通过
- **文件**:
  - `packages/core/src/ditto_engine/engine/factors/` (已删除)
  - `packages/core/src/ditto_engine/engine/evaluation/` (已删除)
  - `packages/core/src/ditto_engine/engine/research.py` (已删除)
  - `packages/core/src/ditto_engine/engine/publication_safety.py` (已删除)
  - `packages/core/src/ditto_engine/engine/__init__.py` (已清理 re-export，仅保留 specs + errors)
  - 6 个测试文件 evaluation 导入迁移至 ditto_analytics.evaluation

### PR6: Wave 1 集成验证 `[S]` ✅ DONE
- **验收**:
  - ✅ `pixi run -e dev check` 通过（ruff lint: all passed, format: 1049 files formatted, basedpyright: 0 errors, 392 tests passed）
  - ✅ `pixi run -e dev arch-check` 全部 KEPT（15 kept, 0 broken）
  - ✅ analytics 对 engine 零依赖（pyproject.toml 无 ditto_engine 依赖，src 零 import）
  - ✅ `ditto_engine.engine/` 仅剩 specs.py shim + errors.py shim + __init__.py + README.md
  - ✅ 分支覆盖率 82.18%（≥ 80%）
  - ✅ grep 零残留引用（factors/evaluation/research/publication_safety 均无外部引用 engine/engine/ 旧路径）

---

## Wave 2: Engine 内部重组

> 前提: Wave 1 完成（analytics 模块已迁出 engine）

### PR7: strategy/ → alpha/ 重命名 `[L]` ✅ DONE
- **操作**: `ditto_engine.strategy/` (19 文件) 机械重命名为 `ditto_engine.alpha/`
- **消费者**: 9 外部
  - app: `builders/strategy.py`, `process/strategy.py`
  - interfaces: 7 个测试文件
- **方法**: 目录重命名 + 全局 import 更新（与 core→engine 重命名相同模式）
- **验收**:
  - `grep "from ditto_engine.strategy" --include="*.py"` 零结果
  - `ditto_engine.alpha/` 含全部 19 文件
  - `pixi run -e dev check` 通过
- **文件**:
  - `packages/core/src/ditto_engine/strategy/` → `packages/core/src/ditto_engine/alpha/`
  - `packages/core/src/ditto_engine/__init__.py` (更新 re-export)
  - `packages/app/src/ditto_app/builders/strategy.py` (更新 import)
  - `packages/app/src/ditto_app/process/strategy.py` (更新 import)
  - `packages/core/tests/unit/strategy/` → `packages/core/tests/unit/alpha/`
  - interfaces 测试文件 (7 个, 更新 import)

### PR8: risk/ 提取为顶层子域 `[M]` ✅ DONE
- **操作**: `ditto_engine.backtest.risk/` (4 文件) → `ditto_engine.risk/`
- **消费者**: 7 外部
  - app: `builders/strategy.py`, `process/strategy.py`
  - interfaces: 5 个测试文件
  - core 内部: `backtest/engine.py`, `backtest/audit/records.py`
- **验收**:
  - `ditto_engine.risk/` 为顶层子域，含 pre_trade.py, post_trade.py, _validation.py
  - `ditto_engine.backtest.risk/` 为 re-export shim（或直接引用新位置）
  - `pixi run -e dev check` 通过
- **文件**:
  - `packages/core/src/ditto_engine/risk/` (新建 4 文件)
  - `packages/core/src/ditto_engine/backtest/risk/` (改为 shim 或删除)
  - `packages/core/src/ditto_engine/backtest/engine.py` (更新 import)
  - `packages/app/src/ditto_app/builders/strategy.py` (更新 import)
  - `packages/app/src/ditto_app/process/strategy.py` (更新 import)

### PR9: engine/engine/ namespace 清理 `[M]` ✅ DONE
- **操作**:
  - Wave 1 完成后 `ditto_engine.engine/` 仅剩 specs.py shim + errors.py shim + __init__.py
  - 将 errors re-export 移至 `ditto_engine/errors.py`
  - 将 specs re-export 移至 `ditto_engine/specs.py`
  - 删除 `engine/engine/` 目录（如果已空）
- **消费者**: specs 18 外部, errors 多个外部
- **验收**:
  - `ditto_engine.engine/` 目录完全删除或仅保留必要的 specs.py
  - `from ditto_engine import DerivedSpec` 仍可用
  - `pixi run -e dev check` 通过
- **文件**:
  - `packages/core/src/ditto_engine/engine/` (清理/删除)
  - `packages/core/src/ditto_engine/__init__.py` (新增 re-export)
  - `packages/core/src/ditto_engine/specs.py` (新建 re-export)
  - `packages/core/src/ditto_engine/errors.py` (新建 re-export)

---

## Wave 3: datahub → data 完整迁移

> 目标：`ditto_data` (290+ 文件) → `ditto_data`，目标子域结构: models/sources/storage/query/quality/ingestion/

### PR10: 合并 data/ 内容到 datahub/ `[L]` ✅ DONE
- **操作**: 将 thin `packages/data/` 的独有内容并入 `packages/data/`
  - `data/quality/` → `data/quality/`（新增）
  - `data/provider.py` → `data/provider.py`（新增）
  - `data/models/ingestion.py` → `data/models/ingestion.py`（合并 5 个 Result model）
  - `data/errors.py` → `data/errors.py`（新增）
- **验收**:
  - ✅ `packages/data/`（旧 thin 包）已删除
  - ✅ data（原 datahub）包含 data 的所有功能（quality, errors, provider, ingestion models）
  - ✅ `pixi run -e dev check` 通过
- **文件**:
  - `packages/data/src/ditto_data/provider.py` (新增)
  - `packages/data/src/ditto_data/quality/` (合并)
  - `packages/data/src/ditto_data/` (迁移后删除)
  - `packages/core/src/ditto_engine/backtest/data_feed.py` (更新 import: ditto_data → ditto_data)
  - `packages/core/src/ditto_engine/engine/errors.py` (更新 import: ditto_data → ditto_data)
  - `pixi.toml` (移除 ditto-data 依赖)
  - `.importlinter` (移除 data-boundary, data 相关引用)

### PR11: 包级重命名 ditto_datahub → ditto_data `[XL]` ✅ DONE
- **操作**（与 PR10 合并执行）:
  1. 合并 data 内容到 datahub
  2. 删除旧 packages/data/
  3. 重命名 packages/datahub/ → packages/data/
  4. pyproject.toml: `name = "ditto-datahub"` → `name = "ditto-data"`
  5. src 目录: `ditto_datahub/` → `ditto_data/`
  6. 全局 import 更新: `ditto_datahub` → `ditto_data`（~250 文件）
  7. pixi.toml 更新（移除 ditto-datahub 条目）
  8. .importlinter 重写（去重、去 "datahub" 命名）
  9. 所有 CLAUDE.md + docs 更新
- **验收**:
  - ✅ `grep "ditto_datahub" --include="*.py" -r` 零结果
  - ✅ `grep "ditto_datahub" --include="*.toml" -r` 零结果
  - ✅ `pixi run -e dev check` 通过（lint + fmt + type + 4271 tests）
  - ✅ `pixi run -e dev arch-check` 15 KEPT, 0 BROKEN
- **文件**:
  - `packages/data/` → `packages/data/` (物理重命名)
  - `packages/data/pyproject.toml` (更新 name)
  - `packages/data/src/ditto_data/` (重命名 namespace 目录)
  - `pixi.toml` (ditto-datahub → ditto-data)
  - `.importlinter` (全部 datahub → data)
  - `CLAUDE.md` + 各子包 CLAUDE.md (更新)
  - ~85 个 .py 文件 (import 更新)

### PR12: 子域重命名 stores/ → storage/ `[L]`
- **操作**: `ditto_data.stores/` (159 文件) → `ditto_data.storage/`
- **方法**: 目录重命名 + 全局 import 更新
- **验收**:
  - `grep "from ditto_data.stores" --include="*.py"` 零结果
  - `pixi run -e dev check` 通过
- **文件**:
  - `packages/data/src/ditto_data/stores/` → `packages/data/src/ditto_data/storage/`
  - 所有引用 stores 的文件 (storage 内部 + services + app + interfaces registry)

### PR13: services 拆分 query/ + ingestion/ 基础 `[L]`
- **操作**:
  - `ditto_data.services/` (41 文件) → 按职责拆分
  - 查询类服务 (MarketService, MetadataService, DerivedQueryService 等) → 保留在 `services/` 或移入 `query/`
  - 写入类服务 (IngestionLogService, FreezeService 等) → 移入 `ingestion/`
  - 保留 `services/` 作为公共 facade
- **验收**:
  - `ditto_data.query/` 提供消费者查询入口
  - `ditto_data.ingestion/` 提供写入/编排逻辑
  - `pixi run -e dev check` 通过
- **文件**:
  - `packages/data/src/ditto_data/query/` (新建/扩展)
  - `packages/data/src/ditto_data/ingestion/` (新建)
  - `packages/data/src/ditto_data/services/` (瘦身/重组)
  - app + interfaces 消费者 (更新 import)

### PR14: helpers/runtime/config 归位 `[M]`
- **操作**:
  - `helpers/` (6 文件: pit/, adjustment.py) → 归入 `ditto_data.helpers/` 或分发至 `storage/`, `query/`
  - `runtime/` (4 文件: FreezeManager, InstrumentIdAllocator, SqlEngine) → 评估是否归入 infra 或保留
  - `config/` (4 文件: DataSourceSettings, DataStoreSettings) → 评估是否归入 infra
- **验收**:
  - 每个子域有明确职责
  - 无孤立目录
- **文件**:
  - `packages/data/src/ditto_data/helpers/` (重组)
  - `packages/data/src/ditto_data/runtime/` (重组)
  - `packages/data/src/ditto_data/config/` (评估)

### PR15: interfaces → data 依赖隔离 `[L]`
- **操作**:
  - 逐步将 interfaces 的 datahub 直接依赖改为通过 app 层代理
  - cli/commands/query/ 下的服务调用改为通过 app.query
  - api/routes/ 改为通过 app.query
  - models/ 中的 data model 引用改为本地定义或 kernel 定义
- **验收**:
  - importlinter `port-boundary` 规则收紧: `ditto_interfaces.**` 禁止导入 `ditto_data.services.**`, `ditto_data.models.**`
  - 保留 `ditto_interfaces.registry.**` 的豁免（DI Composition Root）
  - `pixi run -e dev arch-check` 全部 KEPT
- **文件**:
  - `apps/interfaces/src/ditto_interfaces/cli/commands/query/*.py` (重构)
  - `apps/interfaces/src/ditto_interfaces/api/routes/*.py` (重构)
  - `apps/interfaces/src/ditto_interfaces/models/*.py` (重构)
  - `apps/interfaces/src/ditto_interfaces/jobs/flows/*.py` (重构)
  - `packages/app/src/ditto_app/query/` (扩展 facade)
  - `.importlinter` port-boundary (收紧规则)

---

## Wave 4: App + DomainEvent + 收尾

> 前提: Wave 1-3 完成

### PR16: App command/ 模块创建 `[M]`
- **操作**:
  - 创建 `packages/app/src/ditto_app/command/`
  - 从 `process/` 中提取单次写入操作（ingestion trigger, strategy create 等）
  - 定义 Command 基类和 handler 模式
- **设计参考**: CQRS Command pattern — 单次写入，有明确输入/输出
- **验收**:
  - `ditto_app.command/` 包含 3-5 个 command handler
  - `pixi run -e dev check` 通过
- **文件**:
  - `packages/app/src/ditto_app/command/__init__.py` (新建)
  - `packages/app/src/ditto_app/command/ingestion.py` (从 process 提取)
  - `packages/app/src/ditto_app/command/strategy.py` (从 process 提取)

### PR17: DomainEvent 子类定义 `[M]`
- **操作**:
  - engine: 定义 `OrderSubmitted`, `OrderFilled`, `OrderCanceled`, `PositionChanged`, `RiskGuardTriggered`
  - data: 定义 `DataIngested`, `QualityCheckCompleted`
  - 所有子类继承 `kernel.DomainEvent`
  - 在相关流程中集成事件发布（如果合理）
- **验收**:
  - 各子类为 frozen dataclass，有类型安全的 payload
  - 单元测试覆盖
  - `pixi run -e dev check` 通过
- **文件**:
  - `packages/core/src/ditto_engine/events.py` (新建)
  - `packages/data/src/ditto_data/events.py` (新建)
  - `packages/kernel/src/ditto_kernel/events.py` (已存在基类)
  - 对应测试文件

### PR18: R8 互斥规则补全 + importlinter 终态 `[M]`
- **操作**:
  - 新增 `r8-query-no-command`: app.query 禁止导入 app.command
  - 新增 `r8-command-no-query`: app.command 禁止导入 app.query
  - 新增 `r8-command-no-builders`: app.command 禁止导入 app.builders
  - 更新所有规则中的 datahub → data
  - 移除不再需要的 ignore_imports
  - 合约命名更新（core- → engine-）
- **目标终态规则**:
  ```
  layered-architecture: interfaces → app → engine → data → infra
  kernel-isolation: kernel 不依赖任何包
  foundation-isolation: infra 不依赖任何包
  data-boundary: data 不依赖 engine/interfaces/app
  analytics-isolation: analytics 不依赖 data/engine/app/interfaces
  engine-isolation: engine 不依赖 data/app/interfaces
  engine-no-data-import: engine 不直接导入 data（除 re-export）
  data-internal-storage-no-model: storage 不直接导入 models
  data-internal-sources-no-storage: sources 不导入 storage
  port-boundary: interfaces 非 registry 不导入 data.services/models/storage/runtime
  app-mutual-exclusion: R8 矩阵完整
  acyclic-packages: 无循环依赖
  ```
- **验收**:
  - `pixi run -e dev arch-check` 全部 KEPT
  - 无 ignore_imports（或仅有明确文档化的豁免）
- **文件**:
  - `.importlinter` (全面重写)

### PR19: 文档全面更新 `[L]`
- **操作**:
  - `CLAUDE.md` 依赖层级图更新
  - `.claude/rules/architecture.md` 全面更新（datahub → data, port → interfaces）
  - 各子包 CLAUDE.md 更新
  - 设计文档标注实际完成状态
  - `docs/plans/2026-03-30-architecture-hybrid-plane-design.md` 标注偏差（TradingOrchestrator 推迟等）
- **验收**: 所有文档反映源码实际状态

### PR20: 最终集成验证 `[S]`
- **验收**:
  - `pixi run -e dev ci` 通过
  - `pixi run -e dev arch-check` 全部 KEPT（目标 15+ 条规则）
  - 分支覆盖率 ≥ 80%
  - `grep "ditto_data" --include="*.py" -r` 零结果
  - `grep "ditto_core" --include="*.py" -r` 零结果
  - `grep "AnyFrame" --include="*.py" -r` 零结果
  - analytics 对 engine 零依赖（或仅有 specs 豁免）
  - engine 内部结构: alpha/, risk/, accounting/, backtest/, execution/, portfolio/（无 strategy/, 无 engine/engine/ 嵌套）

---

## 风险与缓解

| # | 风险 | 概率 | 影响 | 缓解 |
|---|------|------|------|------|
| R1 | PR11 包重命名引入遗漏 | 高 | 高 | 自动化 sed + `grep` 零残留验证 |
| R2 | services 拆分破坏现有功能 | 中 | 高 | Re-export shim 兼容 + 测试覆盖 |
| R3 | interfaces 依赖隔离工作量超预期 | 高 | 中 | 分批处理，保留 registry 豁免 |
| R4 | engine/engine/ namespace 清理引入 breaking change | 中 | 中 | Re-export shim 过渡 |
| R5 | Wave 1 analytics 迁移导致测试失败 | 低 | 中 | 每个 PR 独立验证 |

---

## 任务汇总

| Wave | PR | 内容 | 复杂度 | 关键风险 |
|------|-----|------|--------|---------|
| 1 | PR1 | factors/ → analytics | L | 0 外部消费者，低风险 |
| 1 | PR2 | evaluation/ → analytics | L | 3 外部消费者 |
| 1 | PR3 | research + publication_safety → analytics | M | 9 外部消费者 |
| 1 | PR4 | specs 清理 + analytics→engine 断开 | M | 18 specs 消费者 |
| 1 | PR5 | Re-export shim 清理 | S | 需确认消费者已迁移 |
| 1 | PR6 | Wave 1 集成验证 | S | — |
| 2 | PR7 | strategy → alpha 重命名 | L | 9 外部消费者 |
| 2 | PR8 | risk 提取为顶层 | M | 7 外部消费者 |
| 2 | PR9 | engine/engine/ namespace 清理 | M | 18 specs + errors 消费者 |
| 3 | PR10 | 合并 data → datahub | L | ✅ DONE（与 PR11 合并执行） |
| 3 | PR11 | 包级重命名 datahub → data | XL | ✅ DONE（4271 tests, 15 KEPT） |
| 3 | PR12 | stores → storage 重命名 | L | 159 文件内部引用 |
| 3 | PR13 | services 拆分 query/ + ingestion/ | L | 需 re-export shim |
| 3 | PR14 | helpers/runtime/config 归位 | M | 评估依赖 |
| 3 | PR15 | interfaces → data 依赖隔离 | L | 工作量可能超预期 |
| 4 | PR16 | App command 模块 | M | 新模块，无 breaking change |
| 4 | PR17 | DomainEvent 子类 | M | 新功能，增量添加 |
| 4 | PR18 | importlinter 终态 | M | 规则收紧可能暴露违规 |
| 4 | PR19 | 文档全面更新 | L | 多文件同步 |
| 4 | PR20 | 最终集成验证 | S | — |
| **总计** | **20 PR** | | **2XL + 7L + 8M + 3S** | |

---

## 验证命令速查

```bash
# 每个 PR 后
pixi run -e dev check          # lint + fmt + type + test --fast
pixi run -e dev arch-check     # 架构约束检查

# PR11 包重命名后
grep "ditto_data" --include="*.py" -r .  # 零结果
grep "ditto_data" --include="*.toml" -r . # 零结果

# PR7 alpha 重命名后
grep "from ditto_engine.strategy" --include="*.py" -r . # 零结果

# 最终验证
pixi run -e dev ci             # CI 完整检查
```
