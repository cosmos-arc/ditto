# PR #59 Code Review 修复设计

> 修复 PR #59 代码审查中发现的 6 个问题（score >= 50）

## Issue #1: `enrich_calendar` 增量模式边界 bug (score: 90)

**根因**: `enrich_calendar` 过滤 `prev_trade_date IS NULL` 的行后，只传 unenriched 行给 `_compute_calendar_enrichment`。该函数通过列表索引 `[i-1]`/`[i+1]` 计算相邻交易日，增量模式下首尾行丢失已丰富行的边界信息。

**修复**: 在 `enrich_calendar` 中，额外查出 unenriched 边界日期的 1 个已丰富行（各 1 行），合并后传给纯函数，但只 upsert unenriched 行的结果。

**文件**: `packages/data/src/ditto_data/services/metadata_service.py`

## Issue #2: `hydrate_spec` 缺失 `execution_policy` / `time_spec` (score: 85)

**根因**: `hydrate_spec` 从 JSON 重建 `DerivedSpec`，忽略了 `execution_policy` 和 `time_spec`。

**修复**: 从 `payload` 读取并重建这两个字段。

**文件**: `apps/port/src/ditto_port/services/derived/materialization.py`

## Issue #3: `TYPE_CHECKING` 延迟导入 (score: 90)

**根因**: `artifact_persistence_service.py` 用 `TYPE_CHECKING` 导入 core 类型，但同层 `derived_artifact_writer.py` 已直接导入。

**修复**: 删除 `TYPE_CHECKING` guard，改为顶层直接导入。

**文件**: `packages/data/src/ditto_data/services/derived/artifact_persistence_service.py`

## Issue #4: `availability_time` 在 CS amplification 中丢失 (score: 50)

**分析**: `apply_cs_amplification` 第 544 行只 select `[*key_columns, "value"]`，丢弃 `availability_time`。publication 层有 fallback，但防御性保留更安全。

**修复**: 额外保留 `availability_time` 列（如果存在）。

**文件**: `apps/port/src/ditto_port/services/derived/materialization_orchestrator.py`

## Issue #5: 源码中 `# noqa` / `# type: ignore` (score: 75)

| 文件 | 修复方式 |
|------|----------|
| `compile_cache.py:173` | `_fetch_one` 参数改为 `Protocol` |
| `coordinator.py:395` | 提取 DQ 检查为 `_apply_dq_checks()` |
| `metrics.py:895,1104` | 引入 `FamaMacBethConfig` / `FactorExposureConfig` dataclass + 提取子函数 |
| 3 个 datahub 文件 | 引入 `ArtifactWriteParams` / `ArtifactReadParams` dataclass |

## Issue #6: datahub 测试从 port 导入 (score: 75)

**修复**: 将 `test_derived_materialization_orchestrator_unit.py` 移至 `apps/port/tests/unit/services/derived/`。

## 实施顺序

1. Issue #1 (bug fix)
2. Issue #2 (bug fix)
3. Issue #3 (simple removal)
4. Issue #4 (simple fix)
5. Issue #5 (refactoring, 逐文件)
6. Issue #6 (file move)

每个 issue 修复后运行 `pixi run -e dev check` 验证。
