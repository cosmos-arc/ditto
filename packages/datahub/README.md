# ditto-datahub

**版本**: v0.7.0
**最后更新**: 2026-01-27
**状态**: ✅ 稳定

## 概要

Ditto 量化系统的数据层，统一管理数据获取、存储、查询和 PIT (Point-in-Time) 安全。

## 核心功能

- **统一数据入口**: DataHub 门面类，封装所有数据访问
- **PIT 安全**: 时点安全的数据查询，避免未来函数
- **高性能存储**: Parquet 文件存储 + SQLite 元数据
- **数据质量检查**: 多维度 DQ 检查和报告
- **多数据源支持**: Tushare、Akshare 等

## 架构

DataHub 采用分层架构，使用 `@cached_property` 实现延迟加载：

```
┌─────────────────────────────────────────────────────────┐
│                       DataHub                          │
│                   (统一入口/Facade)                      │
└─────────────────────────────────────────────────────────┘
                │
        ┌───────┴───────┬───────────────┬───────────────┐
        ▼               ▼               ▼               ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│ Runtime层    │ │  Store层     │ │ Accessor层   │ │  Sources层   │
│              │ │              │ │              │ │              │
│ SQLitePool   │ │ SecurityStore│ │ Securities   │ │ Tushare      │
│ FileLock     │ │ CalendarStore│ │ Bars         │ │ Akshare      │
│ SidAllocator │ │ BarsStore    │ │ Calendar     │ │              │
│ DQChecker    │ │ AdjFactor... │ │ Universe     │ │              │
│ FreezeMgr    │ │              │ │ Index        │ │              │
│ SqlEngine    │ │              │ │              │ │              │
└──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘
```

### 基础层

基础层提供统一的数据存储抽象接口：

| 组件 | 说明 |
|------|------|
| `BaseStore` | 抽象基类，定义所有存储实现的统一接口 (read/write/delete) |
| `ParquetStore` | Parquet 文件存储实现，支持按年分区、自动去重 |
| `SQLiteStore` | SQLite 数据库存储实现，支持事务、PIT 查询 |

**配置系统**：从多路径配置简化为单 `DATA_ROOT` 配置，所有路径自动生成：

```python
from ditto_datahub.config import DataRootConfig

# 初始化配置（可通过 DATA_ROOT 环境变量设置）
config = DataRootConfig()
# 默认: /data/ditto
# 自动生成: market/stock/bars/daily/, metadata/metadata.sqlite, 等

# 使用配置
store = BarsStore(config.data_root)
```

### Runtime 层

运行时基础设施组件：

| 组件 | 说明 |
|------|------|
| `SQLitePool` | SQLite 连接池，管理元数据数据库 |
| `FileLockManager` | 文件锁管理器，保证并发写入安全 |
| `SidAllocator` | SID (Security ID) 分配器 |
| `DQChecker` | 数据质量检查引擎 |
| `FreezeManager` | 数据冻结管理器 |
| `SqlEngine` | SQL 执行引擎，支持慢查询监控 |
| `DataCache` | 统一缓存层（基于 cachebox） |
| `PitHelper` | PIT SQL 辅助函数 |

### Store 层

数据存储组件（Parquet 文件 + SQLite 元数据）：

| 组件 | 说明 | 存储格式 |
|------|------|----------|
| `SecurityStore` | 证券主数据 | SQLite |
| `CalendarStore` | 交易日历 | SQLite + 内存缓存 |
| `BarsStore` | OHLCV 行情 | Parquet (分区: sid/year) |
| `AdjFactorStore` | 复权因子 | Parquet (分区: sid/year) |
| `UniverseStore` | 股票池 | SQLite |
| `IndexWeightStore` | 指数权重 | SQLite |
| `IngestionLogStore` | 数据摄取事件日志 | SQLite |
| `QuarantineStore` | 数据隔离区 | SQLite |

### 域级组织

DataHub 采用域驱动设计（DDD），按业务域组织代码结构：

#### Metadata 域

- `domains/metadata/`: Metadata 域
  - `security/`: 证券主数据
    - `security_store.py`: SecurityStore（证券主数据存储）
    - `identity_store.py`: IdentityStore（标识符映射存储，支持 PIT）
  - `identity/`: 标识符映射（待迁移）
  - `industry/`: 申万行业分类
    - `industry_basic_store.py`: IndustryBasicStore（行业主数据）
    - `industry_mapping_store.py`: IndustryMappingStore（股票-行业映射，支持 PIT）
  - `calendar/`: 交易日历
    - `calendar_store.py`: CalendarStore（交易日历存储）
  - `universe/`: 标的池
  - `metadata_query_service.py`: 域级统一查询服务

#### Market 域

- `domains/market/`: Market 域（待实现）

#### 架构优势

- **高内聚**: 相关业务逻辑聚合在同一域内
- **低耦合**: 域之间通过明确的接口（QueryService）交互
- **可扩展**: 新增域不影响现有域的实现
- **易测试**: 每个域可独立测试

### Accessor 层

业务逻辑封装层：

| 组件 | 说明 |
|------|------|
| `SecurityAccessor` | 证券查询、注册、标识符解析 |
| `BarsAccessor` | 行情查询、复权计算 |
| `CalendarAccessor` | 交易日历查询、日期偏移 |
| `UniverseAccessor` | 股票池管理 |
| `IndexAccessor` | 指数成分股管理 |

### Sources 层

外部数据源适配器：

| 组件 | 说明 |
|------|------|
| `TushareClient` | Tushare API 客户端 |
| `TushareSource` | Tushare 数据源实现 |
| `DataSources` | 数据源统一访问入口 |

## 使用示例

### 基础层使用

直接使用基础层存储组件：

```python
from ditto_datahub.config import DataRootConfig
from ditto_datahub.stores.base import ParquetStore, SQLiteStore
import polars as pl

# 初始化配置
config = DataRootConfig()

# ParquetStore：按年分区存储
parquet_store = ParquetStore(config.market_stock_bars_path)

# 写入数据
df = pl.DataFrame({
    "sid": [1, 1, 2],
    "trade_date": ["2024-01-02", "2024-01-03", "2024-01-02"],
    "close": [10.5, 10.8, 20.3],
})
result = parquet_store.write(
    dataset="stock_daily",
    data=df,
    on_duplicate="keep_last",
    year=2024,
)

# 读取数据
df = parquet_store.read(
    dataset="stock_daily",
    sids=[1, 2],
    start_date="2024-01-01",
    end_date="2024-01-31",
)

# SQLiteStore：元数据存储
sqlite_store = SQLiteStore(config.metadata_db_path)

# 执行 SQL 查询
rows = sqlite_store.fetchall("SELECT * FROM securities WHERE sid IN (1, 2)")
```

### 基本用法

```python
from ditto_datahub import DataHub

# 初始化 DataHub（使用默认数据目录）
hub = DataHub()

# 查询证券信息
security = hub.securities.get_by_sid(1)

# 查询交易日历
trading_days = hub.calendar.get_range("2024-01-01", "2024-01-31")

# 查询行情数据（带复权）
bars = hub.bars.get_bars(
    sids=[1, 2],
    start="2024-01-01",
    end="2024-01-31",
    adjust="qfq"  # 前复权
)
```

### Metadata 查询（新 API）

DataHub v0.7.0 引入了域级查询服务 `MetadataQueryService`，提供统一的 Metadata 域查询接口：

```python
from ditto_datahub import DataHub

hub = DataHub()

# 标识符解析（支持 PIT）
sid = hub.metadata.resolve_sid("600000.SH", source="tushare")
sid = hub.metadata.resolve_sid("600000.SH", source="tushare", asof="2024-06-30")

# 查询证券信息
df = hub.metadata.get_securities(sids=[1, 2, 3])
df = hub.metadata.get_securities(sids=[1], asset_class="stock", exchange="SSE")

# 查询交易日历
trading_days = hub.metadata.get_trading_days("2024-01-01", "2024-01-31")
trading_days = hub.metadata.get_trading_days("2024-01-01", "2024-01-31", only_open=True)

# 交易日历便捷方法
is_trading = hub.metadata.is_trading_day("2024-01-15")
prev_day = hub.metadata.get_prev_trading_day("2024-01-15")
next_day = hub.metadata.get_next_trading_day("2024-01-15")

# 查询行业分类
industries = hub.metadata.get_industries(level=1)  # 一级行业
mappings = hub.metadata.get_industry_mappings(sids=[1, 2, 3], asof="2024-06-30")

# 查询标的池
universe = hub.metadata.get_universe(name="csi300")
```

#### 向后兼容

为了平滑迁移，DataHub 保留了旧的 API 别名：

```python
# 旧 API（仍然支持）
sid = hub.securities.resolve_sid("600000.SH", source="tushare")
df = hub.securities.get(sids=[1, 2, 3])
trading_days = hub.calendar.get("2024-01-01", "2024-01-31")

# 新 API（推荐）
sid = hub.metadata.resolve_sid("600000.SH", source="tushare")
df = hub.metadata.get_securities(sids=[1, 2, 3])
trading_days = hub.metadata.get_trading_days("2024-01-01", "2024-01-31")
```

**迁移建议**：新代码优先使用 `hub.metadata` 接口，旧代码可逐步迁移。

### PIT 安全查询

```python
from ditto_datahub import DataHub

hub = DataHub()
decision_date = "2024-01-15"

# 使用 Accessor 层的 PIT 安全方法
bars = hub.bars.get(
    sids=[1],
    start="2024-01-01",
    end=decision_date,
    asof=decision_date,  # PIT 查询：只使用 decision_date 之前的数据
)
```

### 数据质量检查

DataHub 提供三级数据质量检查机制：

**L1 技术检查**: 非空、唯一、类型、外键、必需列
**L2 业务检查**: 正值、表达式、范围、非零成交量
**L3 统计检查**: Z-score 异常检测、完整性检查

```python
from ditto_datahub import DataHub

hub = DataHub()

# 运行 DQ 检查
result = hub.dq_checker.check(
    data=bars_df,
    checkers=["business", "statistical", "technical"]
)
```

## PIT 安全核心规则

### PIT 安全三原则

1. **knowledge_date 字段**：所有数据表必须包含此字段，表示数据"已知时间"
2. **closed="left"**：Polars rolling 窗口必须显式指定，避免使用当日数据
3. **T日信号→T+1执行**：信号生成日不能执行，次一交易日才能执行

### 正确示例

```python
# ✅ 正确：使用 knowledge_date 过滤
baseline_df = adj_df.filter(pl.col("knowledge_date") <= asof_date)

# ✅ 正确：rolling 显式指定 closed="left"
pl.col("close").rolling_mean(20, closed="left")
```

### 错误示例

```python
# ❌ 错误：使用 trade_date 过滤（构成未来函数）
baseline_df = adj_df.filter(pl.col("trade_date") <= asof_date)

# ❌ 错误：rolling 使用默认值（包含当日）
pl.col("close").rolling_mean(20)
```

## 数据目录结构

```
${data_root}/
├── meta/
│   ├── hub.sqlite          # 元数据数据库（证券、日历等）
│   └── pipeline.sqlite     # ETL 流水
├── bars/
│   ├── sid=1/
│   │   ├── year=2023/
│   │   │   └── data.parquet
│   │   └── year=2024/
│   └── sid=2/
├── adj_factor/
│   └── (同上)
├── locks/                  # 文件锁目录
├── quarantine/             # 数据隔离区
└── freezes/                # Freeze 管理器清单
```

## 性能优化

### 缓存策略

- **CalendarStore**：启动时全部加载到内存（~1MB，7500条记录）
- **DataCache**：基于 cachebox.TTLCache，支持 TTL + LRU
- **延迟加载**：使用 `@cached_property` 按需初始化组件

### Parquet 分区策略

```
bars/
├── sid=1/          # 按 SID 分区（减少扫描文件数）
│   ├── year=2023/  # 按年份分区（支持时间范围查询）
│   └── year=2024/
└── sid=2/
```

### 并发安全

- **文件锁**：`FileLockManager` 保证并发写入安全
- **连接池**：`SQLitePool` 复用连接，避免频繁打开/关闭

## 相关文档

- [PIT 安全指南](../../../../.claude/skills/pit-guide/SKILL.md)
- [Polars 使用指南](../../../../.claude/skills/polars-guide/SKILL.md)
- [数据设计文档](../../../../docs/design/02_data_design.md)

## 变更记录

### v0.7.0 (2026-01-27)
**新增**
- Metadata 域架构：`domains/metadata/` 目录结构
  - `security/`: 证券主数据域（SecurityStore、IdentityStore）
  - `industry/`: 申万行业分类域（IndustryBasicStore、IndustryMappingStore）
  - `calendar/`: 交易日历域（CalendarStore）
  - `universe/`: 标的池域
- MetadataQueryService：域级统一查询服务（`hub.metadata`）
  - 标识符解析（支持 PIT）
  - 证券信息查询
  - 交易日历查询
  - 行业分类查询
  - 标的池查询

**重构**
- SecurityStore 迁移到 `domains/metadata/security/`
- CalendarStore 迁移到 `domains/metadata/calendar/`
- IndustryBasicStore、IndustryMappingStore 新增
- IdentityStore 新增（支持 PIT 标识符映射）
- DataHub 集成 MetadataQueryService，提供 `hub.metadata` 统一查询接口

**改进**
- 向后兼容性：保留 `hub.securities`、`hub.calendar` 别名
- 所有 Store 继承 SQLiteStore 基类
- 增强类型安全，完善文档注释
- 域驱动设计（DDD）：高内聚、低耦合、易扩展

### v0.6.0 (2026-01-27)
**新增**
- 基础层架构：添加 `BaseStore` 抽象基类，定义统一存储接口
- `ParquetStore`：Parquet 文件存储实现，支持按年分区、自动去重
- `SQLiteStore`：SQLite 数据库存储实现，支持事务、PIT 查询
- `DataRootConfig`：统一数据根路径配置，简化路径管理

**改进**
- 从多路径配置简化为单 `DATA_ROOT` 配置
- 所有存储实现继承 `BaseStore`，保证接口一致性
- 增强类型安全和代码可维护性

### v0.5.0 (2026-01-23)
**新增**
- README 标准化，添加版本、日期、状态元数据
- 添加变更记录部分

**改进**
- 完善架构说明
- 重新组织文档结构

### v0.4.0 (2025-12-27)
**新增**
- Sprint 1 P0 任务全部完成
- DataHub Facade 实现
- SqlEngine 实现

### v0.1.0 (2025-12-08)
**新增**
- 初始数据层实现
- Stores 层基础功能
- Runtime 层基础组件
