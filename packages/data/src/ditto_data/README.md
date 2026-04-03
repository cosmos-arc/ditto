# ditto-datahub

**版本**: v0.5.0
**最后更新**: 2026-01-23
**状态**: ✅ 稳定

## 概要

数据存储与访问层 - Point-in-Time 安全的双存储架构，提供统一的数据访问入口。

## 核心功能

提供统一的数据访问入口，支持 DuckDB (分析型) 和 SQLite (事务型) 双存储，实现 instrument_id 标识体系和 PIT 语义保障。

## 二、架构定位

```
┌─────────────────────────────────────┐
│         ditto-core                  │
├─────────────────────────────────────┤
│        ditto-datahub                │  ← 当前层
│  ┌──────────┐  ┌──────────┐         │
│  │ Stores   │  │ Runtime  │         │
│  │          │  │ Meta     │         │
│  └──────────┘  └──────────┘         │
├─────────────────────────────────────┤
│      ditto-foundation               │
└─────────────────────────────────────┘
```

**依赖方向**: 仅依赖 `ditto-foundation`

## 三、目录结构

```
src/ditto_data/
├── storage/           # 数据存储访问
│   ├── calendar_store.py    # 交易日历
│   ├── instrument_store.py  # 证券信息
│   ├── bars_store.py        # K线数据
│   ├── adj_factor_store.py  # 复权因子
│   ├── quarantine_store.py  # 隔离区存储
│   └── sqlite_client.py     # SQLite客户端
├── accessors/        # 数据访问器
│   ├── bars/               # K线数据访问
│   ├── calendar.py         # 交易日历访问
│   ├── instrument.py       # 证券信息访问
│   └── ...
├── runtime/           # 运行时支持
│   ├── instrument_id_allocator.py  # Instrument ID 分配器
│   ├── freeze_manager.py    # 数据版本管理
│   └── sql_engine.py        # SQL分析引擎
├── sources/          # 外部数据源
│   └── tushare/            # Tushare数据源
├── meta/              # 元数据
│   └── schemas.py           # Parquet Schema定义
└── models/           # 数据模型
    ├── storage.py           # 存储结果模型
    └── ingestion.py         # 摄取日志模型
```

**注意**: 数据质量（DQ）检查功能已迁移到 `ditto-core` 包的 `quality` 模块。

## 四、关键模块说明

### storage/ - 数据存储层
- `BarsStore`: K线数据 Parquet 年分区存储
- `AdjFactorStore`: 复权因子 Parquet 年分区存储
- `CalendarStore`: 交易日历 SQLite 存储
- `InstrumentStore`: 证券元数据 PIT 映射存储
- `QuarantineStore`: DQ 隔离区存储
- `sqlite_client`: SQLite 连接管理与 SQL 路由

### accessors/ - 数据访问层
- `BarsAccessor`: K线数据访问（含复权、PIT 语义）
- `CalendarAccessor`: 交易日历访问
- `InstrumentsAccessor`: 证券信息访问（instrument_id 解析）
- `IngestionLogAccessor`: 摄取日志访问

### runtime/ - 运行时支持
- `InstrumentIdAllocator`: 内部唯一 ID 分配
- `FileLockManager`: 跨进程文件锁
- `FreezeManager`: 轻量级数据版本管理 (SHA-256 checksum)
- `SqlEngine`: DuckDB SQL 分析引擎

### meta/ - 元数据
- `schemas.py`: Polars Schema 定义
  - `STOCK_DAILY_SCHEMA`: 股票日线
  - `ETF_DAILY_SCHEMA`: ETF 日线
  - `ADJ_FACTOR_SCHEMA`: 复权因子

## 五、注意事项

1. **Point-in-Time 安全**: 所有因子数据必须包含 `knowledge_date`
2. **Instrument ID 标识**: 使用内部 instrument_id 而非外部代码
3. **双存储职责**: DuckDB 用于分析/因子，SQLite 用于事务/配置
4. **原子写入**: 使用 `atomic_write()` 确保写入完整性
5. **DQ 检查**: 数据质量检查由应用层（Port）调用 `ditto-core.quality` 模块完成
6. **统一日志**: 所有模块使用 loguru 记录结构化日志，禁止使用 print

## 六、日志使用说明 (NEW)

所有模块使用 `loguru` 记录结构化日志，遵循统一格式：

### 日志级别
- **DEBUG**: 函数入参、中间结果、连接创建等详细信息
- **INFO**: 正常业务流程（操作开始/完成、数据更新成功）
- **WARNING**: 可恢复异常（instrument_id 解析失败、数据源降级、DQ 规则失败）
- **ERROR**: 错误但系统可继续（单个数据写入失败、事务回滚）

### 结构化日志字段
- `event`: 事件类型标识（必须）
- `duration_ms`: 操作耗时毫秒数（性能操作推荐）
- 其他上下文字段（按需）

### 示例
```python
from loguru import logger

logger.info(
    "bars_write_complete",  # 事件描述
    event="bars_write",      # 事件类型
    dataset="stock_daily",   # 上下文
    row_count=1000,           # 上下文
    duration_ms=450,          # 性能指标
)
```

## 七、使用示例

```python
from pathlib import Path
from ditto_data import DataHub
from ditto_data.storage import BarsStore, CalendarStore
from ditto_data.runtime import InstrumentIdAllocator

# Instrument ID 分配
allocator = InstrumentIdAllocator(sqlite_pool)
etf_instrument_id = allocator.allocate("etf")

# K线数据读取
bars_store = BarsStore(data_root=Path("data"))
df = bars_store.read(
    "etf_daily", instrument_ids=[etf_instrument_id], start_date="2024-01-01"
)

# 数据质量检查（需使用 ditto-core.quality 模块）
from ditto_engine.quality import QualityEngine
dq_engine = QualityEngine(data_root=Path("data"))
result = dq_engine.check(df, dataset="etf_daily")
```
