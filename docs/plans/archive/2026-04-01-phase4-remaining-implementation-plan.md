---
date: 2026-04-01
plan_type: refactor
status: completed
origin: docs/plans/2026-04-01-phase4-app-layer-design.md (修订版)
depth: deep
---

# Phase 4 剩余工作 — 实施计划

**目标**：补完 Phase 4 所有剩余 PR，实现 `port/services/` 编排逻辑完全迁入 `packages/app/`。

**前置状态**：

| PR | 状态 | 备注 |
|----|------|------|
| PR1 (4a-1) | ✅ | app 包创建 + Query 服务迁移 |
| PR2 (4a-2) | ⚠️ 85% | Process(derived/strategy) + Builders 已迁入，**ingestion 未迁入** |
| PR3 (4b) | ❌ | DI 重构 |
| PR4 (4d) | ❌ | port→interfaces 重命名 |
| PR5 (4e) | ❌ | 清理 |

**实施进度**：

| PR | 状态 | 验证 |
|----|------|------|
| PR-A (模型/错误/配置提取) | ✅ 完成 | 4264 tests, 19 contracts |
| PR-B (Ingestion + Quality 迁入 app) | ✅ 完成 | 4264 tests, 19 contracts |
| PR-C (DI 重构 — AppProvider) | ✅ 完成 | 4273 tests, 19 contracts |
| PR-D (port → interfaces 重命名) | ✅ 完成 | 4273 tests, 19 contracts |
| PR-E (清理 + 最终验证) | ✅ 完成 | 4272 tests, 19 contracts |

**修订策略**：原计划 PR2 跳过 ingestion（因依赖 `port.models`/`port.errors`），现补为完整迁移方案。

---

## 技术方案

### D0: 模型/错误提取 — 前置解耦

**选择**：将 `port.models.ingestion`（5 个类型）、`port.errors`（DataSourceError 子树）、`port.models.config`（12 个类型）提取到下层包。

**理由**：这些类型是数据操作的结果/配置/错误定义，不是 port 层的 API contract。提取后 app 层可直接引用，无需依赖 port。

**依赖变更**：

```text
提取前: app.process ←X (blocked) ← port.models.ingestion, port.errors
提取后: app.process → ditto_data.models.ingestion, ditto_data.errors

提取前: ingestion config → port.models.config
提取后: ingestion config → ditto_app.config (同层引用)
```

### D1: QualityService 归属

**选择**：QualityService/L3BatchService/QualityReconciliationService 迁入 `app/process/quality.py`。

**理由**：三个服务**零 port 依赖**（仅依赖 `ditto_data.quality` + `ditto_data.services`），是纯编排逻辑。放在 app 层符合 R8 Process 角色定义。

### D2: ingestion 合并策略

**选择**：14 个文件合并为 `app/process/ingestion.py`（~3400 LOC），与 materialization.py（3009 LOC）保持一致。

**理由**：设计文档 D2 要求"扁平模块文件"，已有 precedent。

---

## PR 拆分

### PR-A: 模型/错误/配置提取（前置） `[L]`

**目标**：解除 ingestion 对 port 层的模型/错误依赖，为 PR-B 迁移铺路。

#### A1: 扩展 `ditto_data/errors.py` — DataSourceError 子树 `[M]`

**操作**：

| 操作 | 文件 | 变更 |
|------|------|------|
| EDIT | `packages/data/src/ditto_data/errors.py` | 新增 `DataSourceError`, `NetworkError`, `SourceFetchError`, `AuthError`, `DataValidationError`, `PersistenceError`, `WriteError`, `convert_httpx_to_network_error()` |
| EDIT | `packages/data/src/ditto_data/errors.py` | 更新 `__all__` |

**设计要点**：
- 所有新类继承 `DataHubError`（非 `DittoPortError`），结构兼容（两者都有 `message` + `details`）
- `DataSourceError` 提供 `source` 属性（整合到 `details`）
- `NetworkError` 提供 `timeout`, `cause`, `from_httpx()` classmethod
- `SourceFetchError` 提供 `cause`
- `PersistenceError` 提供 `dataset`
- `WriteError` 提供 `cause`, `from_exception()`
- 保留完整的 `convert_httpx_to_network_error()` 工具函数

**验收**：
- [ ] `pixi run -e dev type --tests` 通过
- [ ] 新类 API 与 port 侧完全兼容（相同构造参数、属性、classmethod）

#### A2: 创建 `ditto_data/models/ingestion.py` `[S]`

**操作**：

| 操作 | 文件 | 变更 |
|------|------|------|
| CREATE | `packages/data/src/ditto_data/models/__init__.py` | 包入口 + 聚合导出 |
| CREATE | `packages/data/src/ditto_data/models/ingestion.py` | 5 个 frozen dataclass |

**迁入类型**（全部从 `ditto_interfaces/models/ingestion.py`）：

| 类型 | 字段数 | 说明 |
|------|--------|------|
| `InstrumentIngestParams` | 6 | 按标的摄取参数 |
| `IngestionResult` | 8 | 单次摄取结果 |
| `ResultCounts` | 3 | 摄取统计 |
| `BackfillResult` | 6 | 回补结果（含 `tuple[IngestionResult, ...]`） |
| `RetryResult` | 6 | 重试结果（含 `tuple[IngestionResult, ...]`） |

**验收**：
- [ ] 类型定义完整复制，无遗漏
- [ ] `from ditto_data.models.ingestion import IngestionResult` 可用

#### A3: 创建 `ditto_app/config.py` `[M]`

**操作**：

| 操作 | 文件 | 变更 |
|------|------|------|
| CREATE | `packages/app/src/ditto_app/config.py` | 摄入配置类型 + 函数 |

**迁入内容**（从 `ditto_interfaces/models/config.py`）：

| 符号 | 类型 | 说明 |
|------|------|------|
| `TaskTier` | StrEnum | 任务层级 |
| `DatasetSpec` | BaseModel | 数据集规格 |
| `T1ConfigSpec` | BaseModel | T1 配置规格 |
| `INGESTION_SPECS` | dict | 数据集配置常量 |
| `create_t0_config()` | function | 创建 T0 配置 |
| `create_t1_config()` | function | 创建 T1 配置 |
| `get_datasets_by_tier()` | function | 按层级获取数据集 |
| `get_dataset_config()` | function | 获取数据集配置 |
| `iter_tier_datasets()` | function | 迭代层级数据集 |
| `get_all_datasets()` | function | 获取所有数据集 |
| `get_parallel_datasets()` | function | 获取并行数据集 |

**依赖**：`ditto_data.models.Dataset`, `ditto_data.errors.DatasetNotFoundError`

**验收**：
- [ ] 所有 11 个符号可从 `ditto_app.config` 导入
- [ ] `pixi run -e dev type` 通过

#### A4: port 侧 re-export shim `[S]`

**操作**：

| 操作 | 文件 | 变更 |
|------|------|------|
| EDIT | `interfaces/src/ditto_interfaces/errors.py` | 全部 re-export from `ditto_data.errors` |
| EDIT | `interfaces/src/ditto_interfaces/models/ingestion.py` | 全部 re-export from `ditto_data.models.ingestion` |
| EDIT | `interfaces/src/ditto_interfaces/models/config.py` | 全部 re-export from `ditto_app.config` |
| EDIT | `interfaces/src/ditto_interfaces/models/__init__.py` | 保持不变（已通过子模块 re-export） |

**注意**：`DittoPortError` 保留在 `ditto_interfaces/errors.py`（API 层仍需要）。

**验收**：
- [ ] `from ditto_interfaces.errors import NetworkError` 仍可用
- [ ] `from ditto_interfaces.models.ingestion import IngestionResult` 仍可用
- [ ] `from ditto_interfaces.models.config import TaskTier` 仍可用

#### A5: 更新 ingestion 服务 import `[M]`

**操作**：

| 文件 | 变更 |
|------|------|
| `services/ingestion/coordinator.py` | `ditto_interfaces.models` → `ditto_data.models.ingestion`；`ditto_interfaces.errors` → `ditto_data.errors` |
| `services/ingestion/backfill.py` | `ditto_interfaces.models` → `ditto_data.models.ingestion` |
| `services/ingestion/retry.py` | `ditto_interfaces.models` → `ditto_data.models.ingestion` |
| `services/ingestion/result_handler.py` | `ditto_interfaces.models` → `ditto_data.models.ingestion` |
| `services/ingestion/result_utils.py` | `ditto_interfaces.models` → `ditto_data.models.ingestion` |
| `services/ingestion/errors.py` | 删除（已变为 ditto_data.errors 的一部分）或改为 re-export |
| `services/ingestion/config/__init__.py` | `ditto_interfaces.models` → `ditto_app.config` |

**验收**：
- [ ] `pixi run -e dev type` 通过
- [ ] ingestion 服务内部无 `from ditto_interfaces.models.ingestion` 或 `from ditto_interfaces.errors` 引用（shim 除外）

#### A6: 更新 tests import `[M]`

**影响的测试文件**（约 16 个，均在 `interfaces/tests/`）：

- `tests/unit/services/ingestion/` — 14 个文件
- `tests/integration/ingestion/` — 1 个文件
- `tests/unit/cli/` — 1 个文件（`InstrumentIngestParams`）
- `tests/unit/jobs/` — 若干文件

**变更**：`from ditto_interfaces.services.ingestion.xxx import IngestionResult` → `from ditto_data.models.ingestion import IngestionResult`

**验收**：
- [ ] `pixi run -e dev test --unit` 通过

#### A7: 最终验证 `[S]`

```bash
pixi run -e dev check          # lint + fmt + type + test --fast
pixi run -e dev arch-check     # 全部 importlinter contract 通过
```

**grep 验证**：
```bash
# ingestion 内部代码不再直接引用 port.models.ingestion
grep -rn "from ditto_interfaces.models.ingestion\|from ditto_interfaces.models import.*IngestionResult" \
  interfaces/src/ditto_interfaces/services/ingestion/ --include="*.py"
# 应仅剩 shim 文件

# ingestion 内部代码不再直接引用 port.errors
grep -rn "from ditto_interfaces.errors" \
  interfaces/src/ditto_interfaces/services/ingestion/ --include="*.py"
# 应仅剩 shim 文件
```

---

### PR-B: Ingestion + Quality 迁入 app（补完 4a-2） `[XL]`

**目标**：将 ingestion 13 个核心服务 + quality 4 个服务迁入 `app/process/`，完成 CQRS Process 角色全覆盖。

#### B1: 创建 `app/process/quality.py` `[M]`

**操作**：

| 操作 | 文件 | 变更 |
|------|------|------|
| CREATE | `packages/app/src/ditto_app/process/quality.py` | 合并 quality 子包 4 个文件（~740 LOC） |

**合并来源**：

| 源文件 | LOC | 迁入内容 |
|--------|-----|---------|
| `quality/models.py` | 37 | `ReconciliationResult` dataclass |
| `quality/service.py` | 151 | `QualityService` |
| `quality/l3_batch_service.py` | 241 | `L3BatchService` |
| `quality/reconciliation_service.py` | 310 | `QualityReconciliationService` |

**依赖**：`ditto_data.quality`, `ditto_data.services`（零 port 依赖）

**验收**：
- [ ] 所有 4 个类型可从 `ditto_app.process.quality` 导入
- [ ] `pixi run -e dev type` 通过

#### B2: 创建 `app/process/ingestion.py` `[XL]`

**操作**：

| 操作 | 文件 | 变更 |
|------|------|------|
| CREATE | `packages/app/src/ditto_app/process/ingestion.py` | 合并 14 个文件（~3400 LOC） |

**合并来源**（按依赖拓扑序）：

| 层级 | 源文件 | LOC | 迁入内容 |
|------|--------|-----|---------|
| 0 | `errors.py` | 11 | 删除（已迁入 ditto_data.errors，或改为 re-export） |
| 0 | `metadata.py` | 186 | `MetadataManager` |
| 0 | `data_writer.py` | 704 | `IngestionDataWriter` |
| 0 | `index_config.py` | 149 | `get_all_index_codes()` |
| 0 | `list_date_inference.py` | 277 | `ListDateInferenceService` |
| 0 | `result_utils.py` | 65 | `count_results()` |
| 1 | `result_handler.py` | 255 | `IngestionResultHandler` |
| 2 | `coordinator.py` | 1221 | `IngestionCoordinator` |
| 2 | `config/config.py` | 23 | `IngestionConfig` |
| 3 | `backfill.py` | 254 | `BackfillManager` |
| 3 | `retry.py` | 140 | `RetryManager` |
| 3 | `factory.py` | 101 | `create_coordinator()` |

**依赖**：
- `ditto_data.models.ingestion`（A2 提取的结果类型）
- `ditto_data.errors`（A1 提取的错误类型）
- `ditto_app.config`（A3 提取的配置类型）
- `ditto_data.services.*`（MetadataService, MarketService, ...）
- `ditto_data.sources.*`（DataSources）
- `ditto_data.quality`（QualityEngine）
- `ditto_app.process.quality`（QualityService — B1）

**验收**：
- [ ] 所有公开类型可从 `ditto_app.process.ingestion` 导入
- [ ] `pixi run -e dev type` 通过

#### B3: port 侧 re-export shim `[S]`

**操作**：

| 操作 | 文件 | 变更 |
|------|------|------|
| EDIT | `port/services/ingestion/__init__.py` | `from ditto_app.process.ingestion import *` |
| EDIT | `port/services/ingestion/quality/__init__.py` | `from ditto_app.process.quality import *` |
| EDIT | `port/services/__init__.py` | 保持不变（通过子模块 re-export） |

**保留的 port 文件**（暂时保留，PR-E 清理）：
- `port/services/ingestion/coordinator.py` 等 — 改为 re-export shim 或直接删除
- `port/services/ingestion/quality/service.py` 等 — 改为 re-export shim 或直接删除

**策略选择**：对于内部模块文件（如 `coordinator.py`），有两种方式：
1. **每个文件改为 re-export shim** — 保持 `from ditto_interfaces.services.ingestion.coordinator import X` 可用
2. **删除文件，仅保留 `__init__.py` shim** — 调用方改为包级 import

**决策**：采用方式 2（删除内部文件），因为 PR-E 最终会清理所有 shim，提前减少维护负担。外部调用方统一改为包级 import。

**验收**：
- [ ] `from ditto_interfaces.services.ingestion import IngestionCoordinator` 可用
- [ ] `from ditto_interfaces.services.ingestion.quality import QualityService` 可用

#### B4: 更新外部引用 `[L]`

**影响的文件**（约 9 个非测试文件）：

| 文件 | 引用类型 | 变更 |
|------|---------|------|
| `cli/executor.py` | `BackfillManager`, `IngestionCoordinator` | → 包级 import from shim |
| `cli/commands/strategy.py` | `BacktestServiceConfig`, `StrategyRunResult` 等 | 已是包级 import（无需变更） |
| `jobs/flows/backfill.py` | `BackfillManager` | → 包级 import from shim |
| `jobs/flows/repair.py` | `BackfillManager`, `RetryManager` | → 包级 import from shim |
| `jobs/flows/daily.py` | `count_results` | → 包级 import from shim |
| `jobs/tasks/dq_batch.py` | `L3BatchService` | → 包级 import from shim |
| `registry/contexts/ingestion.py` | `create_coordinator`, `BackfillManager`, `QualityService` | → 包级 import from shim |
| `registry/contexts/bundle.py` | `BackfillManager`, `IngestionCoordinator` | → 包级 import from shim |
| `registry/core/quality.py` | `QualityService` | → `from ditto_app.process.quality import QualityService` |

**注意**：`ingestion.__init__.py` 需扩展 `__all__`，将 `BackfillManager`、`IngestionCoordinator`、`RetryManager`、`count_results`、`IngestionDataWriter`、`MetadataManager`、`ListDateInferenceService`、`IngestionConfig` 加入 re-export。

**验收**：
- [ ] 所有外部引用路径更新完毕
- [ ] `pixi run -e dev type` 通过

#### B5: 更新 tests `[L]`

**影响的测试文件**（约 30 个）：

- `tests/unit/services/ingestion/` — 14+ 个文件（内部模块 import → 包级 shim import）
- `tests/unit/services/ingestion/quality/` — 4 个文件
- `tests/integration/ingestion/` — 1 个文件
- `tests/unit/jobs/` — 2 个文件

**变更策略**：
- `from ditto_interfaces.services.ingestion.coordinator import X` → `from ditto_interfaces.services.ingestion import X`（通过 shim）
- 或直接引用 `ditto_app.process.ingestion`（测试可跨层引用）
- `from ditto_interfaces.services.ingestion.quality.service import QualityService` → `from ditto_interfaces.services.ingestion.quality import QualityService`

**建议**：测试统一使用 shim 路径（`ditto_interfaces.services.*`），PR-E 清理后再统一改为 `ditto_app.*`。减少本 PR 变更量。

**验收**：
- [ ] `pixi run -e dev test` 通过
- [ ] 测试覆盖率不低于变更前

#### B6: 更新 importlinter `[S]`

R8 规则已在 PR2 中配置，`app.process` 与 `app.query`/`app.command`/`app.builders` 的互斥规则已生效。ingestion 迁入 `app.process` 后自动受规则约束。

**验证**：新增的 ingestion.py 和 quality.py 内部不应 import `app.query`/`app.command`/`app.builders`。

**验收**：
- [ ] `pixi run -e dev arch-check` 全部 contract 通过

#### B7: 最终验证 `[S]`

```bash
pixi run -e dev check
pixi run -e dev arch-check
```

**grep 验证**：
```bash
# ingestion 内部文件已删除（仅保留 __init__.py shim）
ls interfaces/src/ditto_interfaces/services/ingestion/*.py
# 应仅剩 __init__.py

# quality 内部文件已删除（仅保留 __init__.py shim）
ls interfaces/src/ditto_interfaces/services/ingestion/quality/*.py
# 应仅剩 __init__.py
```

---

### PR-C: DI 重构 — AppProvider（4b） `[L]`

**目标**：将 app 层 DI Provider 从 port/datahub 中提取到 `app/providers.py`。

#### C1: 创建 `app/providers.py` `[M]`

**操作**：

| 操作 | 文件 | 变更 |
|------|------|------|
| CREATE | `packages/app/src/ditto_app/providers.py` | AppProvider + 工厂函数 |

**内容**：

```python
def get_app_providers() -> list[Provider]:
    return [
        AppQueryProvider(),      # ← DerivedProvider 中的 Query 部分
        AppProcessProvider(),    # ← DerivedProvider 中的 Process 部分 + IngestionProvider
        AppBuilderFactory(),     # ← StrategyProvider（Builder）
    ]
```

**从 DerivedProvider 迁入的方法**（7 个 app 层方法）：

| 方法 | 返回类型 | 来源 |
|------|---------|------|
| `runtime_mode_resolver` | `StaticRuntimeModeResolver` | `app.query.derived` |
| `derived_input_provider` | `RuntimeDerivedInputProvider` | `app.process.materialization` |
| `derived_materialization_orchestrator` | `DerivedMaterializationOrchestrator` | `app.process.materialization` |
| `derived_invalidation_orchestrator` | `InvalidationCascadeOrchestrator` | `app.process.materialization` |
| `derived_query_facade` | `DerivedQueryFacade` | `app.query.derived` |
| `research_dataset_facade` | `ResearchDatasetFacade` | `app.query.research` |
| `derived_publication_facade` | `DerivedPublicationFacade` | `app.process.materialization` |

**从 StrategyProvider 迁入的方法**（5 个）：

| 方法 | 返回类型 | 来源 |
|------|---------|------|
| `strategy_runtime_builder` | `StrategyRuntimeBuilder` | `app.builders.strategy` |
| `backtest_runtime_builder` | `BacktestRuntimeBuilder` | `app.builders.strategy` |
| `strategy_slice_builder` | `StrategySliceBuilder` | `app.builders.strategy` |
| `strategy_service_factory` | `StrategyServiceFactory` | `app.builders.strategy` |
| `strategy_facade` | `StrategyFacade` | `app.process.strategy` |

**新增方法**（ingestion 相关）：

| 方法 | 返回类型 | 来源 |
|------|---------|------|
| `ingestion_coordinator` | `IngestionCoordinator` | `app.process.ingestion` |
| `backfill_manager` | `BackfillManager` | `app.process.ingestion` |
| `quality_service` | `QualityService` | `app.process.quality` |

**验收**：
- [ ] `get_app_providers()` 返回 15+ 个 provide 方法
- [ ] 所有 import 来自 `ditto_app.*` 或更下层

#### C2: 拆分 DerivedProvider `[M]`

**操作**：

| 操作 | 文件 | 变更 |
|------|------|------|
| EDIT | `registry/datahub/derived.py` | 删除 7 个 app 层 provide 方法 |
| EDIT | `registry/datahub/derived.py` | import 来源从 `ditto_interfaces.services.derived` 改为 `ditto_app.*` |

**保留在 DerivedProvider 的方法**（3 个 datahub 层）：

| 方法 | 返回类型 |
|------|---------|
| `research_artifact_service` | `ResearchArtifactService` |
| `derived_query_service` | `DerivedQueryService` |
| `compile_cache_service` | `SQLiteCompileCache` |

**验收**：
- [ ] DerivedProvider 仅注册 3 个 datahub 层服务
- [ ] `from ditto_interfaces.services import derived` 在 registry 中无引用

#### C3: 删除 StrategyProvider `[S]`

**操作**：

| 操作 | 文件 | 变更 |
|------|------|------|
| DELETE | `registry/port/strategy.py` | 迁入 AppProvider |
| EDIT | `registry/port/__init__.py` | `get_port_providers()` 返回空列表 |

**验收**：
- [ ] `registry/port/` 目录仅剩 `__init__.py`
- [ ] `get_port_providers()` 返回 `()`

#### C4: 更新 container.py `[S]`

**操作**：

| 操作 | 文件 | 变更 |
|------|------|------|
| EDIT | `registry/container.py` | `_get_base_providers()` 新增 `*get_app_providers()` |

**变更后层级**：

```python
def _get_base_providers() -> tuple[Provider, ...]:
    return (
        *get_infra_providers(),     # 1. Infrastructure
        *get_core_providers(),      # 2. Core
        *get_datahub_providers(),   # 3. DataHub
        *get_app_providers(),       # 4. App (NEW)
        # *get_port_providers(),    # 5. Port — 已空，可删除
    )
```

**验收**：
- [ ] 容器组装顺序正确（app 在 datahub 之后）
- [ ] FastAPI 启动无 DI 解析错误

#### C5: 更新 Bundle `[M]`

**操作**：

| 操作 | 文件 | 变更 |
|------|------|------|
| EDIT | `registry/contexts/bundle.py` | import 来源从 `ditto_interfaces.services.*` 改为 `ditto_app.*` |
| EDIT | `registry/contexts/ingestion.py` | 同上 |
| EDIT | `registry/contexts/materialization.py` | 同上 |
| EDIT | `registry/contexts/strategy.py` | 同上 |

**IngestionBundle 变更**：

```python
# 变更前：混合 data 层 + app 层类型
@dataclass(frozen=True)
class IngestionBundle:
    metadata_service: MetadataService       # data 层
    market_service: MarketService           # data 层
    ...
    coordinator: IngestionCoordinator       # app 层

# 变更后：仅持有 app 层类型
@dataclass(frozen=True)
class IngestionBundle:
    coordinator: IngestionCoordinator       # app 层
    backfill_manager: BackfillManager       # app 层
```

**代价**：`cli/executor.py` 和 `jobs/flows/` 中直接使用 `bundle.metadata_service` 的地方需要改为通过 app 层服务间接访问，或独立从容器获取。需逐个评估影响范围。

**注意**：此变更影响面较广，需要详细评估 CLI/jobs 的使用方式。可能需要保留 IngestionBundle 中的 data 层类型以避免大面积改动，在 PR-E 中再清理。

**验收**：
- [ ] 所有 Bundle 的 import 路径更新为 `ditto_app.*`
- [ ] `pixi run -e dev type` 通过

#### C6: 更新 QualityProvider `[S]`

**操作**：

| 操作 | 文件 | 变更 |
|------|------|------|
| EDIT | `registry/core/quality.py` | `QualityService` import 从 `ditto_interfaces.services.ingestion.quality.service` 改为 `ditto_app.process.quality` |

**或**：将 `QualityService` 的 provide 从 `QualityProvider` 迁入 `AppProcessProvider`（C1），因为 QualityService 现在是 app 层服务。

**决策**：将 `quality_service` provide 迁入 `AppProcessProvider`，从 `QualityProvider` 中删除。QualityProvider 仅保留 `dq_spec` 和 `dq_engine`（data 层）。

**验收**：
- [ ] QualityProvider 仅注册 2 个 data 层服务
- [ ] `pixi run -e dev type` 通过

#### C7: 更新 tests `[M]`

**影响的测试文件**：
- `tests/registry/test_strategy_provider_unit.py` — 更新 import 路径
- `tests/registry/test_derived_provider_unit.py` — 更新 import 路径 + 验证拆分后 Provider
- 新增 `packages/app/tests/unit/test_providers.py` — AppProvider 单元测试

**验收**：
- [ ] `pixi run -e dev test` 通过
- [ ] DI smoke test：FastAPI 启动 + CLI help

#### C8: 最终验证 `[S]`

```bash
pixi run -e dev check
pixi run -e dev arch-check
```

**grep 验证**：
```bash
# registry 不再引用 ditto_interfaces.services
grep -rn "from ditto_interfaces.services" interfaces/src/ditto_interfaces/registry/ --include="*.py"
# 应返回 0 结果
```

---

### PR-D: port → interfaces 重命名（4d） `[L]`

**目标**：将 `interfaces/` 重命名为 `interfaces/`，全库引用更新。

#### D1: 目录重命名 `[S]`

```bash
git mv apps/port apps/interfaces
```

#### D2: 更新包名 `[S]`

| 操作 | 文件 | 变更 |
|------|------|------|
| EDIT | `interfaces/pyproject.toml` | `ditto_interfaces` → `ditto_interfaces` |
| EDIT | `interfaces/src/ditto_interfaces/` → `ditto_interfaces/` | 目录重命名 |
| EDIT | `interfaces/src/ditto_interfaces/__init__.py` | 包名更新 |

#### D3: 全库引用更新 `[L]`

```bash
# 批量替换
find packages/ apps/ -name "*.py" -exec sed -i 's/ditto_interfaces/ditto_interfaces/g' {} +
```

**影响的范围**：
- `packages/app/` — `from ditto_app.query.derived` 无变化，但 `__init__.py` 可能引用 port
- `packages/data/` — `importlinter` 配置引用
- `packages/data/` — 测试中可能引用
- `interfaces/` — 自身内部引用
- `interfaces/tests/` → `interfaces/tests/`

**注意**：需仔细处理 `ditto_interfaces` → `ditto_interfaces` 的替换，避免误改 `ditto_data.models.port` 等无关字符串。建议使用精确的正则替换。

**验收**：
- [ ] `grep -rn "ditto_interfaces" packages/ apps/ --include="*.py"` 返回 0
- [ ] `pixi run -e dev type` 通过

#### D4: 更新 importlinter `[S]`

| 变更 | 说明 |
|------|------|
| `root_modules` | `ditto_interfaces` → `ditto_interfaces` |
| 所有 contract | `ditto_interfaces` → `ditto_interfaces` |
| R7: app-no-port-import | `forbidden_modules = ditto_interfaces` |
| 新增 R6: interfaces 层级检查 | `layers = ditto_interfaces → ditto_app → ...` |

**验收**：
- [ ] `pixi run -e dev arch-check` 全部 contract 通过

#### D5: 更新文档 `[S]`

| 文件 | 变更 |
|------|------|
| `CLAUDE.md` | 架构图、依赖矩阵、命令示例中的 `port` → `interfaces` |
| `interfaces/CLAUDE.md` | 全面更新 |
| 各包 `CLAUDE.md` | 引用 `ditto_interfaces` 的地方更新 |

#### D6: 最终验证 `[S]`

```bash
pixi run -e dev check
pixi run -e dev arch-check
grep -rn "ditto_interfaces" packages/ apps/ --include="*.py"
# 应返回 0
```

---

### PR-E: 清理 + 最终验证（4e） `[M]`

**目标**：删除所有 re-export shim，importlinter 全量校准，最终验证。

#### E1: 删除 re-export shim `[M]`

**删除的文件/内容**：

| 文件 | 操作 |
|------|------|
| `ditto_interfaces/models/ingestion.py` | 删除（re-export ditto_data） |
| `ditto_interfaces/models/config.py` | 删除（re-export ditto_app） |
| `ditto_interfaces/models/derived.py` | 删除（re-export ditto_app） |
| `ditto_interfaces/errors.py` | 删除（re-export ditto_data），保留 DittoPortError |
| `ditto_interfaces/services/ingestion/__init__.py` | 删除（re-export ditto_app） |
| `ditto_interfaces/services/ingestion/quality/__init__.py` | 删除（re-export ditto_app） |
| `ditto_interfaces/services/strategy/__init__.py` | 删除（re-export ditto_app） |
| `ditto_interfaces/services/derived/__init__.py` | 删除（re-export ditto_app） |
| `ditto_interfaces/services/ingestion/errors.py` | 删除（re-export ditto_data） |

**更新引用**：

| 文件 | 变更 |
|------|------|
| `ditto_interfaces/models/__init__.py` | 移除 ingestion/config/derived 的 re-export |
| `ditto_interfaces/services/__init__.py` | 移除 derived/ingestion/strategy 的 re-export |

**更新外部引用**（从 shim 路径 → 直接路径）：

| 旧路径 | 新路径 |
|--------|--------|
| `from ditto_interfaces.services.ingestion import BackfillManager` | `from ditto_app.process.ingestion import BackfillManager` |
| `from ditto_interfaces.services.strategy import StrategyFacade` | `from ditto_app.process.strategy import StrategyFacade` |
| `from ditto_interfaces.services.derived import DerivedQueryFacade` | `from ditto_app.query.derived import DerivedQueryFacade` |
| `from ditto_interfaces.models.ingestion import IngestionResult` | `from ditto_data.models.ingestion import IngestionResult` |
| `from ditto_interfaces.errors import NetworkError` | `from ditto_data.errors import NetworkError` |

**验收**：
- [ ] 所有 shim 文件已删除
- [ ] 所有外部引用已更新为直接路径
- [ ] `pixi run -e dev type` 通过

#### E2: importlinter 全量校准 `[S]`

- 移除所有 `ignore_imports` 例外
- 确认 R6（interfaces 层级检查）全通过
- 确认 R7（app 不依赖 interfaces）全通过
- 确认 R8（app 内部互斥）全通过

#### E3: 文档同步 `[S]`

- `CLAUDE.md` — 最终架构图
- `interfaces/CLAUDE.md` — 最终模块结构
- `packages/app/CLAUDE.md` — 新增或更新（如需要）
- 本设计文档状态更新为 `completed`

#### E4: 最终验证 — CI 全通过 `[S]`

```bash
pixi run -e dev ci
pixi run -e dev arch-check
```

**grep 验证**（终极检查）：

```bash
# 无 port 旧引用
grep -rn "ditto_interfaces\|from ditto_interfaces.services" packages/ apps/ --include="*.py"
# 应返回 0

# interfaces 不依赖 services（已清空）
ls interfaces/src/ditto_interfaces/services/
# 应为空目录或不存在
```

---

## 风险与缓解

| # | 风险 | 概率 | 影响 | 缓解 |
|---|------|------|------|------|
| R1 | PR-A 模型提取遗漏字段/方法 | 低 | 中 | 逐类型对比 + type check 验证 |
| R2 | PR-B ingestion 合并后 importlinter R8 失败 | 低 | 低 | ingestion.py 仅依赖 data/app 层，不触犯 R8 |
| R3 | PR-C Bundle 瘦身影响 CLI/jobs | 中 | 中 | 评估后可能保留 Bundle 中 data 层类型，PR-E 再清理 |
| R4 | PR-D 重命名遗漏引用 | 中 | 低 | grep 全量验证 + CI |
| R5 | PR-E 删除 shim 后测试大面积失败 | 中 | 高 | 分批删除 + 每批验证 |

---

## 参考文档

- 源设计文档：[phase4-app-layer-design.md](2026-04-01-phase4-app-layer-design.md)
- 上游计划：[hybrid-plane-v2-migration-plan.md](2026-03-31-hybrid-plane-v2-migration-plan.md)
- 需求文档：[refined-requirements.md](../brainstorms/2026-03-31-hybrid-plane-v2-refined-requirements.md)
