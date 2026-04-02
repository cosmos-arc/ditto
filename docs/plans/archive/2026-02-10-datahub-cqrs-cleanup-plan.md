# DataHub CQRS 重构完成情况分析与清理计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 完成 DataHub Store 层 CQRS 重构的清理工作，删除所有已被 Reader/Writer 替代的 Store 文件，更新 Service 层和 DI 容器

**Architecture:**
- Store 层完全采用 CQRS 模式（Reader/Writer 分离）
- Service 层只依赖 Reader/Writer，不直接使用 Store
- Facade 模式的 Store 保留但标记 DEPRECATED

**Tech Stack:** Python 3.12+, Polars, dishka DI 容器

---

## 分析日期
2026-02-10

## 参考文档
- `docs/plans/2026-02-08-ditto-v5.md` - Ditto V5 架构完整重构计划
- `docs/plans/2026-02-09-datahub-cqrs-refactor.md` - DataHub Store 层 CQRS 重构实施计划

---

## 一、完成情况总结

### 1.1 已完成的阶段

| 阶段 | 状态 | 描述 |
|------|------|------|
| 阶段 0 | ✅ 完成 | 类型重命名（WriteResultStore → WriteStoreResult） |
| 阶段 4 | ✅ 完成 | Ingestion 逻辑清理（删除 fundamental_ingestion.py, capital_ingestion.py） |
| 阶段 5 | ✅ 完成 | Domains 别名清理（删除 domains 目录） |
| Metadata 域 | ✅ 基本完成 | MetadataService 已更新为使用 Reader/Writer |

### 1.2 Reader/Writer 创建情况

| 域 | Reader 数量 | Writer 数量 | 状态 |
|---|---|---|---|
| Market | 8 | 8 | ✅ 大部分完成 |
| Metadata | 6 | 6 | ✅ 完成 |
| Fundamental | 8 | 8 | ✅ 完成 |
| Capital | 6 | 6 | ✅ 完成 |
| Macro | 2 | 2 | ✅ 完成 |
| Features | 2 | 2 | ✅ 完成 |
| Factors | 2 | 2 | ✅ 完成 |

**总计**: 34 个 Reader + 34 个 Writer = 68 个文件已创建

---

## 二、遗留问题清单

### 2.1 剩余 Store 文件分类（29 个）

#### A. 基础类（应该保留）- 3 个
- `stores/base/base_store.py` - 基础抽象类
- `stores/base/parquet_store.py` - Parquet 存储实现
- `stores/base/sqlite_store.py` - SQLite 存储实现

#### B. 运行时类（应该保留）- 3 个
- `runtime/ingestion/ingestion_log_store.py` - 摄入日志存储
- `runtime/quality/comparison_store.py` - 质量对比存储
- `runtime/quality/quarantine_store.py` - 隔离数据存储

#### C. Facade 模式（需要标记 DEPRECATED）- 4 个
这些是 Facade 模式，委托给 Reader/Writer，但代码仍在使用：
- `stores/market/etf/nav/nav_store.py` → 应委托给 NavReader/NavWriter
- `stores/market/etf/adj/adj_factor_store.py` → 应委托给 EtfAdjFactorReader/Writer
- `stores/market/index/bars/bars_store.py` → 应委托给 IndexBarsReader/Writer
- `stores/market/index/constituent/constituent_store.py` → 应委托给 IndexConstituentReader/Writer

#### D. 已标记 DEPRECATED（需要删除）- 4 个
- `stores/metadata/calendar/calendar_store.py` ✅ 已标记 DEPRECATED
- `stores/metadata/industry/industry_basic_store.py` ✅ 已标记 DEPRECATED
- `stores/metadata/instrument/instrument_store.py` ✅ 已标记 DEPRECATED
- `stores/metadata/identity/identity_store.py` - 冗余代码，需要删除

#### E. 需要删除/重构的 Store（约 15 个）
- `stores/metadata/universe/universe_store.py` - 应使用 UniverseReader/Writer
- `stores/metadata/industry/industry_mapping_store.py` - 应使用 IndustryMappingReader/Writer
- `stores/market/stock/bars/bars_store.py` - 应删除（已有 Reader/Writer）
- `stores/market/stock/status/status_store.py` - 应删除（已有 Reader/Writer）
- `stores/market/stock/adj/adj_factor_store.py` - 应删除（已有 Reader/Writer）
- `stores/market/etf/bars/bars_store.py` - 应删除（已有 Reader/Writer）
- `stores/market/etf/status/status_store.py` - 应删除（已有 Reader/Writer）
- `stores/macro/indicator/indicator_store.py` - 应删除（已有 Reader/Writer）
- `stores/macro/indicator/metadata_store.py` - 应删除（已有 Reader/Writer）
- `stores/factors/factor_store.py` - 应删除（已有 Reader/Writer）
- `stores/factors/factor_metadata_store.py` - 应删除（已有 Reader/Writer）
- `stores/features/technical/technical_indicator_store.py` - 应删除（已有 Reader/Writer）
- `stores/features/technical/technical_indicator_metadata_store.py` - 应删除（已有 Reader/Writer）
- `stores/market/index/weight/weight_store.py` - 需要评估

### 2.2 MarketService 中的 Store 依赖

MarketService (`packages/data/src/ditto_data/services/market/market_service.py`) 仍在使用以下 Store：

| 当前依赖 | 应替换为 |
|---------|---------|
| `etf_nav_store: EtfNavStore` | `etf_nav_reader: EtfNavReader, etf_nav_writer: EtfNavWriter` |
| `etf_adj_store: EtfAdjFactorStore` | `etf_adj_reader: EtfAdjFactorReader, etf_adj_writer: EtfAdjFactorWriter` |
| `index_bars_store: IndexBarsStore` | `index_bars_reader: IndexBarsReader, index_bars_writer: IndexBarsWriter` |
| `index_constituent_store: IndexConstituentStore` | `index_constituent_reader: IndexConstituentReader, index_constituent_writer: IndexConstituentWriter` |

### 2.3 DI 容器需要更新

`apps/port/src/ditto_port/registry/datahub.py` 中：
- 仍在导入和提供旧的 Store 类（如 EtfNavStore, IndexBarsStore 等）
- 需要移除对已废弃 Store 的依赖
- 需要更新 MarketService Provider 的参数

### 2.4 代码风格问题

- ruff 检查有 56 个错误（主要是行长度超过 88 字符）
- 需要运行 `pixi run -e dev lint --fix` 修复

### 2.5 测试文件需要更新

- 大量测试文件仍引用旧的 Store 类
- 需要更新为使用 Reader/Writer

---

## 三、清理计划

### 阶段 1: 删除冗余 Store 文件（P0）

#### Task 1.1: 删除已被 Reader/Writer 替代的 Metadata Store

**Files:**
- Delete: `packages/data/src/ditto_data/stores/metadata/universe/universe_store.py`
- Delete: `packages/data/src/ditto_data/stores/metadata/industry/industry_mapping_store.py`
- Delete: `packages/data/src/ditto_data/stores/metadata/identity/identity_store.py`
- Delete: `packages/data/src/ditto_data/stores/metadata/identity/identity_reader.py`
- Delete: `packages/data/src/ditto_data/stores/metadata/identity/identity_writer.py`
- Modify: `packages/data/src/ditto_data/stores/metadata/identity/__init__.py`
- Modify: `packages/data/src/ditto_data/stores/metadata/universe/__init__.py`
- Modify: `packages/data/src/ditto_data/stores/metadata/industry/__init__.py`

**Step 1: 检查引用**

运行以下命令确认无代码引用（除测试和文档）：
```bash
cd /home/chevy/projects/ditto
rg "from.*universe_store import|from.*industry_mapping_store import|from.*identity_store import" --type py packages/
rg "UniverseStore|IndustryMappingStore|IdentityStore" --type py packages/ | grep -v "test" | grep -v "__pycache__"
```

预期结果：无实际代码引用（或仅有废弃警告）

**Step 2: 删除 identity 相关文件（冗余代码）**

```bash
rm packages/data/src/ditto_data/stores/metadata/identity/identity_store.py
rm packages/data/src/ditto_data/stores/metadata/identity/identity_reader.py
rm packages/data/src/ditto_data/stores/metadata/identity/identity_writer.py
```

**Step 3: 更新 identity/__init__.py**

移除已删除类的导出：
```python
# 删除这些行
from ditto_data.stores.metadata.identity.identity_store import IdentityStore
from ditto_data.stores.metadata.identity.identity_reader import IdentityReader
from ditto_data.stores.metadata.identity.identity_writer import IdentityWriter
```

**Step 4: 删除 universe_store.py**

```bash
rm packages/data/src/ditto_data/stores/metadata/universe/universe_store.py
```

**Step 5: 更新 universe/__init__.py**

确认只导出 Reader/Writer：
```python
from ditto_data.stores.metadata.universe.universe_reader import UniverseReader
from ditto_data.stores.metadata.universe.universe_writer import UniverseWriter

__all__ = ["UniverseReader", "UniverseWriter"]
```

**Step 6: 删除 industry_mapping_store.py**

```bash
rm packages/data/src/ditto_data/stores/metadata/industry/industry_mapping_store.py
```

**Step 7: 更新 industry/__init__.py**

确认只导出 Reader/Writer：
```python
from ditto_data.stores.metadata.industry.industry_mapping_reader import (
    IndustryMappingReader,
)
from ditto_data.stores.metadata.industry.industry_mapping_writer import (
    IndustryMappingWriter,
)
from ditto_data.stores.metadata.industry.industry_reader import IndustryReader
from ditto_data.stores.metadata.industry.industry_writer import IndustryWriter

__all__ = [
    "IndustryReader",
    "IndustryWriter",
    "IndustryMappingReader",
    "IndustryMappingWriter",
]
```

**Step 8: 运行验证**

```bash
pixi run -e dev type
pixi run -e dev test --unit -k "metadata"
```

**Step 9: 提交**

```bash
git add packages/data/src/ditto_data/stores/metadata/
git commit -m "refactor(datahub): 删除已被 Reader/Writer 替代的 Metadata Store

- 删除 IdentityStore/Reader/Writer（冗余代码）
- 删除 UniverseStore（使用 UniverseReader/Writer）
- 删除 IndustryMappingStore（使用 IndustryMappingReader/Writer）

相关: #2026-02-09-datahub-cqrs-refactor"
```

---

#### Task 1.2: 删除 Market 域的废弃 Store

**Files:**
- Delete: `packages/data/src/ditto_data/stores/market/stock/bars/bars_store.py`
- Delete: `packages/data/src/ditto_data/stores/market/stock/status/status_store.py`
- Delete: `packages/data/src/ditto_data/stores/market/stock/adj/adj_factor_store.py`
- Delete: `packages/data/src/ditto_data/stores/market/etf/bars/bars_store.py`
- Delete: `packages/data/src/ditto_data/stores/market/etf/status/status_store.py`
- Modify: 各域的 `__init__.py`

**Step 1: 检查引用**

```bash
rg "StockBarsStore|StockStatusStore|StockAdjFactorStore" --type py packages/ | grep -v "test"
rg "EtfBarsStore|EtfStatusStore" --type py packages/ | grep -v "test"
```

**Step 2: 检查 Facade Store 的依赖关系**

首先确认这些 Facade Store 是否被其他代码直接使用：
```bash
rg "EtfAdjFactorStore|EtfNavStore|IndexBarsStore|IndexConstituentStore" --type py packages/
```

**Step 3: 删除 Market Stock 域的旧 Store**

```bash
# 这些已被 Reader/Writer 完全替代
rm packages/data/src/ditto_data/stores/market/stock/bars/bars_store.py
rm packages/data/src/ditto_data/stores/market/stock/status/status_store.py
rm packages/data/src/ditto_data/stores/market/stock/adj/adj_factor_store.py
```

**Step 4: 删除 Market ETF 域的旧 Store**

```bash
rm packages/data/src/ditto_data/stores/market/etf/bars/bars_store.py
rm packages/data/src/ditto_data/stores/market/etf/status/status_store.py
```

**注意**: 保留 `nav_store.py`, `adj_factor_store.py`（Facade 模式），这些在 Task 2 中处理

**Step 5: 更新 __init__.py 文件**

确认只导出 Reader/Writer：
```python
# stores/market/stock/bars/__init__.py
from ditto_data.stores.market.stock.bars.bars_reader import StockBarsReader
from ditto_data.stores.market.stock.bars.bars_writer import StockBarsWriter

__all__ = ["StockBarsReader", "StockBarsWriter"]

# stores/market/stock/status/__init__.py
from ditto_data.stores.market.stock.status.status_reader import StockStatusReader
from ditto_data.stores.market.stock.status.status_writer import StockStatusWriter

__all__ = ["StockStatusReader", "StockStatusWriter"]

# stores/market/stock/adj/__init__.py
from ditto_data.stores.market.stock.adj.adj_factor_reader import (
    StockAdjFactorReader,
)
from ditto_data.stores.market.stock.adj.adj_factor_writer import (
    StockAdjFactorWriter,
)

__all__ = ["StockAdjFactorReader", "StockAdjFactorWriter"]

# stores/market/etf/bars/__init__.py
from ditto_data.stores.market.etf.bars.bars_reader import EtfBarsReader
from ditto_data.stores.market.etf.bars.bars_writer import EtfBarsWriter

__all__ = ["EtfBarsReader", "EtfBarsWriter"]

# stores/market/etf/status/__init__.py
from ditto_data.stores.market.etf.status.status_reader import EtfStatusReader
from ditto_data.stores.market.etf.status.status_writer import EtfStatusWriter

__all__ = ["EtfStatusReader", "EtfStatusWriter"]
```

**Step 6: 运行验证**

```bash
pixi run -e dev type
pixi run -e dev test --unit -k "market"
```

**Step 7: 提交**

```bash
git add packages/data/src/ditto_data/stores/market/
git commit -m "refactor(datahub): 删除 Market 域已被 Reader/Writer 替代的 Store

- 删除 StockBarsStore, StockStatusStore, StockAdjFactorStore
- 删除 EtfBarsStore, EtfStatusStore
- 更新 __init__.py 只导出 Reader/Writer

相关: #2026-02-09-datahub-cqrs-refactor"
```

---

#### Task 1.3: 删除其他域的废弃 Store

**Files:**
- Delete: `packages/data/src/ditto_data/stores/macro/indicator/indicator_store.py`
- Delete: `packages/data/src/ditto_data/stores/macro/indicator/metadata_store.py`
- Delete: `packages/data/src/ditto_data/stores/factors/factor_store.py`
- Delete: `packages/data/src/ditto_data/stores/factors/factor_metadata_store.py`
- Delete: `packages/data/src/ditto_data/stores/features/technical/technical_indicator_store.py`
- Delete: `packages/data/src/ditto_data/stores/features/technical/technical_indicator_metadata_store.py`
- Modify: 各域的 `__init__.py`

**Step 1: 检查引用**

```bash
rg "IndicatorStore|FactorStore|TechnicalIndicatorStore" --type py packages/ | grep -v "test"
```

**Step 2: 删除 Macro 域的旧 Store**

```bash
rm packages/data/src/ditto_data/stores/macro/indicator/indicator_store.py
rm packages/data/src/ditto_data/stores/macro/indicator/metadata_store.py
```

**Step 3: 更新 Macro 域 __init__.py**

```python
# stores/macro/indicator/__init__.py
from ditto_data.stores.macro.indicator.indicator_reader import (
    IndicatorReader,
)
from ditto_data.stores.macro.indicator.indicator_writer import (
    IndicatorWriter,
)
from ditto_data.stores.macro.indicator.metadata_reader import (
    IndicatorMetadataReader,
)
from ditto_data.stores.macro.indicator.metadata_writer import (
    IndicatorMetadataWriter,
)

__all__ = [
    "IndicatorReader",
    "IndicatorWriter",
    "IndicatorMetadataReader",
    "IndicatorMetadataWriter",
]
```

**Step 4: 删除 Factors 域的旧 Store**

```bash
rm packages/data/src/ditto_data/stores/factors/factor_store.py
rm packages/data/src/ditto_data/stores/factors/factor_metadata_store.py
```

**Step 5: 更新 Factors 域 __init__.py**

```python
# stores/factors/__init__.py
from ditto_data.stores.factors.factor_reader import FactorReader
from ditto_data.stores.factors.factor_writer import FactorWriter
from ditto_data.stores.factors.factor_metadata_reader import (
    FactorMetadataReader,
)
from ditto_data.stores.factors.factor_metadata_writer import (
    FactorMetadataWriter,
)

__all__ = [
    "FactorReader",
    "FactorWriter",
    "FactorMetadataReader",
    "FactorMetadataWriter",
]
```

**Step 6: 删除 Features 域的旧 Store**

```bash
rm packages/data/src/ditto_data/stores/features/technical/technical_indicator_store.py
rm packages/data/src/ditto_data/stores/features/technical/technical_indicator_metadata_store.py
```

**Step 7: 更新 Features 域 __init__.py**

```python
# stores/features/technical/__init__.py
from ditto_data.stores.features.technical.technical_indicator_reader import (
    TechnicalIndicatorReader,
)
from ditto_data.stores.features.technical.technical_indicator_writer import (
    TechnicalIndicatorWriter,
)
from ditto_data.stores.features.technical.technical_indicator_metadata_reader import (  # noqa: E501
    TechnicalIndicatorMetadataReader,
)
from ditto_data.stores.features.technical.technical_indicator_metadata_writer import (  # noqa: E501
    TechnicalIndicatorMetadataWriter,
)

__all__ = [
    "TechnicalIndicatorReader",
    "TechnicalIndicatorWriter",
    "TechnicalIndicatorMetadataReader",
    "TechnicalIndicatorMetadataWriter",
]
```

**Step 8: 运行验证**

```bash
pixi run -e dev type
pixi run -e dev test --unit
```

**Step 9: 提交**

```bash
git add packages/data/src/ditto_data/stores/
git commit -m "refactor(datahub): 删除其他域已被 Reader/Writer 替代的 Store

- 删除 Macro 域的 IndicatorStore, MetadataStore
- 删除 Factors 域的 FactorStore, FactorMetadataStore
- 删除 Features 域的 TechnicalIndicatorStore, TechnicalIndicatorMetadataStore
- 更新各域 __init__.py 只导出 Reader/Writer

相关: #2026-02-09-datahub-cqrs-refactor"
```

---

### 阶段 2: 更新 MarketService（P0）

#### Task 2.1: 将 MarketService 中的 Store 依赖替换为 Reader/Writer

**Files:**
- Modify: `packages/data/src/ditto_data/services/market/market_service.py`

**Step 1: 更新构造函数签名**

将 Store 参数替换为对应的 Reader/Writer：

```python
# 之前的构造函数（约第 140 行）
def __init__(
    self,
    stock_bars_reader: StockBarsReader,
    stock_bars_writer: StockBarsWriter,
    stock_status_reader: StockStatusReader,
    stock_status_writer: StockStatusWriter,
    stock_adj_reader: StockAdjFactorReader,
    stock_adj_writer: StockAdjFactorWriter,
    etf_bars_reader: EtfBarsReader,
    etf_bars_writer: EtfBarsWriter,
    etf_status_reader: EtfStatusReader,
    etf_status_writer: EtfStatusWriter,
    instrument_reader: InstrumentReader,
    file_lock: FileLockManager,
    etf_nav_store: EtfNavStore | None = None,
    etf_adj_store: EtfAdjFactorStore | None = None,
    index_bars_store: IndexBarsStore | None = None,
    index_constituent_store: IndexConstituentStore | None = None,
) -> None:

# 修改为
def __init__(
    self,
    stock_bars_reader: StockBarsReader,
    stock_bars_writer: StockBarsWriter,
    stock_status_reader: StockStatusReader,
    stock_status_writer: StockStatusWriter,
    stock_adj_reader: StockAdjFactorReader,
    stock_adj_writer: StockAdjFactorWriter,
    etf_bars_reader: EtfBarsReader,
    etf_bars_writer: EtfBarsWriter,
    etf_status_reader: EtfStatusReader,
    etf_status_writer: EtfStatusWriter,
    instrument_reader: InstrumentReader,
    file_lock: FileLockManager,
    etf_nav_reader: EtfNavReader | None = None,
    etf_nav_writer: EtfNavWriter | None = None,
    etf_adj_reader: EtfAdjFactorReader | None = None,
    etf_adj_writer: EtfAdjFactorWriter | None = None,
    index_bars_reader: IndexBarsReader | None = None,
    index_bars_writer: IndexBarsWriter | None = None,
    index_constituent_reader: IndexConstituentReader | None = None,
    index_constituent_writer: IndexConstituentWriter | None = None,
) -> None:
```

**Step 2: 更新构造函数文档字符串**

```python
"""
初始化 MarketService.

Args:
    stock_bars_reader: 股票 K线读取器.
    stock_bars_writer: 股票 K线写入器.
    stock_status_reader: 股票状态读取器.
    stock_status_writer: 股票状态写入器.
    stock_adj_reader: 股票复权因子读取器.
    stock_adj_writer: 股票复权因子写入器.
    etf_bars_reader: ETF K线读取器.
    etf_bars_writer: ETF K线写入器.
    etf_status_reader: ETF 状态读取器.
    etf_status_writer: ETF 状态写入器.
    instrument_reader: 证券元数据读取器.
    file_lock: 文件锁管理器（用于并发写入保护）.
    etf_nav_reader: ETF 净值读取器（可选）.
    etf_nav_writer: ETF 净值写入器（可选）.
    etf_adj_reader: ETF 复权因子读取器（可选）.
    etf_adj_writer: ETF 复权因子写入器（可选）.
    index_bars_reader: 指数 K线读取器（可选）.
    index_bars_writer: 指数 K线写入器（可选）.
    index_constituent_reader: 指数成分股读取器（可选）.
    index_constituent_writer: 指数成分股写入器（可选）.
"""
```

**Step 3: 更新实例变量赋值**

```python
# 之前（约第 193 行）
self._etf_nav_store = etf_nav_store
self._etf_adj_store = etf_adj_store
self._index_bars_store = index_bars_store
self._index_constituent_store = index_constituent_store

# 修改为
self._etf_nav_reader = etf_nav_reader
self._etf_nav_writer = etf_nav_writer
self._etf_adj_reader = etf_adj_reader
self._etf_adj_writer = etf_adj_writer
self._index_bars_reader = index_bars_reader
self._index_bars_writer = index_bars_writer
self._index_constituent_reader = index_constituent_reader
self._index_constituent_writer = index_constituent_writer
```

**Step 4: 更新 _query_constituents 方法中的调用**

```python
# 之前（约第 286 行）
if self._index_constituent_store is None:
    raise NotImplementedError(
        "IndexConstituentStore not configured. Please provide index_constituent_store when initializing MarketService.",
    )

# 之后
if self._index_constituent_reader is None:
    raise NotImplementedError(
        "IndexConstituentReader not configured. Please provide index_constituent_reader when initializing MarketService.",
    )

# 之前（约第 301 行）
df = self._index_constituent_store.get(query.index_instrument_id, asof_date)

# 之后
df = self._index_constituent_reader.get(query.index_instrument_id, asof_date)
```

**Step 5: 更新 _load_bars_core 方法中的调用**

```python
# 之前（约第 355 行）
if self._index_bars_store is None:
    return pl.DataFrame()
return self._index_bars_store.read(...)

# 之后
if self._index_bars_reader is None:
    return pl.DataFrame()
return self._index_bars_reader.read(...)
```

**Step 6: 更新 _write_adj_factor 方法中的调用**

```python
# 之前（约第 684 行）
if self._etf_adj_store is None:
    raise ValueError("EtfAdjFactorStore not configured")
write_result = self._etf_adj_store.write(...)

# 之后
if self._etf_adj_writer is None:
    raise ValueError("EtfAdjFactorWriter not configured")
write_result = self._etf_adj_writer.write(...)
```

**Step 7: 更新 _write_bars 方法中的调用**

```python
# 之前（约第 783 行）
if self._index_bars_store is None:
    raise ValueError("IndexBarsStore not configured")
write_result = self._index_bars_store.write(...)

# 之后
if self._index_bars_writer is None:
    raise ValueError("IndexBarsWriter not configured")
write_result = self._index_bars_writer.write(...)
```

**Step 8: 更新导入语句**

移除 Store 的导入（如果直接导入）：
```python
# 删除这些行
from ditto_data.stores.market.etf.nav import EtfNavStore
from ditto_data.stores.market.etf.adj import EtfAdjFactorStore
from ditto_data.stores.market.index.bars import IndexBarsStore
from ditto_data.stores.market.index.constituent import IndexConstituentStore
```

**Step 9: 运行验证**

```bash
pixi run -e dev type
pixi run -e dev test --unit -k "market"
```

**Step 10: 提交**

```bash
git add packages/data/src/ditto_data/services/market/market_service.py
git commit -m "refactor(datahub): MarketService 使用 Reader/Writer 替代 Store

- 将 etf_nav_store 拆分为 etf_nav_reader/writer
- 将 etf_adj_store 拆分为 etf_adj_reader/writer
- 将 index_bars_store 拆分为 index_bars_reader/writer
- 将 index_constituent_store 拆分为 index_constituent_reader/writer
- 更新所有方法调用

相关: #2026-02-09-datahub-cqrs-refactor"
```

---

### 阶段 3: 更新 DI 容器（P1）

#### Task 3.1: 更新 datahub.py Provider

**Files:**
- Modify: `apps/port/src/ditto_port/registry/datahub.py`

**Step 1: 移除已删除 Store 的导入**

在导入部分移除或更新：
```python
# 删除或更新这些导入（约第 148-180 行）
from ditto_data.stores.market.etf.adj import EtfAdjFactorStore
from ditto_data.stores.market.etf.nav import EtfNavStore
from ditto_data.stores.market.index.bars import IndexBarsStore
from ditto_data.stores.market.index.constituent import IndexConstituentStore

# 替换为 Reader/Writer 导入
from ditto_data.stores.market.etf.adj.adj_factor_reader import (
    EtfAdjFactorReader,
)
from ditto_data.stores.market.etf.adj.adj_factor_writer import (
    EtfAdjFactorWriter,
)
from ditto_data.stores.market.etf.nav.nav_reader import EtfNavReader
from ditto_data.stores.market.etf.nav.nav_writer import EtfNavWriter
from ditto_data.stores.market.index.bars.bars_reader import IndexBarsReader
from ditto_data.stores.market.index.bars.bars_writer import IndexBarsWriter
from ditto_data.stores.market.index.constituent.constituent_reader import (
    IndexConstituentReader,
)
from ditto_data.stores.market.index.constituent.constituent_writer import (
    IndexConstituentWriter,
)
```

**Step 2: 添加缺失的 Reader/Writer Provider**

在 Market Domain Stores 部分添加：
```python
# ETF Nav Reader/Writer
@provide
def etf_nav_reader(self, data_root: Path) -> EtfNavReader:
    """ETF NAV 数据读取器."""
    return EtfNavReader(data_root=data_root / "market" / "etf" / "nav")

@provide
def etf_nav_writer(self, data_root: Path) -> EtfNavWriter:
    """ETF NAV 数据写入器."""
    return EtfNavWriter(data_root=data_root / "market" / "etf" / "nav")

# ETF Adj Reader/Writer（如果还没有）
@provide
def etf_adj_reader(self, data_root: Path) -> EtfAdjFactorReader:
    """ETF 复权因子读取器."""
    return EtfAdjFactorReader(data_root=data_root / "market" / "etf" / "adj")

@provide
def etf_adj_writer(self, data_root: Path) -> EtfAdjFactorWriter:
    """ETF 复权因子写入器."""
    return EtfAdjFactorWriter(data_root=data_root / "market" / "etf" / "adj")

# Index Bars Reader/Writer（如果还没有）
@provide
def index_bars_reader(self, data_root: Path) -> IndexBarsReader:
    """指数 K线读取器."""
    return IndexBarsReader(data_root=data_root / "market" / "index" / "bars")

@provide
def index_bars_writer(self, data_root: Path) -> IndexBarsWriter:
    """指数 K线写入器."""
    return IndexBarsWriter(data_root=data_root / "market" / "index" / "bars")

# Index Constituent Reader/Writer
@provide
def index_constituent_reader(self, data_root: Path) -> IndexConstituentReader:
    """指数成分股读取器."""
    return IndexConstituentReader(data_root=data_root)

@provide
def index_constituent_writer(self, data_root: Path) -> IndexConstituentWriter:
    """指数成分股写入器."""
    return IndexConstituentWriter(data_root=data_root)
```

**Step 3: 更新 market_query_service Provider**

```python
# 之前（约第 492 行）
@provide
def market_query_service(
    self,
    stock_bars_reader: StockBarsReader,
    stock_bars_writer: StockBarsWriter,
    stock_status_reader: StockStatusReader,
    stock_status_writer: StockStatusWriter,
    stock_adj_reader: StockAdjFactorReader,
    stock_adj_writer: StockAdjFactorWriter,
    etf_bars_reader: EtfBarsReader,
    etf_bars_writer: EtfBarsWriter,
    etf_status_reader: EtfStatusReader,
    etf_status_writer: EtfStatusWriter,
    instrument_reader: InstrumentReader,
    file_lock_manager: FileLockManager,
    etf_nav_store: EtfNavStore,
    etf_adj_store: EtfAdjFactorStore,
    index_bars_store: IndexBarsStore,
    index_constituent_store: IndexConstituentStore,
) -> MarketService:

# 修改为
@provide
def market_query_service(
    self,
    stock_bars_reader: StockBarsReader,
    stock_bars_writer: StockBarsWriter,
    stock_status_reader: StockStatusReader,
    stock_status_writer: StockStatusWriter,
    stock_adj_reader: StockAdjFactorReader,
    stock_adj_writer: StockAdjFactorWriter,
    etf_bars_reader: EtfBarsReader,
    etf_bars_writer: EtfBarsWriter,
    etf_status_reader: EtfStatusReader,
    etf_status_writer: EtfStatusWriter,
    instrument_reader: InstrumentReader,
    file_lock_manager: FileLockManager,
    etf_nav_reader: EtfNavReader = None,
    etf_nav_writer: EtfNavWriter = None,
    etf_adj_reader: EtfAdjFactorReader = None,
    etf_adj_writer: EtfAdjFactorWriter = None,
    index_bars_reader: IndexBarsReader = None,
    index_bars_writer: IndexBarsWriter = None,
    index_constituent_reader: IndexConstituentReader = None,
    index_constituent_writer: IndexConstituentWriter = None,
) -> MarketService:
```

**Step 4: 更新 MarketService 实例化**

```python
# 之前（约第 513 行）
return MarketService(
    stock_bars_reader=stock_bars_reader,
    stock_bars_writer=stock_bars_writer,
    stock_status_reader=stock_status_reader,
    stock_status_writer=stock_status_writer,
    stock_adj_reader=stock_adj_reader,
    stock_adj_writer=stock_adj_writer,
    etf_bars_reader=etf_bars_reader,
    etf_bars_writer=etf_bars_writer,
    etf_status_reader=etf_status_reader,
    etf_status_writer=etf_status_writer,
    instrument_reader=instrument_reader,
    file_lock=file_lock_manager,
    etf_nav_store=etf_nav_store,
    etf_adj_store=etf_adj_store,
    index_bars_store=index_bars_store,
    index_constituent_store=index_constituent_store,
)

# 修改为
return MarketService(
    stock_bars_reader=stock_bars_reader,
    stock_bars_writer=stock_bars_writer,
    stock_status_reader=stock_status_reader,
    stock_status_writer=stock_status_writer,
    stock_adj_reader=stock_adj_reader,
    stock_adj_writer=stock_adj_writer,
    etf_bars_reader=etf_bars_reader,
    etf_bars_writer=etf_bars_writer,
    etf_status_reader=etf_status_reader,
    etf_status_writer=etf_status_writer,
    instrument_reader=instrument_reader,
    file_lock=file_lock_manager,
    etf_nav_reader=etf_nav_reader,
    etf_nav_writer=etf_nav_writer,
    etf_adj_reader=etf_adj_reader,
    etf_adj_writer=etf_adj_writer,
    index_bars_reader=index_bars_reader,
    index_bars_writer=index_bars_writer,
    index_constituent_reader=index_constituent_reader,
    index_constituent_writer=index_constituent_writer,
)
```

**Step 5: 移除旧的 Store Provider**

如果仍有单独的 Store Provider 方法（如 `etf_nav_store`, `etf_adj_store` 等），将它们删除。

**Step 6: 运行验证**

```bash
pixi run -e dev type
pixi run -e dev test --unit -k "registry or di or container"
```

**Step 7: 提交**

```bash
git add apps/port/src/ditto_port/registry/datahub.py
git commit -m "refactor(port): 更新 DI 容器使用 Reader/Writer

- 移除对已删除 Store 的导入
- 添加缺失的 Reader/Writer Provider
- 更新 MarketService Provider 参数
- 移除旧的 Store Provider 方法

相关: #2026-02-09-datahub-cqrs-refactor"
```

---

### 阶段 4: 删除 DEPRECATED Store（P1）

#### Task 4.1: 删除已标记 DEPRECATED 的 Metadata Store

**Files:**
- Delete: `packages/data/src/ditto_data/stores/metadata/calendar/calendar_store.py`
- Delete: `packages/data/src/ditto_data/stores/metadata/industry/industry_basic_store.py`
- Delete: `packages/data/src/ditto_data/stores/metadata/instrument/instrument_store.py`
- Modify: 各域的 `__init__.py`

**Step 1: 检查引用**

```bash
rg "CalendarStore|IndustryBasicStore|InstrumentStore" --type py packages/
```

确认只测试文件引用或无引用。

**Step 2: 检查 DI 容器中的使用**

```bash
rg "provide_calendar_store|provide_industry_basic_store|provide_instrument_store" --type py apps/port/
```

**Step 3: 更新 SqlEngine Provider（如果使用 CalendarStore）**

检查 `apps/port/src/ditto_port/registry/datahub.py` 中的 `sql_engine` 方法：
```python
# 如果有类似代码，需要更新
@provide
def sql_engine(
    self,
    data_root: Path,
    calendar_store: MetadataCalendarStore,  # 需要移除
) -> SqlEngine:
    return SqlEngine(
        data_root=data_root,
        calendar_store=calendar_store,  # 需要移除
    )
```

更新为：
```python
@provide
def sql_engine(
    self,
    data_root: Path,
    calendar_reader: CalendarReader,
) -> SqlEngine:
    """DuckDB SQL 引擎."""
    return SqlEngine(
        data_root=data_root,
        calendar_reader=calendar_reader,
    )
```

**Step 4: 更新 SqlEngine 类（如果需要）**

检查 `packages/data/src/ditto_data/runtime/sql_engine.py`：
```python
# 更新构造函数
def __init__(
    self,
    data_root: Path,
    calendar_reader: CalendarReader,  # 替换 calendar_store
) -> None:
```

**Step 5: 删除 DEPRECATED Store 文件**

```bash
rm packages/data/src/ditto_data/stores/metadata/calendar/calendar_store.py
rm packages/data/src/ditto_data/stores/metadata/industry/industry_basic_store.py
rm packages/data/src/ditto_data/stores/metadata/instrument/instrument_store.py
```

**Step 6: 更新 __init__.py**

移除已删除类的导出：
```python
# stores/metadata/calendar/__init__.py
# 移除: from ...calendar_store import CalendarStore
from ditto_data.stores.metadata.calendar.calendar_reader import CalendarReader
from ditto_data.stores.metadata.calendar.calendar_writer import CalendarWriter

__all__ = ["CalendarReader", "CalendarWriter"]

# stores/metadata/industry/__init__.py
# 移除: from ...industry_basic_store import IndustryBasicStore
from ditto_data.stores.metadata.industry.industry_reader import IndustryReader
from ditto_data.stores.metadata.industry.industry_writer import IndustryWriter
from ditto_data.stores.metadata.industry.industry_mapping_reader import (
    IndustryMappingReader,
)
from ditto_data.stores.metadata.industry.industry_mapping_writer import (
    IndustryMappingWriter,
)

__all__ = [
    "IndustryReader",
    "IndustryWriter",
    "IndustryMappingReader",
    "IndustryMappingWriter",
]

# stores/metadata/instrument/__init__.py
# 移除: from ...instrument_store import InstrumentStore
from ditto_data.stores.metadata.instrument.instrument_reader import (
    InstrumentReader,
)
from ditto_data.stores.metadata.instrument.instrument_writer import (
    InstrumentWriter,
)

__all__ = ["InstrumentReader", "InstrumentWriter"]
```

**Step 7: 更新 datahub.py 中的导入**

移除对已删除 Store 的导入：
```python
# 删除这些行
from ditto_data.stores.metadata.calendar.calendar_store import (
    CalendarStore as MetadataCalendarStore,
)
from ditto_data.stores.metadata.instrument.instrument_store import (
    InstrumentStore,
)
```

**Step 8: 运行验证**

```bash
pixi run -e dev type
pixi run -e dev test --unit -k "metadata"
```

**Step 9: 提交**

```bash
git add packages/data/src/ditto_data/stores/metadata/
git add packages/data/src/ditto_data/runtime/sql_engine.py
git add apps/port/src/ditto_port/registry/datahub.py
git commit -m "refactor(datahub): 删除已标记 DEPRECATED 的 Metadata Store

- 删除 CalendarStore（使用 CalendarReader/Writer）
- 删除 IndustryBasicStore（使用 IndustryReader/Writer）
- 删除 InstrumentStore（使用 InstrumentReader/Writer）
- 更新 SqlEngine 使用 CalendarReader

相关: #2026-02-09-datahub-cqrs-refactor"
```

---

### 阶段 5: 修复代码风格问题（P2）

#### Task 5.1: 运行 lint fix 和 fmt

**Files:**
- All Python files with lint issues

**Step 1: 运行 lint --fix**

```bash
cd /home/chevy/projects/ditto
pixi run -e dev lint --fix
```

**Step 2: 运行 fmt**

```bash
pixi run -e dev fmt
```

**Step 3: 检查剩余问题**

```bash
pixi run -e dev lint
```

如果还有无法自动修复的问题，手动处理。

**Step 4: 运行类型检查**

```bash
pixi run -e dev type
```

**Step 5: 运行测试**

```bash
pixi run -e dev test --fast
```

**Step 6: 提交**

```bash
git add -A
git commit -m "style: 修复代码风格问题

- 运行 ruff --fix 自动修复
- 运行 black 格式化
- 修复剩余的 lint 问题"
```

---

### 阶段 6: 更新测试文件（P2）

#### Task 6.1: 更新单元测试使用 Reader/Writer

**Files:**
- Multiple test files

**Step 1: 查找需要更新的测试**

```bash
rg "StockBarsStore|EtfNavStore|IndexBarsStore" --type py packages/data/tests/
rg "CalendarStore|InstrumentStore|IndustryBasicStore" --type py packages/data/tests/
```

**Step 2: 更新测试文件**

对于每个引用旧 Store 的测试文件：
1. 将 `*_store` 替换为对应的 `*_reader` 或 `*_writer`
2. 更新 fixture
3. 更新 mock 对象

示例：
```python
# 之前
@pytest.fixture
def stock_bars_store(data_root):
    return StockBarsStore(data_root)

def test_read_bars(stock_bars_store):
    df = stock_bars_store.read(...)

# 之后
@pytest.fixture
def stock_bars_reader(data_root):
    return StockBarsReader(data_root)

def test_read_bars(stock_bars_reader):
    df = stock_bars_reader.read(...)
```

**Step 3: 运行测试验证**

```bash
pixi run -e dev test --unit
```

**Step 4: 提交**

```bash
git add packages/data/tests/
git commit -m "test: 更新单元测试使用 Reader/Writer

- 替换所有 Store 引用为 Reader/Writer
- 更新 fixture 和 mock 对象

相关: #2026-02-09-datahub-cqrs-refactor"
```

---

## 四、验收标准

### 4.1 运行完整检查

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

### 4.2 成功标准

1. ✅ 无 `*_store.py` 文件（除基础类、运行时类）
2. ✅ MarketService 只依赖 Reader/Writer
3. ✅ 所有测试通过
4. ✅ 类型检查通过（0 errors, 0 warnings）
5. ✅ 代码风格检查通过
6. ✅ 架构检查通过

### 4.3 验证命令

```bash
# 检查剩余 Store 文件（应该只有基础类和运行时类）
find packages/data/src/ditto_data/stores -name "*_store.py" -type f | grep -v "base_store\|parquet_store\|sqlite_store"

# 检查是否还有 Store 导入（应该只有 Facade 模式）
rg "from.*stores.*import.*Store" --type py packages/data/src/ditto_data/services/ | grep -v "Reader\|Writer"

# 检查是否还有 Facade Store 使用
rg "EtfNavStore|EtfAdjFactorStore|IndexBarsStore|IndexConstituentStore" --type py packages/data/src/ditto_data/
```

---

## 五、风险和缓解

| 风险 | 缓解措施 |
|------|----------|
| 删除 Store 导致运行时错误 | 仔细检查所有引用，运行完整测试套件 |
| DI 容器配置错误 | 逐步更新，每次更新后验证依赖注入 |
| 测试覆盖不足 | 为新的 Reader/Writer 编写完整单元测试 |
| SqlEngine 依赖 CalendarStore | 更新 SqlEngine 使用 CalendarReader |

---

## 六、时间估算

| 阶段 | 预估时间 | 复杂度 |
|------|----------|--------|
| 阶段 1: 删除冗余 Store | 1-2 天 | M |
| 阶段 2: 更新 MarketService | 1 天 | M |
| 阶段 3: 更新 DI 容器 | 0.5 天 | S |
| 阶段 4: 删除 DEPRECATED Store | 0.5 天 | S |
| 阶段 5: 修复代码风格 | 0.5 天 | S |
| 阶段 6: 更新测试文件 | 1-2 天 | L |
| **总计** | **4.5-6.5 天** | |

---

## 七、相关文档

- `docs/plans/2026-02-08-ditto-v5.md` - Ditto V5 架构完整重构计划
- `docs/plans/2026-02-09-datahub-cqrs-refactor.md` - DataHub Store 层 CQRS 重构实施计划
- `packages/data/README.md` - DataHub 包说明
- `.claude/rules/datahub.md` - DataHub 架构规范
