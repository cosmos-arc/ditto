---
date: 2026-04-01
plan_type: refactor
status: active
origin: docs/plans/2026-03-31-hybrid-plane-v2-migration-plan.md (Phase 4)
depth: deep
---

# Phase 4: Application 层提炼 — 设计文档

**目标**：将 `apps/port/services/` 中的业务编排逻辑提取为独立的 `packages/app/`，实现 Query/Command/Process 互斥分离，重构 DI 容器，最终 `port` → `interfaces` 重命名。

**源文档**：[hybrid-plane-v2-migration-plan.md](2026-03-31-hybrid-plane-v2-migration-plan.md)
**需求文档**：[refined-requirements.md](../brainstorms/2026-03-31-hybrid-plane-v2-refined-requirements.md)

---

## 当前进度

> **审计日期**：2026-04-01 | **前置 Phase**：0.5 ✅ 1 ✅ 2 ✅ 3 ✅

| Unit | 状态 | 验证 |
|------|------|------|
| 4a-1 | ⏳ 待实施 | 创建 app 包 + 迁移 Query 服务 |
| 4a-2 | ⏳ 待实施 | 迁移 Process 服务 + Builders |
| 4b | ⏳ 待实施 | DI 容器重构（AppProvider） |
| 4c | ⏳ 待实施 | R8 互斥规则（importlinter） |
| 4d | ⏳ 待实施 | port → interfaces 重命名 |
| 4e | ⏳ 待实施 | 旧路径清理 + importlinter 全量 |

---

## 需求追溯

| 需求 | 内容 | 本 Phase 覆盖 |
|------|------|-------------|
| R4 | `packages/app/` 作为业务包（Use Case 编排） | 4a |
| R6 | 依赖矩阵 `interfaces → app → data, engine, analytics` | 4b + 4d |
| R8 | app 内部互斥（Query/Command/Process/builders） | 4c |
| R12 | AnyFrame 消除（beartype runtime check） | 推迟到 Phase 5 |
| R34 | analytics 纯计算包 | 已在 Phase 2-3 完成 |
| S7 | 每个 Phase 的回归测试策略 | 每个 PR 都 `pixi run -e dev check` |

---

## 设计决策

### D1: 实施顺序 — 先 app 提取，再重命名

**选择**：先创建 `packages/app/` + 迁移服务（4a/c），再 DI 重构（4b），最后 port→interfaces（4d/e）。

**理由**：app 包稳定后再动重命名，减少每 PR 的认知负担。重命名 PR 范围大，应放在最后。

### D2: app 内部结构 — 扁平模块

**选择**：`app/query/`、`app/command/`、`app/process/`、`app/builders/` 各为目录，内部为扁平模块文件。

**理由**：R8 互斥规则通过模块级 importlinter 检查（`app.query` -X-> `app.command`），目录级边界使检查简单可靠。

### D3: DI 策略 — app 自定义 Provider

**选择**：`packages/app/` 定义自己的 Dishka Provider 工厂函数 `get_app_providers()`，`interfaces/` 的 Composition Root 组装时引用。

**理由**：R6 要求 `interfaces → app → data/engine/analytics`。app Provider 只 import 下层具体类，不 import interfaces。app 包不持有 Container 实例。

---

## 架构设计

### 目标结构

```
packages/app/
├── pyproject.toml                          # ditto_app
├── src/ditto_app/
│   ├── __init__.py                         # version + 公共 API
│   ├── py.typed
│   ├── query/                              # Query 角色 — 只读，零副作用
│   │   ├── __init__.py
│   │   ├── derived.py                      # ← port.services.derived.query_facade
│   │   ├── evaluation.py                   # ← port.services.derived.evaluation_facade
│   │   └── research.py                     # ← port.services.derived.research
│   ├── command/                            # Command 角色 — 单次写（暂空，YAGNI）
│   │   └── __init__.py
│   ├── process/                            # Process 角色 — 编排协调
│   │   ├── __init__.py
│   │   ├── ingestion.py                    # ← port.services.ingestion.coordinator + backfill + data_writer + metadata + quality + result_handler + retry + factory + index_config + list_date_inference + result_utils + errors + config
│   │   ├── strategy.py                     # ← port.services.strategy.facade + backtest_service + strategy_run_service + lifecycle + artifact_writer + market_data_feed + input_assembler
│   │   └── materialization.py              # ← port.services.derived.materialization + materialization_orchestrator + publication + publication_rules + cascade_protocol + dq_summary + manifest_builder + input_preparation + runtime_input + factor_orthogonalization_service + _utils
│   ├── builders/                           # Builder 角色 — 装配，不查询不写入
│   │   ├── __init__.py
│   │   └── strategy.py                     # ← port.services.strategy.factory + runtime_builder + backtest_runtime_builder + slice_builder
│   └── providers.py                        # Dishka Provider 工厂
└── tests/
    ├── unit/
    └── integration/
```

### R8 互斥矩阵

```text
app.query     -X-> app.command, app.process, app.builders    # 只读，不得触发写
app.command   -X-> app.query, app.process                    # 单次写，不得查询或编排
app.process   ->  app.query, app.command                     # 允许协调
app.builders  -X-> app.query, app.command                    # 只装配，不查询不写入
```

### 依赖关系

```text
interfaces (apps/) → app (packages/) → data, engine, analytics, kernel, infra
```

**app 包的依赖**：

| 下游包 | 使用方式 | 限制 |
|--------|---------|------|
| `ditto_kernel` | Protocol 类型（Clock, DataProvider, EventBus） | 仅类型引用 |
| `ditto_engine` | BacktestEngine, FactorEvaluator, ResearchDataset | 实例化 + 调用 |
| `ditto_analytics` | CompileCache, ResearchModels | 实例化 + 调用 |
| `ditto_datahub` | Services（MetadataService, MarketService, ...） | 实例化 + 调用 |
| `ditto_infra` | logger, Settings | 仅工具 |
| `ditto_data` | QualityService, Errors | 实例化 + 调用 |

**app 包禁止依赖**：
- `ditto_port` / `ditto_interfaces` — 防止循环

---

## 服务角色分类

### app/query/ — 只读查询

| 模块 | 源文件 | 依赖 | 说明 |
|------|--------|------|------|
| `derived.py` | `services/derived/query_facade.py` | datahub.DerivedQueryService, port.models.derived | 衍生数据统一查询 |
| `evaluation.py` | `services/derived/evaluation_facade.py` | engine.FactorEvaluator, datahub.ForwardReturnService | 因子评估 |
| `research.py` | `services/derived/research.py` | engine.ResearchDataset, datahub.ResearchCatalogService | 研究数据集快照 |

**注意**：`query_facade.py` 依赖 `ditto_port.models.derived`（Pydantic 请求/响应模型）。这些模型是 port 层的 API contract，不应迁入 app。解决方案：
- **方案 A**：`derived.py` 不再直接返回 `DerivedLatestResult` 等类型，改为返回 data 层原生类型，由 interfaces 层做转换。
- **方案 B**：将 Pydantic 模型也迁入 app 层，interfaces 层 re-export。
- **决策**：采用 **方案 A**（最小变更）— `app/query/derived.py` 返回 data 层原生类型（`pl.DataFrame`），interfaces 的 API 路由层负责转换为 Pydantic 响应。需要评估影响范围。

### app/process/ — 编排协调

| 模块 | 源文件 | 依赖 | 说明 |
|------|--------|------|------|
| `ingestion.py` | `services/ingestion/*.py` (13 文件) | datahub.*Services, datahub.Sources, port.errors, port.models | 数据摄取编排 |
| `strategy.py` | `services/strategy/*.py` (8 文件) | engine.BacktestEngine, datahub.*Services | 策略运行编排 |
| `materialization.py` | `services/derived/*.py` (12 文件) | analytics.CompileCache, datahub.*Services | 衍生物化编排 |

**ingestion 的特殊性**：
- `IngestionCoordinator` 不通过 DI 提供，而是通过 `create_coordinator()` 工厂函数创建（contextmanager）
- 依赖 `ditto_port.errors` 和 `ditto_port.models` — 这些需要提取或解耦

**materialization 的拆分**：
- `query_facade.py` → `app/query/derived.py`（Query）
- `evaluation_facade.py` → `app/query/evaluation.py`（Query）
- `research.py` → `app/query/research.py`（Query）
- 其余 12 个文件 → `app/process/materialization.py`（Process）

### app/builders/ — 装配

| 模块 | 源文件 | 依赖 | 说明 |
|------|--------|------|------|
| `strategy.py` | `services/strategy/factory.py` + `runtime_builder.py` + `backtest_runtime_builder.py` + `slice_builder.py` | datahub.*Services, engine.* | 策略运行时装配 |

---

## DI 容器重构

### 当前状态

```text
apps/port/registry/
├── container.py        # Composition Root（14 Provider）
├── infra/              # 3 Provider（Config, Observability, Notification）
├── core/               # 2 Provider（Quality, GoldenDataset）
├── datahub/            # 8 Provider（Sources, Runtime, Metadata, Market, Fundamental, Capital, Macro, Derived）
├── port/               # 1 Provider（Strategy）
└── contexts/
    ├── bundle.py       # IngestionBundle, MaterializationBundle, StrategyBundle
    └── ...
```

**问题**：
1. `DerivedProvider`（datahub 层）注册了 `DerivedQueryFacade`、`ResearchDatasetFacade` 等 app 层服务
2. `StrategyProvider`（port 层）注册了 app 层的 Builder 服务
3. `IngestionBundle` 混合了 data 层类型（MetadataService 等）和 app 层类型（IngestionCoordinator）

### 目标状态

```text
packages/app/src/ditto_app/
└── providers.py        # AppProvider — 注册 app 层 Use Case 服务

apps/port/registry/     # → apps/interfaces/registry/（Phase 4d）
├── container.py        # Composition Root — 引用 get_app_providers()
├── infra/              # 保持不变（3 Provider）
├── datahub/            # DerivedProvider 拆分：只留 data 层服务
├── core/               # 保持不变（2 Provider）
├── port/               # 删除 StrategyProvider（已迁入 AppProvider）
└── contexts/
    ├── bundle.py       # Bundle 只持有 app 层类型
    └── ...
```

### `app/providers.py` 设计

```python
"""App 层 Dishka Provider 工厂."""

from dishka import Provider


def get_app_providers() -> list[Provider]:
    """返回 App 层所有 Provider.

    依赖：datahub.*Services, engine.*, analytics.*, kernel.*
    被依赖：interfaces/ 的 Composition Root
    """
    return [
        StrategyProvider(),       # ← 从 port/registry/port/strategy.py 迁入
        QueryFacadeProvider(),    # ← 从 datahub/registry/datahub/derived.py 拆分（Query 部分）
        ProcessProvider(),        # ← 从 datahub/registry/datahub/derived.py 拆分（Process 部分）
        IngestionProvider(),      # ← 新增：包装 create_coordinator 工厂
    ]
```

### DerivedProvider 拆分

当前 `DerivedProvider`（`registry/datahub/derived.py`）混合了：

| 方法 | 归属 | 迁移目标 |
|------|------|---------|
| `runtime_mode_resolver` | app | AppProvider |
| `research_artifact_service` | datahub | 保留 DerivedProvider |
| `derived_query_service` | datahub | 保留 DerivedProvider |
| `compile_cache_service` | analytics/datahub | 保留 DerivedProvider |
| `derived_input_provider` | datahub | 保留 DerivedProvider |
| `derived_materialization_orchestrator` | app | AppProvider |
| `derived_invalidation_orchestrator` | app | AppProvider |
| `derived_query_facade` | app | AppProvider |
| `research_dataset_facade` | app | AppProvider |
| `derived_publication_facade` | app | AppProvider |

### Bundle 模式变化

```python
# 旧：IngestionBundle 持有 9 个 data 层类型 + 1 个 app 层类型
@dataclass(frozen=True)
class IngestionBundle:
    metadata_service: MetadataService        # data 层
    market_service: MarketService            # data 层
    ...
    coordinator: IngestionCoordinator        # app 层

# 新：IngestionBundle 只持有 app 层类型
@dataclass(frozen=True)
class IngestionBundle:
    coordinator: IngestionCoordinator        # app 层
    backfill_manager: BackfillManager        # app 层
```

**代价**：CLI/Prefect 代码中直接使用 `bundle.metadata_service` 的地方需要改为通过 app 层服务间接访问，或改为独立获取 metadata_service。

---

## importlinter 规则演进

### Phase 4a 后新增

```ini
# root_modules 新增 ditto_app
root_modules = ditto_infra ditto_kernel ditto_datahub ditto_data ditto_analytics ditto_engine ditto_port ditto_app

# R8: app 内部互斥
[importlinter:contract:app-query-isolation]
name = App Query must not import Command or Process
type = forbidden
source_modules = ditto_app.query
forbidden_modules = ditto_app.command, ditto_app.process

[importlinter:contract:app-command-isolation]
name = App Command must not import Query or Process
type = forbidden
source_modules = ditto_app.command
forbidden_modules = ditto_app.query, ditto_app.process

[importlinter:contract:app-builders-isolation]
name = App Builders must not import Query or Command
type = forbidden
source_modules = ditto_app.builders
forbidden_modules = ditto_app.query, ditto_app.command

# R7: app 禁止依赖 port
[importlinter:contract:app-no-port-import]
name = App must not import Port layer
type = forbidden
source_modules = ditto_app
forbidden_modules = ditto_port
```

### Phase 4d 后更新

```ini
# root_modules: ditto_port → ditto_interfaces
root_modules = ditto_infra ditto_kernel ditto_datahub ditto_data ditto_analytics ditto_engine ditto_interfaces ditto_app

# 更新所有 ditto_port 引用为 ditto_interfaces
[importlinter:contract:app-no-port-import]
forbidden_modules = ditto_interfaces
```

### Phase 4e 最终全量

```ini
# R6: interfaces 依赖矩阵
[importlinter:contract:interfaces-depends-only-on-app]
name = Interfaces must only depend on App (then lower layers)
type = layers
layers = ditto_interfaces
  ditto_app
  ditto_engine
  ditto_analytics
  ditto_datahub
  ditto_data
  ditto_kernel
  ditto_infra
```

---

## 已识别风险

| # | 风险 | 概率 | 影响 | 缓解 |
|---|------|------|------|------|
| K1 | `services/derived/` 文件间存在交叉引用 | 高 | 中 | 先理清依赖图，按拓扑序迁移 |
| K2 | `query_facade.py` 依赖 `port.models.derived` Pydantic 模型 | 高 | 中 | 采用方案 A：app 层返回 data 原生类型，interfaces 转换 |
| K3 | `IngestionCoordinator` 依赖 `port.errors` / `port.models` | 中 | 中 | 将 port.errors 中的通用错误类型提取到 data 层或 kernel 层 |
| K4 | `create_coordinator()` 工厂模式与 DI 不兼容 | 中 | 低 | Phase 4b 统一改为 DI Provider |
| K5 | Bundle 模式变化影响 CLI/Prefect 调用方式 | 中 | 中 | 分批更新调用点，保持接口兼容 |
| K6 | 测试文件引用 `ditto_port.services.*` | 高 | 低 | Strangler re-export shim 过渡 |

---

## PR 拆分计划

### PR 1 (4a-1): 创建 app 包 + 迁移 Query 服务

**目标**：最小化起步 — 创建 `packages/app/`，迁入 3 个 Query 服务，验证架构可行。

| 操作 | 文件 | 变更 |
|------|------|------|
| CREATE | `packages/app/pyproject.toml` | ditto_app 包声明 |
| CREATE | `packages/app/src/ditto_app/__init__.py` | version + 公共 API |
| CREATE | `packages/app/src/ditto_app/py.typed` | PEP 561 |
| CREATE | `packages/app/src/ditto_app/query/__init__.py` | query 模块 |
| MOVE | `services/derived/query_facade.py` → `app/query/derived.py` | 移除 port.models 依赖 |
| MOVE | `services/derived/evaluation_facade.py` → `app/query/evaluation.py` | 直接移动 |
| MOVE | `services/derived/research.py` + `_utils.py` → `app/query/research.py` | 合并 _utils |
| EDIT | `services/derived/__init__.py` | re-export shim → `from ditto_app.query import *` |
| EDIT | `.importlinter` | 新增 ditto_app root_module + app-query-isolation + app-no-port-import |
| EDIT | `pixi.toml` | 注册 ditto_app 到 dev 环境 |

**验证**：
- [ ] `pixi run -e dev check` 全通过
- [ ] `pixi run -e dev arch-check` 全通过（含新规则）
- [ ] `grep -rn "from ditto_port.services.derived.query_facade\|from ditto_port.services.derived.evaluation_facade\|from ditto_port.services.derived.research" packages/ apps/ --include="*.py"` 仅剩 re-export shim

### PR 2 (4a-2 + 4c): 迁移 Process 服务 + Builders + R8 全量规则

**目标**：完成 app 包核心内容，R8 互斥规则全量落地。

| 操作 | 文件 | 变更 |
|------|------|------|
| CREATE | `app/process/__init__.py` | process 模块 |
| CREATE | `app/process/ingestion.py` | ← `services/ingestion/*.py`（13 文件合并或子模块化） |
| CREATE | `app/process/strategy.py` | ← `services/strategy/`（8 个核心文件） |
| CREATE | `app/process/materialization.py` | ← `services/derived/`（12 个 Process 文件） |
| CREATE | `app/builders/__init__.py` | builders 模块 |
| CREATE | `app/builders/strategy.py` | ← `services/strategy/`（4 个 Builder 文件） |
| EDIT | `services/` 各 `__init__.py` | re-export shim |
| EDIT | `.importlinter` | 全部 R8 规则 |

**验证**：
- [ ] `pixi run -e dev check` 全通过
- [ ] `pixi run -e dev arch-check` 全通过（含全部 R8 规则）
- [ ] `grep -rn "from ditto_port.services" apps/ --include="*.py"` 仅剩 re-export shim + api/cli/jobs 调用点

### PR 3 (4b): DI 重构 — AppProvider 提取

**目标**：将 app 层 DI Provider 从 port/datahub 中提取到 app 包。

| 操作 | 文件 | 变更 |
|------|------|------|
| CREATE | `app/providers.py` | AppProvider 定义 |
| EDIT | `registry/container.py` | `_get_base_providers()` 引用 `get_app_providers()` |
| EDIT | `registry/datahub/derived.py` | 移除 app 层服务的 provide 方法 |
| DELETE | `registry/port/strategy.py` | 迁入 AppProvider |
| EDIT | `registry/contexts/bundle.py` | Bundle 只持有 app 层类型 |
| EDIT | `registry/port/__init__.py` | 移除 StrategyProvider |

**验证**：
- [ ] `pixi run -e dev check` 全通过
- [ ] DI 解析无错误：FastAPI 启动 + CLI smoke test
- [ ] `grep -rn "from ditto_port.services" apps/port/registry/ --include="*.py"` 返回 0（registry 不再引用 services）

### PR 4 (4d): port → interfaces 重命名

**目标**：将 `apps/port/` 重命名为 `apps/interfaces/`，全库引用更新。

| 操作 | 文件 | 变更 |
|------|------|------|
| RENAME | `apps/port/` → `apps/interfaces/` | 目录重命名 |
| EDIT | `apps/interfaces/pyproject.toml` | `ditto_port` → `ditto_interfaces` |
| EDIT | 全库 `.py` 文件 | `ditto_port` → `ditto_interfaces` |
| EDIT | `.importlinter` | root_modules + contract 中包名更新 |
| EDIT | `CLAUDE.md` | 文档更新 |

**验证**：
- [ ] `pixi run -e dev check` 全通过
- [ ] `grep -rn "ditto_port" packages/ apps/ --include="*.py"` 返回 0

### PR 5 (4e): 清理 + importlinter 全量

**目标**：删除所有 re-export shim，importlinter 规则校准，最终验证。

| 操作 | 文件 | 变更 |
|------|------|------|
| DELETE | `services/` 下的 re-export shim | 清理 |
| EDIT | `.importlinter` | 全量规则校准 + 移除 ignore_imports |
| EDIT | `CLAUDE.md` + 各包 `CLAUDE.md` | 文档同步 |
| VERIFY | `pixi run -e dev ci` | CI 全通过 |

**验证**：
- [ ] `pixi run -e dev ci` 全通过
- [ ] `pixi run -e dev arch-check` 全部 contract 通过
- [ ] `grep -rn "from ditto_port\|from ditto_interfaces.services" packages/ apps/ --include="*.py"` 返回 0
- [ ] 文档反映最终架构

---

## 参考文档

- 源文档：[hybrid-plane-v2-migration-plan.md](2026-03-31-hybrid-plane-v2-migration-plan.md)
- 需求文档：[refined-requirements.md](../brainstorms/2026-03-31-hybrid-plane-v2-refined-requirements.md)
- v2 设计：[architecture-hybrid-plane-design.md](2026-03-30-architecture-hybrid-plane-design.md)
