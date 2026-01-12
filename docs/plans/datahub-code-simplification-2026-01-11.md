# DataHub 代码简化计划

> **目标**: 系统性简化 packages/datahub 代码库，减少重复代码，提高可维护性
> **范围**: 全量代码库分析（不依赖最近提交历史）
> **预期收益**: 减少 15-20% 代码（约 1200-1500 行）
> **创建日期**: 2026-01-11
>
> **⚠️ 重要约束**: 无需向后兼容，所有使用方都在本项目内。破坏性修改直接调整依赖方即可，**禁止保留兼容代码和遗留代码**。

---

## 执行摘要

基于对 **packages/datahub** 的全面分析（覆盖 13+ 核心文件，约 8000+ 行代码），识别出 **10 个主要简化机会**：

| 优先级 | 项目 | 文件 | 预期减少 | 风险 |
|--------|------|------|----------|------|
| 🔴 高 | 数据转换重复模式 | `source.py` | -150~200 行 | 低 |
| 🔴 高 | 错误处理重复模式 | `source.py` | -100~120 行 | 中 |
| 🔴 高 | Store 写入重复逻辑 | `*_store.py` | -80~100 行 | 中 |
| 🔴 高 | BarsRepository.get() 分解 | `bars.py` | 提高可维护性 | 中 |
| 🟡 中 | fetch_stock_status 分解 | `source.py` | 简化结构 | 低 |
| 🟡 中 | _determine_dataset 简化 | `bars.py` | -20 行 | 低 |
| 🟡 中 | SQL IN 子句构建器 | `security_store.py` | -30 行 | 低 |
| 🟢 低 | _collect_checksums 分解 | `freeze_manager.py` | 提高可读性 | 低 |
| 🟢 低 | _apply_qfq_adj 简化 | `bars.py` | -15 行 | 中 |
| 🟢 低 | Schema 常量提取 | 多个文件 | -10 行 | 低 |

---

## Phase 1: 高优先级简化（核心）

### 1.1 数据转换重复模式统一 ✅

**状态**: 已完成 (2026-01-12)

**实现**:
- ✅ 创建 `transformer.py` 工具类
- ✅ 实现 `ColumnMapping` 数据类
- ✅ 实现 `TushareDataTransformer` 类
- ✅ 重构 `fetch_etf_daily` 使用 transformer
- ✅ 重构 `fetch_stock_daily` 使用 transformer
- ✅ 添加 transformer 单元测试

**收益**: 减少 ~116 行重复代码

**目标文件**: `packages/datahub/src/ditto_datahub/sources/tushare/source.py`

**问题**: 以下模式重复 8+ 次：
- 空响应处理
- 列重命名
- 类型转换
- 日志记录

**当前代码模式**（重复 8 次）:
```python
# 在 fetch_etf_daily, fetch_stock_daily 等方法中
if len(response) == 0:
    logger.info("Tushare etf_daily empty", event="tushare_etf_daily_fetch_complete", row_count=0)
    return pl.DataFrame(schema=...)

df = response.rename(
    {"ts_code": "src_code", "vol": "volume", "pct_chg": "pct_change"}
).with_columns(
    pl.col("trade_date").str.to_date("%Y%m%d"),
    pl.col("open").cast(pl.Float64),
    # ... 其他 6 列相同的转换
)

logger.info("Tushare etf_daily fetched", event="tushare_etf_daily_fetch_complete", row_count=len(df))
M.data_records.add(len(df), {"source": "tushare", "dataset": "etf_daily"})

return df
```

**简化方案**:
```python
# 创建新的工具类 ditto_datahub/sources/tushare/transformer.py

from dataclasses import dataclass
from ditto_datahub.types import Date

@dataclass(frozen=True)
class ColumnMapping:
    """列映射配置"""
    rename: dict[str, str]
    date_columns: dict[str, str]  # 列名 -> 格式
    float_columns: list[str]
    int_columns: list[str] = ()

# OHLCV 数据的通用配置
DAILY_OHLCV_MAPPING = ColumnMapping(
    rename={"ts_code": "src_code", "vol": "volume", "pct_chg": "pct_change"},
    date_columns={"trade_date": "%Y%m%d"},
    float_columns=["open", "high", "low", "close", "pre_close", "volume", "amount", "pct_change"],
)

class TushareDataTransformer:
    """Tushare 数据转换工具类"""

    @staticmethod
    def transform_daily_ohlcv(
        df: pl.DataFrame,
        dataset_name: str,
        mapping: ColumnMapping = DAILY_OHLCV_MAPPING,
    ) -> pl.DataFrame:
        """统一转换 daily OHLCV 数据"""
        if len(df) == 0:
            logger.info(
                f"Tushare {dataset_name} empty",
                event=f"tushare_{dataset_name}_fetch_complete",
                row_count=0,
            )
            schema = _build_schema_from_mapping(mapping)
            return pl.DataFrame(schema=schema)

        # 应用列映射
        result = df.rename(mapping.rename)

        # 应用类型转换
        transforms = []
        for col, fmt in mapping.date_columns.items():
            transforms.append(pl.col(col).str.to_date(fmt))
        for col in mapping.float_columns:
            transforms.append(pl.col(col).cast(pl.Float64))
        for col in mapping.int_columns:
            transforms.append(pl.col(col).cast(pl.Int64))

        if transforms:
            result = result.with_columns(transforms)

        logger.info(
            f"Tushare {dataset_name} fetched",
            event=f"tushare_{dataset_name}_fetch_complete",
            row_count=len(result),
        )
        M.data_records.add(len(result), {"source": "tushare", "dataset": dataset_name})

        return result
```

**修改 fetch 方法**（以 fetch_etf_daily 为例）:
```python
# 在 source.py 中
from .transformer import TushareDataTransformer, DAILY_OHLCV_MAPPING

def fetch_etf_daily(self, trade_date: str) -> pl.DataFrame:
    """获取 ETF 日线数据"""
    with self._tushare_fetch_error_handler("etf_daily", "daily"):
        response = self._client.invoke_raw_api(
            api="daily",
            params={
                "ts_code": "",
                "trade_date": trade_date,
                "cal_date": trade_date,  # Tushare API 需要
            },
            fields=DailyFields.ETF,
        )

        return TushareDataTransformer.transform_daily_ohlcv(
            response,
            dataset_name="etf_daily",
            mapping=DAILY_OHLCV_MAPPING,
        )
```

**影响的方法**:
- `fetch_etf_daily()` (行 265-310)
- `fetch_stock_daily()` (行 367-420)
- `fetch_index_daily()` (如果存在)
- 其他 OHLCV 相关的 fetch 方法

**预期收益**:
- 减少约 150-200 行代码
- 统一数据转换逻辑
- 易于添加新的数据集

**测试策略**:
- 为 `TushareDataTransformer` 编写单元测试
- 验证转换后的 DataFrame schema 正确
- 验证边界情况（空 DataFrame、异常值）

---

### 1.2 错误处理重复模式统一 ✅

**状态**: 已完成 (2026-01-12)

**实现**:
- ✅ 创建 `_tushare_fetch_error_handler` 上下文管理器
- ✅ 重构 9 个 fetch 方法使用错误处理上下文管理器:
  - fetch_calendar
  - fetch_etf_basic
  - fetch_etf_daily
  - fetch_stock_basic
  - fetch_stock_daily
  - fetch_adj_factor
  - fetch_fund_adj
  - fetch_stock_limit
  - fetch_stock_status
- ✅ 添加错误处理上下文管理器的单元测试

**收益**: 减少 ~133 行重复代码

---

### 1.3 Store 写入重复逻辑提取 ✅

**状态**: 已完成 (2026-01-12)

**实现**:
- ✅ 创建 `WriteResult` 数据类
- ✅ 添加 `_get_key_columns()` 抽象方法
- ✅ 添加 `_get_sort_columns()` 和 `_get_date_column()` 可覆盖方法
- ✅ 实现 `_prepare_for_write()` 方法
- ✅ 实现 `_merge_with_existing()` 方法
- ✅ 在 `ParquetStoreBase` 中实现统一的 `write()` 方法
- ✅ 删除 `BarsStore` 和 `AdjFactorStore` 中的重复 `write()` 实现
- ✅ 更新所有调用方 (repositories 和 tests)
- ✅ 运行 pre-commit 验证

**收益**: 减少 ~95 行重复代码 (BarsStore: ~70 行, AdjFactorStore: ~25 行)

**目标文件**:
- `packages/datahub/src/ditto_datahub/stores/bars_store.py`
- `packages/datahub/src/ditto_datahub/stores/adj_factor_store.py`
- `packages/datahub/src/ditto_datahub/stores/parquet_store_base.py`

**问题**: `write()` 方法在各个 Store 中有重复的模式（约 80-100 行重复代码）

**简化方案**: 在 `ParquetStoreBase` 中实现统一的 `write()` 方法，**删除子类中的重复实现**

```python
# 在 parquet_store_base.py 中添加统一的 write() 实现
from typing import Protocol
from ditto_datahub.types import Date

@dataclass
class WriteResult:
    """写入结果"""
    added: int
    updated: int
    skipped: int

class ParquetStoreBase(Generic[T]):
    """Parquet 存储基类"""

    # ... 现有代码 ...

    def write(
        self,
        df: pl.DataFrame,
        dataset: str,
        on_duplicate: OnDuplicate = OnDuplicate.ERROR,
    ) -> WriteResult:
        """统一的写入实现（所有子类共享）"""
        if len(df) == 0:
            return WriteResult(added=0, updated=0, skipped=0)

        df_by_year = self._partition_by_year(df, dataset)

        added = 0
        updated = 0
        skipped = 0

        for year, year_df in df_by_year.items():
            file_path = self._get_dataset_path(dataset) / f"{year}.parquet"

            if not file_path.exists():
                self._write_parquet(year_df, file_path)
                added += len(year_df)
            else:
                existing = self._read_parquet(file_path)
                if on_duplicate == OnDuplicate.ERROR:
                    duplicates = self._find_duplicates(existing, year_df)
                    if len(duplicates) > 0:
                        raise DuplicateError(f"Duplicate entries in {file_path}")
                    merged = self._merge_and_write(existing, year_df, file_path)
                    added += len(merged) - len(existing)
                elif on_duplicate == OnDuplicate.KEEP_FIRST:
                    merged = self._deduplicate_keep_first(existing, year_df)
                    self._write_parquet(merged, file_path)
                    added += len(merged) - len(existing)
                elif on_duplicate == OnDuplicate.KEEP_LATEST:
                    merged = self._deduplicate_keep_latest(existing, year_df)
                    self._write_parquet(merged, file_path)
                    updated = len(year_df)

        return WriteResult(added=added, updated=updated, skipped=skipped)

    def _partition_by_year(self, df: pl.DataFrame, dataset: str) -> dict[int, pl.DataFrame]:
        """按年份分区 DataFrame"""
        date_col = self._get_date_column(dataset)
        return {
            year: year_df
            for year, year_df in df.groupby(pl.col(date_col).dt.year())
        }

    def _get_date_column(self, dataset: str) -> str:
        """获取数据集的日期列名（可被子类覆盖）"""
        return "trade_date"
```

**破坏性变更**: 直接删除 `BarsStore.write()` 和 `AdjFactorStore.write()` 中的重复实现，使用基类实现。

**需要调整的依赖方**:
- 使用 `findReferences` 查找所有调用 `BarsStore.write()` 和 `AdjFactorStore.write()` 的地方
- 确保调用方式与基类 API 兼容

**预期收益**:
- 减少约 80-100 行重复代码
- 统一写入行为
- 易于添加新的 Store

---

### 1.4 BarsRepository.get() 方法分解

**目标文件**: `packages/datahub/src/ditto_datahub/repositories/bars.py`

**问题**: `get()` 方法有 101 行，承担多个职责

**当前结构**:
```python
def get(
    self,
    sids: list[int] | None = None,
    src_codes: list[str] | None = None,
    start: str | None = None,
    end: str | None = None,
    adj: AdjType = AdjType.NONE,
    asof: str | None = None,
    asset_class: Literal["stock", "etf", "index"] | None = None,
    market_wide: bool = False,
    with_status: bool = False,
    raw: bool = False,
) -> pl.DataFrame:
    # 101 行的复杂逻辑
    # 包括：参数验证、SID 解析、数据加载、复权处理、状态增强等
```

**简化方案**: 引入 `BarsQuery` 参数对象，分解方法

```python
@dataclass
class BarsQuery:
    """行情查询参数"""
    sids: list[int] | None = None
    src_codes: list[str] | None = None
    start: str | None = None
    end: str | None = None
    adj: AdjType = AdjType.NONE
    asof: str | None = None
    asset_class: Literal["stock", "etf", "index"] | None = None
    market_wide: bool = False
    with_status: bool = False
    raw: bool = False

def get(self, query: BarsQuery) -> pl.DataFrame:
    """获取行情数据（使用查询对象）"""
    # 1. 参数验证和解析
    resolved = self._resolve_query(query)

    # 2. 加载核心数据
    df = self._load_bars_core(resolved)

    # 3. 应用复权
    if not query.raw and query.adj != AdjType.NONE:
        df = self._apply_adjustment(df, query.adj, resolved)

    # 4. 增强数据
    if query.with_status and not query.raw:
        df = self._enrich_with_status(df, resolved.sids, resolved.start, resolved.end)

    return df

def _resolve_query(self, query: BarsQuery) -> _ResolvedQuery:
    """解析和验证查询参数"""
    # 提取参数验证逻辑

def _load_bars_core(self, resolved: _ResolvedQuery) -> pl.DataFrame:
    """加载核心行情数据（不含复权和增强）"""
    # 提取数据加载逻辑

def _apply_adjustment(
    self,
    df: pl.DataFrame,
    adj: AdjType,
    resolved: _ResolvedQuery,
) -> pl.DataFrame:
    """应用复权处理"""
    # 提取复权逻辑

@dataclass
class _ResolvedQuery:
    """解析后的查询参数"""
    sids: list[int]
    start: Date | None
    end: Date | None
    asof: Date | None
    asset_class: str | None
```

**破坏性变更**: `get()` 方法签名从多参数改为单一 `BarsQuery` 对象。

**需要调整的依赖方**:
- 使用 `findReferences` 查找所有调用 `BarsRepository.get()` 的地方
- 修改调用方式：`repo.get(query=BarsQuery(sids=[1], start="2024-01-01"))`

**预期收益**:
- 提高可读性和可测试性
- 每个方法职责单一
- 更易于维护和扩展

---

## Phase 2: 中优先级简化

### 2.1 fetch_stock_status() 方法分解

**目标文件**: `packages/datahub/src/ditto_datahub/sources/tushare/source.py`

**问题**: `fetch_stock_status()` 方法有 172 行，处理 3 个独立数据源

**简化方案**:
```python
def fetch_stock_status(self, trade_date: str) -> pl.DataFrame:
    """获取股票状态信息"""
    suspend_df = self._fetch_suspend_data(trade_date)
    st_df = self._fetch_st_data()
    list_status_df = self._fetch_list_status_data(trade_date)

    return self._merge_status_data(list_status_df, suspend_df, st_df, trade_date)

def _fetch_suspend_data(self, trade_date: str) -> pl.DataFrame:
    """获取停牌数据"""

def _fetch_st_data(self) -> pl.DataFrame:
    """获取 ST 状态数据"""

def _fetch_list_status_data(self, trade_date: str) -> pl.DataFrame:
    """获取上市状态数据"""

def _merge_status_data(
    self,
    list_status_df: pl.DataFrame,
    suspend_df: pl.DataFrame,
    st_df: pl.DataFrame,
    trade_date: str,
) -> pl.DataFrame:
    """合并状态数据"""
```

---

### 2.2 _determine_dataset() 条件逻辑简化

**目标文件**: `packages/datahub/src/ditto_datahub/repositories/bars.py`

**问题**: 复杂的嵌套条件判断

**简化方案**:
```python
def _determine_dataset(self, sids: list[int]) -> str:
    """检测 SID 列表的资产类别"""
    asset_class = self._detect_asset_class(sids)
    return f"{asset_class}_bars"

def _detect_asset_class(self, sids: list[int]) -> str:
    """检测 SID 列表的资产类别（假设单一类别）"""
    ranges = {
        "stock": SidRange.get_range("stock"),
        "etf": SidRange.get_range("etf"),
        "index": SidRange.get_range("index"),
    }

    for class_name, range_info in ranges.items():
        if any(range_info.min_sid <= sid <= range_info.max_sid for sid in sids):
            return class_name

    raise ValueError(f"Cannot determine asset class for SIDs: {sids[:5]}...")
```

---

### 2.3 SQL IN 子句构建器

**目标文件**: `packages/datahub/src/ditto_datahub/stores/security_store.py`

**问题**: 手动构建 IN 子句的逻辑分散

**简化方案**:
```python
def _build_in_clause(
    self,
    column: str,
    values: list[Any],
    chunk_size: int = 900,
) -> tuple[str, list[Any]]:
    """
    构建 IN 子句（自动分块）

    返回: (SQL 片段, 参数列表)
    """
    if not values:
        return "1=0", []

    chunks = [values[i:i + chunk_size] for i in range(0, len(values), chunk_size)]

    if len(chunks) == 1:
        placeholders = ",".join(["?"] * len(values))
        return f"{column} IN ({placeholders})", values

    # 多个 OR 条件
    clauses = []
    params = []
    for chunk in chunks:
        placeholders = ",".join(["?"] * len(chunk))
        clauses.append(f"{column} IN ({placeholders})")
        params.extend(chunk)

    return f"({' OR '.join(clauses)})", params
```

---

## Phase 3: 低优先级简化

### 3.1 _collect_checksums() 方法分解

**目标文件**: `packages/datahub/src/ditto_datahub/runtime/freeze_manager.py`

**问题**: 复杂的校验和收集逻辑

### 3.2 _apply_qfq_adj() 嵌套条件简化

**目标文件**: `packages/datahub/src/ditto_datahub/repositories/bars.py`

**问题**: 深层嵌套的条件判断

### 3.3 Schema 常量提取

**目标文件**: 多个文件

**问题**: Schema 定义重复

---

## 实施计划

### 阶段划分

| 阶段 | 工作内容 | 预期收益 | 时间 |
|------|----------|----------|------|
| Phase 1 | 4 个高优先级项目 | -400~500 行 | 2-3 天 |
| Phase 2 | 3 个中优先级项目 | -100 行 + 结构优化 | 1-2 天 |
| Phase 3 | 3 个低优先级项目 | -30 行 + 可读性提升 | 1 天 |
| **总计** | **所有项目** | **-15% 到 -20% 代码** | **4-6 天** |

### 执行原则

1. **TDD 方法**: RED → GREEN → REFACTOR
2. **独立分支**: 每个项目在独立分支上完成
3. **完整测试**: 每次修改后运行完整测试套件
4. **直接破坏性修改**: 公共 API 可以直接修改，同步调整所有依赖方
5. **删除旧代码**: **禁止保留兼容代码和遗留代码**
6. **文档同步**: 修改后更新相关 README

### 验证流程

```bash
# 每次修改后
pixi run -e dev pytest -m unit

# 每个阶段完成后
pixi run -e dev pytest
pixi run -e dev pre-commit-run
pixi run -e dev pytest --cov=ditto_datahub --cov-report=term
```

---

## 风险评估

| 风险 | 缓解策略 |
|------|----------|
| 复权逻辑修改影响历史数据 | 保持复权核心逻辑不变，只重构结构 |
| 大规模重构可能引入 bug | 充分测试，逐步合并，保持可回滚 |
| 依赖方调整遗漏 | 使用 LSP `findReferences` 查找所有调用点，确保全部更新 |
| 测试覆盖不足 | 重构前先补充测试，确保行为正确性 |

### 破坏性变更处理流程

1. 修改 API 前，使用 `findReferences` 查找所有调用点
2. 列出所有需要调整的依赖文件
3. 在同一 commit 中完成 API 修改和依赖方调整
4. 运行完整测试套件验证

---

## 关键文件清单

### 需要修改的文件

```
packages/datahub/src/ditto_datahub/
├── sources/
│   └── tushare/
│       ├── source.py          # 1.1, 1.2, 2.1
│       └── transformer.py     # 新增
├── stores/
│   ├── parquet_store_base.py # 1.3
│   ├── bars_store.py         # 1.3
│   ├── security_store.py     # 2.3
│   └── adj_factor_store.py   # 1.3
├── repositories/
│   └── bars.py               # 1.4, 2.2, 3.2
└── runtime/
    └── freeze_manager.py     # 3.1
```

---

## 总结

本计划通过系统性重构 packages/datahub 代码库，预期实现：

- ✅ 减少 15-20% 代码（约 1200-1500 行）
- ✅ 降低代码重复率从 15-20% 到 < 5%
- ✅ 提高可维护性和可测试性
- ✅ 统一代码模式和最佳实践

建议从 **Phase 1.1（数据转换重复模式）** 开始，这是风险最低、收益最高的项目。
