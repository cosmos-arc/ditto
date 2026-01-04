# 数据摄取系统修复计划

**日期**: 2026-01-03
**优先级**: P0 (Critical) + P1 (High)
**关联**: 代码审查发现 10 个问题

---

## 概述

基于代码审查发现的 10 个问题，按优先级分阶段修复。用户决策：
- **Security映射**: 建立完整映射，写入 security_store
- **DQ检查**: 支持全市场和样本集两种模式
- **多数据源**: 仅修复硬编码

---

## 问题清单

| 级别 | 问题 | 状态 |
|------|------|------|
| Critical | T0 写入路径缺失 (coordinator.py:231) | 待修复 |
| Critical | 缺少 sid/source 映射 (coordinator.py:96) | 待修复 |
| High | 并发写入无锁保护 (backfill.py:96) | 待验证 |
| High | force 语义错误 (coordinator.py:82) | 待修复 |
| High | DQ 无 SID 返回空表 (bars.py:130) | ✅ 已修复 |
| Medium | adj_factor 重复执行 (daily.py:145) | 待修复 |
| Medium | T1 依赖无效 (daily.py:129) | 待修复 |
| Medium | 多源硬编码 (metadata.py:133) | 待修复 |
| Medium | 游标未更新 (coordinator.py:169) | 待修复 |
| Low | SQLite 连接泄漏 (dq_batch.py:54) | 待修复 |

---

## 阶段 1: Security 映射基础设施 (P0)

### 1.1 新增 SecurityMapper 服务

**文件**: `apps/server/src/ditto_server/ingestion/services/security_mapper.py` (新增)

```python
class SecurityMapper:
    """管理 src_code → sid 映射，为新证券自动分配 SID"""

    def __init__(self, security_store: SecurityStore) -> None:
        self._store = security_store
        self._cache: dict[str, int] = {}  # {src_code: sid}

    def map_or_create(
        self,
        src_codes: list[str],
        source: str,
        asset_class: Literal["stock", "etf"],
        metadata: pl.DataFrame,
    ) -> dict[str, int]:
        """映射 src_code 到 sid，不存在则创建并分配 SID"""

    def enrich_dataframe(
        self,
        df: pl.DataFrame,
        src_code_col: str = "ts_code",
        asset_class: Literal["stock", "etf"] = "stock",
    ) -> pl.DataFrame:
        """为 DataFrame 添加 sid 和 source 列"""
```

**SID 分配规则**:
- stock: 1_000_000 - 1_999_999
- etf: 2_000_000 - 2_999_999

---

### 1.2 修复 Coordinator T0 写入路径

**文件**: `apps/server/src/ditto_server/ingestion/services/coordinator.py`

#### 修改点 1: 添加 SecurityMapper 依赖注入

```python
def __init__(
    self,
    hub: "DataHub",
    source: DataSource,
    source_name: str = "tushare",
    security_mapper: SecurityMapper | None = None,  # 新增
) -> None:
    self._hub = hub
    self._source = source
    self._source_name = source_name
    self._metadata_manager = MetadataManager(log_store=hub.ingestion_log)
    self._security_mapper = security_mapper or SecurityMapper(  # 新增
        security_store=hub.security_store
    )
```

#### 修改点 2: _write_data 添加 T0 分支 (line 231)

将 `else` 分支替换为：

```python
elif dataset == "stock_basic":
    file_path, checksum = self._write_stock_basic(df, trade_date)
elif dataset == "etf_basic":
    file_path, checksum = self._write_etf_basic(df, trade_date)
elif dataset == "calendar":
    # ... 现有逻辑 ...
else:
    raise ValueError(f"不支持写入数据集: {dataset}")
```

#### 修改点 3: 新增 _write_stock_basic 和 _write_etf_basic 方法

```python
def _write_stock_basic(self, df: pl.DataFrame, trade_date: str) -> tuple[str, str]:
    """写入 stock_basic 数据到 security_store"""
    # 1. 映射或创建 SID
    sid_mapping = self._security_mapper.map_or_create(
        src_codes=df["ts_code"].to_list(),
        source=self._source_name,
        asset_class="stock",
        metadata=df,
    )

    # 2. 补齐 DataFrame 的 sid 列
    df = df.with_columns(
        pl.col("ts_code").map_dict(sid_mapping).alias("sid")
    )

    # 3. 批量 register 到 security_store
    for row in df.iter_rows(named=True):
        self._hub.security_store.register(
            sid=row["sid"],
            source=self._source_name,
            src_code=row["ts_code"],
            symbol=row["symbol"],
            name=row["name"],
            exchange=row["market"],
            asset_class="stock",
            list_date=row["list_date"],
        )

    # 4. 更新游标
    self._hub.ingestion_cursor.update_success(
        dataset="stock_basic",
        source=self._source_name,
        trade_date=trade_date,
    )

    file_path = f"security_store:stock_basic"
    checksum = self._metadata_manager.compute_checksum(df)
    return file_path, checksum

def _write_etf_basic(self, df: pl.DataFrame, trade_date: str) -> tuple[str, str]:
    """写入 etf_basic 数据，逻辑同上 (asset_class="etf")"""
```

---

### 1.3 T1 数据 SID 补齐

**文件**: `apps/server/src/ditto_server/ingestion/services/coordinator.py`

在 `_write_data` 的 T1 分支中添加 SID 补齐 (line 231)：

```python
if dataset in ("etf_daily", "stock_daily"):
    # 补齐 sid/source 字段
    asset_class = "etf" if dataset == "etf_daily" else "stock"
    df = self._security_mapper.enrich_dataframe(
        df,
        src_code_col="ts_code",
        asset_class=asset_class,
    )
    file_path, checksum = self._hub.bars_store.write(
        dataset=dataset,
        df=df,
        year=year,
    )
```

---

## 阶段 2: force 语义修复 (P0)

**文件**: `apps/server/src/ditto_server/ingestion/services/coordinator.py`

### 修改点 1: ingest_date 传递 on_duplicate (line 150)

```python
def ingest_date(
    self,
    dataset: str,
    trade_date: str,
    force: bool = False,
) -> IngestionResult:
    # ... 现有逻辑 ...

    # 将 force 映射到 on_duplicate
    on_duplicate = OnDuplicate.KEEP_LAST if force else OnDuplicate.ERROR

    file_path, stored_checksum = self._write_data(
        dataset, df, trade_date, on_duplicate
    )
```

### 修改点 2: _write_data 接收并传递 on_duplicate (line 222)

```python
def _write_data(
    self,
    dataset: str,
    df: pl.DataFrame,
    trade_date: str,
    on_duplicate: OnDuplicate = OnDuplicate.ERROR,  # 新增参数
) -> tuple[str, str]:
    # ... 传递给 store.write
    if dataset in ("etf_daily", "stock_daily"):
        file_path, checksum = self._hub.bars_store.write(
            dataset=dataset,
            df=df,
            year=year,
            on_duplicate=on_duplicate,  # 传递
        )
```

---

## 阶段 3: 并发安全验证 (P1)

**文件**: `apps/server/src/ditto_server/ingestion/flows/backfill.py`

### 验证点

确认 `BarsRepository.write` 已有文件锁保护 (`bars.py:265`)，验证 backfill 是否正确调用 Repository 层而非直接调用 Store 层。

---

## 阶段 4: DQ 全市场和样本集支持 (P1)

### 4.1 bars.get 支持全市场查询 ✅

**状态**: 已完成 (2026-01-03)

**文件**: `packages/datahub/src/ditto_datahub/repositories/bars.py`

### 修改点: get 方法添加 market_wide 参数 (line 86)

```python
def get(
    self,
    sids: list[int] | None = None,
    src_codes: list[str] | None = None,
    symbols: list[str] | None = None,
    start: str | None = None,
    end: str | None = None,
    adj: AdjType = AdjType.NONE,
    asof: str | None = None,
    asset_class: Literal["stock", "etf"] | None = None,
    with_symbol: bool = False,
    with_status: bool = False,
    # 新增参数
    market_wide: bool = False,  # 全市场查询模式
) -> pl.DataFrame:
    """
    Args:
        market_wide: 全市场查询模式，不限制 SID 范围
    """
    # 全市场模式
    if market_wide:
        # 获取所有活跃 SID
        all_sids = self._security_store.list_sids(
            asset_class=asset_class,
            is_active=True,
        )
        resolved_sids = all_sids
    else:
        # 样本集模式 (原逻辑)
        resolved_sids = self._resolve_sids(sids, src_codes, symbols, asof)
        if not resolved_sids:
            return pl.DataFrame()
```

### 4.2 DQ 调用传递 market_wide

**文件**: `packages/datahub/src/ditto_datahub/dq/checkers/statistical.py`

在 `_check_zscore` 和 `_check_completeness` 方法中添加 `market_wide` 参数传递。

**文件**: `apps/server/src/ditto_server/ingestion/tasks/dq_batch.py`

### 修改点: dq_completeness_check 添加参数并修复连接泄漏 (line 168)

```python
@task(name="dq-completeness-check")
def dq_completeness_check(
    trade_date: str,
    dataset: str,
    expected_sids: list[int] | None = None,
    market_wide: bool = True,  # 新增参数
) -> dict[str, Any]:
    hub = DataHub()
    try:
        df = hub.bars.get(
            start=trade_date,
            end=trade_date,
            market_wide=market_wide,  # 传递参数
        )
        # ... 现有逻辑 ...
        return result
    finally:
        hub.close()  # 确保关闭连接
```

同样修复 `dq_batch_check` (line 30) 添加 `try/finally` 块。

---

## 阶段 5: 其他问题修复 (P2)

### 5.1 游标更新 (Medium) ✅

**状态**: 已完成 (2026-01-03)

**文件**: `apps/server/src/ditto_server/ingestion/services/coordinator.py`

在 `ingest_date` 成功后添加游标更新 (line 189-195)：

```python
# 更新游标 (T0 数据集的游标更新已在 _write_stock_basic/_write_etf_basic 中处理)
if dataset not in ("stock_basic", "etf_basic"):
    self._hub.ingestion_cursor.update_success(
        dataset=dataset,
        source=self._source_name,
        trade_date=trade_date,
    )
```

**实现细节**:
- T0 数据集 (`stock_basic`, `etf_basic`) 的游标更新保留在各自的 `_write_*` 方法中,避免重复调用
- T1/T2 数据集 (`stock_daily`, `etf_daily`, `adj_factor`, `fund_adj`, `calendar`) 统一在 `ingest_date` 中更新游标
- 新增 7 个测试验证游标更新正确性
- 失败场景 (fetch/write 失败) 不更新游标

### 5.2 依赖编排修复 (Medium)

**文件**: `apps/server/src/ditto_server/ingestion/flows/daily.py`

#### 修改点 1: 移除重复执行

删除 line 145-156 的 `adj_datasets` 单独处理逻辑。

#### 修改点 2: 使用 get_parallel_datasets

```python
from ditto_server.ingestion.config.datasets import get_parallel_datasets

levels = get_parallel_datasets(TaskTier.T1_INCREMENTAL)

for level in levels:
    wait_for_futures = previous_futures if previous_futures else t0_futures

    for dataset in level:
        if dataset in [Dataset.ADJ_FACTOR, Dataset.FUND_ADJ]:
            task = create_ingest_task_t1_adj(dataset)
        else:
            task = create_ingest_task_t1_bars(dataset)
        future = task.submit(..., wait_for=wait_for_futures)
        t1_futures.append(future)

    previous_futures = t1_futures
```

### 5.3 多源硬编码修复 (Medium) ✅

**状态**: 已完成 (2026-01-04)

**文件**:
- `apps/server/src/ditto_server/ingestion/services/metadata.py` (line 96, 137)
- `apps/server/src/ditto_server/ingestion/services/coordinator.py` (line 91)
- `apps/server/src/ditto_server/ingestion/flows/backfill.py` (无需修改,已正确)

将硬编码的 `"tushare"` 替换为参数化（使用 `source_name` 或传入的 `source` 参数）。

**实现细节**:

1. **metadata.py 修改**:
   - `should_skip()` 方法新增 `source: str = "tushare"` 参数
   - 将硬编码的 `source="tushare"` 改为使用传入的 `source` 参数
   - 添加测试 `test_should_skip_uses_source_parameter` 验证参数正确传递

2. **coordinator.py 修改**:
   - 调用 `should_skip()` 时传递 `source=self._source_name`
   - 确保使用 coordinator 实例的 source_name 而非硬编码

3. **backfill.py 验证**:
   - 确认 `backfill_flow` 和 `backfill_missing_flow` 已正确传递 `source` 参数给 coordinator
   - 无需额外修改

**测试覆盖**:
- 新增 1 个测试验证 source 参数传递
- 所有 143 个 ingestion 单元测试通过
- 向后兼容: 默认值为 `"tushare"`,现有调用无需修改

---

## 修复顺序

| 阶段 | 任务 | 依赖 | 预计文件数 |
|------|------|------|-----------|
| 1.1 | SecurityMapper | 无 | 1 (新增) |
| 1.2 | T0 写入路径 | 1.1 | 1 |
| 1.3 | T1 SID 补齐 | 1.1 | 1 |
| 2 | force 语义修复 | 无 | 1 |
| 3 | 并发安全验证 | 无 | 1 (验证) |
| 4.1 | bars.get 查询模式 | 无 | 1 |
| 4.2 | DQ 调用修改 | 4.1 | 2 |
| 5.1 | 游标更新 | 无 | 1 |
| 5.2 | 依赖编排 | 无 | 1 |
| 5.3 | 多源硬编码 | 无 | 2 |

---

## 关键文件路径

### 新增文件
- `apps/server/src/ditto_server/ingestion/services/security_mapper.py`

### 修改文件
- `apps/server/src/ditto_server/ingestion/services/coordinator.py` - 核心修改
- `packages/datahub/src/ditto_datahub/repositories/bars.py`
- `apps/server/src/ditto_server/ingestion/tasks/dq_batch.py`
- `packages/datahub/src/ditto_datahub/dq/checkers/statistical.py`
- `apps/server/src/ditto_server/ingestion/flows/daily.py`
- `apps/server/src/ditto_server/ingestion/services/metadata.py`
- `apps/server/src/ditto_server/ingestion/flows/backfill.py`

---

## 测试策略

### 单元测试
- `test_security_mapper.py` - SID 映射和创建
- `test_coordinator_t0.py` - T0 写入逻辑
- `test_coordinator_force.py` - force 参数映射
- `test_bars_query_mode.py` - 查询模式切换

### 集成测试
- `test_ingestion_flow.py` - 完整 T0 → T1 → DQ 流程
- `test_dq_statistical.py` - 全市场/样本集 DQ 检查

### 测试覆盖要求
- 单元测试分支覆盖率 >= 80%
- 集成测试覆盖 Critical 和 High 问题

---

## 任务清单

- [ ] 阶段 1.1: 新增 SecurityMapper 服务
- [ ] 阶段 1.2: 修复 T0 写入路径
- [ ] 阶段 1.3: T1 数据 SID 补齐
- [ ] 阶段 2: force 语义修复
- [ ] 阶段 3: 并发安全验证
- [x] 阶段 4.1: bars.get 查询模式 ✅
- [ ] 阶段 4.2: DQ 调用修改
- [x] 阶段 5.1: 游标更新 ✅
- [ ] 阶段 5.2: 依赖编排修复
- [x] 阶段 5.3: 多源硬编码修复 ✅
- [ ] 单元测试编写
- [ ] 集成测试编写
- [ ] 文档更新

---

## 文档更新

完成后更新：
- `docs/design/02_data_design.md` - Security 映射章节
- `docs/design/09_data_quality_design.md` - DQ 查询模式
- `apps/server/README.md` - 摄取流程文档
