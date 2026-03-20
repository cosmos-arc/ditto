# Ditto 架构审计报告

**日期**: 2026-03-20
**分支**: `feature/unified-feature-factor-engine-phase-1`
**审计范围**: `packages/` (foundation, datahub, core), `apps/` (port)
**代码规模**: 72,709 行源码 / 78,975 行测试

---

## Executive Summary

| 指标 | 数值 |
|------|------|
| Ruff lint | **全部通过** |
| BasedPyright | **0 errors, 0 warnings** |
| 单元测试 | **2,751 passed, 14 collection errors** |
| 源码行数 | 72,709 |
| 测试行数 | 78,975 |
| 测试/源码比 | **1.09:1** |

### 问题统计

| 严重度 | 数量 | 说明 |
|--------|------|------|
| **Blocker** | 1 | 测试收集失败（14 个文件无法导入） |
| **High** | 7 | 架构违规、上帝类、依赖方向错误 |
| **Medium** | 11 | 命名不一致、Any 类型、TYPE_CHECKING 违规 |
| **Low** | 8 | 命名风格、noqa 使用、docstring 问题 |
| **Info** | 3 | 建议改进项 |

### Top 5 高优先级问题

1. **[TST-001]** 14 个 ingestion 测试文件收集失败 — `ModuleNotFoundError`
2. **[ARCH-001]** `core → datahub` 反向依赖 — error 类放置位置不当
3. **[ARCH-002]** `datahub → core` 反向依赖 — stores 层直接导入 core 领域模型
4. **[DESIGN-001]** `MetadataService` 上帝类 — 1,316 行 / 41 个方法
5. **[NAM-001]** `vol` vs `volume` 混用 — 跨源对比默认规则失效

---

## Inferred Architecture（推断架构图）

```
                         ┌──────────────┐
                         │  ditto_port   │  (应用层)
                         │  apps/port   │
                         └──────┬───────┘
                                │
                    ┌───────────┼───────────┐
                    ▼           ▼           ▼
              ┌──────────┐ ┌──────────┐ ┌──────────┐
              │ditto_core│ │ditto_hub │ │ditto_inf│
              │packages/ │ │packages/ │ │packages/ │
              │  core    │ │ datahub  │ │  infra   │
              └──────────┘ └──────────┘ └──────────┘

依赖方向（期望）:
  port → core ✅        port → datahub ✅     port → infra ✅
  core → datahub ❌     datahub → core ❌     infra → datahub ❌

实际违规:
  core → datahub errors ⚠️   (2 文件)
  datahub → core engine   ⚠️   (2 文件)
  port → datahub runtime ⚠️   (3 文件)
  port → datahub sources  ⚠️   (4 文件)
```

### 各包职责

```
ditto_infra (基础设施层)
├── foundation/    # 横切关注点: 缓存、日志、追踪、配置、锁
└── services/      # 通知服务

ditto_datahub (数据访问层)
├── models/        # 数据模型 (85 个公共符号)
├── services/      # 领域服务 (30 个公共符号)
├── stores/        # 数据持久化 (Parquet/SQLite)
├── sources/       # 外部数据源适配
├── runtime/       # 运行时基础设施 (连接池、锁、分配器)
└── dq/            # 数据质量检查

ditto_core (核心引擎层)
├── quality/       # 数据质量引擎
├── engine/        # 因子引擎 (表达式、编译、物化)
└── strategy/      # 策略引擎 (规划中)

ditto_port (应用层)
├── api/           # FastAPI 路由
├── cli/           # CLI 命令
├── jobs/          # Prefect 任务/流
├── registry/      # DI 容器配置
└── services/      # 应用服务 (编排/协调)
```

---

## Findings（详细发现）

### Blocker

#### [TST-001] 14 个 ingestion 测试文件收集失败

**严重度**: Blocker
**影响**: 14 个测试文件完全无法运行

**现象**:
```
ERROR apps/port/tests/unit/services/ingestion/test_backfill_adj_factor_unit.py
ERROR apps/port/tests/unit/services/ingestion/test_backfill_manager_unit.py
ERROR apps/port/tests/unit/services/ingestion/test_config_unit.py
ERROR apps/port/tests/unit/services/ingestion/test_coordinator_dq_blocking_unit.py
ERROR apps/port/tests/unit/services/ingestion/test_coordinator_exception_chain.py
ERROR apps/port/tests/unit/services/ingestion/test_coordinator_instrument_unit.py
ERROR apps/port/tests/unit/services/ingestion/test_coordinator_unit.py
ERROR apps/port/tests/unit/services/ingestion/test_data_writer_unit.py
ERROR apps/port/tests/unit/services/ingestion/test_datasets_unit.py
ERROR apps/port/tests/unit/services/ingestion/test_list_date_inference_unit.py
ERROR apps/port/tests/unit/services/ingestion/test_metadata_unit.py
ERROR apps/port/tests/unit/services/ingestion/test_monitoring_unit.py
ERROR apps/port/tests/unit/services/ingestion/test_result_utils_unit.py
ERROR apps/port/tests/unit/services/ingestion/test_retry_unit.py
```

**根因**: `apps/port/tests/unit/services/ingestion/` 目录下既有 `__init__.py` 又有子目录 (`flows/`, `quality/`, `tasks/`)，pytest 收集时将 `ingestion` 视为 Python 包，导致 `from ingestion.test_xxx_unit` 导入失败。

**修复建议**: 将 `__init__.py` 中的 docstring 移除，或将测试文件移入子目录中。

---

### High（架构违规）

#### [ARCH-001] core → datahub 反向依赖

**严重度**: High
**影响**: 核心引擎依赖数据访问层，破坏分层架构

**违规文件**:

| 文件 | 导入 |
|------|------|
| `packages/core/src/ditto_core/engine/research.py:9` | `from ditto_datahub.errors import DerivedNotImplementedError, DerivedValidationError` |
| `packages/core/src/ditto_core/engine/specs.py:9` | `from ditto_datahub.errors import DerivedNotImplementedError` |

**分析**: `DerivedNotImplementedError` 和 `DerivedValidationError` 定义在 datahub errors 模块中，但被 core engine 引用。按依赖方向应为 `datahub → core`，实际反过来了。

**修复建议**: 将这两个异常类下移到 `ditto_core.engine.errors` 或 `ditto_infra.foundation.exceptions`。

---

#### [ARCH-002] datahub → core 反向依赖

**严重度**: High
**影响**: 数据访问层依赖核心引擎，形成双向耦合

**违规文件**:

| 文件 | 导入 | 性质 |
|------|------|------|
| `datahub/src/.../stores/runtime/derived_artifact_writer.py:12-13` | `Analysis, CompileIdentity`, `DerivedSpec` | **运行时导入** |
| `datahub/src/.../services/derived/artifact_persistence_service.py:18-19` | 同上 | TYPE_CHECKING 导入 |

**分析**: stores 层运行时导入了 core 的领域模型，且后者还使用了被禁止的 TYPE_CHECKING。

**修复建议**: 将 `Analysis`, `CompileIdentity`, `DerivedSpec` 提取到 `ditto_datahub.models.derived` 或独立接口包中。

---

#### [ARCH-003] port 非 registry 模块直接导入 datahub runtime/sources

**严重度**: High
**影响**: 应用服务层绕过 DataHub Service 抽象，直接使用底层组件

**违规文件**:

| 文件 | 违规导入 |
|------|---------|
| `services/ingestion/factory.py:12` | `FreezeManager` (runtime) |
| `services/ingestion/coordinator.py:27,34` | `FreezeManager` (runtime), `DataSource` (sources) |
| `services/ingestion/list_date_inference.py:24` | `DataSource` (sources) |
| `registry/contexts/ingestion.py:6,14` | `FreezeManager` (runtime), `ExchangeTransformers` (sources) |
| `registry/contexts/bundle.py:12` | `ExchangeTransformers` (sources) |

**修复建议**: 在 DataHub Service 层封装 FreezeManager 和 DataSource 的访问接口。

---

#### [ARCH-004] datahub 测试导入 port 层类

**严重度**: High
**影响**: 测试代码形成 `datahub → port` 反向依赖

**违规文件**:
- `packages/datahub/tests/unit/services/test_derived_materialization_orchestrator_unit.py:48-54`

导入了 `DerivedMaterializationOrchestrator`、`InMemoryDerivedInputProvider`、`RuntimeDerivedInputProvider`、`SQLiteCompileCache`。

**修复建议**: 将 `DerivedMaterializationOrchestrator` 下沉到 datahub 层，或测试中使用 mock。

---

#### [DESIGN-001] MetadataService 上帝类

**严重度**: High
**文件**: `packages/datahub/src/ditto_datahub/services/metadata_service.py`
**数据**: **1,316 行 / 41 个方法**

**分析**: MetadataService 承担了 metadata、instrument、calendar、industry、universe 等多个领域的职责，严重违反单一职责原则。

**修复建议**: 按子领域拆分：
- `InstrumentService` — 证券基本信息
- `CalendarService` — 交易日历
- `IndustryService` — 行业分类
- `UniverseService` — 股票池

---

#### [DESIGN-002] 其他过大的类

**严重度**: High

| 类 | 文件 | 行数 | 方法数 | 建议 |
|----|------|------|--------|------|
| `RuntimeProvider` | `port/registry/datahub/runtime.py` | — | **37** | 按领域拆分 Provider |
| `DerivedCatalogService` | `datahub/services/derived_catalog_service.py` | — | **32** | 按读写拆分 |
| `TushareSource` | `datahub/sources/tushare/tushare_source.py` | 892 | **29** | 按数据集拆分 |
| `IngestionCoordinator` | `port/services/ingestion/coordinator.py` | 1,215 | **21** | 提取子协调器 |
| `MarketService` | `datahub/services/market_service.py` | 1,065 | **23** | 按市场类型拆分 |

---

### Medium（需计划修复）

#### [NAM-001] vol vs volume 混用

**严重度**: Medium
**影响**: 跨源对比默认规则失效

**核心问题**:
- 跨源对比检查器 (`quality/checkers/cross_source.py:49`) 默认容差规则使用 `"vol"` 键，但实际数据列名为 `"volume"`
- 摄入配置 `critical_fields` 使用 `"vol"` 而非 `"volume"`
- TDX 数据源输出列名为 `"vol"` 而非 `"volume"`（与 Tushare 映射策略不一致）

**修复建议**: 全局统一为 `"volume"`。

---

#### [ENG-001] TYPE_CHECKING 使用违规

**严重度**: Medium
**影响**: 6 处源码使用被禁止的 TYPE_CHECKING 延迟导入

**违规文件**:

| 文件 | 位置 |
|------|------|
| `datahub/services/derived/artifact_persistence_service.py` | L6, L17 |
| `datahub/sources/fred/adapters/base.py` | L5, L9 |
| `port/errors.py` | L16, L18 |
| `port/services/ingestion/index_config.py` | L19, L21 |
| `port/services/ingestion/list_date_inference.py` | L17, L22 |

**修复建议**: 重构消除循环依赖，而非用 TYPE_CHECKING 掩盖。

---

#### [ENG-002] Any 类型使用（63 处）

**严重度**: Medium

**重点关注**:

| 文件 | 行号 | 问题 |
|------|------|------|
| `datahub/stores/base/parquet_store.py` | 43 | `_client: Any` — 应用 `SQLiteClient` 具体类型 |
| `datahub/stores/base/sqlite_store.py` | 46 | `_client: Any` — 应用 `SQLiteClient` 具体类型 |
| `datahub/services/metadata_service.py` | 149-150 | `rebalance_reader/writer: Any` |
| `port/services/ingestion/quality/service.py` | 95 | `result: Any` (注释标注为 DQResult) |
| `port/services/ingestion/quality/reconciliation_service.py` | 61 | `engine: Any` (注释标注为 QualityEngine) |

**修复建议**: 优先为 Store 层 client 和 Service 层依赖定义 Protocol 或具体类型。

---

#### [ENG-003] 行内导入缺少 noqa

**严重度**: Medium

| 文件 | 行号 | 导入 |
|------|------|------|
| `port/main.py` | 201 | `debug_router` 条件注册 |
| `port/main.py` | 310 | `granian.constants.Interfaces` |

**修复建议**: 添加 `# noqa: PLC0415` 注释或重构。

---

#### [NAM-002] source_ticker / ticker / standard_ticker 术语体系混乱

**严重度**: Medium
**影响**: 77 个文件、948 处使用 `source_ticker`

**分析**: 三种 ticker 概念含义边界模糊，`source_ticker` 使用过于广泛，增加了理解成本。

**修复建议**: 建立领域术语表，明确各术语语义边界。

---

#### [NAM-003] MetadataManager 与 MetadataService 命名混淆

**严重度**: Medium

`MetadataManager`（Port 层）和 `MetadataService`（DataHub 层）职责边界不清，命名相似易混淆。

**修复建议**: Port 层的 `MetadataManager` 重命名为 `IngestionMetadataCoordinator` 或类似名称。

---

#### [DESIGN-003] Core 层 SQLiteCompileCache 暴露实现细节

**严重度**: Medium
**文件**: `packages/core/src/ditto_core/engine/compile_cache.py`

Core 层作为纯业务逻辑层，不应包含 SQLite 实现细节。

**修复建议**: 定义 `CompileCacheBackend` Protocol，将 SQLite 实现移到 infra 或 datahub 层。

---

#### [DESIGN-004] 多个 Writer 重复嵌套模式

**严重度**: Medium
**影响**: 11 个 fundamental/capital Writer 文件

多个 Writer 文件有相同的 depth=5 嵌套模式（context manager + records 遍历），暗示 Writer 基类需要抽取公共逻辑。

**修复建议**: 在 Writer 基类中实现通用的批量写入逻辑。

---

### Low（可选修复）

#### [NAM-004] adj 作为函数参数名风格随意

20+ 处使用 `adj="qfq"` 作为参数名，建议统一为 `adjustment_type`。

#### [NAM-005] PitHelper 命名过于宽泛

建议重命名为 `PitQueryBuilder` 或 `PitSqlBuilder`。

#### [NAM-006] DatabaseManager（测试辅助类）命名过于泛化

仅在 `port/testing.py` 中使用，建议重命名为 `TestDatabaseHelper`。

#### [NAM-007] OHLCV 出现在函数名和常量名中

8 处使用 `OHLCV` 作为标识符，金融领域标准术语，暂可接受。

#### [ENG-004] noqa 使用统计

共 73 处 noqa：
- S608（SQL 拼接）: 46 处 — 合法豁免
- C901/PLR091x（复杂度）: 11 处 — 需要通过重构消除
- E501（行过长）: 5 处
- S101（assert）: 4 处（测试文件）
- PLC0415（行内导入）: 4 处
- 其他: 3 处

#### [ENG-005] type:ignore 使用（4 处）

| 文件 | 规则 | 评估 |
|------|------|------|
| `core/engine/compile_cache.py` | `reportOptionalMemberAccess` | 需审查 |
| `port/main.py` | `reportAssignmentType` | Prefect Future，可接受 |
| `core/engine/expression/evaluator.py` | `reportIndexType` | 需审查 |
| `datahub/models/common.py` | `reportExplicitAny` | Pydantic 泛型，可接受 |

#### [ENG-006] models 包导出过多

| 模块 | 导出符号数 |
|------|-----------|
| `ditto_datahub.models` | **85** |
| `ditto_core.engine` | **43** |

过多导出增加模块间耦合。建议分域子包导入（如 `from ditto_datahub.models.market import Bar`）。

---

## Refactor Plan（修复计划）

### P0 — 立即修复（阻塞发布）

| 编号 | 任务 | 预估工作量 |
|------|------|-----------|
| P0-1 | 修复 [TST-001] ingestion 测试收集错误 | 小 |
| P0-2 | 修复 [NAM-001] `vol` → `volume` 全局统一 | 中 |

### P1 — 本迭代修复（架构健康）

| 编号 | 任务 | 预估工作量 |
|------|------|-----------|
| P1-1 | 修复 [ARCH-001] 将 error 类从 datahub 下移到 core | 小 |
| P1-2 | 修复 [ARCH-002] 消除 datahub → core 反向依赖 | 中 |
| P1-3 | 修复 [ENG-001] 消除 6 处 TYPE_CHECKING 违规 | 中 |
| P1-4 | 开始 [DESIGN-001] MetadataService 拆分 | 大 |
| P1-5 | 修复 [ARCH-003] port 层 runtime/sources 导入 | 中 |

### P2 — 后续迭代（持续改进）

| 编号 | 任务 | 预估工作量 |
|------|------|-----------|
| P2-1 | [DESIGN-002] 拆分其他过大类（TushareSource, MarketService 等） | 大 |
| P2-2 | [ENG-002] 收敛 Any 类型（Store client, Service 依赖） | 中 |
| P2-3 | [NAM-002] 整理 ticker 术语体系 | 中 |
| P2-4 | [DESIGN-003] CompileCache 实现下沉 | 中 |
| P2-5 | [DESIGN-004] Writer 基类抽取公共逻辑 | 小 |
| P2-6 | [ENG-006] models 包分域子包化 | 大 |

---

## 验证命令

```bash
# 基础验证
pixi run -e dev lint          # lint 通过 ✅
pixi run -e dev type          # 类型检查通过 ✅
pixi run -e dev test --unit   # 单元测试（14 errors 待修复）

# 架构检查
pixi run -e dev arch-check    # 边界检查

# 完整 CI
pixi run -e dev ci            # CI 全量检查

# 覆盖率
pixi run -e dev test --unit --cov-report=term-missing
```

---

## 附录：合规性检查清单

### 架构约束
- [x] ~~层级穿透检查~~ — 发现 8 处违规（见 ARCH-001 ~ ARCH-004）
- [x] ~~循环依赖检查~~ — 无直接循环，但有双向耦合
- [x] ~~领域层污染检查~~ — Core 层 error 依赖 datahub
- [x] ~~反向依赖检查~~ — core↔datahub 双向违规

### 设计与结构
- [x] ~~类单一职责~~ — 6 个类超过 20 方法
- [x] ~~类规模检查~~ — 3 个文件超过 1000 行
- [x] ~~函数复杂度~~ — 11 处 noqa C901/PLR091x
- [x] ~~深层嵌套~~ — 114 处深度嵌套

### 依赖合规性
- [x] ~~禁止的类库~~ — 无 pandas/sqlalchemy 导入 ✅
- [x] ~~包管理合规~~ — 仅使用 pixi ✅

### 工程实践
- [x] ~~TYPE_CHECKING~~ — 6 处 src 违规
- [x] ~~type:ignore~~ — 4 处（均带具体规则名）
- [x] ~~global 语句~~ — 无 ✅
- [x] ~~禁止导入~~ — 无 pandas/sqlalchemy ✅
- [x] ~~行内导入~~ — 2 处缺 noqa
- [x] ~~Any 类型~~ — 63 处
- [x] ~~未使用 Protocol~~ — 无 ✅

### 命名与概念
- [x] ~~vol/volume 混用~~ — 5+ 文件
- [x] ~~术语体系混乱~~ — ticker 三种表述
- [x] ~~命名风格~~ — 源码无驼峰混入 ✅
- [x] ~~业务层技术术语~~ — SQLiteCompileCache 在 Core 层
- [x] ~~禁止导入 pandas~~ — 无 ✅

### 测试质量
- [ ] ~~测试可运行性~~ — 14 个文件收集失败 ❌
- [x] ~~测试成功率~~ — 2,751 passed ✅
- [ ] ~~覆盖率~~ — 需确认 80% 阈值（测试未完整运行）
