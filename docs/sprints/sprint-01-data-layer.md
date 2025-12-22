# Sprint 1: 数据层与验证（基于官方设计文档）

**时间**: Week 1-2
**Phase**: 0.5 数据质量验证期
**目标**: 按照官方设计文档实现数据层

## 重要说明

**本Sprint严格遵循以下官方设计文档**：
- 《02_data_design.md》 - 数据层设计文档（v2.0 Final）
- 《01_system_design_v1.md》 - 系统架构设计

## Sprint 目标

1. 实现 DataHub 统一数据入口（Facade模式）
2. 实现 Domain Repositories（业务聚合根）
3. 实现 Store Layer（数据存取层）
4. 实现 Runtime Layer（运行时支持）
5. 完成Golden Dataset验证

## 架构概览

```
上层应用
    ↓
DataHub（纯 Facade，唯一入口）
    ↓
Domain Repositories（业务聚合）
    ├── BarsRepository
    ├── CalendarRepository
    ├── SecurityRepository
    ├── IndexRepository
    └── UniverseRepository
    ↓
Store Layer（数据存取）
    ├── SQLite Stores（元数据）
    └── Parquet Stores（年分区事实数据）
    ↓
Runtime Layer（支持组件）
    ├── SQLite Pool
    ├── SID Allocator
    ├── Freeze Manager
    ├── DQ Checker
    └── File Lock Manager
    ↓
物理存储
    ├── SQLite（元数据）
    ├── Parquet（年分区）
    └── DuckDB（OLAP查询）
```

## 任务分解

### P0 - 必须完成

#### 任务1: 实现Runtime Layer（基础组件）✅ 已完成

**1.1 SID分配器** ✅
- 文件：`packages/datahub/src/ditto_datahub/runtime/sid_allocator.py`
- 功能：管理sid序列号分配（100M-299M for ETF）
- 测试：`packages/datahub/tests/unit/runtime/test_sid_allocator.py` ✅

**1.2 SQLite连接池** ✅
- 文件：`packages/datahub/src/ditto_datahub/runtime/sqlite_pool.py`
- 功能：管理SQLite连接，支持并发访问
- 测试：`packages/datahub/tests/unit/runtime/test_sqlite_pool.py`

**1.3 文件锁管理器** ✅
- 文件：`packages/datahub/src/ditto_datahub/runtime/file_lock.py`
- 功能：跨平台文件锁，防止并发写入冲突（基于开源filelock库）
- 测试：`packages/datahub/tests/unit/runtime/test_file_lock.py` ✅

**1.4 DQ检查器** ✅
- 文件：`packages/datahub/src/ditto_datahub/runtime/dq_checker.py`
- 功能：数据质量检查（主键、OHLC关系等）
- 测试：`packages/datahub/tests/unit/runtime/test_dq_checker.py` ✅

**完成状态**:
- ✅ 所有组件实现完成
- ✅ 18个单元测试全部通过
- ✅ Ruff代码质量检查通过
- ✅ MyPy类型检查通过

#### 任务2: 实现Store Layer（数据存取） ✅ 已完成

**2.1 SQLite Stores** ✅
- SecurityStore：`packages/datahub/src/ditto_datahub/stores/security_store.py` ✅
  - 管理security和security_mapping表（含PIT）
  - 支持src_code到sid的映射（Point-in-Time）
- CalendarStore：`packages/datahub/src/ditto_datahub/stores/calendar_store.py` ✅
  - 管理交易日历
  - 内存缓存优化
- PipelineStore：`packages/datahub/src/ditto_datahub/stores/pipeline_store.py` ✅
  - 记录pipeline运行状态
  - DQ异常记录

**2.2 Parquet Stores（年分区）** ✅
- BarsStore：`packages/datahub/src/ditto_datahub/stores/bars_store.py` ✅
  - 读写market_daily/etf_daily
  - 年分区存储（2020.parquet, 2021.parquet...）
- AdjFactorStore：`packages/datahub/src/ditto_datahub/stores/adj_factor_store.py` ✅
  - 复权因子管理
  - 支持增量更新

**完成状态**:
- ✅ 5个Store类实现完成（SecurityStore, CalendarStore, PipelineStore, BarsStore, AdjFactorStore）
- ✅ 83个单元测试全部通过
- ✅ Ruff代码质量检查通过
- ✅ MyPy类型检查通过

#### 任务3: 实现Domain Repositories

**3.1 SecurityRepository**
- 文件：`packages/datahub/src/ditto_data_hub/repositories/security.py`
- 功能：
  - 证券主数据管理
  - src_code → sid映射（支持PIT）
  - SID分配
- 测试：`packages/datahub/tests/unit/test_security_repository.py`

**3.2 BarsRepository**
- 文件：`packages/datahub/src/ditto_data_hub/repositories/bars.py`
- 功能：
  - 行情数据读写（股票/ETF）
  - 复权计算（QFQ/HFQ）
  - 多标识符支持（sid/src_code/symbol）
- 测试：`packages/datahub/tests/unit/test_bars_repository.py`

**3.3 CalendarRepository**
- 文件：`packages/datahub/src/ditto_data_hub/repositories/calendar.py`
- 功能：
  - 交易日历查询
  - 工作日计算
  - 日期序列生成
- 测试：`packages/datahub/tests/unit/test_calendar_repository.py`

#### 任务4: 实现DataHub（Facade）

**4.1 DataHub主类**
- 文件：`packages/datahub/src/ditto_data_hub/hub.py`
- 功能：
  - 统一数据入口（Facade模式）
  - 懒加载Repository（@cached_property）
  - 资源管理（支持with语句）
- 测试：`packages/datahub/tests/unit/test_hub.py`

**4.2 SQL Engine**
- 文件：`packages/datahub/src/ditto_data_hub/runtime/sql_engine.py`
- 功能：
  - DuckDB集成
  - PIT View支持
  - 复权宏（qfq($asof)）

### P1 - 应该完成

#### 任务5: ETL Pipeline

**5.1 数据导入流程**
- 文件：`packages/datahub/src/ditto_data_hub/etl/ingest_pipeline.py`
- 功能：
  - Tushare/AkShare数据获取
  - src_code → sid映射
  - 数据质量检查
  - 年分区写入

#### 任务6: Golden Dataset验证

**6.1 标的选取**（基于sid体系）：
- 先映射src_code到sid：
  - 510300.SH → sid (200M区间)
  - 516010.SH → sid (200M区间)
  - 513100.SH → sid (200M区间)
  - 000300.SH → sid (300M区间)

**6.2 验证任务**：
- 通过DataHub读取数据
- 对比权威数据源
- 验证PIT语义正确性

## 关键实现细节

### 1. SID体系实现
```python
# sid区间定义
STOCK_MIN = 100_000_000, STOCK_MAX = 199_999_999
ETF_MIN = 200_000_000, ETF_MAX = 299_999_999
INDEX_MIN = 300_000_000, INDEX_MAX = 399_999_999

# PIT映射表
CREATE TABLE security_mapping (
    sid INTEGER NOT NULL,
    source TEXT NOT NULL,
    src_code TEXT NOT NULL,
    effective_from DATE NOT NULL,
    effective_to DATE,  -- NULL=当前有效
    PRIMARY KEY (source, src_code, effective_from)
);
```

### 2. DataHub使用示例
```python
from ditto_data_hub import DataHub

# 初始化
hub = DataHub("data")

# Repository访问
bars = hub.bars.get(
    src_codes=["510300.SH"],
    start="2024-01-01",
    adj="qfq"
)

# SQL查询（支持PIT）
df = hub.sql(
    "SELECT * FROM market_daily WHERE trade_date <= $asof",
    asof="2024-06-30"
)

# 资源清理
hub.close()
```

### 3. PIT语义实现
```python
# 解析src_code到sid（支持历史）
sid = hub.security_store.resolve_sid(
    "000022.SZ",
    source="tushare",
    asof="2017-01-01"  # 查询2017年的映射
)
```

## 验收标准

- [ ] 所有组件通过单元测试
- [ ] DataHub API与设计文档一致
- [ ] PIT语义正确实现
- [ ] Golden Dataset通过DataHub验证
- [ ] DQ检查规则生效
- [ ] 年分区存储正确

## 关键文件清单

```
packages/datahub/src/ditto_data_hub/
├── hub.py                        # DataHub Facade
├── types.py                      # 类型定义
├── errors.py                     # 异常定义
├── repositories/
│   ├── base.py                   # Repository基类
│   ├── bars.py                   # 行情数据
│   ├── security.py               # 证券主数据
│   └── calendar.py               # 交易日历
├── stores/
│   ├── security_store.py         # SQLite存储
│   ├── bars_store.py             # Parquet存储
│   └── calendar_store.py         # 日历存储
├── runtime/
│   ├── sqlite_pool.py            # 连接池
│   ├── sid_allocator.py          # SID分配
│   ├── file_lock.py              # 文件锁
│   ├── dq_checker.py             # 数据质量
│   └── sql_engine.py             # DuckDB引擎
└── meta/
    └── schemas.py                # Schema定义
```

## 下一步

Sprint 1完成后，将具备完整的数据访问能力，为Sprint 2的核心引擎提供坚实的数据基础。
