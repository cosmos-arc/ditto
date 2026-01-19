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
| `SourcesProvider` | 数据源统一访问入口 |

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

# 使用 Accessor 层的 PIT 安全方法
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

DataHub 提供三级数据质量检查机制：

**L1 技术检查**
- `not_null`: 非空约束检查
- `unique`: 唯一性约束检查
- `type_check`: 数据类型验证
- `foreign_key`: 外键验证（支持白名单）
- `required_columns`: 必需列验证

**L2 业务检查**
- `positive`: 正值检查（如价格、成交量）
- `expression`: 表达式检查（如 OHLC 一致性）
- `range_check`: 范围检查
- `no_zero_volume`: 非零成交量检查

**L3 统计检查**
- `zscore`: Z-score 异常检测（支持分组）
- `completeness`: 数据完整性检查（交易日覆盖）

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

### DQ 配置管理

Ditto 使用 YAML 配置定义数据质量规则，支持用户自定义覆盖包内默认配置。

#### 配置路径

| 类型 | 路径 | 说明 |
|------|------|------|
| **默认配置** | `{package}/config/dq_rules/*.yml` | 包内默认规则 |
| **用户配置** | `{data_root}/config/dq/*.yml` | 用户自定义规则（覆盖默认） |

#### 加载优先级

用户配置优先级高于默认配置：`用户配置 > 包内默认配置`

#### 初始化用户配置

```bash
# 复制默认配置到用户目录
pixi run -e dev python -m ditto_datahub.cli.init_dq_config /path/to/data_root
```

示例输出：
```
Created: /path/to/data_root/config/dq/stock_daily.yml
Created: /path/to/data_root/config/dq/etf_daily.yml
Skipped (exists): /path/to/data_root/config/dq/index_daily.yml

DQ config initialized at: /path/to/data_root/config/dq
  Created: 2 files
  Skipped: 1 files
You can now customize these files.
```

#### 配置示例

```yaml
# packages/datahub/config/dq_rules/stock_daily.yml
dataset: stock_daily
description: "股票日 K 线数据质量检查规则"

# L1: 技术校验（写入时强制阻断）
l1_technical:
  - rule: not_null
    columns: [sid, trade_date, open, high, low, close, volume, amount]
    message: "必填字段不能为空"

  - rule: unique
    columns: [sid, trade_date]
    message: "主键 (sid, trade_date) 重复"

# L2: 业务规则（写入时警告但不阻断）
l2_business:
  - rule: positive
    columns: [open, high, low, close, volume, amount]
    message: "OHLC 价格、成交额必须为正数"

# L3: 统计异常（定时批量检查）
l3_statistical:
  - rule: zscore
    name: volume_spike
    column: volume
    window: 60
    threshold: 5
    group_by: sid
    message: "成交量异常波动（Z-score > 5）"
```

#### 自定义配置

1. 运行初始化脚本复制默认配置
2. 编辑 `{data_root}/config/dq/*.yml` 自定义规则
3. 重启应用使配置生效

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

相关代码：[accessors/bars.py](src/ditto_datahub/accessors/bars.py)

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

## Ingestion Metadata 系统

### 设计概述

Ingestion Metadata 系统采用 **"事件日志"** 模式，跟踪每日数据摄取状态：

| 组件 | 说明 | 表 |
|------|------|-----|
| `IngestionLogStore` | 每日摄取事件日志 | `ingestion_log` |

### 核心设计

#### 从"推进式"到"事件记录式"

**旧设计（已废弃）**：
```
┌─────────────────────────────────┐
│ IngestionMetadata (推进式)        │
│ ├─ last_trade_date: 2024-12-27   │
│ ├─ last_checksum: a1b2c3...      │
│ └─ last_rows: 500                │
└─────────────────────────────────┘
```

**新设计（事件日志）**：
```
┌─────────────────────────────────────────────────────────┐
│ ingestion_log (每个交易日一条记录)                        │
│ ├──────────┬────────┬──────────┬──────────┬─────────┐  │
│ │ date     │ status │ checksum │ attempts │ updated │  │
│ ├──────────┼────────┼─────────┼──────────┼─────────┤  │
│ │ 12-23    │ SUCCESS│ a1b2...  │ 1        │ 12-23   │  │
│ │ 12-24    │ FAIL   │ NULL     │ 2        │ 12-24   │  │
│ │ 12-25    │ FAIL   │ NULL     │ 1        │ 12-25   │  │
│ │ 12-26    │ SUCCESS│ b2c3...  │ 1        │ 12-26   │  │
│ └──────────┴────────┴─────────┴──────────┴─────────┘  │
└─────────────────────────────────────────────────────────┘
```

#### 状态定义

| 状态 | 场景 |
|------|------|
| **SUCCESS** | 获取成功，DQ 通过 |
| **FAIL** | 获取失败 / DQ 阻断 / 交易日空 df |

**重要**：非交易日不记录，依赖 `calendar` 表判断。

### 使用方式

```python
from ditto_datahub import DataHub
from ditto_datahub.sources.metadata import IngestionStatus

hub = DataHub()

# 记录成功摄取
log_store = hub.ingestion_log

# 保存成功日志
log = log_store.save_log(
    dataset="stock_daily",
    source="tushare",
    trade_date="2024-12-27",
    status=IngestionStatus.SUCCESS,
    checksum="abc123",
    rows=5000,
)

# 记录失败
fail_log = log_store.save_log(
    dataset="stock_daily",
    source="tushare",
    trade_date="2024-12-24",
    status=IngestionStatus.FAIL,
    error_code="DQ_BLOCKED",
    error_message="OHLC consistency check failed",
)

# 查询失败重跑
failed_dates = log_store.get_failed_dates(
    dataset="stock_daily",
    source="tushare",
    limit=10,
    max_attempts=3,
)
# ["2024-12-24", "2024-12-25", ...]

# 获取最后成功日期
last_success = log_store.get_last_success_date(
    dataset="stock_daily",
    source="tushare",
)
# "2024-12-26"
```

### Phase 0.4: Source 层重构 ✅ (已完成 - 2026-01-03)

#### 目标

移除 `IncrementalMode.QUICK/PRECISE`，统一为 `ingest_date()` 接口。

#### 旧接口（已删除）

```python
# ❌ 旧接口：使用 QUICK/PRECISE 模式（已删除）
df, metadata = source.fetch_etf_daily_incremental(
    trade_date="2024-12-27",
    mode=IncrementalMode.QUICK,  # 或 PRECISE
    last_trade_date="2024-12-26",
    last_checksum="abc123",
)
```

#### 新接口（使用 IngestionCoordinator）

```python
# ✅ 新接口：使用 IngestionCoordinator
from ditto_server.ingestion.services.coordinator import IngestionCoordinator

coordinator = IngestionCoordinator(hub, source)
result = coordinator.ingest_date(
    dataset="stock_daily",
    trade_date="2024-12-27",
    force=False,  # 强制更新，忽略 checksum
)
```

#### 实现要点

1. **非交易日检查**：抛出 `NotTradingDayError`
2. **交易日空 df**：抛出 `SourceFetchError`（数据质量异常）
3. **Checksum 验证**：
   - 未变且非 force → 跳过（返回空结果）
   - 变化且非 force → 抛出 `DataChangedError`
4. **返回值**：`IngestionResult` 对象，包含状态和元数据

#### 完成状态

- ✅ 移除 `IncrementalMode` 枚举
- ✅ 移除 `IngestionMetadata` dataclass
- ✅ 移除 `DataSource.fetch_etf_daily_incremental()` 抽象方法
- ✅ 移除 `TushareSource.fetch_etf_daily_incremental()` 实现
- ✅ 实现 `IngestionCoordinator` 作为新的摄取协调器

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
