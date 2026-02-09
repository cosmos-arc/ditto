# DataHub Store 层 CQRS 重构实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将 DataHub Store 层从读写混合的 `*_store.py` 拆分为独立的 Reader/Writer 组件，实现 CQRS 模式

**Architecture:**
- **Store 层拆分**: `*_store.py` → `*_reader.py` + `*_writer.py`
- **组合模式**: Reader/Writer 通过组合 ParquetStore 实现，不使用 Protocol（Store 差异太大）
- **Service 层保持不变**: Service 继续同时提供读写方法，内部调用 Reader/Writer
- **破坏性重构**: 直接替换，无向后兼容层

**Tech Stack:** Python 3.12+, Polars, Pydantic

**Brainstorming 结论 (2026-02-09):**
- ❌ 不使用 Protocol：InstrumentStore/CalendarStore 等与传统 CRUD 差异太大
- ✅ 破坏性重构：直接创建 Reader/Writer，删除旧 Store
- ✅ 类型重命名：`WriteResultStore` → `WriteStoreResult`

---

## 当前状态分析

**Store 文件统计**:
- 总计: 31 个 `*_store.py` 文件
- 代码量: ~8623 行
- 最大文件: `parquet_store.py` (728 行)

**Ingestion 文件** (需删除/迁移):
- `stores/fundamental/fundamental_ingestion.py`
- `stores/capital/capital_ingestion.py`

**Domains 别名** (已废弃):
- `domains/__init__.py` → 已标记 DeprecationWarning

---

## 阶段 0: 类型命名修正 (P0) ✅ 已完成

### Task 0: 重命名 WriteResultStore → WriteStoreResult

**状态**: ✅ 完成 (2026-02-09)
**提交**: `e999aa0`
**分支**: `refactor/datahub-cqrs-stage0-type-rename`

**Files:**
- Modify: `packages/datahub/src/ditto_datahub/models/storage.py`
- Update: 所有引用 `WriteResultStore` 的文件（15 个文件）

**复杂度**: S

**原因**: 遵循命名规范 `ScopePurposeResult`，而非 `PurposeScopeResult`

**变更内容**:
- 重命名 `WriteResultStore` 类为 `WriteStoreResult`
- 更新 15 个引用文件
- 为使用 `from __future__ import annotations` 的文件添加 `TYPE_CHECKING` 导入
- 更新测试文件中的类名和导入

**验证结果**:
- ✅ 单元测试通过 (12 passed)
- ✅ 类型检查通过 (0 errors, 0 warnings)
- ✅ 代码风格检查通过
- ✅ Pre-commit hooks 通过

---

## 阶段 1: Market 域 Store 拆分 (P0)

### Task 1: StockBarsStore → StockBarsReader + StockBarsWriter

**Files:**
- Create: `stores/market/stock/bars/bars_reader.py`
- Create: `stores/market/stock/bars/bars_writer.py`
- Delete: `stores/market/stock/bars/bars_store.py`
- Update: `stores/market/stock/bars/__init__.py`

**复杂度**: M

**Reader 实现:**

```python
# bars_reader.py
class StockBarsReader:
    """Stock daily bars 数据读取器."""

    def __init__(self, data_root: Path) -> None:
        self._store = ParquetStore(data_root, YearlyPartition())
        self._dataset = "market/stock/bars"

    def read(
        self,
        instrument_ids: list[int] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        return self._store.read(self._dataset, instrument_ids, start_date, end_date)

    def count(
        self,
        instrument_ids: list[int] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> int:
        return self._store.count(self._dataset, instrument_ids, start_date, end_date)

    # 元数据方法
    def get_years(self) -> list[int]:
        return self._store.get_years(self._dataset)

    def get_date_range(self) -> tuple[str | None, str | None]:
        return self._store.get_date_range(self._dataset)

    def list_instrument_ids(self) -> list[int]:
        return self._store.list_instrument_ids(self._dataset)

    @property
    def data_root(self) -> Path:
        return self._store.data_root
```

**Writer 实现:**

```python
# bars_writer.py
class StockBarsWriter:
    """Stock daily bars 数据写入器."""

    def __init__(self, data_root: Path) -> None:
        self._store = ParquetStore(data_root, YearlyPartition())
        self._dataset = "market/stock/bars"

    def write(
        self,
        df: pl.DataFrame,
        year: int,
        on_duplicate: str = "error",
    ) -> WriteStoreResult:
        return self._store.write(self._dataset, df, on_duplicate, year=year)

    def delete(
        self,
        instrument_ids: list[int] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> int:
        return self._store.delete(self._dataset, instrument_ids, start_date, end_date)

    def delete_partition(self, partition_key: str) -> bool:
        return self._store.delete_partition(self._dataset, partition_key)

    @property
    def data_root(self) -> Path:
        return self._store.data_root
```

### Task 3-9: 其他 Market Store 拆分

| Task | Store | Reader | Writer |
|------|-------|--------|--------|
| 3 | `market/stock/adj/adj_factor_store.py` | `adj_reader.py` | `adj_writer.py` |
| 4 | `market/stock/status/status_store.py` | `status_reader.py` | `status_writer.py` |
| 5 | `market/etf/bars/bars_store.py` | `bars_reader.py` | `bars_writer.py` |
| 6 | `market/etf/adj/adj_factor_store.py` | `adj_reader.py` | `adj_writer.py` |
| 7 | `market/etf/status/status_store.py` | `status_reader.py` | `status_writer.py` |
| 8 | `market/etf/nav/nav_store.py` | `nav_reader.py` | `nav_writer.py` |
| 9 | `market/index/bars/bars_store.py` | `bars_reader.py` | `bars_writer.py` |

---

## 阶段 2: Metadata 域 Store 拆分 (P0)

### Task 10-15: Metadata Store 拆分

| Task | Store | Reader | Writer |
|------|-------|--------|--------|
| 10 | `metadata/instrument/instrument_store.py` | `instrument_reader.py` | `instrument_writer.py` |
| 11 | `metadata/calendar/calendar_store.py` | `calendar_reader.py` | `calendar_writer.py` |
| 12 | `metadata/identity/identity_store.py` | `identity_reader.py` | `identity_writer.py` |
| 13 | `metadata/industry/industry_basic_store.py` | `industry_reader.py` | `industry_writer.py` |
| 14 | `metadata/industry/industry_mapping_store.py` | `mapping_reader.py` | `mapping_writer.py` |
| 15 | `metadata/universe/universe_store.py` | `universe_reader.py` | `universe_writer.py` |

---

## 阶段 3: 其他域 Store 拆分 (P1)

### Task 16: Fundamental 组合 Store 拆分

**注意**: `fundamental_store.py` 是组合 Store，需要拆分为多个独立的 Reader/Writer:

| 原 Store | 拆分为 |
|---------|--------|
| `fundamental_store.py` | `financial_reader.py`, `financial_writer.py` |
| | `forecast_reader.py`, `forecast_writer.py` |
| | `express_reader.py`, `express_writer.py` |
| | `corporate_reader.py`, `corporate_writer.py` |
| | `dividend_reader.py`, `dividend_writer.py` |

### Task 17: Capital 组合 Store 拆分

**注意**: `capital_store.py` 是组合 Store，需要拆分:

| 原 Store | 拆分为 |
|---------|--------|
| `capital_store.py` | `valuation_reader.py`, `valuation_writer.py` |
| | (margin/pledge 已有独立 store) |

### Task 18-31: 其他 Store 拆分

| Task | Store |
|------|-------|
| 18 | `factors/factor_store.py` |
| 19 | `factors/factor_metadata_store.py` |
| 20 | `features/technical/technical_indicator_store.py` |
| 21 | `features/technical/technical_indicator_metadata_store.py` |
| 22 | `macro/indicator/indicator_store.py` |
| 23 | `macro/indicator/metadata_store.py` |
| 24-31 | 其他剩余 Store |

---

## 阶段 4: Ingestion 逻辑清理 (P0)

### Task 32: 删除 fundamental_ingestion.py

**操作**:
1. 检查引用: `grep -r "fundamental_ingestion" packages/datahub/src`
2. 删除文件
3. 更新 `__init__.py`

### Task 33: 删除 capital_ingestion.py

**同 Task 32**

---

## 阶段 5: Domains 别名清理 (P1)

### Task 34: 删除 domains 别名

**操作**:
1. 查找引用: `grep -r "from ditto_datahub.domains" packages/datahub/tests`
2. 批量替换: `s/from ditto_datahub\.domains/from ditto_datahub.stores/g`
3. 删除目录: `rm -rf packages/datahub/src/ditto_datahub/domains`
4. 删除测试目录: `rm -rf packages/datahub/tests/unit/domains`

---

## 阶段 6: Service 层更新 (P1)

### Task 35: 更新 MarketService

**更改**:
```python
# 之前
def __init__(self, stock_bars_store: StockBarsStore, ...):
    self._stock_bars_store = stock_bars_store

# 之后
def __init__(self, stock_bars_reader: StockBarsReader,
            stock_bars_writer: StockBarsWriter, ...):
    self._stock_bars_reader = stock_bars_reader
    self._stock_bars_writer = stock_bars_writer
```

### Task 36-41: 更新其他 Service

| Task | Service |
|------|---------|
| 36 | `services/metadata/metadata_service.py` |
| 37 | `services/fundamental/fundamental_service.py` |
| 38 | `services/capital/capital_service.py` |
| 39 | `services/macro/macro_service.py` |
| 40 | `services/features/feature_service.py` |
| 41 | `services/factors/factor_service.py` |

---

## 阶段 7: DI 容器更新 (P1)

### Task 42: 更新 Port 层 DI 容器

**文件**: `apps/port/src/ditto_port/registry/datahub.py`

**更改**:
```python
# 更新 Provider
@provider
def provide_stock_bars_reader(...) -> StockBarsReader:
    return StockBarsReader(data_root=...)

@provider
def provide_stock_bars_writer(...) -> StockBarsWriter:
    return StockBarsWriter(data_root=...)

# 更新 Service Provider
@provider
def provide_market_service(
    stock_bars_reader: StockBarsReader = Depends(provide_stock_bars_reader),
    stock_bars_writer: StockBarsWriter = Depends(provide_stock_bars_writer),
) -> MarketService:
    return MarketService(
        stock_bars_reader=stock_bars_reader,
        stock_bars_writer=stock_bars_writer,
        ...
    )
```

---

## 阶段 8: 清理和文档 (P2)

### Task 43: 更新架构文档

**文件**:
- `packages/datahub/README.md`
- `.claude/rules/datahub.md`

### Task 44: 移除 DataHub Facade

**操作**:
1. 删除 `hub.py`
2. 更新 `__init__.py`
3. 更新 port 层直接使用 Service

---

## 验收标准

```bash
# 完整测试
pixi run -e dev test

# 代码质量
pixi run -e dev check
pixi run -e dev type
pixi run -e dev lint

# 架构检查
pixi run -e dev arch-check
```

---

## 执行顺序

```
Task 1 (protocols)
  ↓
Task 2-9 (Market 域)
  ↓
Task 10-15 (Metadata 域)
  ↓
Task 16-31 (其他域)
  ↓
Task 32-33 (Ingestion 清理)
  ↓
Task 34 (Domains 清理)
  ↓
Task 35-41 (Service 更新)
  ↓
Task 42 (DI 容器)
  ↓
Task 43-44 (清理和文档)
```

---

## 风险和缓解

| 风险 | 缓解措施 |
|------|----------|
| 大量文件重构 | 每个 Task 独立提交 |
| 向后兼容性 | 通过 `__init__.py` facade |
| DI 配置复杂 | 渐进式更新 |
| 测试覆盖不足 | 每个 Reader/Writer 都有单元测试 |
