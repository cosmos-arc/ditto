# Repositories - 数据仓储层

## 功能概述

提供统一的数据访问接口，封装底层 Store 操作，实现业务逻辑与数据访问的分离。支持 Point-in-Time (PIT) 查询，确保时点数据安全。

## 核心职责

- **业务封装**: 将领域操作映射到 Store 层调用
- **PIT 支持**: 通过 asof 参数实现时点安全查询
- **并发控制**: 使用 stores 层的文件锁机制保证写入安全
- **标识解析**: 自动处理外部代码/Symbol 与内部 SID 的转换
- **数据质量**: 在写入时集成 DQ 检查

## 可用仓储

| 类名 | 描述 | 主要操作 |
|------|------|----------|
| `BarsRepository` | K线数据仓储 | get/write/复权调整 |
| `SecurityRepository` | 证券主数据仓储 | get/register/标识解析 |
| `CalendarRepository` | 交易日历仓储 | get/is_trading_day/日期查询 |
| `AdjFactorRepository` | 复权因子仓储 | write |
| `IndexRepository` | 指数数据仓储 | get_bars/get_constituents |
| `UniverseRepository` | 股票池仓储 | create/get_constituents |

## BarsRepository - K线数据仓储

### 核心功能

```python
from ditto_datahub.repositories import BarsRepository
from ditto_datahub.types import AdjType

# 查询 K线数据
df = repo.get(
    sids=[1000001, 1000002],
    start="2024-01-01",
    end="2024-12-31",
    adj=AdjType.QFQ,  # 前复权
    asof="2024-06-30",  # PIT 安全查询
    with_symbol=True,  # 包含 symbol 列
    with_status=True,  # 包含停牌/ST状态
)

# 查询单个证券
df = repo.get_single(
    identifier="000001.SZ",
    start="2024-01-01",
    end="2024-12-31",
    adj=AdjType.QFQ,
    asof="2024-06-30",
)

# 写入 K线数据（自动 DQ 检查）
result = repo.write(
    df=bar_df,
    year=2024,
    dataset="stock_daily",
    run_dq_check=True,
    on_duplicate=OnDuplicate.ERROR,
)
```

### PIT 查询支持

```python
# asof 参数确保时点数据安全
# 1. 标识符解析: 使用 asof 当天有效的 SID
# 2. 复权因子: 仅使用 knowledge_date <= asof 的因子
df = repo.get(
    sids=[1000001],
    start="2024-01-01",
    end="2024-12-31",
    asof="2024-06-30",  # 查询 2024-06-30 当天已知的数据
)
```

### 复权类型

| 类型 | 说明 | 适用场景 |
|------|------|----------|
| `AdjType.NONE` | 不复权 | 查看原始价格 |
| `AdjType.QFQ` | 前复权 | 技术分析、趋势判断 |
| `AdjType.HFQ` | 后复权 | 长期收益计算 |

### 并发安全

```python
# 写入时自动使用文件锁保护
# Lock name: "bars_write_{dataset}_{year}"
# Timeout: 60s
with repo._file_lock.acquire("bars_write_stock_daily_2024"):
    # DQ 检查
    dq_result = repo._dq_engine.check(df, dataset)

    # 写入 Parquet
    file_path, checksum = repo._bars_store.write(...)
```

## SecurityRepository - 证券主数据仓储

### 核心功能

```python
from ditto_datahub.repositories import SecurityRepository

# 查询证券信息
df = repo.get(
    sids=[1000001],
    asset_class="stock",
    is_active=True,
    asof="2024-06-30",  # PIT 安全
)

# 标识符解析
sid = repo.resolve_identifier(
    identifier="000001.SZ",
    source="tushare",
    asof="2024-06-30",
)

# 批量解析
mapping = repo.resolve_identifiers_batch(
    identifiers=["000001.SZ", "000002.SZ"],
    source="tushare",
    asof="2024-06-30",
)
# 返回: {"000001.SZ": 1000001, "000002.SZ": 1000002}

# 注册新证券
from ditto_datahub.models.security import SecurityRegistration

sid = repo.register(
    SecurityRegistration(
        src_code="000001.SZ",
        symbol="平安银行",
        name="平安银行股份有限公司",
        exchange="SZ",
        asset_class="stock",
        list_date="1991-04-03",
    )
)
```

### 标识符解析策略

```python
# resolve_identifier 尝试顺序:
# 1. 作为 src_code 查询 (如 "000001.SZ")
# 2. 作为 symbol 查询 (如 "平安银行")
# 返回匹配的第一个 SID
```

## CalendarRepository - 交易日历仓储

### 核心功能

```python
from ditto_datahub.repositories import CalendarRepository

# 获取交易日历
df = repo.get(
    start="2024-01-01",
    end="2024-12-31",
    only_open=True,  # 仅返回开市日
)

# 检查是否交易日
is_open = repo.is_trading_day("2024-01-15")

# 列出交易日
trading_days = repo.list_trading_days(
    start="2024-01-01",
    end="2024-12-31",
)

# 获取最新交易日
last_day = repo.get_last_trading_day()

# 获取前一/后一交易日
prev_day = repo.get_prev("2024-01-15")
next_day = repo.get_next("2024-01-15")

# 获取月末日
month_ends = repo.get_month_ends(
    start="2024-01-01",
    end="2024-12-31",
)

# 获取季末日
quarter_ends = repo.get_quarter_ends(
    start="2024-01-01",
    end="2024-12-31",
)
```

## AdjFactorRepository - 复权因子仓储

### 核心功能

```python
from ditto_datahub.repositories import AdjFactorRepository
from ditto_datahub.types import OnDuplicate

# 写入复权因子
file_path, checksum = repo.write(
    dataset="adj_factor",
    df=adj_df,
    year=2024,
    on_duplicate=OnDuplicate.ERROR,
)
```

### 并发安全

```python
# 写入时自动使用文件锁保护
# Lock name: "adj_factor_write_{dataset}_{year}"
# Timeout: 60s
```

## IndexRepository - 指数数据仓储

### 核心功能

```python
from ditto_datahub.repositories import IndexRepository

# 查询指数日线
df = repo.get_bars(
    sids=[3000001],  # CSI 300 SID
    start="2024-01-01",
    end="2024-12-31",
    asof="2024-06-30",
)

# 查询指数成分股
constituents = repo.get_constituents(
    index_id="000300.SH",  # CSI 300
    asof="2024-06-30",
    with_symbol=True,
    min_weight=0.01,  # 权重 >= 1%
)

# 获取成分股 SID 列表
sids = repo.get_index_constituents_sids(
    index_id="000300.SH",
    asof="2024-06-30",
)

# 预定义快捷方式
csi300_bars = repo.get_csi300_bars(
    start="2024-01-01",
    end="2024-12-31",
)

csi300_sids = repo.get_csi300_constituents(asof="2024-06-30")

csi500_sids = repo.get_csi500_constituents(asof="2024-06-30")
```

### PIT 支持

```python
# asof 参数确保查询时点成分股
# 返回 asof 当天有效的成分股列表
constituents = repo.get_constituents(
    index_id="000300.SH",
    asof="2020-06-30",  # 2020年6月底的成分股
)
```

## UniverseRepository - 股票池仓储

### 核心功能

```python
from ditto_datahub.repositories import UniverseRepository

# 创建股票池
repo.create(
    universe_id="my_strategy",
    name="我的策略池",
    description="自定义选股池",
    universe_type="custom",
)

# 添加成分股
count = repo.add_constituents(
    universe_id="my_strategy",
    sids=[1000001, 1000002, 1000003],
    effective_date="2024-01-01",
    weights=[0.5, 0.3, 0.2],  # 可选权重
)

# 查询成分股
constituents = repo.get_constituents(
    universe_id="my_strategy",
    asof="2024-06-30",
    with_symbol=True,
)

# 列出所有股票池
pools = repo.list_universes(universe_type="custom")

# 预定义快捷方式
csi300_sids = repo.get_csi300(asof="2024-06-30")
csi500_sids = repo.get_csi500(asof="2024-06-30")
```

### PIT 支持

```python
# asof 参数确保查询时点成分股
# 返回 asof 当天有效的成分股列表
constituents = repo.get_constituents(
    universe_id="my_strategy",
    asof="2024-06-30",
)
```

## 设计模式

### Repository 模式

```
┌─────────────────┐
│   Application   │
├─────────────────┤
│  Repository     │  ← 业务封装层
├─────────────────┤
│     Store       │  ← 数据访问层
├─────────────────┤
│  Parquet/SQLite │  ← 存储层
└─────────────────┘
```

### 职责分离

| 层级 | 职责 | 示例 |
|------|------|------|
| Repository | 业务逻辑、协调多 Store | 复权计算、标识解析 |
| Store | 单一数据源访问 | Parquet 读写、SQLite 查询 |
| Foundation | 基础设施 | 日志、追踪、锁 |

## 数据质量集成

```python
# BarsRepository 写入时自动触发 DQ 检查
result = repo.write(
    df=bar_df,
    year=2024,
    dataset="stock_daily",
    run_dq_check=True,  # 启用 DQ 检查
)

# DQ 检查流程:
# 1. L1 技术检查 (空值、唯一、外键)
#    - 失败: 阻断写入，数据进入 quarantine
# 2. L2 业务检查 (OHLC、价格合理性)
#    - 失败: 警告记录，继续写入
# 3. 生成 DQ 报告
```

## 并发安全机制

### 文件锁策略

```python
# 所有写操作都使用文件锁保护
lock_name = f"{resource}_{dataset}_{year}"

with repo._file_lock.acquire(lock_name, timeout=60.0):
    # 执行写入操作
    repo._store.write(...)
```

### 锁命名规范

| 操作 | Lock 名称 |
|------|-----------|
| Bars 写入 | `bars_write_{dataset}_{year}` |
| AdjFactor 写入 | `adj_factor_write_{dataset}_{year}` |

## 日志与追踪

```python
# Repository 使用 @traced 装饰器
@traced("repository.bars.get")
def get(self, ...) -> pl.DataFrame:
    # 自动记录:
    # - 执行时间
    # - 参数
    # - 返回值

# 结构化日志
logger.info(
    "bars_write_complete",
    event="bars_write",
    dataset="stock_daily",
    row_count=1000,
    duration_ms=450,
)
```

## 相关文档

- [Stores 层文档](../stores/README.md)
- [DQ 数据质量模块](../dq/README.md)
- [PIT 查询设计](../../../../../docs/design/07_pit_query_design.md)
- [数据质量设计](../../../../../docs/design/09_data_quality_design.md)
