# Unified Feature/Factor Engine Development Execution Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 在已收敛的 unified-feature-factor-engine 设计基线之上，按阶段落地统一派生引擎，实现从 metadata、query、materialization、research dataset 到 publication safety 的完整主链路。
**Architecture:** 采用“Core 负责统一语义与执行模型、DataHub 负责存储与元数据、Port 负责 facade 与 orchestration”的分层实现路径。开发顺序坚持“先控制面与契约，再执行主链路，再研究/发布闭环”，避免一开始就把 DSL、在线查询、研究数据集和发布流程同时摊开。
**Tech Stack:** Python 3.13、polars、orjson、SQLite、Parquet、QuestDB、Kvrocks、Dishka、Prefect、pytest、basedpyright、ruff。

---

## 0. 设计基线审计结论

### 0.1 当前事实基础

当前应作为统一引擎开发基线的文档只有以下几类：

1. `docs/design/unified-feature-factor-engine/README.md`
2. `docs/design/unified-feature-factor-engine/main-design.md`
3. `docs/design/unified-feature-factor-engine/decisions/adr-032` ~ `adr-043`
4. `docs/plans/2026-03-13-unified-feature-factor-engine-remediation-design.md`

### 0.2 历史/废弃文档

以下文档保留演化轨迹，但不再作为当前设计真相源：

1. `docs/design/unified-feature-factor-engine/issues.md`
2. `docs/design/unified-feature-factor-engine/design-analysis-report.md`
3. `docs/design/unified-feature-factor-engine/optimization-review.md`
4. `docs/design/unified-feature-factor-engine/optimization-backlog.md`
5. `docs/design/unified-feature-factor-engine/revision-questdb-hot-layer.md`
6. `docs/design/unified-feature-factor-engine/archive/*`

### 0.3 最终判断

结论不是“所有未来功能都设计完了”，而是：

1. **统一引擎核心设计已完成并达到可实施态。**
2. **当前不存在阻塞开发启动的 P0 级设计缺口。**
3. **仍有显式延期项**：
   - `grain="1m"` 全链路支持
   - 复合键与多市场扩展
   - Phase 2 之后的正式 SLO 数值收敛
   - request-time derived features

这些属于后续阶段范围，不应再阻塞当前开发。

---

## 1. 当前进度快照（2026-03-14）

### 已完成

1. 文档真相源收敛完成。
2. `ADR-040` ~ `ADR-043` 已新增并回写完成。
3. 主设计与控制面口径已对齐。
4. 发布安全控制面第一批代码已落地：
   - `packages/core/src/ditto_core/engine/publication_safety.py`
   - `packages/datahub/src/ditto_datahub/models/publication_safety.py`
   - `packages/datahub/src/ditto_datahub/stores/runtime/publication_safety/*`
   - `packages/datahub/src/ditto_datahub/services/publication_safety_record_service.py`
   - `apps/port/src/ditto_port/registry/datahub/runtime.py`
5. 发布安全控制面最小测试已落地并通过。
6. Phase 1 runtime metadata / derived catalog SQLite 基线已落地：
   - `packages/core/src/ditto_core/engine/specs.py`
   - `packages/core/src/ditto_core/engine/materialization/models.py`
   - `packages/datahub/src/ditto_datahub/models/derived.py`
   - `packages/datahub/src/ditto_datahub/stores/runtime/derived_catalog/*`
   - `packages/datahub/src/ditto_datahub/stores/runtime/derived_sqlite/*`
   - `packages/datahub/src/ditto_datahub/services/derived_catalog_service.py`
   - `packages/datahub/src/ditto_datahub/scripts/schema.sql`
   - `apps/port/src/ditto_port/registry/datahub/runtime.py`
7. Phase 2 unified derived query contract layer 已落地：
   - `packages/datahub/src/ditto_datahub/services/derived/*`
   - `apps/port/src/ditto_port/models/derived.py`
   - `apps/port/src/ditto_port/services/derived/query_facade.py`
   - `apps/port/src/ditto_port/registry/datahub/derived.py`
   - 旧 `FeatureService / FactorService / FeaturesProvider` 入口已移除
8. Phase 3 unified materialization 主链路 MVP 已落地：
   - `packages/core/src/ditto_core/engine/expression/*`
   - `packages/core/src/ditto_core/engine/materialization/*`
   - `apps/port/src/ditto_port/services/derived/compile_cache.py`
   - `apps/port/src/ditto_port/services/derived/materialization.py`
   - `apps/port/src/ditto_port/services/derived/invalidation.py`
   - `apps/port/src/ditto_port/jobs/flows/materialization.py`
9. Pratt 表达式引擎已对齐 ADR-004 / ADR-014：
   - 支持 `dataset.column`、`@derived`、带点 `@factor.alpha_upstream`
   - 支持 `STRING`、`and / or / not`
   - 支持结构化 span-aware 诊断、未知算子建议、复杂度门禁
10. 对应单元测试已落地并通过：
   - `packages/core/tests/unit/engine/test_specs_unit.py`
   - `packages/core/tests/unit/engine/test_materialization_models_unit.py`
   - `packages/core/tests/unit/engine/test_expression_parser_unit.py`
   - `packages/core/tests/unit/engine/test_expression_diagnostics_unit.py`
   - `packages/core/tests/unit/engine/test_expression_engine_unit.py`
   - `packages/datahub/tests/unit/stores/runtime/derived_catalog/test_derived_catalog_store_unit.py`
   - `packages/datahub/tests/unit/services/test_derived_catalog_service.py`
   - `packages/datahub/tests/unit/services/test_derived_query_service.py`
   - `packages/datahub/tests/unit/services/test_derived_materialization_service_unit.py`
   - `packages/datahub/tests/unit/services/test_derived_invalidation_service_unit.py`
   - `apps/port/tests/registry/test_runtime_provider_derived_catalog_unit.py`
   - `apps/port/tests/registry/test_derived_provider_unit.py`
   - `apps/port/tests/unit/jobs/flows/test_materialization_flows_unit.py`
11. 最新全量验证已通过：
   - `pixi run -e dev check`
   - `basedpyright`: `0 errors, 0 warnings, 0 notes`
   - `pytest --fast`: `2000 passed in 23.80s`
   - `arch-check`: `6 kept, 0 broken`

### 尚未完成或仅完成骨架

1. legacy `data_root/derived/catalog/` 到 SQLite 的 one-shot migration 尚未实现。
2. `DerivedQueryService` 仍是 contract-first fail-closed，真实 `serving / offline / compare_sources` 读取后端尚未接通。
3. `DerivedMaterializationService` 默认仍使用 `UnavailableDerivedInputProvider`，真实输入加载器尚未接线。
4. `ResearchDatasetSpec / SpineSpec / DatasetSnapshot / availability-time` 仍未启动。
5. `shadow_publish -> dual_read_compare -> certify -> promote` 仍停留在 publication safety 基座，未形成完整业务编排。

---

## 2. 阶段总览

| 阶段 | 目标 | 状态 | 依赖 |
|------|------|------|------|
| Phase 0 | 文档基线冻结与历史入口治理 | 已完成 | 无 |
| Phase 1 | Derived catalog / runtime metadata 基线 | 已完成 | Phase 0 |
| Phase 2 | Derived query implementation + Port facade | 已完成（contract-first） | Phase 1 |
| Phase 3 | Materialization engine + artifact / invalidation 主链路 | 部分完成（主链路已落地，运行时闭环待收尾） | Phase 1, 2 |
| Phase 4 | Research dataset / spine / availability-time | 待开发 | Phase 1, 2, 3 |
| Phase 5 | Publication orchestration + shadow/certification integration | 部分完成 | Phase 3, 4 |
| Phase 6 | 性能、运维、回归基线与最终硬化 | 待开发 | 全部前置阶段 |

---

## 3. Phase 1: Derived Catalog / Runtime Metadata 基线

**目标:** 先把统一引擎最核心的 metadata 与运行时状态骨架立住，避免后续 query / materialize / publish 各自维护一套状态。

### 当前状态（2026-03-14）

1. `DerivedSpec / DerivedVersion / DerivedRun / DerivedPartition / DerivedState` Core/DataHub 模型已落地。
2. DataHub `derived_catalog` 服务与 SQLite runtime stores 已落地，`schema.sql` 已补齐统一 derived 控制面表。
3. RuntimeProvider 已接入 `DerivedCatalogService`，Phase 1 的主契约与控制面基线已经完成。
4. 当前仍保留一个收尾项：
   - legacy file-based catalog 到 SQLite 的 one-shot migration 尚未实现。

### 范围

1. `DerivedSpec`、`DerivedVersion`、`DerivedRun`、`DerivedPartition`
2. derived state / watermark / publication metadata
3. DataHub catalog reader / writer / service
4. Port registry 接线

### 推荐文件落点

**Core**
- Create: `packages/core/src/ditto_core/engine/specs.py`
- Create: `packages/core/src/ditto_core/engine/materialization/models.py`

**DataHub Models**
- Create: `packages/datahub/src/ditto_datahub/models/derived.py`

**DataHub Stores**
- Create: `packages/datahub/src/ditto_datahub/stores/runtime/derived_catalog/__init__.py`
- Create: `packages/datahub/src/ditto_datahub/stores/runtime/derived_catalog/derived_catalog_reader.py`
- Create: `packages/datahub/src/ditto_datahub/stores/runtime/derived_catalog/derived_catalog_writer.py`

**DataHub Services**
- Create: `packages/datahub/src/ditto_datahub/services/derived_catalog_service.py`
- Modify: `packages/datahub/src/ditto_datahub/services/__init__.py`

**Port Registry**
- Modify: `apps/port/src/ditto_port/registry/datahub/runtime.py`

### 验收标准

1. 可以注册 / 读取 derived spec 与 version metadata。
2. 可以写入 / 查询 derived run 与 partition 状态。
3. 不破坏现有分层与 import 约束。

### 验证

1. `pixi run -e dev pytest packages/datahub/tests/unit/stores/runtime/derived_catalog -v`
2. `pixi run -e dev pytest packages/datahub/tests/unit/services/test_derived_catalog_service.py -v`
3. `pixi run -e dev arch-check`

---

## 4. Phase 2: Derived Query Implementation + Port Facade

**目标:** 冻结统一派生查询契约，把 Port/DataHub 查询入口收敛到 `DerivedQuery*` 主线，同时清理旧 `FeatureService / FactorService` 体系；本阶段只固定接口、失败语义、DI 边界和替换路径，不提前实现 Phase 3 的真实多源查询后端。

### 当前状态（2026-03-14）

1. `DerivedQueryService`、DTO、稳定 schema 与 fail-closed 失败语义已落地。
2. `DerivedQueryFacade`、`DerivedProvider`、Port models 与 DI wiring 已落地。
3. 旧 `FeatureService / FactorService / FeaturesProvider` 运行时入口、导出与测试已清理。
4. 当前剩余项不是 Phase 2 契约问题，而是下一步真实 backend 读取实现。

### 2.1 契约冻结

1. 固定三类查询用例：`latest`、`series`、`compare_sources`。
2. `runtime_mode` 只允许作为 Facade 内部保留缝隙，不对调用方暴露。
3. DataHub Query DTO 最小字段集固定为：
   - `derived_ids / instrument_ids / start / end / as_of / version / source_scope / limit`
4. Phase 2 明确不引入：
   - `universe_id`
   - `SpineSpec`
   - `known_at`
   - research dataset build
5. 返回列契约固定为：
   - `latest`: `derived_id, instrument_id, value, trade_date, bar_time?, asof_ts, version`
   - `series`: `derived_id, instrument_id, trade_date, bar_time?, value, asof_ts, version`
   - `compare_sources`: `derived_id, instrument_id, trade_date, serving_value, offline_value, diff`
6. 失败语义固定为：
   - 非法 DTO 或不支持的 `source_scope`：`ValueError`
   - catalog 无法解析 spec/version：`KeyError`
   - 需要真实 backend 的路径：`NotImplementedError("Phase 3 backend not ready ...")`

### 2.2 DataHub Contract Layer

### 范围

1. 新增 `DerivedQueryService`
2. 新增 query DTO（latest / series / source-scope / as_of）
3. 稳定空结果 schema helper
4. 以 `DerivedCatalogService` 解析 active version / spec / version metadata
5. 在真实 backend 未落地前显式 fail closed，不做临时桥接实现

### 推荐文件落点

**DataHub Services**
- Create: `packages/datahub/src/ditto_datahub/services/derived/__init__.py`
- Create: `packages/datahub/src/ditto_datahub/services/derived/queries.py`
- Create: `packages/datahub/src/ditto_datahub/services/derived/results.py`
- Create: `packages/datahub/src/ditto_datahub/services/derived/query_service.py`
- Modify: `packages/datahub/src/ditto_datahub/services/__init__.py`
- Modify: `packages/datahub/src/ditto_datahub/__init__.py`

**Port Models**
- Create: `apps/port/src/ditto_port/models/derived.py`

**Port Facade**
- Create: `apps/port/src/ditto_port/services/derived/__init__.py`
- Create: `apps/port/src/ditto_port/services/derived/query_facade.py`

**Port Registry**
- Create: `apps/port/src/ditto_port/registry/datahub/derived.py`
- Modify: `apps/port/src/ditto_port/registry/datahub/__init__.py`
- Modify: `apps/port/src/ditto_port/registry/__init__.py`
- Delete: `apps/port/src/ditto_port/registry/datahub/features.py`

### 2.3 Port Facade + DI

1. 新增 `DerivedQueryFacade` 作为唯一 Port 查询入口。
2. Facade 默认策略固定为：
   - `get_latest()` → `source_scope="serving"`
   - `get_series()` → `source_scope="offline"`
   - `compare_sources()` → 固定 `("serving", "offline")`
3. `RuntimeModeResolver` 作为内部 seam 保留，但不对外暴露到 request model。
4. Port 模型只保留 `LatestDerivedRequest / SeriesDerivedRequest / SourceCompareRequest` 与对应 result wrapper。

### 2.4 旧入口退场

1. 删除 `FeatureService`、`FactorService`、`FeatureQuery`、`FactorQuery`。
2. 删除 `FeaturesProvider`，改为 `DerivedProvider`。
3. `ditto_datahub.services`、`ditto_datahub.__init__`、Port registry 聚合不再暴露旧名字或兼容别名。
4. 对应旧单元测试一并删除，由 `DerivedQuery*` 契约测试替代。

### 验收标准

1. `DerivedQueryService` 与 `DerivedQueryFacade` 契约层已落地，`latest / series / compare_sources` 三类入口可调用。
2. 在 backend 未就绪时，调用明确抛出约定失败语义，而不是静默回落到旧 service。
3. `FeatureService / FactorService / FeaturesProvider` 已从运行时入口、导出面和测试面移除。
4. research dataset build 未混入 `DerivedQueryFacade`。

### 验证

1. `pixi run -e dev pytest packages/datahub/tests/unit/services/test_derived_query_service.py -v`
2. `pixi run -e dev pytest apps/port/tests/unit/services/derived/test_query_facade_unit.py -v`
3. `pixi run -e dev pytest apps/port/tests/registry/test_derived_provider_unit.py -v`

---

## 5. Phase 3: Unified Materialization Engine + Artifact / Invalidation 主链路

**目标:** 交付 `Unified Derived Materialization Engine`，打通 `编译 -> 执行 -> artifact 提交 -> SQLite 控制面 -> invalidation repair` 主链路，不再继续沿用 `feature_engine / factor_engine` 双轨根对象。

### 当前状态（2026-03-14）

1. `DerivedSpec` 执行字段、统一 compile identity、compile cache、execution planner 已落地。
2. Pratt 表达式编译链已落地并补齐到 ADR-004 / ADR-014 当前范围：
   - `lexer / parser / ast / analyzer / codegen / compiler`
   - `dataset.column`、`@derived`、带点 `@factor.alpha_upstream`
   - `STRING`、`and / or / not`
   - span-aware diagnostics、未知算子建议、复杂度限制
3. Port 侧 `DerivedMaterializationService / DerivedInvalidationService`、`daily_materialization_flow / repair_from_invalidation_flow` 已落地。
4. SQLite 控制面 + Parquet artifact 提交路径已落地，`SERIES / STATE / OFFLINE / DERIVE` 四类 profile 已进入统一主链路。
5. 当前尚未完成的收尾项：
   - real input backend 未接线
   - query backend 仍未消费 materialized artifacts
   - file-based baseline 到 SQLite 的 one-shot migration 未落地

### 范围

1. `DerivedSpec` 扩展执行字段：`pit_required / normalization_preset / operator_versions`
2. Pratt 表达式编译链：`lexer / parser / ast / analyzer / codegen`
3. 统一 compile identity / compile cache / execution plan
4. 四类 `MaterializationProfile`：`SERIES / STATE / OFFLINE / DERIVE`
5. `SQLite 控制面 + Parquet artifact 真相层`
6. invalidation fan-out 与 repair flow 骨架

### 推荐文件落点

**Core Expression**
- Create: `packages/core/src/ditto_core/engine/expression/lexer.py`
- Create: `packages/core/src/ditto_core/engine/expression/parser.py`
- Create: `packages/core/src/ditto_core/engine/expression/ast.py`
- Create: `packages/core/src/ditto_core/engine/expression/analyzer.py`
- Create: `packages/core/src/ditto_core/engine/expression/codegen.py`
- Create: `packages/core/src/ditto_core/engine/expression/compiler.py`

**Core Materialization**
- Create: `packages/core/src/ditto_core/engine/materialization/contracts.py`
- Create: `packages/core/src/ditto_core/engine/materialization/planner.py`
- Modify: `packages/core/src/ditto_core/engine/specs.py`
- Modify: `packages/core/src/ditto_core/engine/materialization/__init__.py`

**DataHub**
- Create: `packages/datahub/src/ditto_datahub/stores/runtime/derived_sqlite/*`
- Modify: `packages/datahub/src/ditto_datahub/services/derived_catalog_service.py`
- Modify: `packages/datahub/src/ditto_datahub/scripts/schema.sql`

**Port**
- Create: `apps/port/src/ditto_port/services/derived/compile_cache.py`
- Create: `apps/port/src/ditto_port/services/derived/materialization.py`
- Create: `apps/port/src/ditto_port/services/derived/invalidation.py`
- Create: `apps/port/src/ditto_port/jobs/flows/materialization.py`
- Create: `apps/port/src/ditto_port/registry/contexts/materialization.py`
- Modify: `apps/port/src/ditto_port/registry/contexts/bundle.py`
- Modify: `apps/port/src/ditto_port/registry/datahub/runtime.py`
- Modify: `apps/port/src/ditto_port/registry/datahub/derived.py`

### 契约与默认规则

1. `SERIES / STATE / OFFLINE` 是 durable profile，会产出长期 artifact、checkpoint、state；`DERIVE` 只保留运行记录与可选临时结果。
2. compile cache key 固定为 `compile_input_hash + compiler_fingerprint`，`operator_fingerprint` 来自 `sorted[(operator_name, operator_version)]`。
3. `incremental` 从 `min(request_start, earliest_pending_invalidation_start)` 起算，并按 `lookback` 预热；`full` 直接按请求窗口全量执行。
4. `role=factor` 默认 `pit_required=True`、`normalization_preset="default"`；其他 role 默认为 `False / none`。
5. artifact 根路径固定为 `data_root/derived/artifacts/<profile>/<derived_id>/v<version>/...`，控制面主实现切到 SQLite。

### 验收标准

1. `full` 与 `incremental` 通过同一执行链路运行，并共享 `DerivedExecutionPlanner`。
2. compile metadata、artifact metadata、catalog `run / partition / checkpoint / state` 一致。
3. `DERIVE` 不落长期 artifact；durable profiles 会写 checkpoint 与 state。
4. invalidation 能展开 durable downstream，并通过 repair flow 触发增量重算。
5. Port 已提供 `daily_materialization_flow` 与 `repair_from_invalidation_flow` 骨架。

### 验证

1. `pixi run -e dev pytest packages/core/tests/unit/engine -v`
2. `pixi run -e dev pytest packages/datahub/tests -k "derived_materialization or invalidation or compile_cache" -v`
3. `pixi run -e dev pytest apps/port/tests -k "materialization_flow or invalidation_flow" -v`
4. `pixi run -e dev check`

---

## 6. Phase 4: Research Dataset / Spine / Availability-Time

**目标:** 把研究与训练路径做成正式能力，避免统一引擎只会物化和上线、不会稳定构建研究数据集。

### 范围

1. `SpineSpec`
2. `ResearchDatasetSpec`
3. `DatasetSnapshot`
4. availability-time / known-at join 语义

### 推荐文件落点

**Core**
- Create: `packages/core/src/ditto_core/engine/research/models.py`
- Create: `packages/core/src/ditto_core/engine/research/pit_join.py`

**DataHub**
- Create: `packages/datahub/src/ditto_datahub/services/research_dataset_service.py`

**Port**
- Create: `apps/port/src/ditto_port/services/derived/research_dataset_facade.py`

### 验收标准

1. spine + derived versions 可生成 dataset snapshot。
2. `availability_time` 明确参与 PIT build。
3. 研究路径与 serving 查询默认隔离。

### 验证

1. `pixi run -e dev pytest packages/core/tests/unit/engine/research -v`
2. `pixi run -e dev pytest packages/datahub/tests/unit/services/test_research_dataset_service.py -v`

---

## 7. Phase 5: Publication Orchestration + Shadow/Certification Integration

**目标:** 把当前已实现的 publication safety 基座接进真正业务流程。

### 当前已完成

1. Core publication safety models 已完成。
2. DataHub runtime persistence 已完成。
3. `PublicationSafetyRecordService` 已接入 DI。

### 本阶段剩余任务

1. materialize 后自动生成 `CompatibilityManifest`
2. shadow slot 管理
3. dual-read compare 执行器
4. certification aggregation
5. `promote / rollback / deprecate` orchestration

### 推荐文件落点

**Core**
- Create: `packages/core/src/ditto_core/engine/publish/manifest.py`
- Create: `packages/core/src/ditto_core/engine/publish/certification.py`

**DataHub**
- Create: `packages/datahub/src/ditto_datahub/services/publication_service.py`

**Port**
- Create: `apps/port/src/ditto_port/services/derived/publication_facade.py`
- Create: `apps/port/src/ditto_port/jobs/flows/derived_publication.py`

### 验收标准

1. candidate 可从 materialized 进入 shadow 路由。
2. shadow diff 与 certification 结果进入 promote gate。
3. rollback 复用 primary 指针模型。

### 验证

1. `pixi run -e dev pytest packages/datahub/tests/unit/services/test_publication_service.py -v`
2. `pixi run -e dev pytest apps/port/tests/unit/services/derived/test_publication_facade_unit.py -v`
3. `pixi run -e dev pytest --integration -k publication`

---

## 8. Phase 6: 性能 / 运维 / 最终硬化

**目标:** 在主链路可用之后，再把 Phase 2/3 级别的性能、可观测与运维闭环补齐。

### 范围

1. benchmark workload
2. CI regression budget
3. 正式 SLO 数值收敛
4. rebuild / DR / retention housekeeping

### 推荐文件落点

- Create: `packages/core/tests/benchmarks/test_derived_benchmarks.py`
- Create: `scripts/benchmarks/derived_benchmark.py`
- Modify: `docs/design/unified-feature-factor-engine/decisions/adr-037-performance-slo.md`

### 验收标准

1. benchmark 可重复运行。
2. CI 能阻断明显 regression。
3. SLO 不再只是测量框架，而有正式数值。

---

## 9. 开发顺序与停靠点

### 推荐执行顺序

1. Phase 1
2. Phase 2
3. Phase 3
4. Phase 5 中与 materialize 紧耦合的部分
5. Phase 4
6. Phase 5 剩余 orchestration
7. Phase 6

### 原因

1. 没有 catalog / runtime metadata，就没有可追踪的 derived 运行主线。
2. 没有 query layer，就很难稳定定义 shadow compare 与 research build 的读取行为。
3. publication safety 虽然已经起步，但它仍依赖真正的 materialization / query 主链路。
4. research dataset 很重要，但应该建立在统一 query / artifact / manifest 之上。

---

## 10. 每阶段统一完成定义

每个阶段结束前都必须满足：

1. 对应计划任务与测试落地。
2. 文档与代码口径一致。
3. `pixi run -e dev check` 全绿。
4. 不保留“临时兼容”或“旧入口继续扩展”的技术债。

---

## 11. 下一步建议

如果按 ROI 排序，最建议立刻进入：

1. **Phase 3 收尾**
   - 实现 legacy file-based catalog -> SQLite one-shot migration
   - 接通 real input backend，替换 `UnavailableDerivedInputProvider`
   - 让 query backend 真正消费 materialized artifacts，而不是继续 fail-closed
2. **Phase 4**
   - 启动 `ResearchDatasetSpec / SpineSpec / DatasetSnapshot`
   - 把 `availability-time / known-at` 契约做成正式能力
3. **Phase 5 前半段**
   - 在 materialize 后自动生成 `CompatibilityManifest`
   - 接通 shadow / certification / promote orchestration
