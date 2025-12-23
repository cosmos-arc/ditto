# ditto-datahub

> 数据存储与访问层 - Point-in-Time 安全的双存储架构

## 一、核心功能

提供统一的数据访问入口，支持 DuckDB (分析型) 和 SQLite (事务型) 双存储，实现 SID 标识体系和 PIT 语义保障。

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
src/ditto_datahub/
├── stores/            # 数据存储访问
│   ├── calendar_store.py    # 交易日历
│   ├── security_store.py    # 证券信息
│   ├── bars_store.py        # K线数据
│   ├── adj_factor_store.py  # 复权因子
│   ├── pipeline_store.py    # Pipeline状态
│   └── sqlite_client.py     # SQLite客户端
├── runtime/           # 运行时支持
│   ├── sid_allocator.py     # SID分配器
│   ├── dq_checker.py        # 数据质量检查
│   ├── dq_rules.py          # DQ规则定义
│   ├── file_lock.py         # 文件锁
│   └── sqlite_pool.py       # 连接池
├── meta/              # 元数据
│   └── schemas.py           # Parquet Schema定义
├── types.py           # 类型定义
└── errors.py          # 异常定义
```

## 四、关键模块说明

### stores/ - 数据存储层
- `BarsStore`: K线数据 Parquet 年分区存储
- `AdjFactorStore`: 复权因子 Parquet 年分区存储
- `CalendarStore`: 交易日历 SQLite 存储
- `SecurityStore`: 证券元数据 PIT 映射存储
- `PipelineStore`: Pipeline 运行状态管理
- `sqlite_client`: SQLite 连接管理与 SQL 路由

### runtime/ - 运行时支持
- `SidAllocator`: 内部唯一 ID 分配 (100M-299M for ETF)
- `DQChecker`: 数据质量检查引擎
- `FileLockManager`: 跨进程文件锁
- `SQLitePool`: SQLite 连接池

### meta/ - 元数据
- `schemas.py`: Polars Schema 定义
  - `STOCK_DAILY_SCHEMA`: 股票日线
  - `ETF_DAILY_SCHEMA`: ETF 日线
  - `ADJ_FACTOR_SCHEMA`: 复权因子

## 五、注意事项

1. **Point-in-Time 安全**: 所有因子数据必须包含 `knowledge_date`
2. **SID 标识**: 使用内部 SID 而非外部代码
3. **双存储职责**: DuckDB 用于分析/因子，SQLite 用于事务/配置
4. **原子写入**: 使用 `atomic_write()` 确保写入完整性
5. **DQ 规则**: 数据写入前必须通过 DQ 检查

## 六、使用示例

```python
from ditto_datahub.stores import BarsStore, CalendarStore
from ditto_datahub.runtime import DQChecker, SidAllocator

# SID 分配
allocator = SidAllocator()
etf_sid = allocator.get_or_allocate_sid("510300.SH", "etf")

# K线数据读取
bars_store = BarsStore(data_root=Path("data"))
df = bars_store.read("etf_daily", sids=[etf_sid], start_date="2024-01-01")

# 数据质量检查
checker = DQChecker()
result = checker.check(df, dataset_id="etf_daily")
```
