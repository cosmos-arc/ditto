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

## 1. 当前进度快照（2026-03-13）

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

### 尚未开始或仅停留在设计

1. `DerivedSpec` 真实代码模型
2. derived catalog / run / partition / publication 元数据
3. `DerivedQueryService` 与 `DerivedQueryFacade`
4. materialization engine 主执行链
5. `ResearchDatasetSpec / SpineSpec / DatasetSnapshot` 实现
6. `shadow_publish -> dual_read_compare -> certify -> promote` 真正业务编排

---

## 2. 阶段总览

| 阶段 | 目标 | 状态 | 依赖 |
|------|------|------|------|
| Phase 0 | 文档基线冻结与历史入口治理 | 已完成 | 无 |
| Phase 1 | Derived catalog / runtime metadata 基线 | 待开发 | Phase 0 |
| Phase 2 | Derived query implementation + Port facade | 待开发 | Phase 1 |
| Phase 3 | Materialization engine + artifact / invalidation 主链路 | 待开发 | Phase 1, 2 |
| Phase 4 | Research dataset / spine / availability-time | 待开发 | Phase 1, 2, 3 |
| Phase 5 | Publication orchestration + shadow/certification integration | 部分完成 | Phase 3, 4 |
| Phase 6 | 性能、运维、回归基线与最终硬化 | 待开发 | 全部前置阶段 |

---

## 3. Phase 1: Derived Catalog / Runtime Metadata 基线

**目标:** 先把统一引擎最核心的 metadata 与运行时状态骨架立住，避免后续 query / materialize / publish 各自维护一套状态。

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

**目标:** 落地统一查询链路，让 feature / factor 查询逐步从历史 service 形状过渡到 derived query 语义。

### 范围

1. `DerivedQueryService`
2. query DTO（latest / series / source-scope / as_of）
3. `DerivedQueryFacade`
4. DataHub 与 Port 边界固定

### 推荐文件落点

**DataHub Services**
- Create: `packages/datahub/src/ditto_datahub/services/derived_query_service.py`

**Port Models**
- Create: `apps/port/src/ditto_port/models/derived.py`

**Port Facade**
- Create: `apps/port/src/ditto_port/services/derived/query_facade.py`

**Port Registry**
- Modify: `apps/port/src/ditto_port/registry/datahub/__init__.py`
- Modify: `apps/port/src/ditto_port/registry/datahub/runtime.py`

### 验收标准

1. `latest / series / compare-source slice` 三类查询入口可调用。
2. `FeatureService / FactorService` 不再继续扩历史接口形状。
3. research dataset build 未混入 `DerivedQueryFacade`。

### 验证

1. `pixi run -e dev pytest packages/datahub/tests/unit/services/test_derived_query_service.py -v`
2. `pixi run -e dev pytest apps/port/tests/unit/services/derived/test_query_facade_unit.py -v`

---

## 5. Phase 3: Materialization Engine + Artifact / Invalidation 主链路

**目标:** 打通统一引擎真正的“算出来并写出去”的主干。

### 范围

1. Pratt 表达式编译链与 analyzer 落点
2. run config / execution plan
3. materialize full / incremental
4. artifact metadata 与 invalidation 主链路

### 推荐文件落点

**Core Expression**
- Create: `packages/core/src/ditto_core/engine/expression/lexer.py`
- Create: `packages/core/src/ditto_core/engine/expression/parser.py`
- Create: `packages/core/src/ditto_core/engine/expression/ast.py`
- Create: `packages/core/src/ditto_core/engine/expression/analyzer.py`
- Create: `packages/core/src/ditto_core/engine/expression/codegen.py`

**Core Materialization**
- Create: `packages/core/src/ditto_core/engine/materialization/feature_engine.py`
- Create: `packages/core/src/ditto_core/engine/materialization/factor_engine.py`
- Create: `packages/core/src/ditto_core/engine/materialization/pit.py`
- Create: `packages/core/src/ditto_core/engine/materialization/normalization.py`

**DataHub**
- Create: `packages/datahub/src/ditto_datahub/services/derived_materialization_service.py`
- Create: `packages/datahub/src/ditto_datahub/stores/features/materialized/*`
- Create: `packages/datahub/src/ditto_datahub/stores/factors/materialized/*`

### 验收标准

1. `full` 与 `incremental` 通过同一执行链路运行。
2. artifact metadata 与 catalog run/partition 一致。
3. invalidation 能记录待处理更新。

### 验证

1. `pixi run -e dev pytest packages/core/tests/unit/engine -v`
2. `pixi run -e dev pytest packages/datahub/tests/unit/services/test_derived_materialization_service.py -v`
3. `pixi run -e dev pytest --integration -k derived_materialization`

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

1. **Phase 1**：derived catalog / runtime metadata
2. **Phase 2**：derived query implementation + Port facade
3. **Phase 5 前半段**：把已经完成的 publication safety 基座接入真正的 materialize / publish 主链路
