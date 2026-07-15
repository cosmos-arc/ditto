# Parquet 追加写入 + 定期合并设计

## 0. 文档状态

- **状态**: 设计完成，待实施
- **日期**: 2026-03-19
- **范围**: `ParquetStore` + `DerivedArtifactWriter` + `io.py`
- **动机**: 缩短写入锁持有时间（50-100x），为 Prefect 并行任务调度提供更好的并发支持

## 1. 背景与动机

### 1.1 当前写入模式的瓶颈

当前 `ParquetStore.write()` 采用**全量重写**模式：

```
acquire lock
  pl.read_parquet(existing_file)   ← 读整个年分区到内存
  concat(existing, new_data)       ← 合并
  unique(keep="last")              ← 去重
  sort()                           ← 排序
  atomic_write(merged)             ← 写回全量
  file_md5()                       ← 校验
release lock
```

以 A 股 stock_daily 2025 年为例（~30 万行，zstd 压缩后 ~20MB）：
- 每次增量写入锁持有时间：1.5-3 秒
- 其中 97% 的时间花在处理与本次写入无关的旧数据上

### 1.2 为什么不引入 Iceberg/Delta Lake

经调研（详见设计过程记录），不引入湖仓格式的原因：
- Polars `write_iceberg()` 仍标记为 UNSTABLE（无稳定发布时间表）
- Iceberg 引入大量运维复杂度（catalog、compaction、schema evolution）
- Ditto 是单用户本地系统，不需要分布式事务和多写入者并发
- 当前锁粒度（dataset + year）已覆盖 Prefect 主要并行模式
- 业界量化系统共识：Parquet + DuckDB 是本地单机最佳实践

### 1.3 `fsync(dir)` 缺陷

当前 `atomic_write()` 只 fsync 数据文件，未 fsync 父目录。POSIX 语义下，`rename()` 修改的是父目录的 inode 条目，如果系统在 rename 后崩溃，目录条目可能丢失。

## 2. 设计目标

1. **锁持有时间降低 50-100x**（2s → 30-50ms）
2. **不改公共 API**：Reader/Writer 接口保持不变
3. **不改读取逻辑**：`_collect_paths()` + `scan_parquet` + `unique(keep="last")` 天然兼容
4. **不改 DuckDB SqlEngine**：`read_parquet("*.parquet")` 天然支持多文件
5. **不新增依赖**：复用现有 filelock / SQLite / polars

## 3. 文件命名约定

```
data/market/stock/bars/daily/
├── 2024.parquet                    # base（合并后的完整分区）
├── 2025.parquet                    # base
├── 2025.20260319_143052.parquet    # delta（追加的新数据）
├── 2025.20260320_180015.parquet    # delta
└── 2025.20260321_093000.parquet    # delta
```

### 规则

| 文件类型 | 命名模式 | 示例 |
|---------|---------|------|
| base | `{partition_key}.parquet` | `2025.parquet` |
| delta | `{partition_key}.{YYYYMMDD_HHMMSS}.parquet` | `2025.20260319_143052.parquet` |

### base 与 delta 的区分

```python
def _is_delta_file(path: Path) -> bool:
    """文件名 stem 中包含 '.' 即为 delta。"""
    return "." in path.stem
```

### 合并后状态

合并完成后只保留 base 文件，所有 delta 被删除。

### 时间戳碰撞安全性

同一 dataset + year 的写入已被文件锁串行化，时间戳碰撞不可能发生。

## 4. `fsync(dir)` 修复

### 修改文件

`packages/infra/src/ditto_infra/foundation/util/io.py` — `atomic_write()` 和 `atomic_bytes_write()`

### 修改内容

在 `fsync(data_file)` 之后、`rename()` 之前，增加父目录 fsync：

```python
if fsync:
    with temp_path.open("r+b") as f:
        os.fsync(f.fileno())

    # fsync 父目录，确保 rename 的目录条目落盘
    dir_fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)

temp_path.replace(path)
```

### WSL2 兼容性

WSL2 上 Linux 语义完全适用，无特殊处理。

## 5. 写入路径改造

### 5.1 新增方法

```python
def _write_delta(self, df: pl.DataFrame, file_path: Path) -> Path:
    """写入 delta 文件（不读旧数据）。"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    delta_path = file_path.with_suffix(f".{timestamp}.parquet")
    atomic_write(df, delta_path, compression=self._compression)
    return delta_path

def _list_delta_files(self, dataset: str, partition_key: str) -> list[Path]:
    """列出分区下的所有 delta 文件。"""
    dataset_dir = self._data_root / dataset
    if not dataset_dir.exists():
        return []
    base_stem = partition_key  # e.g. "2025"
    return sorted([
        p for p in dataset_dir.glob(f"{base_stem}.*.parquet")
        if _is_delta_file(p)
    ])
```

### 5.2 改造 `write()`

```python
DELTA_MERGE_THRESHOLD = 5

def write(self, dataset, data, on_duplicate="keep_last", **kwargs) -> WriteResult:
    year = kwargs["year"]
    df = self._prepare_for_write(data)
    file_path = self._get_path(dataset, str(year))

    with self._file_lock.acquire(f"{dataset}_{year}", timeout=60.0):
        has_base = file_path.exists()
        has_deltas = bool(self._list_delta_files(dataset, str(year)))

        if has_base or has_deltas:
            # 追加模式：只写 delta
            delta_path = self._write_delta(df, file_path)

            # 检查是否需要合并
            delta_files = self._list_delta_files(dataset, str(year))
            merged = False
            if len(delta_files) >= DELTA_MERGE_THRESHOLD:
                self._compact(dataset, str(year))
                merged = True

            return WriteResult(
                file_path=str(delta_path),
                is_merge=False,
                compacted=merged,
            )
        else:
            # 首次写入：直接写 base
            atomic_write(df, file_path)
            return WriteResult(
                file_path=str(file_path),
                is_merge=True,
                compacted=False,
            )
```

### 5.3 `on_duplicate` 策略变化

| 策略 | 当前行为 | 追加模式行为 |
|------|---------|------------|
| `keep_last` | 写入时合并去重 | 延迟到读取时去重（`unique(keep="last")`） |
| `keep_first` | 写入时过滤重复 | 同上 |
| `error` | 写入时检测并报错 | **降级为警告**（无法在写入时精确检测） |

`error` 降级为警告的权衡：追加模式下不读旧数据，无法检测重复。但实际使用中重复写入通常由重试导致，`keep_last` 本身就是正确语义。

## 6. 合并（Compaction）

### 6.1 合并流程

```python
def _compact(self, dataset: str, partition_key: str) -> None:
    """合并 base + 所有 delta 为新的 base，在同一锁内完成。"""
    file_path = self._get_path(dataset, partition_key)
    delta_files = self._list_delta_files(dataset, partition_key)

    all_paths = []
    if file_path.exists():
        all_paths.append(file_path)
    all_paths.extend(delta_files)

    if not all_paths:
        return

    merged = (
        pl.scan_parquet([str(p) for p in all_paths])
        .sort(self._get_sort_columns())
        .unique(subset=self._get_key_columns(), keep="last")
        .collect()
    )

    if merged.is_empty():
        # 无数据，全部清理
        file_path.unlink(missing_ok=True)
        for d in delta_files:
            d.unlink(missing_ok=True)
        return

    # 原子替换 base
    temp_base = file_path.with_suffix(".parquet.compact")
    merged.write_parquet(temp_base, compression=self._compression)
    os.replace(temp_base, file_path)

    # 删除所有 delta
    for d in delta_files:
        d.unlink(missing_ok=True)

    # fsync(dir) 确保删除操作落盘
    dir_fd = os.open(file_path.parent, os.O_RDONLY)
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)
```

### 6.2 合并触发方式

| 触发方式 | 时机 | 适用场景 |
|---------|------|---------|
| **写入时自检** | delta 数量 ≥ 5 时，写入后立即合并 | 高频写入场景 |
| **Prefect 定时任务** | 每日收盘后低峰期，遍历所有分区 | 保守兜底 |

两种方式并存。写入时自检保证 delta 数量有上限；定时任务作为兜底，处理未达到阈值但需要清理的场景。

### 6.3 合并期间的一致性

读取者在任何时间点看到的状态都是自愈的：

| 时间点 | 文件系统状态 | 读取结果 | 正确性 |
|--------|------------|---------|--------|
| 合并前 | base + d1 + d2 | base ∪ d1 ∪ d2，`unique(keep="last")` 正确 | ✅ |
| 新 base 写完，旧 delta 未删 | 旧 base + 新 base + d1 + d2 | 两份 base + delta，去重后正确 | ✅ |
| delta 删除完，旧 base 删前 | 旧 base + 新 base | 两份 base，去重后正确 | ✅ |
| 全部完成 | 新 base | 正确 | ✅ |

关键保障：`unique(keep="last")` + 排序确保即使短暂出现数据重复，结果仍然正确。

## 7. 删除路径改造

删除操作采用**"过滤 + 合并"**策略：删除 = 读取全量 → 过滤删除行 → 写回 base → 清理 delta。

```python
def delete(self, dataset, instrument_ids=None, start_date=None, end_date=None):
    paths = self._collect_paths(dataset, start_date, end_date)

    for partition_path in self._partition_paths_from_filters(paths):
        partition_key = self._partition.extract_key(partition_path)

        with self._file_lock.acquire(f"{dataset}_{partition_key}", timeout=60.0):
            delta_files = self._list_delta_files(dataset, partition_key)
            all_paths = [partition_path, *delta_files] if partition_path.exists() else delta_files

            if not all_paths:
                continue

            # 扫描 + 过滤 + 去重，一步到位
            filtered = (
                pl.scan_parquet([str(p) for p in all_paths])
                .filter(keep_mask)
                .sort(self._get_sort_columns())
                .unique(subset=self._get_key_columns(), keep="last")
                .collect()
            )

            deleted_count = sum_of_original_rows - len(filtered)

            if filtered.is_empty():
                partition_path.unlink(missing_ok=True)
                for d in delta_files:
                    d.unlink(missing_ok=True)
            else:
                atomic_write(filtered, partition_path)
                for d in delta_files:
                    d.unlink(missing_ok=True)

    return total_deleted
```

**权衡**：删除时锁持有时间长（~2s），但删除是低频操作，且顺便清理了积攒的 delta，一举两得。

## 8. 元数据操作调整

### `get_checksum()`

语义调整为"上次合并后的 base 快照指纹"：

```python
def get_checksum(self, dataset: str, partition_key: str) -> str:
    path = self._get_path(dataset, partition_key)
    return file_md5(path) if path.exists() else ""
```

只有 delta 没有 base 时返回空字符串。这更合理——`FreezeManager` 标记版本应在合并后的干净状态下生成。

### `delete_partition()`

删除整个分区（base + 所有 delta）：

```python
def delete_partition(self, dataset: str, partition_key: str) -> bool:
    base = self._get_path(dataset, partition_key)
    deltas = self._list_delta_files(dataset, partition_key)
    deleted = False
    if base.exists():
        base.unlink()
        deleted = True
    for d in deltas:
        d.unlink(missing_ok=True)
        deleted = True
    return deleted
```

### 不需要改动的元数据方法

| 方法 | 原因 |
|------|------|
| `get_years()` | 依赖 `glob("*.parquet")`，天然兼容 |
| `get_date_range()` | 依赖 `_collect_paths()` + `scan_parquet` |
| `list_instrument_ids()` | 同上 |
| `count()` | 同上 |

## 9. 不受影响的组件

| 组件 | 原因 |
|------|------|
| `SqlEngine` | DuckDB `read_parquet("*.parquet")` 天然支持多文件查询 |
| `read()` / `_collect_paths()` | 已有 `glob + scan_parquet + unique(keep="last")` 逻辑 |
| Reader/Writer 公共 API | 接口签名不变 |
| `FreezeManager` | checksum 语义兼容 |
| Service 层 | 不感知存储层实现变化 |

## 10. DerivedArtifactWriter 改造

### 差异点

`DerivedArtifactWriter` 与 `ParquetStore` 的场景略有不同：

| 差异 | ParquetStore | DerivedArtifactWriter |
|------|-------------|----------------------|
| 路径结构 | `data/{dataset}/{YYYY}.parquet` | `artifacts/{profile}/{spec_id}/v{ver}/{YYYY}.parquet` |
| 两阶段提交 | 无 | 已有两阶段提交（多分区原子写入） |
| 合并语义 | dedup by key | `diagonal_relaxed` schema evolution |

### 改造策略

`DerivedArtifactWriter` 沿用相同的追加+合并模式，但需要调整：

1. **`write_durable_partitions()`**：快路径改为每个分区写 delta，不再先写 `.tmp` 再 rename
2. **`write_incremental_partition()`**：已经是追加模式（`_merge_partitions`），改造为只写 delta
3. **两阶段提交**：保持不变（Phase 1 写所有 delta，Phase 2 不再需要 rename）

### 独立改造

`DerivedArtifactWriter` 的改造与 `ParquetStore` 独立进行，可作为第二阶段实施。

## 11. 变更清单

| 组件 | 变更 | 改动量 |
|------|------|--------|
| `io.py` | 新增 `fsync(dir)` | ~5 行 |
| `ParquetStore` | 新增 `_write_delta()`、`_list_delta_files()`、`_is_delta_file()` | ~30 行 |
| `ParquetStore.write()` | 改为追加模式 + 自动合并触发 | 改造 ~40 行 |
| `ParquetStore.delete()` | 改为"过滤 + 合并" | 改造 ~30 行 |
| `ParquetStore` 元数据方法 | `get_checksum` / `delete_partition` 微调 | ~10 行 |
| `DerivedArtifactWriter` | 追加+合并模式（独立改造，第二阶段） | ~50 行 |
| 常量 | `DELTA_MERGE_THRESHOLD = 5` | 1 行 |

**总计：~170 行新代码/改造代码，不新增依赖，不新增文件，不改公共 API。**

## 12. 配置项

```python
# 合并阈值：delta 文件数量达到此值时触发自动合并
DELTA_MERGE_THRESHOLD: int = 5
```

暂不暴露为环境变量。如果后续需要动态调整，可在 `DataStoreSettings` 中添加。
