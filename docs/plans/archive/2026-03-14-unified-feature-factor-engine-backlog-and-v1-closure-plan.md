# Unified Feature/Factor Engine Backlog and V1 Closure Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 在当前 artifact-first unified derived engine 基础上，补齐 research / publication / integration / hardening 的剩余关键能力，使系统从“主链可运行”推进到“可稳定发布、可复现研究、可持续演进”的 v1.1 完整态。

**Architecture:** 继续坚持“Core 定义语义与规则、DataHub 负责控制面与持久化、Port 负责 facade / flow / orchestration”的分层。后续执行优先关闭设计与代码之间的 correctness gap，再补运营出口与集成验证，最后进入性能、SLO 与热层演进，避免一边扩范围一边放大治理缺口。

**Tech Stack:** Python 3.13、polars、orjson、SQLite、Parquet、Prefect、pytest、basedpyright、ruff。

---

## 1. 当前基线

### 执行状态

### 已完成阶段

1. `Task 1: 对齐 Research Snapshot 契约` 已完成：
   - `LateArrivalPolicy` 已对齐 ADR-041，默认值改为 `require_rebuild`
   - `DatasetSnapshot` / `ResearchDatasetSnapshotRecord` 已补齐
     - `dataset_spec_version`
     - `resolved_inputs`
     - `source_snapshot_ids`
     - `effective_cutoff`
     - `builder_version`
   - `research_dataset_snapshot` SQLite schema / reader / writer 已同步扩展
   - `ResearchDatasetFacade.build(...)` 已冻结 artifact 路径与上游 source snapshot ids
   - 已新增 research SQLite store unit test，并补充 research facade 契约测试
2. `Task 1` 验证结果：
   - `pixi run -e dev pytest -n0 --no-cov packages/core/tests/unit/engine/test_research_unit.py packages/datahub/tests/unit/stores/runtime/research_sqlite/test_research_catalog_store_unit.py apps/port/tests/unit/services/derived/test_research_dataset_facade_unit.py -v`
     - 结果：`9 passed`
   - `pixi run -e dev ruff check ...`
     - 结果：`All checks passed!`
   - `pixi run -e dev basedpyright ...`
     - 结果：`0 errors, 0 warnings, 0 notes`
3. `Task 2: 增加 Research Build Flow 与 Build Report` 已完成：
   - 已新增 `research_dataset_build_flow(...)`，通过 `MaterializationBundle` 暴露 `ResearchDatasetFacade`
   - `ResearchDatasetFacade.build(...)` 现在会落盘 `build_report.json`
   - build report 已覆盖
     - `row_count`
     - `spine_row_count`
     - `null_counts`
     - `resolved_versions`
     - `known_at_policy`
     - `effective_cutoff`
     - `source_snapshot_ids`
     - `builder_version`
   - 已补充 flow unit test、research facade build report unit test、research flow integration test
4. `Task 2` 验证结果：
   - `pixi run -e dev pytest -n0 --no-cov apps/port/tests/unit/jobs/flows/test_research_flows_unit.py apps/port/tests/unit/services/derived/test_research_dataset_facade_unit.py -v`
     - 结果：`6 passed`
   - `pixi run -e dev pytest -n0 --no-cov apps/port/tests/integration/flows/test_research_dataset_integration.py -v`
     - 结果：`1 passed`
   - `pixi run -e dev ruff check ...`
     - 结果：`All checks passed!`
   - `pixi run -e dev basedpyright ...`
     - 结果：`0 errors, 0 warnings, 0 notes`
   - 备注：当前 dev 环境里的 Prefect ephemeral server 因缺少 `lupa` 无法启动，因此 research flow integration test 改为调用真实 `Flow.fn(...)`，保留 flow wiring / container / artifact/report 落盘的集成覆盖，同时避开环境依赖噪音。
5. `Task 3: 引入 Derived Minimal DQ Summary` 已完成：
   - Core 已新增 `DerivedMinimalDQSummary`
   - DataHub 已新增 `DerivedMinimalDQSummaryRecord` 与 file-based `MinimalDQReader / MinimalDQWriter`
   - `PublicationSafetyRecordService` 已扩展 minimal DQ 读写接口，并收敛为 `PublicationSafetyRuntimeStores` bundle
   - `DerivedMaterializationService` 现在会在 durable materialization 后生成 minimal DQ summary，并持久化到
     - publication safety runtime store
     - artifact metadata `publication.minimal_dq_summary`
   - 当前最小检查已经覆盖
     - `row_count > 0`
     - 主键列存在且非空
     - 主键无重复
     - `value` 存在、至少有可计算行、且不含 `NaN`
   - 语义上已避免把正常 warm-up 边界 `null` 误判成失败
6. `Task 3` 验证结果：
   - `pixi run -e dev pytest -n0 --no-cov packages/datahub/tests/unit/stores/runtime/publication_safety/test_minimal_dq_store_unit.py packages/datahub/tests/unit/services/test_derived_materialization_service_unit.py packages/datahub/tests/unit/services/test_publication_safety_record_service.py apps/port/tests/unit/services/derived/test_publication_facade_unit.py apps/port/tests/registry/test_derived_provider_unit.py -v`
     - 结果：`22 passed`
   - `pixi run -e dev ruff check ...`
     - 结果：`All checks passed!`
   - `pixi run -e dev basedpyright ...`
     - 结果：`0 errors, 0 warnings, 0 notes`
7. `Task 4: 让 Certification 真正消费 DQ + Role/Profile Rules` 已完成：
   - `DerivedPublicationFacade.certify(...)` 已切到 `publication_rules.py` 统一组装 stage / role / profile checks
   - `shadow_ready` 现已显式消费
     - `minimal_dq_passed`
     - `manifest_complete`
   - `publish_ready` 现已显式消费
     - `shadow_ready_passed`
     - `shadow_diff_passed` 或 `sample_audit_passed`
     - `factor_distribution_stability`
     - `series_shadow_parity`
     - `offline_dataset_reproducibility`
   - `CertificationPack.check_names` 已反映第一批 role/profile pack 语义，不再只是占位壳
8. `Task 4` 验证结果：
   - `pixi run -e dev pytest -n0 --no-cov apps/port/tests/unit/services/derived/test_publication_facade_unit.py packages/datahub/tests/unit/services/test_publication_safety_record_service.py apps/port/tests/registry/test_derived_provider_unit.py -v`
     - 结果：`16 passed`
   - `pixi run -e dev ruff check apps/port/src/ditto_port/services/derived/publication.py apps/port/src/ditto_port/services/derived/publication_rules.py apps/port/tests/unit/services/derived/test_publication_facade_unit.py`
     - 结果：`All checks passed!`
   - `pixi run -e dev basedpyright apps/port/src/ditto_port/services/derived/publication.py apps/port/src/ditto_port/services/derived/publication_rules.py`
     - 结果：`0 errors, 0 warnings, 0 notes`
9. `Task 5: 补全 Publication Lifecycle 的操作面` 已完成：
   - `DerivedPublicationFacade` 已新增
     - `rollback(...)`
     - `deprecate(...)`
   - publication flow 层已新增
     - `shadow_publish_flow`
     - `rollback_publication_flow`
     - `deprecate_publication_flow`
   - `rollback` 现已复用 primary pointer model，只移动 primary 指针，不重物化
   - `deprecate` 现已只修改版本可见性与状态，不删除已生成 artifact
10. `Task 5` 验证结果：
   - `pixi run -e dev pytest -n0 --no-cov apps/port/tests/unit/jobs/flows/test_materialization_flows_unit.py apps/port/tests/unit/services/derived/test_publication_facade_unit.py -v`
     - 结果：`17 passed`
   - `pixi run -e dev ruff check apps/port/src/ditto_port/services/derived/publication.py apps/port/src/ditto_port/jobs/flows/materialization.py apps/port/src/ditto_port/jobs/flows/__init__.py apps/port/tests/unit/jobs/flows/test_materialization_flows_unit.py apps/port/tests/unit/services/derived/test_publication_facade_unit.py`
     - 结果：`All checks passed!`
   - `pixi run -e dev basedpyright apps/port/src/ditto_port/services/derived/publication.py apps/port/src/ditto_port/jobs/flows/materialization.py apps/port/src/ditto_port/jobs/flows/__init__.py`
     - 结果：`0 errors, 0 warnings, 0 notes`
11. `Task 6: 补齐专项 Integration Tests` 已完成：
   - 已补齐并跑通四条专项链路
     - `legacy JSON catalog -> SQLite migration -> artifact query`
     - `materialize -> query -> invalidation repair`
     - `spine build -> dataset snapshot`
     - `materialize -> manifest -> shadow compare -> certify -> promote`
   - 其中 `research dataset integration` 为前序阶段已落地，本阶段将其纳入专项回归并与另外三条链路一起收口
12. `Task 6` 验证结果：
   - `pixi run -e dev pytest -n0 --no-cov packages/datahub/tests/integration/runtime/test_legacy_derived_catalog_migration_query_integration.py apps/port/tests/integration/flows/test_derived_materialization_query_repair_integration.py apps/port/tests/integration/flows/test_research_dataset_integration.py apps/port/tests/integration/flows/test_derived_publication_integration.py -v`
     - 结果：`4 passed`
   - `pixi run -e dev ruff check --fix packages/datahub/tests/integration/runtime/test_legacy_derived_catalog_migration_query_integration.py apps/port/tests/integration/flows/test_derived_materialization_query_repair_integration.py apps/port/tests/integration/flows/test_research_dataset_integration.py apps/port/tests/integration/flows/test_derived_publication_integration.py`
     - 结果：`All checks passed!`
   - `pixi run -e dev basedpyright packages/datahub/tests/integration/runtime/test_legacy_derived_catalog_migration_query_integration.py apps/port/tests/integration/flows/test_derived_materialization_query_repair_integration.py apps/port/tests/integration/flows/test_research_dataset_integration.py apps/port/tests/integration/flows/test_derived_publication_integration.py`
     - 结果：`0 errors, 0 warnings, 0 notes`
   - 扩面回归备注：
     - `pixi run -e dev pytest apps/port/tests/integration/flows -m integration -v` 暴露既有 `Prefect ephemeral server` 启动失败，集中在 `test_helpers_integration.py`，不属于本阶段新增链路
     - `pixi run -e dev pytest packages/datahub/tests/integration/runtime -m integration -v` 暴露既有 `sql_engine` / `sql_engine_injection` runtime integration 失败；本阶段新增的 `legacy migration query` 用例已通过
13. `Task 7: 进入 Phase 6 硬化` 已完成：
   - 已新增 `scripts/benchmarks/derived_benchmark.py`，固化 `query / materialize / shadow_compare` 三类 synthetic benchmark harness 与 regression budget
   - 已新增 `packages/core/tests/benchmarks/test_derived_benchmarks.py`，覆盖 workload 定义、budget 约束与 `S` 规模 smoke benchmark
   - [ADR-037](../design/unified-feature-factor-engine/decisions/adr-037-performance-slo.md) 已回写本地 `S / M / L` baseline 与 CI gate matrix
   - 已新增 [2026-03-14-unified-feature-factor-engine-phase-6-hardening-plan.md](./2026-03-14-unified-feature-factor-engine-phase-6-hardening-plan.md)，把 Phase 6 拆到 `H1-H4`
   - 为确保 dev 环境下的 fast/unit suite 稳定运行，已把受影响的 flow/task 单测统一切到 `Flow.fn(...)` / `Task.fn(...)` runner，避开 `Prefect ephemeral server` 对 `lupa` 的环境依赖噪音
14. `Task 7` 验证结果：
   - `pixi run -e dev pytest -n0 --no-cov packages/core/tests/benchmarks/test_derived_benchmarks.py -v`
     - 结果：`5 passed`
   - `pixi run -e dev ruff check scripts/benchmarks/derived_benchmark.py packages/core/tests/benchmarks/test_derived_benchmarks.py`
     - 结果：`All checks passed!`
   - `pixi run -e dev basedpyright scripts/benchmarks/derived_benchmark.py packages/core/tests/benchmarks/test_derived_benchmarks.py`
     - 结果：`0 errors, 0 warnings, 0 notes`
   - `pixi run -e dev pytest -m 'not slow and not integration and not snapshot' --no-cov -n auto --dist loadfile --maxfail=1 -q`
     - 结果：`2047 passed in 24.40s`
   - `pixi run -e dev check`
     - 结果：`PASS`
   - `pixi run -e dev arch-check`
     - 结果：`6 kept, 0 broken`

### 当前进行中

1. 无。本计划内 `Task 1-Task 7` 已全部完成，后续工作转入下方 v1.1 backlog。

---

### 已完成

1. unified derived query 已切到 artifact-backed 主链。
2. materialization 已接通 `market.*` 与 `@derived` 真实输入。
3. `derived_dependency`、`availability_time`、legacy catalog migration 已落地。
4. research dataset v1 主链已落地，支持 spine、PIT join、snapshot 持久化。
5. publication orchestration v1 已落地，支持 manifest、minimal DQ、shadow publish、shadow compare、certify、promote、rollback、deprecate。
6. Phase 6 的 benchmark harness、local baseline、ADR-037 gate matrix 与 hardening plan 已落地。
7. `pixi run -e dev arch-check` 与 `pixi run -e dev check` 已通过。

### 当前仍未封板

1. 当前 certification pack 已具备第一批 role/profile 规则，但还不是完整治理体系。
2. `apps/port/tests/integration/flows` 与 `packages/datahub/tests/integration/runtime` 目录级回归仍有既有失败，主要集中在 `Prefect ephemeral server` 与 `sql_engine` 链路。
3. research 已有标准 build flow，但 CLI/API/schedule 出口仍未落地。
4. Phase 6 的第一阶段 benchmark / SLO baseline 已落地，但 `retention / rebuild / DR / housekeeping` 尚未开始。
5. publication 侧仍缺更完整的 operator-facing summary / sample audit summary。
6. QuestDB / Kvrocks hot layer 仍是后续阶段。

---

## 2. 优先级 Backlog

### P0: 必须先补的 correctness / release gap

1. **Research 契约对齐 ADR-041**
   - 现状：`late_arrival_policy` 仍是占位实现，`DatasetSnapshot` 缺 `dataset_spec_version`、`resolved_inputs`、`source_snapshot_ids`、`effective_cutoff`、`builder_version` 等关键字段。
   - 风险：研究数据集虽然可构建，但还不够“精确版本绑定、可复现、可审计”。
   - 完成定义：Research snapshot 元数据与 ADR-041 对齐，SQLite / metadata 文件 / facade 返回值一致。

2. **[已完成] 让 publication gate 消费 derived minimal DQ**
   - 当前状态：minimal DQ summary 已在 materialize 后生成并持久化，`shadow_ready` / `publish_ready` 也已显式消费它。
   - 剩余收尾：还需在 publication chain integration tests 与 operator-facing summary 中继续补证据面。

3. **[已完成] Role/Profile Certification Pack 第一阶段落地**
   - 当前状态：`CertificationPack` 已承载 `shadow_ready + diff/audit + role/profile` 的第一批规则化检查项。
   - 剩余收尾：仍需把更完整的 profile family、operator-facing evidence 与更细颗粒规则补齐。

4. **[已完成] 专项 integration tests 补齐**
   - 当前状态：四条计划内专项链路均已落地并通过 targeted integration tests。
   - 剩余收尾：更大范围的 integration 目录仍存在既有 `Prefect` 与 `sql_engine` 噪音，需要在后续独立清理。

### P1: 直接提升可操作性的运营化工作

5. **Research build 运营出口补全**
   - 现状：research dataset build flow 已有，但 CLI/API/schedule 入口仍缺。
   - 完成定义：research dataset build 具备 CLI/API 或调度入口，并延续当前 build report 输出。

6. **[已完成] Publication 生命周期补全**
   - 当前状态：`shadow_publish / compare / certify / promote / rollback / deprecate` 已具备 facade + flow + 测试。
   - 剩余收尾：仍需把 publication summary / sample audit summary 与 integration coverage 补齐。

7. **Publication 报告可读性增强**
   - 现状：research build report 已落地，但 publication 侧仍缺 sample audit summary 与更明确的 operator-facing 输出。
   - 完成定义：publication summary / sample audit summary 能被 flow 返回并落盘。

### P2: v1.1 之后的硬化与演进

8. **[进行中] Phase 6 benchmark / SLO / regression budget**
   - 当前状态：benchmark harness、local baseline、ADR-037 gate matrix 与 Phase 6 hardening plan 已落地。
   - 剩余收尾：把 `H2-H4` 的 retention / rebuild / DR / housekeeping 真正落到实现与回归。
9. **Retention / rebuild / DR / housekeeping**
10. **Hot layer: QuestDB / Kvrocks 正式接入 serving 与 state**

### Deferred: 设计已明确延期

1. `grain="1m"` 全链路支持
2. 复合键
3. 多市场
4. request-time derived features

---

## 3. 推荐执行顺序

1. 先做 P0-1 与 P0-2，关闭 research / publication 的 correctness gap。
2. 再做 P0-3，把 certification 从“最小闭环”提升到“规则化 gate”。
3. 然后做 P1-5 与 P1-6，补 research / publication 的标准操作入口。
4. 最后补 P0-4 integration tests，把主链能力真正封板。
5. Phase 6 与 hot layer 放到 v1.1 封板之后执行。

---

## 4. 可直接执行的详细计划

### Task 1: 对齐 Research Snapshot 契约

**Files:**
- Modify: `packages/core/src/ditto_core/engine/research.py`
- Modify: `packages/datahub/src/ditto_datahub/models/research.py`
- Modify: `packages/datahub/src/ditto_datahub/scripts/schema.sql`
- Modify: `packages/datahub/src/ditto_datahub/stores/runtime/research_sqlite/reader.py`
- Modify: `packages/datahub/src/ditto_datahub/stores/runtime/research_sqlite/writer.py`
- Modify: `apps/port/src/ditto_port/services/derived/research.py`
- Test: `packages/core/tests/unit/engine/test_research_unit.py`
- Test: `apps/port/tests/unit/services/derived/test_research_dataset_facade_unit.py`
- Create: `packages/datahub/tests/unit/stores/runtime/research_sqlite/test_research_catalog_store_unit.py`

**Step 1: Write the failing tests**

1. 在 `test_research_unit.py` 增加：
   - `test_late_arrival_policy_defaults_to_require_rebuild`
   - `test_dataset_snapshot_requires_precise_snapshot_contract_fields`
2. 在 `test_research_dataset_facade_unit.py` 增加：
   - `test_build_persists_dataset_spec_version_and_resolved_inputs`
   - `test_build_persists_effective_cutoff_and_source_snapshot_ids`
3. 新增 `test_research_catalog_store_unit.py`，覆盖新增 SQLite 字段 round-trip。

**Step 2: Run tests to verify they fail**

Run:

```bash
pixi run -e dev pytest -n0 --no-cov \
  packages/core/tests/unit/engine/test_research_unit.py \
  packages/datahub/tests/unit/stores/runtime/research_sqlite/test_research_catalog_store_unit.py \
  apps/port/tests/unit/services/derived/test_research_dataset_facade_unit.py -v
```

Expected: FAIL，提示缺少新字段、枚举值不匹配或 SQLite schema 不一致。

**Step 3: Write the minimal implementation**

1. 将 `LateArrivalPolicy` 改为 ADR-041 对齐的枚举：
   - `exclude_from_current_snapshot`
   - `shift_to_next_snapshot`
   - `require_rebuild`
2. 扩展 `DatasetSnapshot` 与 `ResearchDatasetSnapshotRecord`：
   - `dataset_spec_version`
   - `resolved_inputs`
   - `source_snapshot_ids`
   - `effective_cutoff`
   - `builder_version`
3. 更新 research SQLite schema / reader / writer。
4. 在 `ResearchDatasetFacade.build(...)` 中：
   - 冻结精确 `resolved_inputs`
   - 持久化 `effective_cutoff`
   - 将底层 `source_snapshot_ids` 统一写入 metadata
   - 将 builder 版本写入 snapshot metadata

**Step 4: Run tests to verify they pass**

Run the same pytest command, then:

```bash
pixi run -e dev basedpyright \
  packages/core/src/ditto_core/engine/research.py \
  packages/datahub/src/ditto_datahub/models/research.py \
  packages/datahub/src/ditto_datahub/stores/runtime/research_sqlite \
  apps/port/src/ditto_port/services/derived/research.py
```

Expected: PASS，且类型检查无告警。

**Step 5: Commit**

```bash
git add packages/core/src/ditto_core/engine/research.py \
  packages/datahub/src/ditto_datahub/models/research.py \
  packages/datahub/src/ditto_datahub/scripts/schema.sql \
  packages/datahub/src/ditto_datahub/stores/runtime/research_sqlite \
  apps/port/src/ditto_port/services/derived/research.py \
  packages/core/tests/unit/engine/test_research_unit.py \
  packages/datahub/tests/unit/stores/runtime/research_sqlite/test_research_catalog_store_unit.py \
  apps/port/tests/unit/services/derived/test_research_dataset_facade_unit.py
git commit -m "feat: align research snapshot contract with adr 041"
```

### Task 2: 增加 Research Build Flow 与 Build Report

**Files:**
- Create: `apps/port/src/ditto_port/jobs/flows/research.py`
- Modify: `apps/port/src/ditto_port/jobs/flows/__init__.py`
- Modify: `apps/port/src/ditto_port/services/derived/research.py`
- Test: `apps/port/tests/unit/jobs/flows/test_research_flows_unit.py`
- Create: `apps/port/tests/integration/flows/test_research_dataset_integration.py`

**Step 1: Write the failing tests**

1. 在 `test_research_flows_unit.py` 增加：
   - `test_research_dataset_build_flow_delegates_to_facade`
   - `test_research_dataset_build_flow_returns_snapshot_and_summary`
2. 新增 `test_research_dataset_integration.py`：
   - 构造 spine spec + dataset spec + materialized artifacts
   - 验证 flow 能产出 snapshot、metadata、build summary

**Step 2: Run tests to verify they fail**

Run:

```bash
pixi run -e dev pytest -n0 --no-cov \
  apps/port/tests/unit/jobs/flows/test_research_flows_unit.py \
  apps/port/tests/integration/flows/test_research_dataset_integration.py -v
```

Expected: FAIL，提示 flow 或 summary 尚不存在。

**Step 3: Write the minimal implementation**

1. 新增 `research_dataset_build_flow(...)`。
2. flow 直接调用 `ResearchDatasetFacade.build(...)`。
3. 在 facade 中补最小 `build_report`：
   - `row_count`
   - `spine_row_count`
   - `null_counts`
   - `resolved_versions`
   - `known_at_policy`
4. flow 返回 `snapshot + summary`，并把 report 落到 snapshot 目录。

**Step 4: Run tests to verify they pass**

Run the same pytest command, then:

```bash
pixi run -e dev ruff check \
  apps/port/src/ditto_port/jobs/flows/research.py \
  apps/port/src/ditto_port/services/derived/research.py \
  apps/port/tests/unit/jobs/flows/test_research_flows_unit.py \
  apps/port/tests/integration/flows/test_research_dataset_integration.py
```

Expected: PASS。

**Step 5: Commit**

```bash
git add apps/port/src/ditto_port/jobs/flows/research.py \
  apps/port/src/ditto_port/jobs/flows/__init__.py \
  apps/port/src/ditto_port/services/derived/research.py \
  apps/port/tests/unit/jobs/flows/test_research_flows_unit.py \
  apps/port/tests/integration/flows/test_research_dataset_integration.py
git commit -m "feat: add research dataset build flow"
```

### Task 3: 引入 Derived Minimal DQ Summary

**Files:**
- Modify: `packages/core/src/ditto_core/engine/publication_safety.py`
- Modify: `packages/datahub/src/ditto_datahub/models/publication_safety.py`
- Modify: `packages/datahub/src/ditto_datahub/services/publication_safety_record_service.py`
- Create: `packages/datahub/src/ditto_datahub/stores/runtime/publication_safety/minimal_dq_reader.py`
- Create: `packages/datahub/src/ditto_datahub/stores/runtime/publication_safety/minimal_dq_writer.py`
- Modify: `packages/datahub/src/ditto_datahub/stores/runtime/publication_safety/__init__.py`
- Modify: `apps/port/src/ditto_port/registry/datahub/runtime.py`
- Modify: `apps/port/src/ditto_port/services/derived/materialization.py`
- Test: `packages/datahub/tests/unit/services/test_derived_materialization_service_unit.py`
- Create: `packages/datahub/tests/unit/stores/runtime/publication_safety/test_minimal_dq_store_unit.py`

**Step 1: Write the failing tests**

1. 新增 `test_minimal_dq_store_unit.py`，覆盖 DQ summary round-trip。
2. 在 `test_derived_materialization_service_unit.py` 增加：
   - `test_durable_materialization_persists_minimal_dq_summary`
   - `test_empty_or_invalid_output_is_marked_as_failed_minimal_dq`

**Step 2: Run tests to verify they fail**

Run:

```bash
pixi run -e dev pytest -n0 --no-cov \
  packages/datahub/tests/unit/stores/runtime/publication_safety/test_minimal_dq_store_unit.py \
  packages/datahub/tests/unit/services/test_derived_materialization_service_unit.py -v
```

Expected: FAIL，提示缺少 DQ summary 模型与持久化。

**Step 3: Write the minimal implementation**

1. 在 Core 增加 `DerivedMinimalDQSummary`。
2. 最小检查先固定为：
   - `row_count > 0`
   - 主键列非空
   - `value` 可计算且非 NaN
   - 主键不重复
3. 在 materialization 成功后生成并持久化 DQ summary。
4. 通过 `PublicationSafetyRecordService` 暴露读写接口。

**Step 4: Run tests to verify they pass**

Run the same pytest command, then:

```bash
pixi run -e dev basedpyright \
  packages/core/src/ditto_core/engine/publication_safety.py \
  packages/datahub/src/ditto_datahub/models/publication_safety.py \
  packages/datahub/src/ditto_datahub/stores/runtime/publication_safety \
  apps/port/src/ditto_port/services/derived/materialization.py
```

Expected: PASS。

**Step 5: Commit**

```bash
git add packages/core/src/ditto_core/engine/publication_safety.py \
  packages/datahub/src/ditto_datahub/models/publication_safety.py \
  packages/datahub/src/ditto_datahub/services/publication_safety_record_service.py \
  packages/datahub/src/ditto_datahub/stores/runtime/publication_safety \
  apps/port/src/ditto_port/registry/datahub/runtime.py \
  apps/port/src/ditto_port/services/derived/materialization.py \
  packages/datahub/tests/unit/stores/runtime/publication_safety/test_minimal_dq_store_unit.py \
  packages/datahub/tests/unit/services/test_derived_materialization_service_unit.py
git commit -m "feat: persist derived minimal dq summary"
```

### Task 4: 让 Certification 真正消费 DQ + Role/Profile Rules

**Files:**
- Modify: `packages/core/src/ditto_core/engine/publication_safety.py`
- Create: `apps/port/src/ditto_port/services/derived/publication_rules.py`
- Modify: `apps/port/src/ditto_port/services/derived/publication.py`
- Test: `apps/port/tests/unit/services/derived/test_publication_facade_unit.py`

**Step 1: Write the failing tests**

1. 在 `test_publication_facade_unit.py` 增加：
   - `test_shadow_ready_requires_manifest_and_minimal_dq`
   - `test_publish_ready_requires_shadow_diff_and_profile_rules`
   - `test_offline_profile_uses_sample_audit_instead_of_shadow_diff`
   - `test_factor_series_pack_includes_distribution_and_parity_checks`

**Step 2: Run tests to verify they fail**

Run:

```bash
pixi run -e dev pytest -n0 --no-cov \
  apps/port/tests/unit/services/derived/test_publication_facade_unit.py -v
```

Expected: FAIL，提示缺少 DQ 依赖、pack rule 或 OFFLINE audit 逻辑。

**Step 3: Write the minimal implementation**

1. 新建 `publication_rules.py`，集中实现：
   - `role 基础包`
   - `profile 增补包`
   - stage 级检查组合
2. `shadow_ready` 至少消费：
   - minimal DQ
   - manifest complete
3. `publish_ready` 至少消费：
   - `shadow_ready`
   - shadow diff 或 OFFLINE sample audit
   - 第一批 profile-specific checks
4. `DerivedPublicationFacade.certify(...)` 改为通过 rule builder 组装 `CertificationPack`。

**Step 4: Run tests to verify they pass**

Run the same pytest command, then:

```bash
pixi run -e dev ruff check \
  apps/port/src/ditto_port/services/derived/publication.py \
  apps/port/src/ditto_port/services/derived/publication_rules.py \
  apps/port/tests/unit/services/derived/test_publication_facade_unit.py
```

Expected: PASS。

**Step 5: Commit**

```bash
git add packages/core/src/ditto_core/engine/publication_safety.py \
  apps/port/src/ditto_port/services/derived/publication_rules.py \
  apps/port/src/ditto_port/services/derived/publication.py \
  apps/port/tests/unit/services/derived/test_publication_facade_unit.py
git commit -m "feat: enforce dq and certification pack rules"
```

### Task 5: 补全 Publication Lifecycle 的操作面

**Files:**
- Modify: `apps/port/src/ditto_port/services/derived/publication.py`
- Modify: `apps/port/src/ditto_port/jobs/flows/materialization.py`
- Modify: `apps/port/src/ditto_port/jobs/flows/__init__.py`
- Test: `apps/port/tests/unit/jobs/flows/test_materialization_flows_unit.py`
- Test: `apps/port/tests/unit/services/derived/test_publication_facade_unit.py`

**Step 1: Write the failing tests**

1. 增加：
   - `test_shadow_publish_flow_delegates_to_publication_facade`
   - `test_rollback_flow_switches_primary_to_previous_version`
   - `test_deprecate_flow_marks_candidate_offline`
2. 在 facade 单测中增加：
   - `test_rollback_reuses_existing_primary_pointer_model`
   - `test_deprecate_does_not_delete_candidate_artifacts`

**Step 2: Run tests to verify they fail**

Run:

```bash
pixi run -e dev pytest -n0 --no-cov \
  apps/port/tests/unit/jobs/flows/test_materialization_flows_unit.py \
  apps/port/tests/unit/services/derived/test_publication_facade_unit.py -v
```

Expected: FAIL，提示 flow / facade 方法不存在。

**Step 3: Write the minimal implementation**

1. 在 `DerivedPublicationFacade` 中新增：
   - `rollback(...)`
   - `deprecate(...)`
2. 在 flow 中新增：
   - `shadow_publish_flow`
   - `rollback_publication_flow`
   - `deprecate_publication_flow`
3. `rollback` 复用 primary pointer model，不重物化。
4. `deprecate` 只修改版本可见性，不删除 artifact。

**Step 4: Run tests to verify they pass**

Run the same pytest command, then:

```bash
pixi run -e dev basedpyright \
  apps/port/src/ditto_port/services/derived/publication.py \
  apps/port/src/ditto_port/jobs/flows/materialization.py
```

Expected: PASS。

**Step 5: Commit**

```bash
git add apps/port/src/ditto_port/services/derived/publication.py \
  apps/port/src/ditto_port/jobs/flows/materialization.py \
  apps/port/src/ditto_port/jobs/flows/__init__.py \
  apps/port/tests/unit/jobs/flows/test_materialization_flows_unit.py \
  apps/port/tests/unit/services/derived/test_publication_facade_unit.py
git commit -m "feat: complete publication lifecycle operations"
```

### Task 6: 补齐四条专项 Integration Tests

**Files:**
- Create: `packages/datahub/tests/integration/runtime/test_legacy_derived_catalog_migration_query_integration.py`
- Create: `apps/port/tests/integration/flows/test_derived_materialization_query_repair_integration.py`
- Create: `apps/port/tests/integration/flows/test_research_dataset_integration.py`
- Create: `apps/port/tests/integration/flows/test_derived_publication_integration.py`

**Step 1: Write the failing tests**

1. migration -> query
2. materialize -> query -> invalidation repair
3. spine build -> dataset snapshot
4. materialize -> manifest -> shadow compare -> certify -> promote

**Step 2: Run tests to verify they fail**

Run:

```bash
pixi run -e dev pytest -n0 --no-cov \
  packages/datahub/tests/integration/runtime/test_legacy_derived_catalog_migration_query_integration.py \
  apps/port/tests/integration/flows/test_derived_materialization_query_repair_integration.py \
  apps/port/tests/integration/flows/test_research_dataset_integration.py \
  apps/port/tests/integration/flows/test_derived_publication_integration.py -v
```

Expected: FAIL，直到主链 fixture、flow surface 与持久化行为全部连通。

**Step 3: Write the minimal implementation**

1. 优先复用已有 unit fixture 与 bundle/container wiring。
2. 所有 integration test 都使用 schema-initialized SQLite + 临时 data_root。
3. 明确只覆盖当前 v1 边界：
   - `cn_stock`
   - `1d`
   - 单 `instrument_id`

**Step 4: Run tests to verify they pass**

Run the same pytest command, then:

```bash
pixi run -e dev pytest apps/port/tests/integration/flows -m integration -v
pixi run -e dev pytest packages/datahub/tests/integration/runtime -m integration -v
```

Expected: PASS。

**Step 5: Commit**

```bash
git add packages/datahub/tests/integration/runtime/test_legacy_derived_catalog_migration_query_integration.py \
  apps/port/tests/integration/flows/test_derived_materialization_query_repair_integration.py \
  apps/port/tests/integration/flows/test_research_dataset_integration.py \
  apps/port/tests/integration/flows/test_derived_publication_integration.py
git commit -m "test: add end to end coverage for derived engine v1"
```

### Task 7: 进入 Phase 6 硬化

**Files:**
- Create: `packages/core/tests/benchmarks/test_derived_benchmarks.py`
- Create: `scripts/benchmarks/derived_benchmark.py`
- Modify: `docs/design/unified-feature-factor-engine/decisions/adr-037-performance-slo.md`
- Create: `docs/plans/2026-03-14-unified-feature-factor-engine-phase-6-hardening-plan.md`

**Step 1: Write the failing benchmark / regression harness**

1. 定义 query / materialize / shadow compare 三类 benchmark workload。
2. 定义 CI regression budget 的阈值文件或断言脚本。

**Step 2: Run harness to verify baseline is missing**

Run:

```bash
pixi run -e dev pytest -n0 --no-cov packages/core/tests/benchmarks/test_derived_benchmarks.py -v
```

Expected: FAIL，直到 benchmark harness 落地。

**Step 3: Write the minimal implementation**

1. 固化 benchmark fixture。
2. 记录本地基线并回写 ADR-037。
3. 明确哪些指标进入 CI 阻断，哪些先只做观测。

**Step 4: Run verification**

Run:

```bash
pixi run -e dev pytest -n0 --no-cov packages/core/tests/benchmarks/test_derived_benchmarks.py -v
pixi run -e dev check
```

Expected: PASS。

**Step 5: Commit**

```bash
git add packages/core/tests/benchmarks/test_derived_benchmarks.py \
  scripts/benchmarks/derived_benchmark.py \
  docs/design/unified-feature-factor-engine/decisions/adr-037-performance-slo.md \
  docs/plans/2026-03-14-unified-feature-factor-engine-phase-6-hardening-plan.md
git commit -m "perf: add derived engine benchmark and slo baseline"
```

---

## 5. 每批执行停靠点

### Batch A

1. Task 1
2. Task 2

**Checkpoint:**

```bash
pixi run -e dev pytest -n0 --no-cov \
  packages/core/tests/unit/engine/test_research_unit.py \
  packages/datahub/tests/unit/stores/runtime/research_sqlite/test_research_catalog_store_unit.py \
  apps/port/tests/unit/services/derived/test_research_dataset_facade_unit.py \
  apps/port/tests/unit/jobs/flows/test_research_flows_unit.py -v
```

### Batch B

1. Task 3
2. Task 4

**Checkpoint:**

```bash
pixi run -e dev pytest -n0 --no-cov \
  packages/datahub/tests/unit/services/test_derived_materialization_service_unit.py \
  packages/datahub/tests/unit/stores/runtime/publication_safety/test_minimal_dq_store_unit.py \
  apps/port/tests/unit/services/derived/test_publication_facade_unit.py -v
```

执行结果（2026-03-14）：
- `Task 3` 与 `Task 4` 已完成
- publication gate 已消费 minimal DQ，并具备第一批 role/profile certification pack

### Batch C

1. Task 5
2. Task 6

**Checkpoint:**

```bash
pixi run -e dev pytest -n0 --no-cov \
  apps/port/tests/unit/jobs/flows/test_materialization_flows_unit.py \
  apps/port/tests/integration/flows/test_derived_publication_integration.py \
  apps/port/tests/integration/flows/test_derived_materialization_query_repair_integration.py \
  packages/datahub/tests/integration/runtime/test_legacy_derived_catalog_migration_query_integration.py -v
```

执行进度（2026-03-14）：
- `Task 5` 已完成
- `Task 6` 已完成
- 目录级 integration 扩面回归仍有既有噪音，待后续独立清理

### Batch D

1. Task 7

**Checkpoint:**

```bash
pixi run -e dev check
pixi run -e dev arch-check
```

执行结果（2026-03-14）：
- `Task 7` 已完成
- benchmark harness、ADR-037 baseline / gate matrix、Phase 6 hardening plan 已落地
- 最终验证通过：`pixi run -e dev check` PASS，`pixi run -e dev arch-check` = `6 kept, 0 broken`

---

## 6. 完成定义

本计划全部完成时，必须同时满足：

1. research snapshot 契约与 ADR-041 对齐。
2. publication gate 消费 minimal DQ、shadow diff / audit、manifest。
3. role/profile certification pack 已成为正式 gate，而不是占位壳。
4. research / publication 均有 flow 级操作面。
5. 四条专项 integration tests 全部落地并通过。
6. `pixi run -e dev check` 与 `pixi run -e dev arch-check` 全绿。
7. 不再保留“已完成主链但仍缺 release gate / reproducibility contract”的明显治理缺口。
