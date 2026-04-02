# Derived Publication Safety Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 为 unified-feature-factor-engine 的发布安全控制面落地第一批可运行实现，补齐 `CompatibilityManifest`、`ShadowDiffReport / ShadowTraceReport`、`CertificationReport` 的核心模型、DataHub 持久化与服务接线，为后续 publish orchestration / facade 留出干净扩展点。
**Architecture:** 采用“Core 负责领域模型，DataHub 负责 runtime 持久化与记录服务，Port 后续负责 orchestration”的分层落点；首批实现避免修改 SQLite schema，先采用文件型 runtime persistence（JSON）落地 manifest / diff / trace / certification 记录。
**Tech Stack:** Python 3.13、dataclasses、StrEnum、orjson、pathlib、Dishka Provider、pytest、polars（仅在后续 trace 扩展需要时使用）。

---

## 0. 当前进度（2026-03-13）

### 已完成

1. Core 发布安全模型已落地：
   - `packages/core/src/ditto_core/engine/publication_safety.py`
2. DataHub runtime record 与 file persistence 已落地：
   - `packages/data/src/ditto_data/models/publication_safety.py`
   - `packages/data/src/ditto_data/stores/runtime/publication_safety/*`
3. `PublicationSafetyRecordService` 已落地并接入 RuntimeProvider。
4. 对应单元测试已补齐并通过。

### 尚未完成

1. publish orchestration / API / CLI
2. dual-read compare 真正执行器
3. role/profile 认证规则引擎
4. SQLite catalog / publication schema phase

## 1. 范围与边界

### 本轮必须完成

1. `packages/core` 新增发布安全控制面模型：
   - `CompatibilityManifest`
   - `ShadowDiffReport`
   - `ShadowTraceRecord`
   - `CertificationCheckResult`
   - `CertificationPack`
   - `CertificationReport`
2. `packages/data` 新增 runtime 记录模型与文件持久化：
   - manifest record
   - shadow diff record
   - shadow trace record
   - certification report record
3. `packages/data` 新增统一服务：
   - `PublicationSafetyRecordService`
4. `apps/port` registry 接入 DataHub runtime provider，使新服务可被容器组装。
5. 补齐单元测试，覆盖模型行为、reader/writer roundtrip、service delegation。

### 本轮明确不做

1. 不修改 SQLite schema。
2. 不落地 publish orchestration / API / CLI。
3. 不实现真实 dual-read compare 执行器。
4. 不实现 role/profile 认证规则引擎，仅落地记录模型与结果持久化。

---

## 2. 实现原则

1. **先测试后实现**：每个新增行为先补失败测试，再补最小实现。
2. **避免双真相源**：DataHub 只保存 runtime record，不在此轮引入第二套业务判定逻辑。
3. **文件型持久化优先**：首轮先用 `data_root/derived/publication_safety/` 作为 runtime 记录根目录，规避 schema 变更审批。
4. **Core/DataHub 严格分层**：DataHub 不依赖 `ditto_core`，只使用本层 DTO/record。
5. **为后续 facade 预留稳定接口**：service 方法按“存 / 取 / 列表最新记录”组织，不耦合具体发布流程。

---

## 3. 目录与文件落点

### Core

- `packages/core/src/ditto_core/engine/publication_safety.py`
- `packages/core/src/ditto_core/engine/__init__.py`
- `packages/core/tests/unit/engine/test_publication_safety_unit.py`

### DataHub Models

- `packages/data/src/ditto_data/models/publication_safety.py`
- `packages/data/src/ditto_data/models/__init__.py`

### DataHub Runtime Stores

- `packages/data/src/ditto_data/stores/runtime/publication_safety/__init__.py`
- `packages/data/src/ditto_data/stores/runtime/publication_safety/manifest_reader.py`
- `packages/data/src/ditto_data/stores/runtime/publication_safety/manifest_writer.py`
- `packages/data/src/ditto_data/stores/runtime/publication_safety/shadow_report_reader.py`
- `packages/data/src/ditto_data/stores/runtime/publication_safety/shadow_report_writer.py`
- `packages/data/src/ditto_data/stores/runtime/publication_safety/certification_reader.py`
- `packages/data/src/ditto_data/stores/runtime/publication_safety/certification_writer.py`

### DataHub Service / Provider

- `packages/data/src/ditto_data/services/publication_safety_record_service.py`
- `packages/data/src/ditto_data/services/__init__.py`
- `apps/port/src/ditto_port/registry/datahub/runtime.py`

### Tests

- `packages/data/tests/unit/stores/runtime/publication_safety/test_manifest_store_unit.py`
- `packages/data/tests/unit/stores/runtime/publication_safety/test_shadow_report_store_unit.py`
- `packages/data/tests/unit/stores/runtime/publication_safety/test_certification_store_unit.py`
- `packages/data/tests/unit/services/test_publication_safety_record_service.py`

---

## 4. 数据结构设计

### 4.1 Core 模型

#### `CompatibilityManifest`

必填字段：
- `engine_codegen_version`
- `analysis_version`
- `polars_version`
- `expr_serialization_format`
- `operator_fingerprint`
- `global_compile_flags`
- `calendar_id`
- `timezone`
- `time_semantics_version`

推荐附加字段：
- `python_version`
- `platform`
- `builder_version`
- `manifest_hash`

最小行为：
- `missing_required_fields() -> tuple[str, ...]`
- `is_complete() -> bool`

#### `ShadowDiffReport`

核心字段：
- `report_id`
- `derived_id`
- `candidate_version`
- `baseline_version`
- `request_count`
- `sample_count`
- `schema_match`
- `value_diff_rate`
- `coverage_delta`
- `freshness_delta`
- `latency_p50_delta`
- `latency_p95_delta`
- `fallback_ratio_delta`
- `error_count`
- `warning_count`
- `info_count`
- `candidate_manifest_hash`
- `baseline_manifest_hash`
- `created_at`

最小行为：
- `has_blocking_errors() -> bool`

#### `ShadowTraceRecord`

核心字段：
- `trace_id`
- `report_id`
- `request_context`
- `candidate_value`
- `baseline_value`
- `diff_category`
- `candidate_manifest_hash`
- `baseline_manifest_hash`
- `sampled_at`

#### `CertificationPack` / `CertificationReport`

`CertificationPack`：
- `pack_id`
- `role`
- `materialization_profile`
- `stage`
- `check_names`

`CertificationCheckResult`：
- `name`
- `severity`
- `passed`
- `message`
- `metric_value`
- `threshold_value`

`CertificationReport`：
- `report_id`
- `pack`
- `derived_id`
- `version`
- `checks`
- `manifest_hash`
- `shadow_diff_report_id`
- `created_at`

最小行为：
- `has_blocking_errors() -> bool`
- `passed() -> bool`

### 4.2 DataHub Runtime Record

DataHub 侧不依赖 Core 模型，统一采用 record DTO：

- `CompatibilityManifestRecord`
- `ShadowDiffReportRecord`
- `ShadowTraceRecordRecord`
- `CertificationReportRecord`

共同约束：
- 记录层只保存 `payload: dict[str, JsonValue]`
- 记录层提供 `to_json_dict()` / `from_json_dict()`
- 由 Port/Orchestration 在未来负责 Core ↔ Record 转换

---

## 5. 持久化布局

根目录：

```text
data_root/
  derived/
    publication_safety/
      manifests/
        {derived_id}/v{version}.json
      shadow_diff/
        {derived_id}/candidate=v{candidate_version}/baseline=v{baseline_version}/{report_id}.json
      shadow_trace/
        {derived_id}/{report_id}/{trace_id}.json
      certification/
        {derived_id}/v{version}/{stage}/{report_id}.json
```

规则：

1. manifest 以 `(derived_id, version)` 唯一定位。
2. diff report 按 `candidate_version / baseline_version` 分区。
3. trace 记录按 `report_id` 聚合。
4. certification 按 `version + stage` 分区。
5. 首轮不做自动 TTL 清理；如需清理，由后续 retention 任务统一补齐。

---

## 6. 任务拆解

### Task 1: Core 模型与行为测试

**先写测试**

文件：
- `packages/core/tests/unit/engine/test_publication_safety_unit.py`

覆盖：
- manifest 缺字段时 `is_complete()` 为 `False`
- manifest 完整时缺字段列表为空
- shadow diff 有 `error_count > 0` 时阻断
- certification report 只要存在 blocking error 即不通过
- certification report 全部 pass 时返回通过

**再写实现**

文件：
- `packages/core/src/ditto_core/engine/publication_safety.py`
- `packages/core/src/ditto_core/engine/__init__.py`

验证：
- `pixi run -e dev pytest packages/core/tests/unit/engine/test_publication_safety_unit.py`

### Task 2: DataHub record DTO 与 manifest store

**先写测试**

文件：
- `packages/data/tests/unit/stores/runtime/publication_safety/test_manifest_store_unit.py`

覆盖：
- writer 能落盘 manifest JSON
- reader 能按 `derived_id/version` roundtrip 读回
- 不存在文件时返回 `None`

**再写实现**

文件：
- `packages/data/src/ditto_data/models/publication_safety.py`
- `packages/data/src/ditto_data/models/__init__.py`
- `packages/data/src/ditto_data/stores/runtime/publication_safety/manifest_reader.py`
- `packages/data/src/ditto_data/stores/runtime/publication_safety/manifest_writer.py`
- `packages/data/src/ditto_data/stores/runtime/publication_safety/__init__.py`

验证：
- `pixi run -e dev pytest packages/data/tests/unit/stores/runtime/publication_safety/test_manifest_store_unit.py`

### Task 3: shadow diff / trace store

**先写测试**

文件：
- `packages/data/tests/unit/stores/runtime/publication_safety/test_shadow_report_store_unit.py`

覆盖：
- writer 能同时写入 diff report 与 trace records
- reader 能按 `report_id` 读取 diff report
- reader 能读取某个 report 的 trace records
- 能返回指定 `(derived_id, candidate_version, baseline_version)` 的最新 diff report

**再写实现**

文件：
- `packages/data/src/ditto_data/stores/runtime/publication_safety/shadow_report_reader.py`
- `packages/data/src/ditto_data/stores/runtime/publication_safety/shadow_report_writer.py`

验证：
- `pixi run -e dev pytest packages/data/tests/unit/stores/runtime/publication_safety/test_shadow_report_store_unit.py`

### Task 4: certification store 与统一 service

**先写测试**

文件：
- `packages/data/tests/unit/stores/runtime/publication_safety/test_certification_store_unit.py`
- `packages/data/tests/unit/services/test_publication_safety_record_service.py`

覆盖：
- certification writer/read roundtrip
- reader 能返回某个 `derived_id/version/stage` 的最新 certification report
- service 对 manifest / diff / trace / certification 的 save/get/list 方法正确委派

**再写实现**

文件：
- `packages/data/src/ditto_data/stores/runtime/publication_safety/certification_reader.py`
- `packages/data/src/ditto_data/stores/runtime/publication_safety/certification_writer.py`
- `packages/data/src/ditto_data/services/publication_safety_record_service.py`
- `packages/data/src/ditto_data/services/__init__.py`

验证：
- `pixi run -e dev pytest packages/data/tests/unit/stores/runtime/publication_safety/test_certification_store_unit.py`
- `pixi run -e dev pytest packages/data/tests/unit/services/test_publication_safety_record_service.py`

### Task 5: Provider 接线与文档回写

文件：
- `apps/port/src/ditto_port/registry/datahub/runtime.py`
- `docs/plans/2026-03-13-unified-feature-factor-engine-remediation-design.md`

动作：
- RuntimeProvider 注册新的 readers / writers / service
- 整改计划中把 implementation plan 标为已形成，并链接本文件

验证：
- `pixi run -e dev pytest apps/port/tests/unit/registry/test_di_no_duplicate_path_unit.py`

### Task 6: 全量验证

命令：

```bash
pixi run -e dev check
```

---

## 7. 风险与化解

### 风险 1：DataHub 误依赖 Core 模型

化解：
- DataHub 仅使用 record DTO 与 JSON payload
- Core 模型只在 core tests 中验证行为，不直接进入 DataHub

### 风险 2：过早引入 catalog/schema 复杂度

化解：
- 首轮只落 runtime file persistence
- catalog/schema phase 单独进入后续计划，并在需要时申请 schema 变更

### 风险 3：trace 结构过于开放，后续难以稳定

化解：
- 首轮 trace payload 只要求 JSON-safe
- 稳定字段由后续 orchestration 层收敛

---

## 8. 完成定义

满足以下条件后，本计划视为完成：

1. Core 发布安全模型已落地并有单元测试。
2. DataHub runtime manifest / shadow / certification 记录可 roundtrip 持久化。
3. `PublicationSafetyRecordService` 已可由 RuntimeProvider 注入。
4. 整改计划已正式链接本 implementation plan。
5. `pixi run -e dev check` 全绿。
