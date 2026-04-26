# Phase 2 设计文档：Data 层 Protocol 化 + Reader/Writer 参数化

## Context

基于全架构审计 Phase 2 计划，对 Data 层进行两项核心重构：
1. Port dataclass → Protocol + Readers/Writers 参数聚合器
2. 92 个 Reader/Writer 中 ~44 个机械类参数化

**调研基础**：LEAN/NautilusTrader/Zipline/Backtrader/vectorbt 命名对比，
Cockburn 六边形架构原始定义，Fowler 重构模式，Go Wire / FastAPI 依赖组织惯例。

---

## 决策记录

| # | 决策项 | 选择 | 理由 |
|---|--------|------|------|
| 1 | Ports 命名 | `{Domain}Readers/Writers` | Cockburn 原文 Port = Protocol 接口，非参数聚合器；Fowler Introduce Parameter Object |
| 2 | Protocol 层 | 双层——Protocol 接口 + dataclass 聚合器 | Protocol 给 Service 类型注解，dataclass 给 DI 装配 |
| 3 | Parquet 机械类 | `ParquetDatasetReader/Writer` 基类 + 薄具体类 | 组合 ParquetStore，具体类提供领域名称和扩展点 |
| 4 | SQLite 机械类 | `SqliteTableSpec` + `SqliteTableReader/Writer` 基类 + 薄具体类 | 组合 SQLiteClient，spec 参数化表结构差异 |
| 5 | 复杂类 | 保留独立文件，实现 Protocol 接口 | IndexConstituent（SQLite+PIT）、factors/features（ParquetStore 子类）等 |
| 6 | trade/ 重构 | 拆为 strategy/signals + execution/orders,fills + portfolio/positions | 按领域归属拆分，Signal 属 Strategy，Order/Fill 属 Execution，Position 属 Portfolio |
| 7 | 实体命名 | SignalRecord / OrderRecord / FillRecord / PositionRecord | 业界统一：Signal=策略观点，Order=执行指令，Fill=成交结果，Position=持仓状态 |

---

## 2.1 Protocol 接口层

**新增文件**：`data/providers/protocols.py`

```python
class DatasetReader(Protocol):
    """Parquet 数据集读取接口。"""
    def read(self, instrument_ids: list[int] | None = None,
             start_date: str | None = None, end_date: str | None = None) -> pl.DataFrame: ...
    def count(self, instrument_ids: list[int] | None = None,
              start_date: str | None = None, end_date: str | None = None) -> int: ...
    def get_years(self) -> list[int]: ...
    def get_date_range(self) -> tuple[str | None, str | None]: ...
    def get_checksum(self, partition_key: str) -> str: ...
    def list_instrument_ids(self) -> list[int]: ...

class DatasetWriter(Protocol):
    """Parquet 数据集写入接口。"""
    def write(self, df: pl.DataFrame, year: int,
              on_duplicate: OnDuplicate = OnDuplicate.ERROR) -> WriteStoreResult: ...
    def delete(self, instrument_ids: list[int] | None = None,
               start_date: str | None = None, end_date: str | None = None) -> int: ...
    def delete_partition(self, partition_key: str) -> bool: ...

class SqliteReader(Protocol):
    """SQLite 表读取接口。"""
    def get(self, id_value: int, as_of_date: date) -> pl.DataFrame: ...

class SqliteWriter(Protocol):
    """SQLite 表写入接口。"""
    def write(self, df: pl.DataFrame) -> int: ...
```

---

## 2.2 Parquet 机械类参数化

### 基类（组合 ParquetStore）

**新增文件**：`storage/base/dataset_reader.py`, `storage/base/dataset_writer.py`

```python
# dataset_reader.py
class ParquetDatasetReader:
    """通用 Parquet 数据集读取器，通过 dataset 路径参数化。"""
    def __init__(self, store: ParquetStore, dataset: str) -> None:
        self._store = store
        self._dataset = dataset
    # read / count / get_years / get_date_range / get_checksum / list_instrument_ids / data_root

# dataset_writer.py
class ParquetDatasetWriter:
    """通用 Parquet 数据集写入器，通过 dataset 路径参数化。"""
    def __init__(self, store: ParquetStore, dataset: str) -> None:
        self._store = store
        self._dataset = dataset
    # write / delete / delete_partition / data_root
```

### 薄具体类（~5 行/类）

```python
# storage/market/stock/bars/bars_reader.py（~5 行，原 140 行）
class StockBarsReader(ParquetDatasetReader):
    def __init__(self, store: ParquetStore) -> None:
        super().__init__(store, "market/stock/bars")
```

### 机械类清单（20 个文件缩减）

| 子域 | Reader | Writer |
|------|--------|--------|
| stock/bars | StockBarsReader | StockBarsWriter |
| stock/status | StockStatusReader | StockStatusWriter |
| stock/adj | StockAdjFactorReader | StockAdjFactorWriter |
| etf/bars | EtfBarsReader | EtfBarsWriter |
| etf/status | EtfStatusReader | EtfStatusWriter |
| etf/adj | EtfAdjFactorReader | EtfAdjFactorWriter |
| etf/nav | EtfNavReader | EtfNavWriter |
| index/bars | IndexBarsReader | IndexBarsWriter |
| fx/bars | FxBarsReader | FxBarsWriter |
| commodity/bars | CommodityBarsReader | CommodityBarsWriter |

### 非机械类（保留独立文件）

| 类 | 原因 |
|----|------|
| IndexConstituentReader/Writer | SQLiteStore，有 PIT get() 自定义逻辑 |
| StChangeHistoryReader/Writer | 需确认是否有额外逻辑 |

### 扩展机制

需要自定义查询方法时，子类添加方法：

```python
class StockBarsReader(ParquetDatasetReader):
    def __init__(self, store: ParquetStore) -> None:
        super().__init__(store, "market/stock/bars")

    def get_latest(self, instrument_id: int) -> pl.DataFrame:
        return self._store.read(self._dataset, instrument_ids=[instrument_id]).tail(1)
```

分区策略差异在 Store 层消化，Reader 层无感（组合模式天然支持）。

---

## 2.3 SQLite 机械类参数化

### Spec 定义

**新增文件**：`storage/base/sqlite_table_spec.py`

```python
@dataclass(frozen=True)
class SqliteTableSpec:
    """SQLite 表查询规格。"""
    table: str
    columns: tuple[str, ...]           # 业务列（不含 PIT 公共列）
    id_column: str                     # "instrument_id" / "index_id"
    date_column: str                   # "report_date" / "trade_date"
    nullable_columns: frozenset[str] = frozenset()
```

### 基类（组合 SQLiteClient）

**新增文件**：`storage/base/sqlite_table_reader.py`, `storage/base/sqlite_table_writer.py`

```python
# sqlite_table_reader.py
class SqliteTableReader:
    """通用 SQLite PIT 表读取器，通过 spec 参数化。"""
    def __init__(self, spec: SqliteTableSpec, client: SQLiteClient) -> None: ...
    def get(self, id_value: int, as_of_date: date) -> pl.DataFrame: ...

# sqlite_table_writer.py
class SqliteTableWriter:
    """通用 SQLite 表写入器，通过 spec 参数化。"""
    def __init__(self, spec: SqliteTableSpec, client: SQLiteClient) -> None: ...
    def write(self, df: pl.DataFrame) -> int: ...
```

### Spec 定义（7 个）

```python
# storage/fundamental/financial/specs.py
BALANCE_SHEET_SPEC = SqliteTableSpec(
    table="balance_sheet",
    columns=("total_assets", "total_liabilities", "net_assets",
             "current_assets", "current_liabilities"),
    id_column="instrument_id", date_column="report_date",
)
# ... income_statement, cash_flow, dividend, corporate_actions, forecast, express
```

```python
# storage/capital/specs.py
# ... valuation_metrics, margin_trading, pledge_ratio, index_composition
```

### 薄具体类（11R + 11W，每个 ~5 行）

```python
# storage/fundamental/financial/balance_sheet_reader.py
class BalanceSheetReader(SqliteTableReader):
    def __init__(self, client: SQLiteClient) -> None:
        super().__init__(BALANCE_SHEET_SPEC, client)
```

---

## 2.4 Readers/Writers 重命名（原 Ports）

**文件**：`services/ports.py` → `services/deps.py`

```python
# services/deps.py
@dataclass
class MarketReaders:
    stock_bars: DatasetReader       # Protocol 类型
    etf_bars: DatasetReader
    stock_status: DatasetReader
    stock_adj: DatasetReader
    etf_status: DatasetReader
    instrument: DatasetReader
    etf_adj: DatasetReader | None = None
    etf_nav: DatasetReader | None = None
    index_bars: DatasetReader | None = None
    index_constituent: DatasetReader | None = None
    fx_bars: DatasetReader | None = None
    commodity_bars: DatasetReader | None = None
```

重命名映射：

```
MarketReadPorts       → MarketReaders
MarketWritePorts      → MarketWriters
FundamentalReadPorts  → FundamentalReaders
FundamentalWritePorts → FundamentalWriters
CapitalReadPorts      → CapitalReaders
CapitalWritePorts     → CapitalWriters
```

---

## 2.5 DI Provider 简化

### Before（market.py ~270 行）

```python
@provide
def stock_bars_reader(self, settings) -> StockBarsReader: ...
@provide
def etf_bars_reader(self, settings) -> EtfBarsReader: ...
# ... 22 个 @provide 方法
```

### After（market.py ~60 行）

```python
@provide
def parquet_store(self, settings: DataStoreSettings) -> ParquetStore:
    return ParquetStore(settings.data_root, YearlyPartition())

@provide
def market_readers(self, store: ParquetStore, ...) -> MarketReaders:
    return MarketReaders(
        stock_bars=StockBarsReader(store),
        etf_bars=EtfBarsReader(store),
        ...
    )
```

---

## 2.6 execution/ 实体重构 + CQRS 纯化

### 包结构

```
services/trade/ → 拆分为：
├── strategy/
│   └── signals.py       # SignalRecord Reader/Writer
├── execution/
│   ├── __init__.py
│   ├── orders.py        # OrderRecord Reader/Writer
│   └── fills.py         # FillRecord Reader/Writer
└── portfolio/
    ├── __init__.py
    └── positions.py     # PositionRecord Reader/Writer
```

### 实体重命名

| 原实体 | 新实体 | 领域归属 | 说明 |
|--------|--------|---------|------|
| `TradeIntentRecord` | `SignalRecord` | strategy/ | 去掉 quantity/status，保留 strategy/signal/direction/score |
| (从 Intent 拆出) | `OrderRecord` | execution/ | quantity/status/order_type |
| `ManualExecutionFillRecord` | `FillRecord` | execution/ | 去掉 "Manual" 前缀 |
| `ActualPositionSnapshotRecord` | `PositionRecord` | portfolio/ | 简化命名 |

### Pipeline 流转（App 层编排）

```
SignalRecord (strategy output)
  → Portfolio Construction (App 层) →
OrderRecord (execution instruction)
  → Execution Engine →
FillRecord (execution result)
  → Position Tracker →
PositionRecord (portfolio state)
```

### CQRS 拆分

每个实体独立 Reader + Writer，不再混合读写：

```python
# Before: TradeIntentWriter 包含读写
class TradeIntentWriter:
    def save(self, record): ...      # 写
    def get(self, intent_id): ...    # 读
    def list(self, ...): ...         # 读

# After: SignalReader + SignalWriter
class SignalReader:
    def get(self, signal_id) -> SignalRecord | None: ...
    def list(self, ...) -> list[SignalRecord]: ...

class SignalWriter:
    def save(self, record) -> None: ...
```

---

## 2.7 importlinter 规则

- `data-sources-cross-isolation`：禁止 sources 子域互相导入
- `data-services-cqrs-mutual-exclusion`：Reader 禁止调用写方法

---

## 改动量估算

| 类别 | 新增文件 | 修改文件 | 说明 |
|------|---------|---------|------|
| Protocol 层 | 1 | 0 | providers/protocols.py |
| Parquet 基类 | 2 | 0 | dataset_reader.py, dataset_writer.py |
| Parquet 具体类 | 0 | 20 | 每个文件 ~130 行 → ~5 行 |
| SQLite 基类 | 3 | 0 | spec + reader + writer |
| SQLite Spec | 2 | 0 | fundamental/specs.py, capital/specs.py |
| SQLite 具体类 | 0 | 22 | 每个文件 ~70 行 → ~5 行 |
| Readers/Writers | 0 | 3 | ports.py → deps.py + DI files |
| execution 重构 | 6 | 3 | 新包 + service.py + models/trade.py |
| importlinter | 0 | 1 | .importlinter |
| **合计** | ~14 | ~49 | |

---

## 实施顺序

```
Step 1: Protocol 接口层定义（无破坏性）
Step 2: Parquet 基类 + 具体类迁移（逐子域）
Step 3: SQLite 基类 + 具体类迁移（逐子域）
Step 4: Readers/Writers 重命名 + DI 简化
Step 5: execution/ 实体重构 + CQRS 拆分
Step 6: importlinter 规则更新
Step 7: 验证（pixi run -e dev check）
```

每个 Step 独立可验证，确保渐进式安全重构。
