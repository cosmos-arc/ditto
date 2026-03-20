# Layer 3: 物化 + 存储 + 查询 — 实施计划

**日期**: 2026-03-19
**来源**: [daily-strategy-readiness-gap-analysis.md](2026-03-18-daily-strategy-readiness-gap-analysis.md) 第三层
**范围**: 11 个缺口全量实施（3 P0 + 4 P1 + 4 P2）
**前置依赖**: Layer 2 P0（表达式引擎正确性）已完成
**状态**: ✅ 全部 6 Phase 已完成（2026-03-19）

---

## Context

现有 derived materialization 管线已完整（Reader/Writer/Service/Catalog），本次工作是修补性能、可靠性、运维能力缺陷。

---

## Phase 1: 读取分区裁剪 + Schema 演化 (MAT-M-1, MAT-M-2) ✅

### 修改文件

| 文件 | 变更 |
|------|------|
| `packages/datahub/src/ditto_datahub/services/derived/artifact_reader.py` | 重构 `read_frame()` 读取路径 |
| `packages/datahub/src/ditto_datahub/services/derived/_pruning.py` (新建) | 分区裁剪纯函数 |
| `packages/datahub/tests/unit/services/test_derived_artifact_reader_unit.py` (新建) | 测试 |

### MAT-M-1: 分区裁剪

**问题**: `artifact_reader.py:122` 用 `glob("*.parquet")` 扫描全部年份文件，查 1 个月数据也要扫全部。

**方案**: 复用 `ParquetStore._collect_paths()` 模式（`parquet_store.py:108-129`），利用 `YearlyPartition.get_partitions_from_filters()` 逻辑。

实现 `_prune_parquet_paths(version_root, start, end) -> list[Path]`:
- `start` + `end` 都存在时: 计算年份范围，只构造 `version_root / f"{year}.parquet"` 检查存在性
- 否则 fallback 到 glob

在 `read_frame()` 中替换 `sorted(version_root.glob("*.parquet"))` 为 `_prune_parquet_paths(version_root, start, end)`。

### MAT-M-2: Schema 演化

**问题**: 新旧版本 parquet schema 不一致时读取报错或丢列。

**方案**: `pl.concat(lazy_frames, how="diagonal_relaxed")` 替代不可用的 `union_dtypes=True`，polars 自动处理列增减和类型扩展。

### 测试

- `test_prune_paths_with_both_start_end` — 多年文件 + 日期范围 → 仅扫描对应年份
- `test_prune_paths_without_filters_returns_all` — 无过滤 → glob 全部
- `test_prune_paths_excludes_non_partition_files` — `_ephemeral/` 不被扫到
- `test_schema_evolution_new_column_in_later_year` — 2024 无 extra_col，2025 有 → 合并成功
- `test_schema_evolution_type_widen` — int → float → union_dtypes 处理

---

## Phase 2: 原子多分区写入 + 全量原子化 (MAT-M-5, MAT-M-8) ✅

### 修改文件

| 文件 | 变更 |
|------|------|
| `packages/datahub/src/ditto_datahub/stores/runtime/derived_artifact_writer.py` | 重构写入路径 |
| `packages/datahub/tests/unit/stores/runtime/test_derived_artifact_writer_unit.py` (新建) | 测试 |

### MAT-M-5: 事务性多分区写入

**问题**: `write_durable_partitions()` 逐文件写入，部分失败后残留不完整文件。

**方案**: 两阶段提交:
1. Phase 1: 所有分区写 `.tmp.parquet`
2. Phase 2: 原子 rename 全部临时文件
3. Phase 1 异常 → 清理所有临时文件后 re-raise
4. checksum 在 rename 后对最终文件计算

### MAT-M-8: ephemeral/metadata 原子写入

**问题**: `write_ephemeral_result()` 直接 `write_parquet()`，`write_artifact_metadata()` 直接 `write_bytes()`。

**方案**: 改用 `atomic_write()` 和 `atomic_bytes_write()`（来自 `packages/infra/src/ditto_infra/foundation/util/io.py`）。

### 测试

- `test_multi_partition_all_or_nothing` — mock 中途失败，验证无残留
- `test_multi_partition_temp_files_cleaned_up` — 成功后无 `.tmp` 文件
- `test_ephemeral_result_uses_atomic_write` — 验证临时文件模式
- `test_artifact_metadata_uses_atomic_write` — 验证临时文件模式

---

## Phase 3: 版本/运行记录 GC (MAT-M-3) ✅

### 修改文件

| 文件 | 变更 |
|------|------|
| `packages/datahub/src/ditto_datahub/services/derived/garbage_collector.py` (新建) | GC 逻辑 |
| `packages/datahub/src/ditto_datahub/services/derived/gc_models.py` (新建) | GC 数据模型 |
| `packages/datahub/src/ditto_datahub/services/derived_catalog_service.py` | 新增 `gc()` 委托方法 + writer protocol 扩展 |
| `packages/datahub/src/ditto_datahub/stores/runtime/derived_sqlite/writer.py` | 实现 delete SQL |
| `packages/datahub/tests/unit/services/test_derived_garbage_collector_unit.py` (新建) | 测试 |

### MAT-M-3: 基于版本状态的 GC

**问题**: SQLite 记录和磁盘 artifact 无限膨胀。

**方案**:

1. `DerivedCatalogWriterProtocol` 新增 `delete_version_records(derived_id, version)` — 删除 `derived_run`、`derived_partition`、`derived_checkpoint`、`derived_spec`、`derived_version` 中对应记录

2. `DerivedGarbageCollector` 类:
   - `dry_run(derived_id, keep_last_n=3) -> list[GcPlan]` — 只计算不执行
   - `gc_versions(derived_id, keep_last_n=3) -> GcReport` — 实际清理
   - `gc_all(keep_last_n=3) -> list[GcReport]` — 全量清理

3. 保护策略:
   - primary_online 版本永不删除
   - 最近 N 个 published/materialized 版本保留
   - 可删除: deprecated/archived/draft 状态且非 protected

4. 清理范围:
   - 磁盘: parquet 文件 + `_runs/` 元数据目录
   - SQLite: run/partition/checkpoint/spec/version 记录

### 数据模型

```python
@dataclass(frozen=True)
class GcConfig:
    keep_last_n: int = 3

@dataclass(frozen=True)
class GcReport:
    derived_id: str
    versions_deleted: int
    files_removed: int
    records_removed: int
    errors: list[str]

@dataclass(frozen=True)
class GcPlan:
    derived_id: str
    version: int
    partition_paths: list[str]
    run_ids: list[str]
```

### 测试

- `test_gc_skips_primary_online_version`
- `test_gc_keeps_last_n_versions`
- `test_gc_deletes_parquet_and_sqlite_records`
- `test_dry_run_does_not_delete`
- `test_gc_empty_catalog_noop`

---

## Phase 4: 内存管理 + 增量物化优化 (MAT-M-4, MAT-M-6) ✅

### 修改文件

| 文件 | 变更 |
|------|------|
| `packages/datahub/src/ditto_datahub/services/derived/artifact_reader.py` | 新增参数 |
| `packages/datahub/src/ditto_datahub/stores/runtime/derived_artifact_writer.py` | 新增增量合并 |
| 扩展 Phase 1/2 测试文件 | 新测试 |

### MAT-M-4: 内存管理

**方案**: `read_frame()` 新增 opt-in 参数（默认不变）:
- `streaming: bool = False` → `collect(streaming=True)`
- `max_rows: int | None = None` → collect 前 `.head(max_rows)`
- `as_lazy: bool = False` → 返回 `pl.LazyFrame`

### MAT-M-6: 增量物化优化

**问题**: 改 1 天数据需重写整个年分区。

**方案**: `write_incremental_partition()` 方法:
1. 读取已有年分区（如存在）
2. `pl.concat([existing, new], how="diagonal_relaxed")`
3. groupby `(instrument_id, trade_date)` 取 last（新值覆盖旧值）
4. 原子写入合并结果

### 测试

- `test_read_frame_streaming_mode`
- `test_read_frame_max_rows_limit`
- `test_read_frame_as_lazy_returns_lazyframe`
- `test_incremental_partition_merges_with_existing`
- `test_incremental_partition_new_overwrites_old`
- `test_incremental_partition_creates_new_if_missing`

---

## Phase 5: 并发物化 + 可配置压缩 (MAT-M-7, MAT-M-9) ✅

### 修改文件

| 文件 | 变更 |
|------|------|
| `packages/datahub/src/ditto_datahub/services/derived/concurrent_materializer.py` (新建) | 并发编排 |
| `packages/datahub/src/ditto_datahub/stores/runtime/derived_artifact_writer.py` | compression 参数 |
| `packages/infra/src/ditto_infra/foundation/util/io.py` | `atomic_write` 新增 compression 参数 |
| `packages/datahub/tests/unit/services/test_concurrent_materializer_unit.py` (新建) | 测试 |

### MAT-M-7: 并发物化

**问题**: `materialize_daily` 串行处理所有 spec。

**方案**: `ConcurrentMaterializer` 类:
- `concurrent.futures.ThreadPoolExecutor`，可配置 `max_workers`
- 每个 spec 独立（独立 parquet 目录、独立 UnitOfWork）
- 返回 `list[MaterializationTaskResult]`，含成功/异常
- 不修改现有 `materialize_daily` 签名，作为可选加速层

### MAT-M-9: 可配置压缩

**问题**: 默认 Snappy，无法配置。

**方案**:
- `atomic_write()` 新增 `compression: str = "zstd"` 参数（向后兼容，默认与当前行为一致）
- `DerivedArtifactWriter` 各写入方法透传 compression 参数

### 测试

- `test_batch_materializes_all_specs`
- `test_batch_collects_exceptions`
- `test_configurable_compression_snappy`
- `test_default_compression_zstd`

---

## Phase 6: 查询适配器 + Catalog Dashboard (MAT-M-10, MAT-M-11) ✅

### 修改文件

| 文件 | 变更 |
|------|------|
| `packages/datahub/src/ditto_datahub/services/derived/query_service.py` | 新增方法 |
| `packages/datahub/src/ditto_datahub/services/derived_catalog_service.py` | 新增 dashboard |
| 扩展测试文件 | 新测试 |

### MAT-M-10: Query→Evaluation 适配器

**方案**: `DerivedQueryService` 新增 `query_for_evaluation()`:
- 输入: derived_ids + instrument_ids + start/end + as_of + version
- 输出: 干净 DataFrame `(derived_id, instrument_id, trade_date, value)`
- 内部调用 `read_frame()` + 自动 drop 内部列 + 统一排序

### MAT-M-11: Unified Catalog Dashboard

**方案**: `DerivedCatalogService` 新增 `catalog_dashboard()`:
- 联合查询 spec + version + latest_run + state
- 返回 `pl.DataFrame`，包含: derived_id, version, role, profile, version_status, is_online, is_primary, active_version, latest_run_id, latest_run_status, total_rows, watermark

### 测试

- `test_query_for_evaluation_returns_clean_columns`
- `test_query_for_evaluation_multiple_derived_ids`
- `test_query_for_evaluation_applies_date_filters`
- `test_dashboard_returns_joined_view`
- `test_dashboard_empty_catalog`

---

## 可复用的现有基础设施

| 组件 | 路径 | 用途 |
|------|------|------|
| `YearlyPartition` | `packages/datahub/src/ditto_datahub/stores/base/partition_strategy.py` | 分区裁剪参考实现 |
| `atomic_write` / `atomic_bytes_write` | `packages/infra/src/ditto_infra/foundation/util/io.py` | 原子文件写入 |
| `FileLockManager` | `packages/infra/src/ditto_infra/foundation/concurrency/filelock.py` | 写入并发控制 |
| `DataCache` | `packages/infra/src/ditto_infra/foundation/cache/core.py` | 内存缓存 |
| `UnitOfWork` | `packages/datahub/src/ditto_datahub/stores/runtime/unit_of_work.py` | SQLite 事务管理 |
| `ParquetStore._collect_paths()` | `packages/datahub/src/ditto_datahub/stores/base/parquet_store.py:108` | 分区裁剪模式参考 |

## 新建文件汇总

```
packages/datahub/src/ditto_datahub/services/derived/
  _pruning.py                    # Phase 1: 分区裁剪函数
  garbage_collector.py           # Phase 3: GC 逻辑
  gc_models.py                   # Phase 3: GC 数据模型
  concurrent_materializer.py     # Phase 5: 并发物化编排

packages/datahub/tests/unit/
  services/
    test_derived_artifact_reader_unit.py   # Phase 1+4
    test_derived_garbage_collector_unit.py # Phase 3
    test_concurrent_materializer_unit.py   # Phase 5
  stores/runtime/
    test_derived_artifact_writer_unit.py   # Phase 2+4+5
```

## 阶段依赖

```
Phase 1 (MAT-M-1, M-2)  ─┐
Phase 2 (MAT-M-5, M-8)  ─┤─ 全部独立，可任意顺序
Phase 3 (MAT-M-3)        ─┤
Phase 4 (MAT-M-4, M-6)  ─┤
Phase 5 (MAT-M-7, M-9)  ─┤
Phase 6 (MAT-M-10, M-11)─┘
```

建议实施顺序: Phase 1 → 2 → 3 → 4 → 5 → 6（P0 优先）

## 验证

每个 Phase 完成后:
```bash
# 单元测试
pixi run -e dev test --unit -k "derived"

# 完整检查
pixi run -e dev check
```

全部完成后:
```bash
pixi run -e dev check     # lint + fmt + type + test
pixi run -e dev ci        # CI 完整检查
```

### 完成记录

- **ruff check**: All checks passed
- **ruff format**: 313 files already formatted
- **pytest**: 106 tests passed (derived suite: 100 passed in 14.28s)
- **basedpyright**: 0 errors, 0 warnings, 0 notes

## 实施偏差记录

| 计划项 | 实际实现 | 原因 |
|--------|----------|------|
| `union_dtypes=True` | `pl.concat(how="diagonal_relaxed")` | polars 1.38.1 不支持 `union_dtypes` 参数 |
| 测试文件 top-level import `_scan_with_schema_evolution` | 测试方法内 local import | ruff 自动移除未使用的 private import |
| `DerivedArtifactWriter.__init__` 新增 compression 参数 | ✅ 按计划实现 | — |
| `@overload` 类型窄化 `read_frame()` | ✅ 按计划实现 | — |
