# storage

数据存储层 — SQLite 与 Parquet 双存储，CQRS 读写分离，按业务领域组织。

## 目录结构

```
storage/
├── base/             # BaseReader/BaseWriter 抽象, SQLiteStore
├── metadata/         # 元数据域（instrument, identity, industry, calendar, universe）
├── market/           # 行情域（stock/etf/index/commodity/fx: bars, status, adj, nav）
├── fundamental/      # 基本面域（financial, corporate, forecast）
├── capital/          # 资本域（margin, pledge, valuation, futures, index_composition）
├── macro/            # 宏观域（indicator, metadata）
├── features/         # 特征域（技术指标）
├── factors/          # 因子域（因子信号）
├── runtime/          # 运行时 store（摄入游标/日志/质量）
├── schemas/          # Schema 定义
└── sqlite_client.py  # SQLite 客户端
```

## 各 Store 职责

### 元数据域 (`metadata/`)

| Store | 职责 | 存储 |
|-------|------|------|
| CalendarReader/Writer | 交易日历 | SQLite |
| InstrumentReader/Writer | 证券工具主数据 | SQLite |
| IndustryReader/Writer | 行业分类与映射 | SQLite |
| UniverseReader/Writer | 自定义 Universe 成分与再平衡记录 | SQLite |
| FeeScheduleReader/Writer | 交易费率表 | SQLite |
| TradingRuleReader/Writer | 交易规则（涨跌停/手数等） | SQLite |

### 行情域 (`market/`)

| Store | 职责 | 存储 |
|-------|------|------|
| StockBarReader/Writer | 股票日/分钟行情 | Parquet |
| EtfBarReader/Writer | ETF 日行情 | Parquet |
| IndexBarReader/Writer | 指数行情 | Parquet |
| CommodityBarReader/Writer | 商品行情 | Parquet |
| FxBarReader/Writer | 外汇行情 | Parquet |
| AdjFactorReader/Writer | 复权因子 | SQLite |
| NavReader/Writer | ETF 净值 | SQLite |

### 基本面域 (`fundamental/`)

| Store | 职责 | 存储 |
|-------|------|------|
| FinancialReader/Writer | 财报（利润表/资产负债表/现金流量表） | SQLite |
| ForecastReader/Writer | 业绩快报/一致性预测 | SQLite |
| CorporateReader/Writer | 公司行为（分红/拆股） | SQLite |

### 资本域 (`capital/`)

| Store | 职责 | 存储 |
|-------|------|------|
| ValuationReader/Writer | 估值指标（PE/PB/PS 等） | SQLite |
| MarginReader/Writer | 融资融券数据 | SQLite |
| PledgeReader/Writer | 股票质押数据 | SQLite |
| IndexCompositionReader/Writer | 指数成分股 | SQLite |

### 宏观域 (`macro/`)

| Store | 职责 | 存储 |
|-------|------|------|
| MacroIndicatorReader/Writer | 宏观经济指标 | SQLite |

## CQRS 模式

每个 store 拆分为 `*_reader.py` 和 `*_writer.py`：

| 组件 | 职责 | 方法 | 副作用 |
|------|------|------|--------|
| Reader | 查询 | `read()`, `count()`, `get_*()` | 无，可并发 |
| Writer | 写入/删除 | `write()`, `delete()` | 有，需并发控制 |

### CQRS 读写接口示例

```python
# Reader：只读查询
class InstrumentReader:
    def read(self, instrument_ids: Sequence[int]) -> pl.DataFrame: ...
    def count(self) -> int: ...
    def get_by_ticker(self, ticker: str) -> pl.DataFrame: ...

# Writer：写入操作
class InstrumentWriter:
    def write(self, df: pl.DataFrame) -> None: ...
    def delete(self, instrument_ids: Sequence[int]) -> None: ...
```

## 与 Service 层的交互模式

```
┌──────────────────────────────────────────────────────┐
│                   Service 层                         │
│  MetadataService / MarketService / CapitalService    │
│  组合 Reader + Writer 封装业务逻辑                     │
└──────────────┬───────────────────────┬───────────────┘
               │ read                  │ write
               ▼                       ▼
┌──────────────────────┐  ┌──────────────────────┐
│    Reader (CQRS Q)   │  │   Writer (CQRS C)    │
│  无副作用，可并发     │  │  有副作用，需并发控制   │
└──────────────────────┘  └──────────────────────┘
```

- Service 层持有 Reader + Writer 引用，对外暴露业务方法
- Service 层负责事务边界、DQ 检查、事件发布
- 外部调用者只与 Service 交互，禁止直接实例化 Reader/Writer

## Reader vs Writer 职责边界

| 关注点 | Reader | Writer |
|--------|--------|--------|
| 数据查询 | ✅ | ❌ |
| 数据写入 | ❌ | ✅ |
| 并发控制 | 不需要 | 需要（FileLock） |
| 缓存 | 可选（DataCache） | ❌ |
| PIT 过滤 | ✅（透明注入） | ❌ |
| DQ 检查 | ❌ | ✅（写入前） |

## 访问规则

- **外部调用者**：通过 Domain Service 间接访问，禁止直接实例化 Reader/Writer
- **Service 层**：组合 Reader + Writer 封装业务逻辑
- **DI 注册**：Reader/Writer 在 data 域 DI Provider 中注册，由 Service 注入
