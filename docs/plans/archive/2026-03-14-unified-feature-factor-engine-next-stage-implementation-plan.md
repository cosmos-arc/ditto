# Unified Feature/Factor Engine Next Stage Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 在已完成的 unified derived query/materialization 基线上，收尾 Phase 3 运行时闭环，落地 Phase 4 research dataset / availability-time 正式能力，并接通 Phase 5 前半段 publication orchestration 主链路。

**Architecture:** 继续采用“Core 定义统一语义与领域模型、DataHub 提供 SQLite/Parquet 控制面与 artifact 访问、Port 负责 facade/flow/orchestration”的分层实现。查询与研究先统一走 artifact 真相层闭环，暂不引入 QuestDB/Kvrocks 热层实现；publication 维持文件制 payload store，但增加 SQLite 编排控制面。

**Tech Stack:** Python 3.13、polars、orjson、SQLite、Parquet、Prefect、pytest、basedpyright、ruff。

---

## Execution Status

### 已完成

- Phase 3 首批闭环已完成：
  - `DerivedArtifactReader` 落地，统一 serving/offline/query/research 的 artifact 读取。
  - `DerivedQueryService` 已切到 artifact-backed `latest / series / compare_sources`。
  - `RuntimeDerivedInputProvider` 已接通 `market.*` 与 `@derived`。
  - 物化成功后已自动持久化 `derived_dependency`，并保留/写入 `availability_time`。
- legacy catalog 一次性迁移已完成：
  - 新增 `LegacyDerivedCatalogMigrationService`。
  - `migrate_legacy_derived_catalog_flow` 已接通到 Port flow。
- Phase 4 research 主链路已完成：
  - Core research 类型与边界约束已补齐。
  - SQLite research control-plane（spec/snapshot）已落地。
  - `ResearchDatasetFacade.build(...)` 已支持 `trading_calendar × universe` spine、primary 版本解析、override、`availability_time <= known_at` 的 left-preserving PIT join、snapshot metadata/manifest hash 持久化。
- 当前已通过的阶段性验证：
  - 目标单测：`30 passed`
  - `ruff check`：通过
  - `basedpyright`：`0 errors, 0 warnings, 0 notes`

### 下阶段待做

- Phase 5 publication orchestration 前半段：
  - 新增 SQLite `derived_shadow_slot` 控制面与对应 reader/writer/service。
  - `materialize` 成功后自动生成 `CompatibilityManifest`、写入 publication record、把 manifest 信息回填到 artifact metadata，并注册/更新 shadow slot。
  - 新增 `DerivedPublicationFacade`，先接通 `shadow_publish / run_shadow_compare / certify / promote` 的最小闭环。
  - 补齐 flow/DI wiring 与对应单测。
- 全量收尾验证：
  - `pixi run -e dev arch-check`
  - `pixi run -e dev check`

## Summary

- 采用 `artifact-first` 收尾策略：`DerivedQueryService` 的 `serving / offline / compare_sources` 都先基于已物化 Parquet artifacts 闭环，热层 QuestDB/Kvrocks 继续留在后续阶段。
- real input backend 首批只做两类真实输入：`market.*` 本地真相层读取，以及 `@derived` 递归读取已物化 artifact；`fundamental / capital / macro` 只预留 adapter seam，不在本批实装。
- Research 控制面正式进入 SQLite；publication payload 继续复用现有文件制 runtime stores，但增加 SQLite 级 shadow slot 协调状态。
- `materialize` 成功后自动生成 `CompatibilityManifest` 并登记 shadow candidate；`dual-read compare / certify / promote` 仍为显式 flow。
- `certify/promote` 本批先以 `manifest + shadow/audit` 为硬门禁，derived-output minimal DQ 作为必接 seam 保留，不在这批补实现。

## Public APIs / Types

- 保持现有 `DerivedQueryFacade` 与 `LatestDerivedRequest / SeriesDerivedRequest / SourceCompareRequest` 对外契约不变，不向公共查询接口暴露 `known_at`。
- `DerivedQueryService` 改为注入真实 artifact backend，不再在 backend-ready 路径上 fail-closed。
- 新增 Core 研究类型：
  - `SpineSpec`
  - `ResearchDatasetSpec`
  - `SpineSnapshot`
  - `DatasetSnapshot`
  - `KnownAtPolicy`
  - `LateArrivalPolicy`
- 新增 Port facade：
  - `ResearchDatasetFacade.build(...)`
  - `DerivedPublicationFacade.shadow_publish(...)`
  - `DerivedPublicationFacade.run_shadow_compare(...)`
  - `DerivedPublicationFacade.certify(...)`
  - `DerivedPublicationFacade.promote(...)`
- 新增显式 one-shot migration 入口：Port CLI/flow 调用 DataHub migration service；不做隐式启动期迁移。

## Implementation Changes

### 1. Phase 3 收尾

- 新增一个 DataHub 级共享 artifact 读取服务，负责：
  - `derived_id + version` 解析
  - 读取 SQLite `derived_partition / derived_state / derived_version`
  - 扫描 Parquet partitions
  - 统一返回 query / research / publication compare 所需 frame
- `DerivedQueryService` 改为真实消费该 reader：
  - `offline`：显式 `version` 优先，否则走 `DerivedState.active_version`
  - `serving`：优先走 `is_primary=True and is_online=True` 的版本；若当前还没有 primary，则临时回退到 `active_version`
  - `compare_sources`：比较 serving-resolved 与 offline-resolved 两个 slice，底层都读 artifact
- 替换 `UnavailableDerivedInputProvider`：
  - `market.*` v1 固定映射到 `cn_stock` 日频真相层
  - 数据集依赖按稳定根引用持久化：`market.stock_daily`、`market.adj_factor`、`market.stock_status`
  - `@derived` 依赖读取上游 artifact，并记录真实上游 `derived_id`
- `DerivedMaterializationService` 在成功物化时自动持久化依赖边：
  - dataset 依赖写入 `derived_dependency`
  - upstream derived 依赖写入 `derived_dependency`
  - invalidation repair 从真实依赖图展开，不再依赖测试手工 seed
- durable artifact 新增/保留 `availability_time`：
  - v1 market 输入默认 `availability_time == trade_date`
  - 递归 `@derived` 输入优先保留上游已有 `availability_time`
- 实现 idempotent one-shot migration：
  - 读取 `data_root/derived/catalog/` 下 legacy JSON
  - 迁移 `spec / version / run / state / partition`
  - 源目录不存在或目标已有记录时 no-op
  - 不做双写，不保留长期兼容层

### 2. Phase 4 Research Dataset / Spine / Availability-Time

- `SpineSpec` 的 v1 左表来源固定为 `trading_calendar × universe`：
  - 仅支持 `cn_stock`
  - 仅支持 `1d`
  - 仅支持单 `instrument_id`
  - 不支持任意 SQL / 任意数据集驱动 spine
- SQLite 新增 research 控制面表：
  - `research_spine_spec`
  - `research_dataset_spec`
  - `research_spine_snapshot`
  - `research_dataset_snapshot`
- 研究产物目录固定为不可变 snapshot 目录：
  - `data_root/derived/research/spines/<spine_id>/snapshots/<spine_snapshot_id>/...`
  - `data_root/derived/research/datasets/<dataset_id>/snapshots/<snapshot_id>/...`
- `ResearchDatasetSpec` v1 只允许引用 derived IDs：
  - 默认解析到当前 primary 版本
  - build 请求可带 explicit overrides
  - 一旦进入 `DatasetSnapshot`，必须冻结成精确版本与源快照
- PIT join 规则固定：
  - `join_policy = left_preserving_pit`
  - `known_at_policy = sample_time` 为默认
  - `explicit_cutoff` 由 build 请求提供并写入 snapshot
  - join 条件始终为 `availability_time <= known_at`
  - 缺失命中保留左表行并记为 null，不缩样本基数
- `availability_time / known_at` 只进入 research 链路与 snapshot metadata：
  - 不改公共 query DTO
  - 缺失 `availability_time` 的输入统一按 `event_time` 归一

### 3. Phase 5 前半段 Publication Orchestration

- 保留现有文件制 publication runtime stores：
  - manifest
  - shadow diff / trace
  - certification
- 新增 SQLite `derived_shadow_slot` 作为编排控制面：
  - 每个 `derived_id` 最多一个 active shadow candidate
  - 记录 `candidate_version / baseline_version / activated_at / disabled_at`
- materialize 成功后的自动动作固定为：
  - 生成 `CompatibilityManifest`
  - 写入 publication record service
  - 把 manifest hash/payload 写入当次 artifact metadata
  - 注册或更新 shadow slot
- `run_shadow_compare` 为显式 batch audit：
  - 不接实时镜像流量
  - 基于 candidate / baseline 覆盖窗口生成共享请求上下文
  - 通过共享 artifact reader 做 candidate-vs-baseline 双读
  - `SERIES / STATE / DERIVE` 默认要求 shadow diff；`OFFLINE` 允许等价 sample audit
- `certify` 为显式 gate：
  - 生成 `shadow_ready / publish_ready`
  - 当前输入固定消费 `CompatibilityManifest + ShadowDiffReport`
  - derived-output minimal DQ 作为必接 seam 预留，不在本批实装
- `promote` 为显式原子操作：
  - 前置：materialized、manifest 完整、最近一次 `publish_ready` 通过、最近一次 shadow/audit 通过
  - 行为：candidate 版本置为 `PUBLISHED`、`is_online=True`、`is_primary=True`
  - 旧 primary 仅取消 `is_primary`，状态保持 `PUBLISHED`
  - `rollback / deprecate` 不纳入这批

## Test Plan

- 单元测试：
  - legacy catalog migration 映射与幂等
  - artifact-backed `latest / series / compare_sources`
  - `market.* + @derived` 输入加载与依赖持久化
  - `availability_time / known_at` PIT join
  - `DatasetSnapshot` 不可变与 manifest hash
  - shadow slot 唯一性
  - certification 严重级别汇总
  - promote 指针切换
- 集成测试：
  - `materialize -> query -> invalidation repair`
  - legacy JSON catalog -> SQLite migration -> query
  - `spine build -> dataset snapshot`
  - `materialize -> manifest -> shadow compare -> certify -> promote`
- 最终验证：
  - `pixi run -e dev arch-check`
  - `pixi run -e dev check`

## Assumptions

- 本批继续坚持 `cn_stock`、`1d`、单 `instrument_id` 边界，不扩 `1m`、复合键、多市场。
- 公共查询接口不新增 `known_at`、`availability_time` 参数。
- artifact-first serving 是本批的有意实现策略，不是终局热层替代。
- research metadata 进 SQLite；publication payload 继续文件制。
- `manifest + shadow/audit` 是本批 certify/promote 的硬门禁；derived-output minimal DQ 留为下一条 seam。
