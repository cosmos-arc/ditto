# ditto-datahub

Ditto 量化系统的数据层，统一管理数据获取、存储、查询和 PIT (Point-in-Time) 安全。

## 概述

`ditto-datahub` 是 Ditto 量化系统的核心数据模块，提供：

- **统一数据入口**：`DataHub` 门面类，封装所有数据访问
- **PIT 安全**：时点安全的数据查询，避免未来函数
- **高性能存储**：Parquet 文件存储 + SQLite 元数据
- **数据质量检查**：多维度 DQ 检查和报告
- **多数据源支持**：Tushare、Akshare 等

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
│ Runtime层    │ │  Store层     │ │ Repository层  │ │  Sources层   │
│              │ │              │ │              │ │              │
│ SQLitePool   │ │ SecurityStore│ │ Securities   │ │ Tushare      │
│ FileLock     │ │ CalendarStore│ │ Bars         │ │ Akshare      │
│ SidAllocator │ │ BarsStore    │ │ Calendar     │ │              │
│ DQChecker    │ │ AdjFactor... │ │ Universe     │ │              │
│ FreezeMgr    │ │              │ │ Index        │ │              │
│ SqlEngine    │ │              │ │              │ │              │
└──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘
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
| `PipelineStore` | ETL 流水 | SQLite |
| `UniverseStore` | 股票池 | SQLite |
| `IndexWeightStore` | 指数权重 | SQLite |
| `IngestionMetadataStore` | 数据摄取元数据 | SQLite |
| `QuarantineStore` | 数据隔离区 | SQLite |

### Repository 层

业务逻辑封装层：

| 组件 | 说明 |
|------|------|
| `SecurityRepository` | 证券查询、注册、标识符解析 |
| `BarsRepository` | 行情查询、复权计算 |
| `CalendarRepository` | 交易日历查询、日期偏移 |
| `UniverseRepository` | 股票池管理 |
| `IndexRepository` | 指数成分股管理 |

### Sources 层

外部数据源适配器：

| 组件 | 说明 |
|------|------|
| `TushareClient` | Tushare API 客户端 |
| `TushareSource` | Tushare 数据源实现 |
| `SourcesAccessor` | 数据源统一访问入口 |

## 安装

```bash
# 通过 pixi 安装（推荐）
pixi install

# 开发模式安装
pip install -e ./packages/datahub
```

## 快速开始

### 基本用法

```python
from ditto_datahub import DataHub

# 初始化 DataHub（使用默认数据目录）
hub = DataHub()

# 或者指定数据目录
hub = DataHub(data_root="/path/to/data")

# 查询证券信息
security = hub.securities.get_by_sid(1)
print(security)  # {sid: 1, symbol: "600000", name: "浦发银行", ...}

# 查询交易日历
trading_days = hub.calendar.get_range("2024-01-01", "2024-01-31")
print(trading_days)  # ["2024-01-02", "2024-01-03", ...]

# 查询行情数据（带复权）
bars = hub.bars.get_bars(
    sids=[1, 2],
    start="2024-01-01",
    end="2024-01-31",
    adjust="qfq"  # 前复权
)
print(bars)
# shape: (62, 8)
# ┌──────┬──────┬────────────┬───────┬───────┬───────┬───────┬───────┐
# │ sid  ┆ ...  ┆ trade_date ┆ open  ┆ high  ┆ low   ┆ close ┆ volume│
# │ ---  ┆ ---  ┆ ---        ┆ ---   ┆ ---   ┆ ---   ┆ ---   ┆ ---   │
# │ i64  ┆ ...  ┆ str        ┆ f64   ┆ f64   ┆ f64   ┆ f64   ┆ i64   │
# ╞══════╪══════╪════════════╪═══════╪═══════╪═══════╪═══════╪═══════╡
# │ 1    ┆ ...  ┆ 2024-01-02 ┆ 7.25  ┆ 7.32  ┆ 7.23  ┆ 7.31  ┆ ...  │
# └──────┴──────┴────────────┴───────┴───────┴───────┴───────┴───────┘
```

### PIT 安全查询

```python
from ditto_datahub import DataHub
from ditto_datahub.runtime.pit_helper import PitHelper

hub = DataHub()

# PIT 安全：查询 2024-01-15 时点的已知数据
# 确保只使用该时点之前公布的数据，避免未来函数
decision_date = "2024-01-15"

# 使用 Repository 层的 PIT 安全方法
bars = hub.bars.get(
    sids=[1],
    start="2024-01-01",
    end=decision_date,  # 决策日
    asof=decision_date,  # PIT 查询：只使用 decision_date 之前的数据
)

# 或者使用 PitHelper 手动构建 PIT SQL
query = "SELECT * FROM stock_daily WHERE sid = 1"
pit_query = PitHelper.add_pit_filter(query, decision_date)
# "SELECT * FROM stock_daily WHERE sid = 1 AND knowledge_date <= '2024-01-15'"

result = hub.sql_engine.execute(pit_query)
```

### 数据源管理

```python
from ditto_datahub import DataHub

hub = DataHub()

# 获取数据源访问器
sources = hub.sources

# 使用 Tushare 数据源
tushare = sources.tushare

# 获取证券列表
securities = tushare.get_securities()

# 获取行情数据
bars = tushare.get_bars(
    trade_date="2024-01-15",
    source="tushare"
)
```

### 数据质量检查

```python
from ditto_datahub import DataHub

hub = DataHub()

# 运行 DQ 检查
result = hub.dq_checker.check(
    data=bars_df,
    checkers=["business", "statistical", "technical"]
)

# 查看检查结果
print(result.summary())
# DQCheckResult(
#     total_checks=50,
#     passed=45,
#     failed=5,
#     warnings=2,
#     severities={"ERROR": 3, "WARNING": 2}
# )

# 生成报告
report = hub.dq_checker.generate_report(result)
report.save_html("dq_report.html")
```

## PIT 安全核心规则

### 为什么需要 PIT 安全？

量化回测中，使用"未来数据"会导致回测收益虚高。例如：
- **错误做法**：使用 T+1 日公布的复权因子决策 T 日交易
- **正确做法**：只使用 T 日及之前公布的数据

### PIT 安全三原则

1. **knowledge_date 字段**：所有数据表必须包含此字段，表示数据"已知时间"
2. **closed="left"**：Polars rolling 窗口必须显式指定，避免使用当日数据
3. **T日信号→T+1执行**：信号生成日不能执行，次一交易日才能执行

### 错误示例

```python
# ❌ 错误：使用 trade_date 过滤（构成未来函数）
baseline_df = adj_df.filter(pl.col("trade_date") <= asof_date)

# ❌ 错误：rolling 使用默认值（包含当日）
pl.col("close").rolling_mean(20)
```

### 正确示例

```python
# ✅ 正确：使用 knowledge_date 过滤
baseline_df = adj_df.filter(pl.col("knowledge_date") <= asof_date)

# ✅ 正确：rolling 显式指定 closed="left"
pl.col("close").rolling_mean(20, closed="left")
```

### PitHelper 辅助函数

```python
from ditto_datahub.runtime.pit_helper import PitHelper

# 添加 PIT 过滤条件
query = "SELECT * FROM stock_daily"
pit_query = PitHelper.add_pit_filter(query, "2024-01-15")
# "SELECT * FROM stock_daily WHERE knowledge_date <= '2024-01-15'"

# PIT ASOF JOIN
pit_join = PitHelper.add_pit_join(
    left_table="stock_daily s",
    right_table="adj_factor a",
    join_keys=["s.sid = a.sid"],
    asof_date="2024-01-15",
    date_column="trade_date"  # 可指定不同的日期列
)
# "stock_daily s LEFT JOIN adj_factor a ON s.sid = a.sid AND a.trade_date <= '2024-01-15'"
```

详细 PIT 指南请参考：`.claude/skills/pit-guide/SKILL.md`

## 复权数据说明

### Tushare pre_close 字段特性

**重要**：Tushare 返回的 `pre_close` 字段不需要复权调整

- `pre_close` 是**除权参考价**（已处理除权除息）
- Tushare 保证 `pre_close` 用于计算当日涨跌幅的正确性
- 只需对 `open/high/low/close` 进行复权（这些是原始价格）
- `pre_close` 保持原样即可

### 涨跌幅计算

```python
# 当日涨跌幅 = (close - pre_close) / pre_close
# pre_close 已经是正确的参考价，无需调整
daily_return = (close - pre_close) / pre_close
```

### 复权实现

DataHub 的复权逻辑已正确实现此行为：

```python
# 只对 OHLC 进行复权，pre_close 保持不变
def _apply_qfq_adj(df, adj_df, asof=None):
    df = df.with_columns([
        (pl.col("open") * adj_factor / latest_factor).alias("open"),
        (pl.col("high") * adj_factor / latest_factor).alias("high"),
        (pl.col("low") * adj_factor / latest_factor).alias("low"),
        (pl.col("close") * adj_factor / latest_factor).alias("close"),
        # pre_close 不需要调整
    ])
```

相关代码：[repositories/bars.py](src/ditto_datahub/repositories/bars.py)

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
└── quarantine/             # 数据隔离区
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

## 开发

### 运行测试

```bash
# 单元测试（快速）
pixi run -e dev test-unit

# PIT 数据正确性测试
pixi run -e dev test-pit

# 完整测试（带覆盖率）
pixi run -e dev test-cov
```

### 代码质量检查

```bash
# 快速检查（自动修复）
pixi run -e dev quick-check

# 提交前检查
pixi run -e dev pre-push-check

# 完整 CI 检查
pixi run -e dev ci-check
```

## 相关文档

- [PIT 安全指南](.claude/skills/pit-guide/SKILL.md)
- [Polars 使用指南](.claude/skills/polars-guide/SKILL.md)
- [风控指南](.claude/skills/risk-guide/SKILL.md)
- [数据设计文档](docs/design/02_data_design.md)

## 许可证

MIT License
