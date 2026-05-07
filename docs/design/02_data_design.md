> **⚠️ Historical Document**: 本文档撰写于旧架构（engine/analytics/infra/interfaces）时期。
> 当前架构请参考 `CLAUDE.md` 和 `docs/architecture/` 下的活跃文档。
# Ditto 数据层设计文档

**版本：v2.0 Final（Phase 0–1：ETF 行业轮动）**

**日期：2025-12-22**

---

## 变更记录

| 日期 | 变更内容 |
|------|----------|
| 2026-01-27 | **基础层重构**: 添加 `BaseStore` 抽象基类，定义统一存储接口 (read/write/delete)。实现 `ParquetStore`（按年分区、自动去重）和 `SQLiteStore`（事务支持、PIT 查询）。引入 `DataRootConfig` 统一数据根路径配置，从多路径配置简化为单 `data_root` 配置（`data_store.env`），所有路径自动生成。 |
| 2026-01-16 | **架构简化**: 移除 `PipelineStore`（pipeline_run + dq_issue 表），采用简化的 `IngestionLogStore` 统一摄取元数据管理。原设计中的 run_id 跟踪和 DQ 详情记录被简化为按交易日的 UPSERT 模式，避免游标倒退问题并降低复杂度。 |

---

## 一、架构总览

### 1.1 分层架构图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              上层应用                                        │
│         策略引擎 / 回测框架 / 研究 Notebook / CLI / 监控仪表盘                    │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         DataHub（纯 Facade）                                 │
│                                                                             │
│   职责：暴露统一入口，路由到对应 Accessor，不持有任何业务逻辑                        │
│                                                                             │
│   hub.bars         → BarsAccessor                                           │
│   hub.calendar     → CalendarAccessor                                       │
│   hub.universe     → UniverseAccessor                                       │
│   hub.securities   → SecuritiesAccessor                                     │
│   hub.index        → IndexAccessor                                          │
│   hub.sql(...)     → SqlEngine（DuckDB View + 复权宏）                        │
│   hub.freeze       → FreezeManager                                          │
│   hub.sources      → DataSources                                        │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
                                    │
                    ┌───────────────┴───────────────┐
                    ▼                               ▼
┌──────────────────────────────┐    ┌──────────────────────────────┐
│      Sources Layer（新增）    │    │   Domain Accessors           │
│                              │    │                              │
│   hub.sources.tushare        │    │   BarsAccessor               │
│   hub.sources.akshare        │    │   CalendarAccessor           │
│                              │    │   SecuritiesAccessor         │
│   支持：                      │    │   ...                        │
│   - 研究 Notebook 实时查询     │    │                              │
│   - Server 摄取任务调用        │    │                              │
└──────────────────────────────┘    └──────────────────────────────┘
                                                │
                                                ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           Store Layer（数据存取层）                          │
│                                                                              │
│   ┌─────────────────────────────────────────────────────────────┐           │
│   │                    SQLite Stores                            │           │
│   │  SecurityStore │ CalendarStore │ IngestionLogStore          │           │
│   └───────────────────────────┬─────────────────────────────────┘           │
│                               │                                             │
│   ┌───────────────────────────┼─────────────────────────────────┐           │
│   │                    Parquet Stores（年分区）                  │           │
│   │  BarsStore │ IndexStore │ AdjFactorStore                    │           │
│   └───────────────────────────┬─────────────────────────────────┘           │
│                               │                                             │
└───────────────────────────────┼─────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                            Runtime Layer                                    │
│                                                                             │
│   ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
│   │   SQLite    │  │   Freeze    │  │   File      │  │   SQL       │        │
│   │    Pool     │  │  Manager    │  │    Lock     │  │  Engine     │        │
│   └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘        │
│                                                                             │
│   ┌─────────────┐  ┌─────────────┐                                          │
│   │     DQ      │  │    SID      │                                          │
│   │   Checker   │  │  Allocator  │                                          │
│   └─────────────┘  └─────────────┘                                          │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              物理存储层                                       │
│              Parquet (年分区事实数据)  +  SQLite (元数据)  +  DuckDB (OLAP)   │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 1.2 设计原则

| 原则 | 说明 |
|-----|------|
| **单一入口** | 上层只面对 `DataHub`，通过 Accessor 访问数据 |
| **职责分离** | DataHub(Facade) → Accessor(业务) → Store(存取) → Runtime(支持) |
| **基础层抽象** | 所有存储实现继承 `BaseStore`，保证接口一致性 |
| **语义正确** | sid 是唯一身份；(source, src_code) 是映射通道；symbol 仅 UI 展示 |
| **Point-in-Time** | 任何时点的回测只能看到该时点已公开的信息，包括标识符解析 |
| **幂等可重跑** | 同一任务对同一日期重跑，产出结果完全一致 |
| **年分区存储** | Parquet 按年分区，平衡读写性能与文件管理复杂度 |
| **Freeze 校验** | 通过 checksum 清单实现轻量级可复现性验证 |

### 1.3 基础层架构

基础层提供统一的数据存储抽象接口，确保所有存储实现的一致性：

#### BaseStore 抽象基类

定义所有数据存储的统一接口：

```python
class BaseStore(ABC):
    """数据存储抽象基类."""

    @abstractmethod
    def read(
        self,
        dataset: str,
        sids: list[int] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        **kwargs: object,
    ) -> object:
        """读取数据."""
        ...

    @abstractmethod
    def write(
        self,
        dataset: str,
        data: object,
        on_duplicate: str = "error",
        **kwargs: object,
    ) -> WriteResultStore:
        """写入数据."""
        ...

    @abstractmethod
    def delete(
        self,
        dataset: str,
        sids: list[int] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        **kwargs: object,
    ) -> int:
        """删除数据."""
        ...
```

#### ParquetStore

Parquet 文件存储实现：

- **按年分区**：`data_root/dataset/YYYY.parquet`
- **自动去重**：支持 `error/keep_first/keep_last` 策略
- **日期范围查询**：自动扫描相关年份分区
- **原子写入**：使用临时文件 + 重命名保证数据一致性

#### SQLiteStore

SQLite 数据库存储实现：

- **单库多表**：一个 SQLite 文件存储多张表
- **事务支持**：自动提交事务，保证数据一致性
- **PIT 查询**：支持历史时点数据查询
- **连接池**：使用 `SQLitePool` 复用连接

#### 配置系统

从多路径配置简化为单 `data_root` 配置（来自 `config/{env}/data_store.env`）：

```python
class DataRootConfig(BaseModel):
    """数据根路径配置（纯模型）."""

    data_root: Path = Field(default=Path("data"))

    # 所有路径自动生成
    @property
    def market_stock_bars_path(self) -> Path:
        return self.data_root / "market" / "stock" / "bars" / "daily"

    @property
    def metadata_db_path(self) -> Path:
        return self.data_root / "metadata" / "metadata.sqlite"
```

**配置文件示例**：

```bash
# config/development/data_store.env
DATA_ROOT=data

# 将自动生成：
# data/market/stock/bars/daily/
# data/metadata/metadata.sqlite
```

### 1.4 核心标识符体系

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           标识符体系                                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  sid        = 内部唯一身份标识，永不改变（主键）                              │
│  source     = 数据源标识（tushare / ricequant / akshare）                   │
│  src_code   = 数据源原始代码（Ingestion 主通道）                             │
│  symbol     = 展示/交易代码（仅 UI 用，按需派生，不存入事实表）                │
│                                                                             │
│  映射关系：(source, src_code, asof) → sid                                   │
│  - 当前查询：effective_to IS NULL                                           │
│  - 历史查询：effective_from <= asof < effective_to                          │
│                                                                             │
│  事实表主键：(sid, trade_date)                                              │
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│  sid 分区规则（预留区间）：                                                   │
│  ┌───────────────┬──────────────────────────┐                               │
│  │   资产类别     │      sid 区间             │                               │
│  ├───────────────┼──────────────────────────┤                               │
│  │   股票         │  100,000,000 ~ 199,999,999│                               │
│  │   ETF         │  200,000,000 ~ 299,999,999│                               │
│  │   指数        │  300,000,000 ~ 399,999,999│                               │
│  │   债券/可转债  │  400,000,000 ~ 499,999,999│                               │
│  │   期货        │  500,000,000 ~ 599,999,999│                               │
│  └───────────────┴──────────────────────────┘                               │
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│  代码变更场景示例：                                                          │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ 深赤湾A (000022.SZ) 被招商港口吸收合并：                              │   │
│  │                                                                      │   │
│  │ security_mapping:                                                    │   │
│  │   sid=12345, source='tushare', src_code='000022.SZ'                 │   │
│  │   effective_from='1990-01-01', effective_to='2018-12-25'            │   │
│  │                                                                      │   │
│  │ 查询 asof='2017-01-01' → 返回 sid=12345 ✓                           │   │
│  │ 查询 asof='2019-01-01' → 返回 NULL（代码已消失）                     │   │
│  │ 查询当前（无 asof）   → 返回 NULL                                   │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 1.5 存储引擎职责边界

| 引擎 | 职责 | 场景 |
|-----|------|------|
| **SQLite** | 治理元数据、运行记录、映射表（含 PIT） | OLTP、事务、配置 |
| **Parquet + Polars** | 事实数据存储（年分区）、批处理计算 | DataFrame 计算 |
| **DuckDB** | OLAP 查询、多表聚合、PIT View | 复杂 SQL、研究探索 |

### 1.6 Sources 与 Stores 的职责对比

| 层 | 职责 | 数据流向 |
|---|---|---|
| **Sources** | 从外部数据源（Tushare/AkShare）获取数据 | 外部 → 系统 |
| **Stores** | 本地存储读写（Parquet/SQLite） | 系统 ↔ 磁盘 |

> 数据摄取任务设计详见：10_data_ingestion_scheduler_design.md
---

## 二、目录结构

```
packages/
  ditto-data/
    pyproject.toml
    README.md

    config/
      dq_rules.yaml             # DQ 规则配置
      sources.yaml              # 数据源配置（限流、超时）

    src/
      ditto_data_hub/
        __init__.py
        py.typed                 # PEP 561 类型标记

        # ============ 入口层 ============
        hub.py                   # DataHub Facade：唯一上层入口
        types.py                 # 强类型定义
        errors.py                # 统一异常
        settings.py              # 配置（paths, defaults）
        # ============ 数据源层 ============
        sources/
          __init__.py           # 导出 get_source, DataSource
          base.py               # DataSource 基类 + 工厂 + 异常定义
          tushare/
            __init__.py
            client.py           # Tushare 客户端（连接、限流、重试）
            source.py           # TushareSource 实现
          akshare/
            __init__.py
            client.py
            source.py

        # ============ 数据质量层（重构）============
        dq/
          __init__.py           # 导出 DQEngine, get_dq_engine
          engine.py             # 统一 DQ 执行引擎
          result.py             # DQResult, DQIssue 等模型
          rules.py              # 规则加载与解析
          checkers/
            __init__.py
            technical.py        # L1 技术校验
            business.py         # L2 业务规则
            statistical.py      # L3 统计异常

        # ============ Accessor 层 ============
        accessors/
          __init__.py
          base.py                # BaseAccessor 基类
          bars.py                # BarsAccessor（股票/ETF 行情）
          calendar.py            # CalendarAccessor（交易日历）
          universe.py            # UniverseAccessor（标的池/成分股）
          securities.py          # SecuritiesAccessor（证券主数据）
          index.py               # IndexAccessor（指数行情/权重）

        # ============ Store 层 ============
        stores/
          __init__.py

          # 基础层
          base/
            __init__.py
            base_store.py         # BaseStore 抽象基类
            parquet_store.py      # ParquetStore 实现
            sqlite_store.py       # SQLiteStore 实现

          # SQLite Stores
          sqlite_client.py        # sqlite_client 客户端
          security_store.py       # security + security_mapping（含 PIT）
          calendar_store.py       # trading_calendar
          ingestion_log.py        # 摄取事件日志（SUCCESS/FAIL + 重试）

          # Parquet Stores（年分区）
          bars_store.py           # stock_daily / etf_daily 读写
          index_store.py          # index_daily / index_weight 读写
          adj_factor_store.py     # adj_factor 读写

        # ============ 配置层 ============
        config/
          __init__.py
          data_root.py            # DataRootConfig 统一数据根路径配置

        # ============ Runtime 层 ============
        runtime/
          __init__.py
          sqlite_pool.py          # SQLite 连接池
          freeze_manager.py       # Freeze 冻结点管理
          sid_allocator.py        # SID 分配器
          file_lock.py            # 跨平台文件锁
          dq_checker.py           # 数据质量检查器
          sql_engine.py           # DuckDB View + PIT

        # ============ 元数据层 ============
        meta/
          __init__.py
          schemas.py             # Schema 常量定义

        # ============ 工具层 ============
        utils/
          __init__.py
          io.py                  # file_md5, atomic_write
          dates.py               # 日期工具

    tests/
      conftest.py
      unit/
      integration/
        test_pit_compliance.py
        test_freeze_verify.py
```

---

## 三、数据目录结构

```
$DATA_ROOT/
│
├── meta/
│   └── hub.sqlite                    # SQLite 元数据库
│
├── stock_daily/                     # 股票日线（年分区）
│   ├── 2020.parquet
│   ├── 2021.parquet
│   ├── 2022.parquet
│   ├── 2023.parquet
│   ├── 2024.parquet
│   └── 2025.parquet
│
├── etf_daily/                        # ETF 日线（年分区）
│   ├── 2020.parquet
│   └── ...
│
├── index_daily/                      # 指数日线（年分区）
│   ├── 2020.parquet
│   └── ...
│
├── index_weight/                     # 指数权重（年分区）
│   ├── 2020.parquet
│   └── ...
│
├── adj_factor/                       # 复权因子（年分区）
│   ├── 2020.parquet
│   └── ...
│
├── freezes/                          # Freeze 冻结点
│   ├── backtest_v1.json
│   └── prod_2025q1.json
│
├── staging/                          # 写入临时区
│   └── _tmp/
│
├── quarantine/                       # DQ 隔离区
│   └── <dataset>/<run_id>/data.parquet
│
└── locks/                            # 文件锁
    └── <dataset>.lock
```

---

## 四、PIT 语义规范

### 4.1 PIT 覆盖范围

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           PIT 覆盖范围                                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  1. 行情数据：trade_date <= asof                                            │
│     - 自然满足，无需额外机制                                                 │
│                                                                             │
│  2. 标识符解析：(source, src_code, asof) → sid                              │
│     - 通过 security_mapping 的 effective_from/to 实现                       │
│     - 解决代码消失、代码变更等历史场景                                       │
│                                                                             │
│  3. 复权因子：trade_date <= asof                                            │
│     - 历史复权因子在历史时点确定                                             │
│                                                                             │
│  4. 成分股权重：trade_date <= asof（取最新）                                 │
│     - 或 effective_from <= asof < effective_to                              │
│                                                                             │
│  5. 行业分类：effective_from <= asof < effective_to                         │
│     - 股票可能调整行业归属                                                   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 4.2 asof 参数传递

```python
# asof 参数在整个调用链中传递

# 1. 用户调用
bars = hub.bars.get(src_codes=["000022.SZ"], start="2015-01-01", asof="2017-01-01")

# 2. Accessor 层：用 asof 解析 src_code → sid
sid = self.security_store.resolve_sid("000022.SZ", source="tushare", asof="2017-01-01")

# 3. Store 层：用 asof 过滤数据
df = df.filter(pl.col("trade_date") <= "2017-01-01")

# 4. SQL 查询同样支持
df = hub.sql("SELECT * FROM stock_daily WHERE sid = ?", asof="2017-01-01")
```

---

## 五、类型定义

### 5.1 数据对象定义

```python
# src/ditto_data_hub/types.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import NewType, Literal, Any
from enum import Enum

# ============ 基础类型 ============
DatasetId = NewType("DatasetId", str)
Sid = NewType("Sid", int)

AdjustType = Literal["none", "qfq", "hfq"]
AssetClass = Literal["stock", "etf", "index", "bond", "future"]


# ============ sid 区间常量 ============
class AssetSidRange:
    """sid 预留区间"""
    STOCK_MIN = 100_000_000
    STOCK_MAX = 199_999_999
    ETF_MIN = 200_000_000
    ETF_MAX = 299_999_999
    INDEX_MIN = 300_000_000
    INDEX_MAX = 399_999_999
    BOND_MIN = 400_000_000
    BOND_MAX = 499_999_999
    FUTURE_MIN = 500_000_000
    FUTURE_MAX = 599_999_999

    @classmethod
    def get_asset_class(cls, sid: int) -> str:
        """根据 sid 获取资产类别"""
        if cls.STOCK_MIN <= sid <= cls.STOCK_MAX:
            return "stock"
        elif cls.ETF_MIN <= sid <= cls.ETF_MAX:
            return "etf"
        elif cls.INDEX_MIN <= sid <= cls.INDEX_MAX:
            return "index"
        elif cls.BOND_MIN <= sid <= cls.BOND_MAX:
            return "bond"
        elif cls.FUTURE_MIN <= sid <= cls.FUTURE_MAX:
            return "future"
        return "unknown"

    @classmethod
    def get_range(cls, asset_class: str) -> tuple[int, int]:
        """获取资产类别的 sid 区间"""
        ranges = {
            "stock": (cls.STOCK_MIN, cls.STOCK_MAX),
            "etf": (cls.ETF_MIN, cls.ETF_MAX),
            "index": (cls.INDEX_MIN, cls.INDEX_MAX),
            "bond": (cls.BOND_MIN, cls.BOND_MAX),
            "future": (cls.FUTURE_MIN, cls.FUTURE_MAX),
        }
        return ranges.get(asset_class, (0, 0))


# ============ DQ 枚举 ============
class DQSeverity(Enum):
    """DQ 严重级别"""
    FAIL = "fail"
    WARN = "warn"


class WriteStatus(Enum):
    """写入状态"""
    SUCCESS = "success"
    REJECTED = "rejected"
    QUARANTINED = "quarantined"
    FAILED = "failed"


# ============ 数据类 ============
@dataclass(frozen=True)
class WriteRequest:
    """统一写入请求"""
    dataset: DatasetId
    df: Any                     # pl.DataFrame
    year: int
    source: str = "tushare"
    dq_fail_action: Literal["reject", "quarantine"] = "reject"


@dataclass
class WriteResult:
    """写入结果"""
    dataset: DatasetId
    status: WriteStatus
    year: int
    run_id: str | None = None
    file_path: str | None = None
    row_count: int = 0
    checksum: str | None = None
    dq_passed: bool = True
    dq_failures: list[dict] = field(default_factory=list)
    error_message: str | None = None

@dataclass(frozen=True)
class DQResult:
    """数据质量检查结果"""
    passed: bool
    severity: DQSeverity
    rule_name: str
    message: str
    affected_rows: int = 0


@dataclass
class FreezeManifest:
    """Freeze 冻结点清单"""
    freeze_id: str
    description: str
    created_at: str
    files: dict[str, str]  # {file_path: checksum}
```

#### 5.2 异常定义

``` python
"""
Ditto Data Hub 统一异常定义

异常层次结构：
    DataHubError (基类)
    ├── ConfigurationError          # 配置错误
    ├── DataError                   # 数据相关错误
    │   ├── DataNotFoundError       # 数据不存在
    │   ├── DataValidationError     # 数据校验失败
    │   └── DuplicateDataError      # 数据重复
    ├── StoreError                  # 存储层错误
    │   ├── WriteError              # 写入失败
    │   ├── ReadError               # 读取失败
    │   ├── ConcurrentModificationError  # 并发修改冲突
    │   └── LockAcquisitionError    # 获取锁失败
    ├── IdentifierError             # 标识符相关错误
    │   ├── SidNotFoundError        # SID 不存在
    │   ├── SidResolutionError      # SID 解析失败
    │   ├── AmbiguousIdentifierError # 标识符歧义（多解）
    │   └── SidExhaustedError       # SID 耗尽
    ├── QueryError                  # 查询相关错误
    │   ├── SqlExecutionError       # SQL 执行失败
    │   └── InvalidQueryError       # 无效查询
    ├── DQError                     # 数据质量错误
    │   ├── DQValidationError       # DQ 校验失败
    │   └── DQRuleNotFoundError     # DQ 规则不存在
    └── FreezeError                 # 冻结点错误
        ├── FreezeNotFoundError     # 冻结点不存在
        └── FreezeVerificationError # 冻结点校验失败
"""

from __future__ import annotations
from typing import Any


# ============================================================
# 基类
# ============================================================

class DataHubError(Exception):
    """DataHub 所有异常的基类"""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def __str__(self) -> str:
        if self.details:
            detail_str = ", ".join(f"{k}={v}" for k, v in self.details.items())
            return f"{self.message} ({detail_str})"
        return self.message


# ============================================================
# 配置错误
# ============================================================

class ConfigurationError(DataHubError):
    """配置错误"""
    pass


# ============================================================
# 数据相关错误
# ============================================================

class DataError(DataHubError):
    """数据相关错误基类"""
    pass


class DataNotFoundError(DataError):
    """数据不存在"""

    def __init__(
        self,
        message: str = "Data not found",
        dataset: str | None = None,
        sid: int | None = None,
        date_range: tuple[str, str] | None = None,
    ):
        details = {}
        if dataset:
            details["dataset"] = dataset
        if sid:
            details["sid"] = sid
        if date_range:
            details["date_range"] = date_range
        super().__init__(message, details)


class DataValidationError(DataError):
    """数据校验失败"""

    def __init__(
        self,
        message: str = "Data validation failed",
        field: str | None = None,
        expected: Any = None,
        actual: Any = None,
    ):
        details = {}
        if field:
            details["field"] = field
        if expected is not None:
            details["expected"] = expected
        if actual is not None:
            details["actual"] = actual
        super().__init__(message, details)


class DuplicateDataError(DataError):
    """数据重复"""

    def __init__(
        self,
        message: str = "Duplicate data detected",
        key_columns: list[str] | None = None,
        duplicate_count: int | None = None,
    ):
        details = {}
        if key_columns:
            details["key_columns"] = key_columns
        if duplicate_count:
            details["duplicate_count"] = duplicate_count
        super().__init__(message, details)


# ============================================================
# 存储层错误
# ============================================================

class StoreError(DataHubError):
    """存储层错误基类"""
    pass


class WriteError(StoreError):
    """写入失败"""

    def __init__(
        self,
        message: str = "Write operation failed",
        dataset: str | None = None,
        file_path: str | None = None,
        cause: Exception | None = None,
    ):
        details = {}
        if dataset:
            details["dataset"] = dataset
        if file_path:
            details["file_path"] = file_path
        if cause:
            details["cause"] = str(cause)
        super().__init__(message, details)
        self.__cause__ = cause


class ReadError(StoreError):
    """读取失败"""

    def __init__(
        self,
        message: str = "Read operation failed",
        dataset: str | None = None,
        file_path: str | None = None,
        cause: Exception | None = None,
    ):
        details = {}
        if dataset:
            details["dataset"] = dataset
        if file_path:
            details["file_path"] = file_path
        if cause:
            details["cause"] = str(cause)
        super().__init__(message, details)
        self.__cause__ = cause


class ConcurrentModificationError(StoreError):
    """并发修改冲突（乐观锁失败）"""

    def __init__(
        self,
        message: str = "File was modified by another process",
        file_path: str | None = None,
        expected_checksum: str | None = None,
        actual_checksum: str | None = None,
    ):
        details = {}
        if file_path:
            details["file_path"] = file_path
        if expected_checksum:
            details["expected_checksum"] = expected_checksum
        if actual_checksum:
            details["actual_checksum"] = actual_checksum
        super().__init__(message, details)


class LockAcquisitionError(StoreError):
    """获取锁失败（超时）"""

    def __init__(
        self,
        message: str = "Failed to acquire lock",
        lock_name: str | None = None,
        timeout_seconds: float | None = None,
    ):
        details = {}
        if lock_name:
            details["lock_name"] = lock_name
        if timeout_seconds:
            details["timeout_seconds"] = timeout_seconds
        super().__init__(message, details)


# ============================================================
# 标识符相关错误
# ============================================================

class IdentifierError(DataHubError):
    """标识符相关错误基类"""
    pass


class SidNotFoundError(IdentifierError):
    """SID 不存在"""

    def __init__(
        self,
        message: str = "SID not found",
        sid: int | None = None,
    ):
        details = {"sid": sid} if sid else {}
        super().__init__(message, details)


class SidResolutionError(IdentifierError):
    """SID 解析失败（无法从 src_code 映射到 sid）"""

    def __init__(
        self,
        message: str = "Failed to resolve SID",
        src_code: str | None = None,
        source: str | None = None,
        asof: str | None = None,
    ):
        details = {}
        if src_code:
            details["src_code"] = src_code
        if source:
            details["source"] = source
        if asof:
            details["asof"] = asof
        super().__init__(message, details)


class AmbiguousIdentifierError(IdentifierError):
    """标识符歧义（一个 symbol 映射到多个 sid）"""

    def __init__(
        self,
        message: str = "Identifier is ambiguous",
        identifier: str | None = None,
        candidates: list[int] | None = None,
    ):
        details = {}
        if identifier:
            details["identifier"] = identifier
        if candidates:
            details["candidates"] = candidates
        super().__init__(message, details)


class SidExhaustedError(IdentifierError):
    """SID 区间耗尽"""

    def __init__(
        self,
        message: str = "SID range exhausted",
        asset_class: str | None = None,
        current_max: int | None = None,
        range_max: int | None = None,
    ):
        details = {}
        if asset_class:
            details["asset_class"] = asset_class
        if current_max:
            details["current_max"] = current_max
        if range_max:
            details["range_max"] = range_max
        super().__init__(message, details)


# ============================================================
# 查询相关错误
# ============================================================

class QueryError(DataHubError):
    """查询相关错误基类"""
    pass


class SqlExecutionError(QueryError):
    """SQL 执行失败"""

    def __init__(
        self,
        message: str = "SQL execution failed",
        query: str | None = None,
        cause: Exception | None = None,
    ):
        details = {}
        if query:
            # 截断过长的 SQL
            details["query"] = query[:500] + "..." if len(query) > 500 else query
        if cause:
            details["cause"] = str(cause)
        super().__init__(message, details)
        self.__cause__ = cause


class InvalidQueryError(QueryError):
    """无效查询（参数错误等）"""

    def __init__(
        self,
        message: str = "Invalid query parameters",
        param_name: str | None = None,
        param_value: Any = None,
    ):
        details = {}
        if param_name:
            details["param_name"] = param_name
        if param_value is not None:
            details["param_value"] = param_value
        super().__init__(message, details)


# ============================================================
# 数据质量错误
# ============================================================

class DQError(DataHubError):
    """数据质量错误基类"""
    pass


class DQValidationError(DQError):
    """DQ 校验失败"""

    def __init__(
        self,
        message: str = "Data quality validation failed",
        rule_name: str | None = None,
        severity: str | None = None,
        affected_rows: int | None = None,
        dataset: str | None = None,
    ):
        details = {}
        if rule_name:
            details["rule_name"] = rule_name
        if severity:
            details["severity"] = severity
        if affected_rows:
            details["affected_rows"] = affected_rows
        if dataset:
            details["dataset"] = dataset
        super().__init__(message, details)


class DQRuleNotFoundError(DQError):
    """DQ 规则不存在"""

    def __init__(
        self,
        message: str = "DQ rule not found",
        rule_name: str | None = None,
        dataset: str | None = None,
    ):
        details = {}
        if rule_name:
            details["rule_name"] = rule_name
        if dataset:
            details["dataset"] = dataset
        super().__init__(message, details)


# ============================================================
# 冻结点错误
# ============================================================

class FreezeError(DataHubError):
    """冻结点错误基类"""
    pass


class FreezeNotFoundError(FreezeError):
    """冻结点不存在"""

    def __init__(
        self,
        message: str = "Freeze point not found",
        freeze_id: str | None = None,
    ):
        details = {"freeze_id": freeze_id} if freeze_id else {}
        super().__init__(message, details)


class FreezeVerificationError(FreezeError):
    """冻结点校验失败（数据已变更）"""

    def __init__(
        self,
        message: str = "Freeze verification failed",
        freeze_id: str | None = None,
        mismatched_files: list[str] | None = None,
    ):
        details = {}
        if freeze_id:
            details["freeze_id"] = freeze_id
        if mismatched_files:
            details["mismatched_files"] = mismatched_files[:10]  # 最多显示 10 个
            if len(mismatched_files) > 10:
                details["total_mismatched"] = len(mismatched_files)
        super().__init__(message, details)


# ============================================================
# 日历相关错误
# ============================================================

class CalendarError(DataHubError):
    """日历相关错误基类"""
    pass


class TradingDateNotFoundError(CalendarError):
    """交易日不存在（超出日历范围）"""

    def __init__(
        self,
        message: str = "Trading date not found",
        date: str | None = None,
        direction: str | None = None,  # "prev" | "next"
    ):
        details = {}
        if date:
            details["date"] = date
        if direction:
            details["direction"] = direction
        super().__init__(message, details)


# ============================================================
# Universe 相关错误
# ============================================================

class UniverseError(DataHubError):
    """Universe 相关错误基类"""
    pass


class UniverseNotFoundError(UniverseError):
    """Universe 不存在"""

    def __init__(
        self,
        message: str = "Universe not found",
        universe_id: str | None = None,
    ):
        details = {"universe_id": universe_id} if universe_id else {}
        super().__init__(message, details)


class UniverseAlreadyExistsError(UniverseError):
    """Universe 已存在"""

    def __init__(
        self,
        message: str = "Universe already exists",
        universe_id: str | None = None,
    ):
        details = {"universe_id": universe_id} if universe_id else {}
        super().__init__(message, details)

```

---

## 六、Schema 定义

```python
# src/ditto_data_hub/meta/schemas.py
import polars as pl

# ============================================================
# 股票日线 Schema
# ============================================================
STOCK_DAILY_SCHEMA = {
    "sid":              pl.Int64,
    "trade_date":       pl.Date,
    "source":           pl.Utf8,
    "src_code":         pl.Utf8,
    "open":             pl.Float64,
    "high":             pl.Float64,
    "low":              pl.Float64,
    "close":            pl.Float64,
    "pre_close":        pl.Float64,
    "volume":           pl.Float64,
    "amount":           pl.Float64,
    "pct_change":       pl.Float64,
    "turnover":         pl.Float64,
    "is_suspended":     pl.Boolean,
    "is_limit_up":      pl.Boolean,
    "is_limit_down":    pl.Boolean,
    "is_st":            pl.Boolean,
}


# ============================================================
# ETF 日线 Schema
# ============================================================
ETF_DAILY_SCHEMA = {
    "sid":              pl.Int64,
    "trade_date":       pl.Date,
    "source":           pl.Utf8,
    "src_code":         pl.Utf8,
    "open":             pl.Float64,
    "high":             pl.Float64,
    "low":              pl.Float64,
    "close":            pl.Float64,
    "pre_close":        pl.Float64,
    "volume":           pl.Float64,
    "amount":           pl.Float64,
    "pct_change":       pl.Float64,
    "turnover":         pl.Float64,
    "is_suspended":     pl.Boolean,
    "is_limit_up":      pl.Boolean,
    "is_limit_down":    pl.Boolean,
    "is_st":            pl.Boolean,
}


# ============================================================
# 指数日线 Schema
# ============================================================
INDEX_DAILY_SCHEMA = {
    "sid":              pl.Int64,
    "trade_date":       pl.Date,
    "source":           pl.Utf8,
    "src_code":         pl.Utf8,
    "open":             pl.Float64,
    "high":             pl.Float64,
    "low":              pl.Float64,
    "close":            pl.Float64,
    "pre_close":        pl.Float64,
    "change":           pl.Float64,
    "pct_change":       pl.Float64,
    "volume":           pl.Float64,
    "amount":           pl.Float64,
}


# ============================================================
# 复权因子 Schema
# ============================================================
ADJ_FACTOR_SCHEMA = {
    "sid":              pl.Int64,
    "trade_date":       pl.Date,
    "source":           pl.Utf8,
    "src_code":         pl.Utf8,
    "adj_factor":       pl.Float64,
}


# ============================================================
# 指数成分权重 Schema
# ============================================================
INDEX_WEIGHT_SCHEMA = {
    "index_sid":        pl.Int64,
    "con_sid":          pl.Int64,
    "trade_date":       pl.Date,
    "weight":           pl.Float64,
    "source":           pl.Utf8,
    "index_code":       pl.Utf8,
    "con_code":         pl.Utf8,
}


# ============================================================
# 标的池成分 Schema（PIT）
# ============================================================
UNIVERSE_CONSTITUENT_SCHEMA = {
    "universe_id":      pl.Utf8,
    "sid":              pl.Int64,
    "source":           pl.Utf8,
    "src_code":         pl.Utf8,
    "effective_from":   pl.Date,
    "effective_to":     pl.Date,
    "weight":           pl.Float64,
}
```

---

## 七、SQLite 元数据表结构

```sql
-- ============================================================
-- SID 序列号表
-- ============================================================
CREATE TABLE IF NOT EXISTS sid_sequence (
    asset_class     TEXT PRIMARY KEY,
    current_max     INTEGER NOT NULL,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

INSERT OR IGNORE INTO sid_sequence VALUES ('stock', 100000000, CURRENT_TIMESTAMP);
INSERT OR IGNORE INTO sid_sequence VALUES ('etf', 200000000, CURRENT_TIMESTAMP);
INSERT OR IGNORE INTO sid_sequence VALUES ('index', 300000000, CURRENT_TIMESTAMP);
INSERT OR IGNORE INTO sid_sequence VALUES ('bond', 400000000, CURRENT_TIMESTAMP);
INSERT OR IGNORE INTO sid_sequence VALUES ('future', 500000000, CURRENT_TIMESTAMP);


-- ============================================================
-- 证券主表
-- ============================================================
CREATE TABLE IF NOT EXISTS security (
    sid             INTEGER PRIMARY KEY,
    symbol          TEXT NOT NULL,
    name            TEXT,
    display_name    TEXT,
    exchange        TEXT NOT NULL,
    board           TEXT,
    asset_class     TEXT NOT NULL,
    list_date       DATE NOT NULL,
    delist_date     DATE,
    is_st           BOOLEAN DEFAULT FALSE,
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_security_symbol ON security(symbol);
CREATE INDEX IF NOT EXISTS idx_security_asset_class ON security(asset_class);
CREATE INDEX IF NOT EXISTS idx_security_active ON security(is_active);


-- ============================================================
-- 证券数据源映射表（支持 PIT）
-- ============================================================
CREATE TABLE IF NOT EXISTS security_mapping (
    sid             INTEGER NOT NULL,
    source          TEXT NOT NULL,
    src_code        TEXT NOT NULL,
    effective_from  DATE NOT NULL DEFAULT '1990-01-01',
    effective_to    DATE,                   -- NULL = 当前有效
    is_primary      BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (source, src_code, effective_from),
    FOREIGN KEY (sid) REFERENCES security(sid)
);

-- 当前有效映射的快速查询
CREATE INDEX IF NOT EXISTS idx_mapping_current
    ON security_mapping(source, src_code) WHERE effective_to IS NULL;

-- 按 sid 查询所有映射
CREATE INDEX IF NOT EXISTS idx_mapping_sid ON security_mapping(sid);

-- PIT 查询优化
CREATE INDEX IF NOT EXISTS idx_mapping_pit
    ON security_mapping(source, src_code, effective_from, effective_to);


-- ============================================================
-- 交易日历
-- ============================================================
CREATE TABLE IF NOT EXISTS trading_calendar (
    trade_date      DATE PRIMARY KEY,
    is_open         BOOLEAN NOT NULL,
    prev_trade_date DATE,
    next_trade_date DATE,
    week_of_year    INTEGER,
    month           INTEGER,
    quarter         INTEGER,
    year            INTEGER,
    is_week_end     BOOLEAN,
    is_month_end    BOOLEAN,
    is_quarter_end  BOOLEAN
);

CREATE INDEX IF NOT EXISTS idx_calendar_open ON trading_calendar(is_open);


-- ============================================================
-- Pipeline 运行记录
-- ============================================================
CREATE TABLE IF NOT EXISTS pipeline_run (
    run_id          TEXT PRIMARY KEY,
    task_name       TEXT NOT NULL,
    dataset_id      TEXT NOT NULL,
    year            INTEGER,
    rows_read       INTEGER,
    rows_written    INTEGER,
    status          TEXT NOT NULL,
    error_message   TEXT,
    dq_passed       BOOLEAN,
    dq_fail_count   INTEGER DEFAULT 0,
    dq_warn_count   INTEGER DEFAULT 0,
    started_at      TIMESTAMP,
    finished_at     TIMESTAMP,
    duration_sec    REAL
);

CREATE INDEX IF NOT EXISTS idx_run_dataset ON pipeline_run(dataset_id);


-- ============================================================
-- DQ 异常记录
-- ============================================================
CREATE TABLE IF NOT EXISTS dq_issue (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          TEXT NOT NULL,
    dataset_id      TEXT NOT NULL,
    year            INTEGER,
    sid             INTEGER,
    trade_date      DATE,
    rule_name       TEXT NOT NULL,
    severity        TEXT NOT NULL,
    message         TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_dq_run ON dq_issue(run_id);


-- ============================================================
-- Freeze 冻结点
-- ============================================================
CREATE TABLE IF NOT EXISTS freeze_point (
    freeze_id       TEXT PRIMARY KEY,
    description     TEXT,
    manifest_path   TEXT NOT NULL,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);


-- ============================================================
-- 涨跌幅制度配置
-- ============================================================
CREATE TABLE IF NOT EXISTS price_limit_config (
    config_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    exchange        TEXT,
    board           TEXT,
    is_st           BOOLEAN,
    min_list_days   INTEGER,
    max_list_days   INTEGER,
    limit_pct       REAL NOT NULL,
    priority        INTEGER DEFAULT 0,
    description     TEXT
);

INSERT OR IGNORE INTO price_limit_config
    (config_id, exchange, board, is_st, min_list_days, max_list_days, limit_pct, priority, description)
VALUES
    (1, NULL, NULL, NULL, NULL, 5, 1000, 100, '新股前5个交易日：不限制'),
    (2, NULL, NULL, 1, 6, NULL, 5, 90, 'ST股：±5%'),
    (3, 'BSE', NULL, NULL, 6, NULL, 30, 80, '北交所：±30%'),
    (4, NULL, '科创板', NULL, 6, NULL, 20, 70, '科创板：±20%'),
    (5, NULL, '创业板', NULL, 6, NULL, 20, 70, '创业板：±20%'),
    (6, NULL, NULL, NULL, 6, NULL, 10, 0, '默认（主板）：±10%');


-- ============================================================
-- 标的池
-- ============================================================
-- 标的池定义
CREATE TABLE IF NOT EXISTS universe (
    universe_id     TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    description     TEXT,
    universe_type   TEXT NOT NULL,        -- 'custom' | 'index' | 'sector'
    source_ref      TEXT,                  -- 关联来源，如指数代码
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP
);

-- 标的池成分（支持 PIT）
CREATE TABLE IF NOT EXISTS universe_constituent (
    universe_id     TEXT NOT NULL,
    sid             INTEGER NOT NULL,
    effective_from  DATE NOT NULL,
    effective_to    DATE,                  -- NULL = 当前有效
    weight          REAL DEFAULT 1.0,
    source          TEXT,
    src_code        TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (universe_id, sid, effective_from),
    FOREIGN KEY (universe_id) REFERENCES universe(universe_id),
    FOREIGN KEY (sid) REFERENCES security(sid)
);

-- 当前有效成分快速查询
CREATE INDEX IF NOT EXISTS idx_constituent_current
    ON universe_constituent(universe_id, sid) WHERE effective_to IS NULL;

-- PIT 查询优化
CREATE INDEX IF NOT EXISTS idx_constituent_pit
    ON universe_constituent(universe_id, effective_from, effective_to);
```

---

## 八、DQ 规则校验
> 详见 09_data_quality_design.md 设计文档

## 九、核心组件实现

### 9.2 DataHub（纯 Facade）

```python
# src/ditto_data_hub/hub.py
"""
DataHub - 统一数据入口（Pythonic 版本）

核心设计：
- DataHub 既是 Facade 也是 Factory
- 使用 @cached_property 实现懒加载
- 显式依赖注入到 Accessor
- 无需额外的 Context 类

使用示例：
    hub = DataHub("data")

    # Accessor 访问
    bars = hub.bars.get(src_codes=["600000.SH"], start="2024-01-01")

    # SQL 查询
    df = hub.sql("SELECT * FROM stock_daily WHERE sid = 10001")

    # 资源清理
    hub.close()
"""

from __future__ import annotations
from functools import cached_property
from pathlib import Path
from typing import TYPE_CHECKING
import polars as pl

if TYPE_CHECKING:
    from .stores.security_store import SecurityStore
    from .stores.calendar_store import CalendarStore
    from .stores.ingestion_log import IngestionLogStore
    from .stores.bars_store import BarsStore
    from .stores.index_store import IndexStore
    from .stores.adj_factor_store import AdjFactorStore
    from .stores.universe_store import UniverseStore
    from .accessors.bars import BarsAccessor
    from .accessors.calendar import CalendarAccessor
    from .accessors.securities import SecuritiesAccessor
    from .accessors.index import IndexAccessor
    from .accessors.universe import UniverseAccessor
    from .runtime.sqlite_pool import SQLitePool
    from .runtime.sql_engine import SqlEngine
    from .runtime.freeze_manager import FreezeManager
    from .runtime.sid_allocator import SidAllocator
    from .runtime.dq_checker import DQChecker
    from .runtime.file_lock import FileLockManager
    from .runtime.sqlite_client import SQLiteClient


class DataHub:
    """
    统一数据入口

    使用 @cached_property 实现懒加载：
    - 只有在第一次访问时才会初始化对应组件
    - 例如只使用 hub.calendar 时，不会初始化 DuckDB 或扫描 Parquet

    属性分层：
    - 基础资源：sqlite_pool, db, lock_manager
    - Stores：security_store, calendar_store, bars_store, ...
    - Accessors：bars, calendar, securities, index, universe
    - 工具：sql_engine, freeze
    """

    def __init__(self, data_root: str | Path = "data"):
        """
        初始化 DataHub

        Args:
            data_root: 数据根目录路径
        """
        self.data_root = Path(data_root)

        # 确保目录存在
        self.data_root.mkdir(parents=True, exist_ok=True)
        (self.data_root / "meta").mkdir(parents=True, exist_ok=True)

    # ========================================================================
    # 基础资源 (Base Resources)
    # ========================================================================

    @cached_property
    def sqlite_pool(self) -> "SQLitePool":
        """SQLite 连接池"""
        from .runtime.sqlite_pool import SQLitePool

        db_path = self.data_root / "meta" / "hub.sqlite"
        pool = SQLitePool(db_path)
        pool.init_schema()
        return pool

    @cached_property
    def sqlite_client(self) -> "SQLiteClient":
        """SQLite 客户端（组合模式，供 Store 使用）"""
        from .runtime.sqlite_client import SQLiteClient
        return SQLiteClient(self.sqlite_pool)

    @cached_property
    def lock_manager(self) -> "FileLockManager":
        """文件锁管理器"""
        from .runtime.file_lock import FileLockManager
        return FileLockManager(self.data_root / "locks")

    @cached_property
    def sid_allocator(self) -> "SidAllocator":
        """SID 分配器"""
        from .runtime.sid_allocator import SidAllocator
        return SidAllocator(self.sqlite_client)

    @cached_property
    def dq_checker(self) -> "DQChecker":
        """数据质量检查器"""
        from .runtime.dq_checker import DQChecker
        return DQChecker()

    # ========================================================================
    # Stores (数据存取层)
    # ========================================================================

    @cached_property
    def security_store(self) -> "SecurityStore":
        """证券主数据存储"""
        from .stores.security_store import SecurityStore
        return SecurityStore(self.sqlite_client)

    @cached_property
    def calendar_store(self) -> "CalendarStore":
        """交易日历存储（内存缓存）"""
        from .stores.calendar_store import CalendarStore
        return CalendarStore(self.sqlite_client)

    @cached_property
    def pipeline_store(self) -> "PipelineStore":
        """Pipeline 运行记录存储"""
        from .stores.pipeline_store import PipelineStore
        return PipelineStore(self.sqlite_client)

    @cached_property
    def universe_store(self) -> "UniverseStore":
        """标的池存储"""
        from .stores.universe_store import UniverseStore
        return UniverseStore(self.sqlite_client)

    @cached_property
    def bars_store(self) -> "BarsStore":
        """行情数据存储（Parquet）"""
        from .stores.bars_store import BarsStore
        return BarsStore(self.data_root)

    @cached_property
    def index_store(self) -> "IndexStore":
        """指数数据存储（Parquet）"""
        from .stores.index_store import IndexStore
        return IndexStore(self.data_root)

    @cached_property
    def adj_factor_store(self) -> "AdjFactorStore":
        """复权因子存储（Parquet）"""
        from .stores.adj_factor_store import AdjFactorStore
        return AdjFactorStore(self.data_root)

    # ========================================================================
    # Accessors (业务聚合层) - 显式依赖注入
    # ========================================================================

    @cached_property
    def bars(self) -> "BarsAccessor":
        """行情数据 Accessor"""
        from .accessors.bars import BarsAccessor
        return BarsAccessor(
            bars_store=self.bars_store,
            security_store=self.security_store,
            adj_factor_store=self.adj_factor_store,
            dq_checker=self.dq_checker,
            lock_manager=self.lock_manager,
            pipeline_store=self.pipeline_store,
        )

    @cached_property
    def calendar(self) -> "CalendarAccessor":
        """交易日历 Accessor"""
        from .accessors.calendar import CalendarAccessor
        return CalendarAccessor(calendar_store=self.calendar_store)

    @cached_property
    def securities(self) -> "SecuritiesAccessor":
        """证券主数据 Accessor"""
        from .accessors.securities import SecuritiesAccessor
        return SecuritiesAccessor(
            security_store=self.security_store,
            sid_allocator=self.sid_allocator,
        )

    @cached_property
    def index(self) -> "IndexAccessor":
        """指数数据 Accessor"""
        from .accessors.index import IndexAccessor
        return IndexAccessor(
            index_store=self.index_store,
            security_store=self.security_store,
            dq_checker=self.dq_checker,
            lock_manager=self.lock_manager,
        )

    @cached_property
    def universe(self) -> "UniverseAccessor":
        """标的池 Accessor"""
        from .accessors.universe import UniverseAccessor
        return UniverseAccessor(
            universe_store=self.universe_store,
            security_store=self.security_store,
            index_store=self.index_store,
        )

    # ========================================================================
    # SQL Engine
    # ========================================================================

    @cached_property
    def sql_engine(self) -> "SqlEngine":
        """DuckDB SQL 引擎"""
        from .runtime.sql_engine import SqlEngine
        return SqlEngine(
            data_root=self.data_root,
            security_store=self.security_store,
            calendar_store=self.calendar_store,
        )

    def sql(
        self,
        query: str,
        asof: str | None = None,
        params: dict | None = None,
    ) -> pl.DataFrame:
        """
        执行 SQL 查询

        Args:
            query: SQL 语句
            asof: PIT 截断日期，会注册为 $asof 变量
            params: 其他查询参数

        Returns:
            pl.DataFrame: 查询结果

        示例：
            # 基础查询
            hub.sql("SELECT * FROM stock_daily WHERE sid = 10001")

            # PIT 查询
            hub.sql("SELECT * FROM stock_daily WHERE trade_date <= $asof", asof="2024-06-30")

            # 前复权查询
            hub.sql("SELECT * FROM qfq($asof) WHERE sid = 10001", asof="2024-06-30")
        """
        return self.sql_engine.execute(query, asof=asof, params=params)

    # ========================================================================
    # Freeze Manager
    # ========================================================================

    @cached_property
    def freeze(self) -> "FreezeManager":
        """Freeze 冻结点管理器"""
        from .runtime.freeze_manager import FreezeManager
        return FreezeManager(self.data_root)

    # ========================================================================
    # 便捷方法
    # ========================================================================

    def resolve_sid(
        self,
        identifier: str,
        source: str = "tushare",
        asof: str | None = None,
    ) -> int | None:
        """
        解析标识符为 sid（支持 PIT）

        Args:
            identifier: 数据源代码，如 "600000.SH"
            source: 数据源标识
            asof: 时点（PIT）

        Returns:
            sid 或 None（未找到）
        """
        return self.security_store.resolve_sid(identifier, source, asof)

    def refresh_sql_views(self):
        """刷新 SQL 引擎的 View（数据更新后调用）"""
        if "sql_engine" in self.__dict__:
            self.sql_engine.refresh_views()

    # ========================================================================
    # 资源管理
    # ========================================================================

    def close(self):
        """
        关闭所有已初始化的资源

        只会关闭已经被访问过（初始化过）的资源，
        未使用的资源不会被创建也不需要关闭。
        """
        # 检查并关闭 SQL 引擎
        if "sql_engine" in self.__dict__:
            self.sql_engine.close()

        # 检查并关闭 SQLite 连接池
        if "sqlite_pool" in self.__dict__:
            self.sqlite_pool.close()

    def __enter__(self) -> "DataHub":
        """支持 with 语句"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """退出时自动关闭资源"""
        self.close()

    def __repr__(self) -> str:
        initialized = [k for k in self.__dict__ if not k.startswith("_") and k != "data_root"]
        return f"DataHub(data_root='{self.data_root}', initialized={initialized})"

```

### 9.4 BarsAccessor

```python
# src/ditto_data_hub/accessors/bars.py
"""
行情数据 Accessor

提供股票/ETF 日线数据的读写操作，支持：
- PIT (Point-in-Time) 查询
- 复权计算 (QFQ/HFQ)
- 数据质量检查
"""

from __future__ import annotations
from typing import Literal, TYPE_CHECKING
from datetime import datetime, date
from uuid import uuid4
import polars as pl

if TYPE_CHECKING:
    from ..stores.bars_store import BarsStore
    from ..stores.security_store import SecurityStore
    from ..stores.adj_factor_store import AdjFactorStore
    from ..stores.pipeline_store import PipelineStore
    from ..runtime.dq_checker import DQChecker
    from ..runtime.file_lock import FileLockManager

from ..types import WriteRequest, WriteResult, WriteStatus, DatasetId
from ..errors import SidResolutionError, AmbiguousIdentifierError


class BarsAccessor:
    """
    行情数据 Accessor

    使用示例：
        # 读取行情
        bars = accessor.get(src_codes=["600000.SH"], start="2024-01-01", adj="qfq")

        # 写入行情
        result = accessor.write(df, year=2024, dataset="stock_daily")
    """

    def __init__(
        self,
        bars_store: "BarsStore",
        security_store: "SecurityStore",
        adj_factor_store: "AdjFactorStore",
        dq_checker: "DQChecker",
        lock_manager: "FileLockManager",
        pipeline_store: "PipelineStore",
    ):
        self.bars_store = bars_store
        self.security_store = security_store
        self.adj_factor_store = adj_factor_store
        self.dq_checker = dq_checker
        self.lock_manager = lock_manager
        self.pipeline_store = pipeline_store

    def get(
        self,
        *,
        sids: list[int] | None = None,
        src_codes: list[str] | None = None,
        symbols: list[str] | None = None,
        source: str = "tushare",
        start: str | None = None,
        end: str | None = None,
        columns: list[str] | None = None,
        adj: Literal["none", "qfq", "hfq"] = "none",
        with_symbol: bool = False,
        asset_class: Literal["stock", "etf", "all"] = "stock",
        asof: str | None = None,
    ) -> pl.DataFrame:
        """
        获取行情数据

        Args:
            sids: 内部 ID 列表
            src_codes: 数据源代码列表，如 ["600000.SH"]
            symbols: 展示代码列表，如 ["600000"]
            source: 数据源标识
            start/end: 日期范围 (YYYY-MM-DD)
            columns: 选择列
            adj: 复权类型 (none/qfq/hfq)
            with_symbol: 是否派生 symbol 列
            asset_class: 资产类别 (stock/etf/all)
            asof: PIT 截断点（同时用于标识符解析和数据过滤）

        Returns:
            pl.DataFrame: 行情数据
        """
        # 1. 解析 sids（支持 PIT）
        resolved_sids = self._resolve_sids(sids, src_codes, symbols, source, asof)

        if not resolved_sids and (src_codes or symbols):
            return pl.DataFrame()

        # 2. 标准化日期
        start_date = self._normalize_date(start) or "2010-01-01"
        end_date = self._normalize_date(end) or "2099-12-31"

        # 3. 应用 asof 截断
        if asof:
            asof_date = self._normalize_date(asof)
            if asof_date and asof_date < end_date:
                end_date = asof_date

        # 4. 读取数据
        dfs = []

        if asset_class in ("stock", "all"):
            df = self.bars_store.read(
                dataset="stock_daily",
                sids=resolved_sids,
                start_date=start_date,
                end_date=end_date,
            )
            if not df.is_empty():
                dfs.append(df)

        if asset_class in ("etf", "all"):
            df = self.bars_store.read(
                dataset="etf_daily",
                sids=resolved_sids,
                start_date=start_date,
                end_date=end_date,
            )
            if not df.is_empty():
                dfs.append(df)

        if not dfs:
            return pl.DataFrame()

        df = pl.concat(dfs) if len(dfs) > 1 else dfs[0]

        # 5. 列选择
        if columns:
            base_cols = ["sid", "trade_date"]
            select_cols = base_cols + [c for c in columns if c in df.columns and c not in base_cols]
            df = df.select(select_cols)

        # 6. 复权
        if adj != "none":
            df = self._apply_adjustment(df, adj, asof)

        # 7. 派生 symbol
        if with_symbol:
            df = self.security_store.enrich_with_symbol(df)

        return df.sort(["trade_date", "sid"])

    def get_single(
        self,
        identifier: str,
        start: str | None = None,
        end: str | None = None,
        source: str = "tushare",
        adj: Literal["none", "qfq", "hfq"] = "none",
        asof: str | None = None,
    ) -> pl.DataFrame:
        """
        获取单只标的行情

        Args:
            identifier: 标识符 (src_code 或 symbol)
            start/end: 日期范围
            source: 数据源
            adj: 复权类型
            asof: PIT 截断点
        """
        if "." in identifier:
            return self.get(
                src_codes=[identifier],
                source=source,
                start=start, end=end,
                adj=adj, asof=asof,
                asset_class="all",
            )
        else:
            return self.get(
                symbols=[identifier],
                source=source,
                start=start, end=end,
                adj=adj, asof=asof,
                asset_class="all",
            )

    def write(
        self,
        df: pl.DataFrame,
        year: int,
        dataset: Literal["stock_daily", "etf_daily"] = "stock_daily",
        source: str = "tushare",
        dq_fail_action: Literal["reject", "quarantine"] = "reject",
    ) -> WriteResult:
        """
        写入行情数据

        Args:
            df: 待写入数据
            year: 年份
            dataset: 数据集名称
            source: 数据源
            dq_fail_action: DQ 失败时的处理方式

        Returns:
            WriteResult: 写入结果
        """
        run_id = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid4().hex[:8]}"
        started_at = datetime.now()

        # DQ 检查
        dq_result = self.dq_checker.check(df, dataset)

        if not dq_result.passed:
            if dq_fail_action == "quarantine":
                return self._quarantine(df, dataset, year, run_id, dq_result)
            else:
                return self._reject(dataset, year, run_id, dq_result, started_at)

        # 获取锁并写入
        with self.lock_manager.acquire(dataset):
            try:
                file_path, checksum = self.bars_store.write(
                    dataset=dataset,
                    df=df,
                    year=year,
                )

                # 记录运行日志
                self.pipeline_store.insert_run(
                    run_id=run_id,
                    task_name=f"ingest_{dataset}",
                    dataset_id=dataset,
                    year=year,
                    rows_written=df.height,
                    status="success",
                    dq_passed=True,
                    dq_fail_count=dq_result.fail_count,
                    dq_warn_count=dq_result.warn_count,
                    started_at=started_at,
                    finished_at=datetime.now(),
                )

                return WriteResult(
                    dataset=DatasetId(dataset),
                    status=WriteStatus.SUCCESS,
                    year=year,
                    run_id=run_id,
                    file_path=file_path,
                    row_count=df.height,
                    checksum=checksum,
                    dq_passed=True,
                )

            except Exception as e:
                self.pipeline_store.insert_run(
                    run_id=run_id,
                    task_name=f"ingest_{dataset}",
                    dataset_id=dataset,
                    year=year,
                    status="failed",
                    error_message=str(e),
                    started_at=started_at,
                    finished_at=datetime.now(),
                )
                raise

    # ========== 私有方法 ==========

    def _resolve_sids(
        self,
        sids: list[int] | None,
        src_codes: list[str] | None,
        symbols: list[str] | None,
        source: str,
        asof: str | None,
    ) -> list[int] | None:
        """解析 sids（支持 PIT）"""
        if sids:
            return sids

        result = []

        if src_codes:
            for code in src_codes:
                sid = self.security_store.resolve_sid(code, source, asof)
                if sid:
                    result.append(sid)

        elif symbols:
            for sym in symbols:
                if "." in sym:
                    sid = self.security_store.resolve_sid(sym, source, asof)
                else:
                    sids_found = self.security_store.resolve_by_symbol(sym, source)
                    if len(sids_found) == 1:
                        sid = sids_found[0]
                    elif len(sids_found) > 1:
                        raise AmbiguousIdentifierError(
                            f"Symbol '{sym}' maps to multiple sids",
                            identifier=sym,
                            candidates=sids_found,
                        )
                    else:
                        sid = None

                if sid:
                    result.append(sid)

        return result if result else None

    def _apply_adjustment(
        self,
        df: pl.DataFrame,
        adj: str,
        asof: str | None,
    ) -> pl.DataFrame:
        """应用复权"""
        if df.is_empty():
            return df

        sids = df["sid"].unique().to_list()
        start_date = str(df["trade_date"].min())
        end_date = str(df["trade_date"].max())

        adj_df = self.adj_factor_store.read(
            sids=sids,
            start_date=start_date,
            end_date=end_date,
        )

        if adj_df.is_empty():
            return df

        df = df.join(
            adj_df.select(["sid", "trade_date", "adj_factor"]),
            on=["sid", "trade_date"],
            how="left"
        )
        df = df.with_columns(pl.col("adj_factor").fill_null(1.0))

        price_cols = [c for c in ["open", "high", "low", "close"] if c in df.columns]

        if adj == "hfq":
            # 后复权：价格 * 因子
            for col in price_cols:
                df = df.with_columns((pl.col(col) * pl.col("adj_factor")).alias(col))

        elif adj == "qfq":
            # 前复权：价格 * 因子 / 最新因子
            # 使用 asof 截断后的最新因子
            if asof:
                adj_df_for_latest = adj_df.filter(pl.col("trade_date") <= asof)
            else:
                adj_df_for_latest = adj_df

            latest = (
                adj_df_for_latest
                .sort(["sid", "trade_date"])
                .group_by("sid")
                .agg(pl.col("adj_factor").last().alias("latest_factor"))
            )
            df = df.join(latest, on="sid", how="left")
            df = df.with_columns(pl.col("latest_factor").fill_null(1.0))

            for col in price_cols:
                df = df.with_columns(
                    (pl.col(col) * pl.col("adj_factor") / pl.col("latest_factor")).alias(col)
                )
            df = df.drop("latest_factor")

        return df.drop("adj_factor")

    def _quarantine(self, df, dataset, year, run_id, dq_result) -> WriteResult:
        """移入隔离区"""
        quarantine_path = self.bars_store.data_root / "quarantine" / dataset / run_id
        quarantine_path.mkdir(parents=True, exist_ok=True)
        file_path = quarantine_path / f"{year}.parquet"
        df.write_parquet(file_path, compression="zstd")

        return WriteResult(
            dataset=DatasetId(dataset),
            status=WriteStatus.QUARANTINED,
            year=year,
            run_id=run_id,
            file_path=str(file_path),
            row_count=df.height,
            dq_passed=False,
            dq_failures=[{"rule": r.rule_name, "message": r.message}
                        for r in dq_result.results if not r.passed],
        )

    def _reject(self, dataset, year, run_id, dq_result, started_at) -> WriteResult:
        """拒绝写入"""
        self.pipeline_store.insert_run(
            run_id=run_id,
            task_name=f"ingest_{dataset}",
            dataset_id=dataset,
            year=year,
            status="rejected",
            dq_passed=False,
            dq_fail_count=dq_result.fail_count,
            dq_warn_count=dq_result.warn_count,
            started_at=started_at,
            finished_at=datetime.now(),
        )

        return WriteResult(
            dataset=DatasetId(dataset),
            status=WriteStatus.REJECTED,
            year=year,
            run_id=run_id,
            dq_passed=False,
            dq_failures=[{"rule": r.rule_name, "message": r.message}
                        for r in dq_result.results if not r.passed],
        )

    def _normalize_date(self, date_str: str | None) -> str | None:
        """标准化日期为 YYYY-MM-DD"""
        if not date_str:
            return None
        date_str = str(date_str).replace("-", "")
        if len(date_str) == 8:
            return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
        return date_str

```

### 9.5 CalendarAccessor

```python
# src/ditto_data_hub/accessors/calendar.py
"""
交易日历 Accessor

提供交易日历查询功能，所有操作都使用内存缓存，性能极高。
"""

from __future__ import annotations
from typing import Literal, TYPE_CHECKING
import polars as pl

if TYPE_CHECKING:
    from ..stores.calendar_store import CalendarStore


class CalendarAccessor:
    """
    交易日历 Accessor

    使用示例：
        # 判断交易日
        is_open = accessor.is_trading_day("2024-01-02")

        # 获取交易日列表
        days = accessor.list_trading_days("2024-01-01", "2024-03-31")

        # 偏移交易日
        next_day = accessor.offset("2024-01-02", 1)
        prev_5_day = accessor.offset("2024-01-02", -5)
    """

    def __init__(self, calendar_store: "CalendarStore"):
        self.calendar_store = calendar_store

    def get(
        self,
        start: str | None = None,
        end: str | None = None,
        only_open: bool = True,
    ) -> pl.DataFrame:
        """
        获取交易日历 DataFrame

        Args:
            start: 开始日期
            end: 结束日期
            only_open: 是否只返回交易日

        Returns:
            pl.DataFrame: 日历数据
        """
        return self.calendar_store.get_range_df(
            start=self._normalize_date(start) or "2010-01-01",
            end=self._normalize_date(end) or "2099-12-31",
            only_open=only_open,
        )

    def is_trading_day(self, date: str) -> bool:
        """
        判断是否交易日

        Args:
            date: 日期 (YYYY-MM-DD)

        Returns:
            bool: 是否交易日
        """
        return self.calendar_store.is_trading_day(self._normalize_date(date))

    def list_trading_days(self, start: str, end: str) -> list[str]:
        """
        列出交易日

        Args:
            start: 开始日期
            end: 结束日期

        Returns:
            list[str]: 交易日列表
        """
        return self.calendar_store.get_range(
            self._normalize_date(start),
            self._normalize_date(end),
        )

    def get_prev(self, date: str) -> str | None:
        """
        获取前一交易日

        Args:
            date: 当前日期

        Returns:
            str | None: 前一交易日
        """
        return self.calendar_store.get_prev(self._normalize_date(date))

    def get_next(self, date: str) -> str | None:
        """
        获取后一交易日

        Args:
            date: 当前日期

        Returns:
            str | None: 后一交易日
        """
        return self.calendar_store.get_next(self._normalize_date(date))

    def offset(self, date: str, n: int) -> str | None:
        """
        偏移 n 个交易日

        Args:
            date: 起始日期
            n: 偏移量（正数向后，负数向前）

        Returns:
            str | None: 目标交易日

        示例：
            offset("2024-01-02", 1)   # 下一个交易日
            offset("2024-01-02", -1)  # 上一个交易日
            offset("2024-01-02", 250) # 约一年后
        """
        return self.calendar_store.offset(self._normalize_date(date), n)

    def count_trading_days(self, start: str, end: str) -> int:
        """
        计算交易日数量

        Args:
            start: 开始日期
            end: 结束日期

        Returns:
            int: 交易日数量
        """
        return len(self.list_trading_days(start, end))

    def get_period_ends(
        self,
        start: str,
        end: str,
        period: Literal["week", "month", "quarter"] = "month",
    ) -> list[str]:
        """
        获取周期末交易日

        Args:
            start: 开始日期
            end: 结束日期
            period: 周期类型 (week/month/quarter)

        Returns:
            list[str]: 周期末交易日列表
        """
        return self.calendar_store.get_period_ends(
            self._normalize_date(start),
            self._normalize_date(end),
            period,
        )

    def get_month_ends(self, start: str, end: str) -> list[str]:
        """获取月末交易日"""
        return self.get_period_ends(start, end, "month")

    def get_quarter_ends(self, start: str, end: str) -> list[str]:
        """获取季末交易日"""
        return self.get_period_ends(start, end, "quarter")

    def get_latest_before(self, date: str) -> str | None:
        """获取指定日期之前（含）的最近交易日"""
        return self.calendar_store.get_latest_before(self._normalize_date(date))

    def get_earliest_after(self, date: str) -> str | None:
        """获取指定日期之后（含）的最近交易日"""
        return self.calendar_store.get_earliest_after(self._normalize_date(date))

    def get_first_trading_day(self) -> str | None:
        """获取最早交易日"""
        return self.calendar_store.get_first_trading_day()

    def get_last_trading_day(self) -> str | None:
        """获取最新交易日"""
        return self.calendar_store.get_last_trading_day()

    def _normalize_date(self, date_str: str | None) -> str | None:
        """标准化日期为 YYYY-MM-DD"""
        if not date_str:
            return None
        date_str = str(date_str).replace("-", "")
        if len(date_str) == 8:
            return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
        return date_str

```

### 9.6 SecuritiesAccessor

```python
# src/ditto_data_hub/accessors/securities.py
"""
证券主数据 Accessor

提供证券基本信息的查询和管理，支持：
- SID 解析（PIT）
- 代码变更注册
- 证券信息查询
"""

from __future__ import annotations
from typing import TYPE_CHECKING
import polars as pl

if TYPE_CHECKING:
    from ..stores.security_store import SecurityStore
    from ..runtime.sid_allocator import SidAllocator


class SecuritiesAccessor:
    """
    证券主数据 Accessor

    使用示例：
        # 解析 SID
        sid = accessor.resolve_sid("600000.SH")

        # 注册新证券
        sid = accessor.register(
            source="tushare",
            src_code="688001.SH",
            symbol="688001",
            name="华兴源创",
            exchange="SSE",
            asset_class="stock",
            list_date="2019-07-22",
        )

        # 注册代码变更
        accessor.register_code_change(
            sid=12345,
            source="tushare",
            old_code="000022.SZ",
            new_code=None,  # 退市
            change_date="2018-12-25",
        )
    """

    def __init__(
        self,
        security_store: "SecurityStore",
        sid_allocator: "SidAllocator",
    ):
        self.security_store = security_store
        self.sid_allocator = sid_allocator

    def get(
        self,
        sids: list[int] | None = None,
        src_codes: list[str] | None = None,
        source: str = "tushare",
        asset_class: str | None = None,
        exchange: str | None = None,
        is_active: bool | None = True,
        asof: str | None = None,
    ) -> pl.DataFrame:
        """
        获取证券主数据

        Args:
            sids: SID 列表
            src_codes: 数据源代码列表
            source: 数据源
            asset_class: 资产类别过滤
            exchange: 交易所过滤
            is_active: 是否只返回活跃证券
            asof: PIT 时点

        Returns:
            pl.DataFrame: 证券数据
        """
        return self.security_store.find_securities(
            sids=sids,
            src_codes=src_codes,
            source=source,
            asset_class=asset_class,
            exchange=exchange,
            is_active=is_active,
            asof=asof,
        )

    def get_by_sid(self, sid: int) -> dict | None:
        """
        获取单只证券信息

        Args:
            sid: 证券 ID

        Returns:
            dict | None: 证券信息字典
        """
        return self.security_store.get_by_sid(sid)

    def resolve_sid(
        self,
        identifier: str,
        source: str = "tushare",
        asof: str | None = None,
    ) -> int | None:
        """
        解析标识符为 SID（支持 PIT）

        Args:
            identifier: 数据源代码，如 "600000.SH"
            source: 数据源
            asof: PIT 时点

        Returns:
            int | None: SID 或 None
        """
        return self.security_store.resolve_sid(identifier, source, asof)

    def resolve_sids_batch(
        self,
        src_codes: list[str],
        source: str = "tushare",
        asof: str | None = None,
    ) -> dict[str, int]:
        """
        批量解析 SID

        Args:
            src_codes: 数据源代码列表
            source: 数据源
            asof: PIT 时点

        Returns:
            dict[str, int]: {src_code: sid} 映射
        """
        return self.security_store.resolve_sids_batch(src_codes, source, asof)

    def list_all(
        self,
        asset_class: str | None = None,
        exchange: str | None = None,
        is_active: bool = True,
    ) -> list[int]:
        """
        列出所有 SID

        Args:
            asset_class: 资产类别过滤
            exchange: 交易所过滤
            is_active: 是否只返回活跃证券

        Returns:
            list[int]: SID 列表
        """
        return self.security_store.list_sids(
            asset_class=asset_class,
            exchange=exchange,
            is_active=is_active,
        )

    def register(
        self,
        source: str,
        src_code: str,
        symbol: str,
        name: str,
        exchange: str,
        asset_class: str,
        list_date: str,
        board: str | None = None,
        display_name: str | None = None,
    ) -> int:
        """
        注册新证券

        Args:
            source: 数据源
            src_code: 数据源代码
            symbol: 展示代码
            name: 证券名称
            exchange: 交易所
            asset_class: 资产类别 (stock/etf/index/bond/future)
            list_date: 上市日期
            board: 板块（主板/科创板/创业板等）
            display_name: 显示名称

        Returns:
            int: 分配的 SID
        """
        # 分配 SID
        sid = self.sid_allocator.allocate(asset_class)

        # 注册到 Store
        self.security_store.register(
            sid=sid,
            source=source,
            src_code=src_code,
            symbol=symbol,
            name=name,
            exchange=exchange,
            board=board,
            asset_class=asset_class,
            list_date=list_date,
            display_name=display_name,
        )

        return sid

    def register_code_change(
        self,
        sid: int,
        source: str,
        old_code: str,
        new_code: str | None,
        change_date: str,
    ) -> None:
        """
        注册代码变更

        用于处理：
        - 股票代码变更
        - 股票退市（new_code=None）
        - 吸收合并

        Args:
            sid: 证券 ID
            source: 数据源
            old_code: 旧代码
            new_code: 新代码（退市时为 None）
            change_date: 变更日期
        """
        self.security_store.register_code_change(
            sid=sid,
            source=source,
            old_code=old_code,
            new_code=new_code,
            change_date=change_date,
        )

    def update_status(
        self,
        sid: int,
        is_st: bool | None = None,
        is_active: bool | None = None,
        delist_date: str | None = None,
    ) -> None:
        """
        更新证券状态

        Args:
            sid: 证券 ID
            is_st: 是否 ST
            is_active: 是否活跃
            delist_date: 退市日期
        """
        self.security_store.update_status(
            sid=sid,
            is_st=is_st,
            is_active=is_active,
            delist_date=delist_date,
        )

    def get_symbol(self, sid: int) -> str | None:
        """获取证券的展示代码"""
        return self.security_store.get_symbol(sid)

    def get_src_code(
        self,
        sid: int,
        source: str = "tushare",
        asof: str | None = None,
    ) -> str | None:
        """反向查询：SID → src_code"""
        return self.security_store.get_src_code(sid, source, asof)
```

### 9.7 IndexAccessor

```python
# src/ditto_data_hub/accessors/index.py
"""
指数数据 Accessor

提供指数行情和成分权重的读写操作。
"""

from __future__ import annotations
from typing import TYPE_CHECKING
from datetime import datetime
from uuid import uuid4
import polars as pl

if TYPE_CHECKING:
    from ..stores.index_store import IndexStore
    from ..stores.security_store import SecurityStore
    from ..runtime.dq_checker import DQChecker
    from ..runtime.file_lock import FileLockManager

from ..types import WriteResult, WriteStatus, DatasetId


class IndexAccessor:
    """
    指数数据 Accessor

    使用示例：
        # 获取指数日线
        df = accessor.get_daily(src_codes=["000300.SH"], start="2024-01-01")

        # 获取指数成分权重
        weights = accessor.get_weight(index_code="000300.SH", asof="2024-06-30")

        # 获取成分股列表
        sids = accessor.get_constituents(index_code="000300.SH", asof="2024-06-30")
    """

    def __init__(
        self,
        index_store: "IndexStore",
        security_store: "SecurityStore",
        dq_checker: "DQChecker",
        lock_manager: "FileLockManager",
    ):
        self.index_store = index_store
        self.security_store = security_store
        self.dq_checker = dq_checker
        self.lock_manager = lock_manager

    def get_daily(
        self,
        *,
        sids: list[int] | None = None,
        src_codes: list[str] | None = None,
        source: str = "tushare",
        start: str | None = None,
        end: str | None = None,
        columns: list[str] | None = None,
        with_symbol: bool = False,
        asof: str | None = None,
    ) -> pl.DataFrame:
        """
        获取指数日线

        Args:
            sids: SID 列表
            src_codes: 数据源代码列表
            source: 数据源
            start/end: 日期范围
            columns: 选择列
            with_symbol: 是否添加 symbol 列
            asof: PIT 截断点

        Returns:
            pl.DataFrame: 指数日线数据
        """
        # 解析 sids（支持 PIT）
        resolved_sids = None
        if sids:
            resolved_sids = sids
        elif src_codes:
            resolved_sids = []
            for code in src_codes:
                sid = self.security_store.resolve_sid(code, source, asof)
                if sid:
                    resolved_sids.append(sid)

        if not resolved_sids and src_codes:
            return pl.DataFrame()

        start_date = self._normalize_date(start) or "2010-01-01"
        end_date = self._normalize_date(end) or "2099-12-31"

        if asof:
            asof_date = self._normalize_date(asof)
            if asof_date and asof_date < end_date:
                end_date = asof_date

        df = self.index_store.read_daily(
            sids=resolved_sids,
            start_date=start_date,
            end_date=end_date,
        )

        if df.is_empty():
            return df

        if columns:
            base_cols = ["sid", "trade_date"]
            select_cols = base_cols + [c for c in columns if c in df.columns and c not in base_cols]
            df = df.select(select_cols)

        if with_symbol:
            df = self.security_store.enrich_with_symbol(df)

        return df.sort(["trade_date", "sid"])

    def get_weight(
        self,
        index_sid: int | None = None,
        index_code: str | None = None,
        source: str = "tushare",
        asof: str | None = None,
    ) -> pl.DataFrame:
        """
        获取指数成分权重（PIT）

        Args:
            index_sid: 指数 SID
            index_code: 指数代码
            source: 数据源
            asof: PIT 截断点（取该日期最新的权重数据）

        Returns:
            pl.DataFrame: 权重数据（index_sid, con_sid, weight, trade_date）
        """
        if index_sid is None and index_code:
            index_sid = self.security_store.resolve_sid(index_code, source, asof)

        if index_sid is None:
            return pl.DataFrame()

        df = self.index_store.read_weight(index_sids=[index_sid])

        if df.is_empty():
            return df

        # PIT 过滤：取 <= asof 的最新数据
        if asof:
            asof_date = self._normalize_date(asof)
            df = df.filter(pl.col("trade_date") <= asof_date)
            if not df.is_empty():
                latest_date = df["trade_date"].max()
                df = df.filter(pl.col("trade_date") == latest_date)

        return df

    def get_constituents(
        self,
        index_sid: int | None = None,
        index_code: str | None = None,
        source: str = "tushare",
        asof: str | None = None,
    ) -> list[int]:
        """
        获取指数成分股 SID 列表

        Args:
            index_sid: 指数 SID
            index_code: 指数代码
            source: 数据源
            asof: PIT 截断点

        Returns:
            list[int]: 成分股 SID 列表
        """
        df = self.get_weight(
            index_sid=index_sid,
            index_code=index_code,
            source=source,
            asof=asof,
        )

        if df.is_empty():
            return []

        return df["con_sid"].unique().to_list()

    def get_constituent_weights(
        self,
        index_code: str,
        source: str = "tushare",
        asof: str | None = None,
    ) -> dict[int, float]:
        """
        获取成分股权重字典

        Args:
            index_code: 指数代码
            source: 数据源
            asof: PIT 截断点

        Returns:
            dict[int, float]: {con_sid: weight} 映射
        """
        df = self.get_weight(index_code=index_code, source=source, asof=asof)

        if df.is_empty():
            return {}

        return dict(zip(df["con_sid"].to_list(), df["weight"].to_list()))

    def write_daily(
        self,
        df: pl.DataFrame,
        year: int,
        source: str = "tushare",
    ) -> WriteResult:
        """
        写入指数日线

        Args:
            df: 待写入数据
            year: 年份
            source: 数据源

        Returns:
            WriteResult: 写入结果
        """
        run_id = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid4().hex[:8]}"

        dq_result = self.dq_checker.check(df, "index_daily")
        if not dq_result.passed:
            return WriteResult(
                dataset=DatasetId("index_daily"),
                status=WriteStatus.REJECTED,
                year=year,
                run_id=run_id,
                dq_passed=False,
            )

        with self.lock_manager.acquire("index_daily"):
            file_path, checksum = self.index_store.write_daily(df, year)

            return WriteResult(
                dataset=DatasetId("index_daily"),
                status=WriteStatus.SUCCESS,
                year=year,
                run_id=run_id,
                file_path=file_path,
                row_count=df.height,
                checksum=checksum,
            )

    def write_weight(
        self,
        df: pl.DataFrame,
        year: int,
        source: str = "tushare",
    ) -> WriteResult:
        """
        写入指数权重

        Args:
            df: 待写入数据
            year: 年份
            source: 数据源

        Returns:
            WriteResult: 写入结果
        """
        run_id = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid4().hex[:8]}"

        dq_result = self.dq_checker.check(df, "index_weight")
        if not dq_result.passed:
            return WriteResult(
                dataset=DatasetId("index_weight"),
                status=WriteStatus.REJECTED,
                year=year,
                run_id=run_id,
                dq_passed=False,
            )

        with self.lock_manager.acquire("index_weight"):
            file_path, checksum = self.index_store.write_weight(df, year)

            return WriteResult(
                dataset=DatasetId("index_weight"),
                status=WriteStatus.SUCCESS,
                year=year,
                run_id=run_id,
                file_path=file_path,
                row_count=df.height,
                checksum=checksum,
            )

    def _normalize_date(self, date_str: str | None) -> str | None:
        """标准化日期"""
        if not date_str:
            return None
        date_str = str(date_str).replace("-", "")
        if len(date_str) == 8:
            return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
        return date_str

```

### 9.8 UniverseAccessor

``` python
# src/ditto_data_hub/accessors/universe.py
"""
标的池 Accessor

提供标的池（Universe）的管理功能，支持：
- 自定义标的池创建和管理
- 成分股的 PIT 查询
- 从指数同步成分
"""

from __future__ import annotations
from typing import Literal, TYPE_CHECKING
from datetime import date
import polars as pl

if TYPE_CHECKING:
    from ..stores.universe_store import UniverseStore
    from ..stores.security_store import SecurityStore
    from ..stores.index_store import IndexStore

from ..errors import UniverseNotFoundError


class UniverseAccessor:
    """
    标的池 Accessor

    使用示例：
        # 创建标的池
        accessor.create("my_pool", "我的股票池")

        # 添加成分
        accessor.add("my_pool", src_codes=["600000.SH", "000001.SZ"])

        # 获取成分（PIT）
        sids = accessor.get_constituents("my_pool", asof="2024-06-30")

        # 从指数同步
        accessor.sync_from_index("hs300", "000300.SH")
    """

    def __init__(
        self,
        universe_store: "UniverseStore",
        security_store: "SecurityStore",
        index_store: "IndexStore",
    ):
        self.universe_store = universe_store
        self.security_store = security_store
        self.index_store = index_store

    # ============ Universe 管理 ============

    def create(
        self,
        universe_id: str,
        name: str,
        universe_type: Literal["custom", "index", "sector"] = "custom",
        description: str | None = None,
        source_ref: str | None = None,
    ) -> None:
        """
        创建标的池

        Args:
            universe_id: 唯一标识
            name: 名称
            universe_type: 类型
            description: 描述
            source_ref: 来源引用（如指数代码）
        """
        self.universe_store.create_universe(
            universe_id=universe_id,
            name=name,
            universe_type=universe_type,
            description=description,
            source_ref=source_ref,
        )

    def get(self, universe_id: str) -> dict | None:
        """获取标的池信息"""
        return self.universe_store.get_universe(universe_id)

    def list(self, universe_type: str | None = None) -> list[dict]:
        """列出所有标的池"""
        return self.universe_store.list_universes(universe_type)

    def delete(self, universe_id: str) -> bool:
        """删除标的池"""
        return self.universe_store.delete_universe(universe_id)

    def exists(self, universe_id: str) -> bool:
        """检查标的池是否存在"""
        return self.get(universe_id) is not None

    # ============ 成分查询（PIT）============

    def get_constituents(
        self,
        universe_id: str,
        asof: str | None = None,
    ) -> list[int]:
        """
        获取成分股 SID 列表（支持 PIT）

        Args:
            universe_id: 标的池 ID
            asof: 时点，None 表示当前

        Returns:
            list[int]: 成分股 SID 列表
        """
        return self.universe_store.get_constituents(
            universe_id,
            asof=self._normalize_date(asof),
        )

    def get_constituents_df(
        self,
        universe_id: str,
        asof: str | None = None,
        with_symbol: bool = False,
    ) -> pl.DataFrame:
        """
        获取成分股 DataFrame（含权重）

        Args:
            universe_id: 标的池 ID
            asof: 时点
            with_symbol: 是否添加 symbol 列

        Returns:
            pl.DataFrame: 成分数据
        """
        df = self.universe_store.get_constituents_with_weight(
            universe_id,
            asof=self._normalize_date(asof),
        )

        if df.is_empty():
            return df

        if with_symbol:
            df = self.security_store.enrich_with_symbol(df)

        return df

    def is_constituent(
        self,
        universe_id: str,
        sid: int | None = None,
        src_code: str | None = None,
        source: str = "tushare",
        asof: str | None = None,
    ) -> bool:
        """
        判断是否为成分股

        Args:
            universe_id: 标的池 ID
            sid: SID（与 src_code 二选一）
            src_code: 数据源代码
            source: 数据源
            asof: 时点

        Returns:
            bool: 是否为成分
        """
        if sid is None and src_code:
            sid = self.security_store.resolve_sid(
                src_code, source, self._normalize_date(asof)
            )

        if sid is None:
            return False

        return self.universe_store.is_constituent(
            universe_id, sid, self._normalize_date(asof)
        )

    # ============ 成分管理 ============

    def add(
        self,
        universe_id: str,
        sids: list[int] | None = None,
        src_codes: list[str] | None = None,
        source: str = "tushare",
        effective_from: str | None = None,
        weight: float = 1.0,
        weights: dict[int, float] | None = None,
    ) -> int:
        """
        添加成分股

        Args:
            universe_id: 标的池 ID
            sids: SID 列表
            src_codes: 数据源代码列表
            source: 数据源
            effective_from: 生效日期
            weight: 默认权重
            weights: 各成分权重 {sid: weight}

        Returns:
            int: 添加的成分数量
        """
        # 解析 sids
        resolved_sids = []
        if sids:
            resolved_sids = sids
        elif src_codes:
            for code in src_codes:
                sid = self.security_store.resolve_sid(code, source)
                if sid:
                    resolved_sids.append(sid)

        if not resolved_sids:
            return 0

        effective_from = self._normalize_date(effective_from) or self._today()
        weights = weights or {}

        for sid in resolved_sids:
            self.universe_store.add_constituent(
                universe_id=universe_id,
                sid=sid,
                effective_from=effective_from,
                weight=weights.get(sid, weight),
                source=source,
            )

        return len(resolved_sids)

    def remove(
        self,
        universe_id: str,
        sids: list[int] | None = None,
        src_codes: list[str] | None = None,
        source: str = "tushare",
        effective_date: str | None = None,
    ) -> int:
        """
        移除成分股

        Args:
            universe_id: 标的池 ID
            sids: SID 列表
            src_codes: 数据源代码列表
            source: 数据源
            effective_date: 生效日期

        Returns:
            int: 移除的成分数量
        """
        resolved_sids = []
        if sids:
            resolved_sids = sids
        elif src_codes:
            for code in src_codes:
                sid = self.security_store.resolve_sid(code, source)
                if sid:
                    resolved_sids.append(sid)

        effective_date = self._normalize_date(effective_date) or self._today()

        removed = 0
        for sid in resolved_sids:
            if self.universe_store.remove_constituent(universe_id, sid, effective_date):
                removed += 1

        return removed

    def set_constituents(
        self,
        universe_id: str,
        sids: list[int] | None = None,
        src_codes: list[str] | None = None,
        source: str = "tushare",
        effective_from: str | None = None,
        weights: dict[int, float] | None = None,
    ) -> None:
        """
        设置成分股（全量替换）

        不在列表中的现有成分会被移除。

        Args:
            universe_id: 标的池 ID
            sids: SID 列表
            src_codes: 数据源代码列表
            source: 数据源
            effective_from: 生效日期
            weights: 各成分权重
        """
        resolved_sids = []
        if sids:
            resolved_sids = sids
        elif src_codes:
            for code in src_codes:
                sid = self.security_store.resolve_sid(code, source)
                if sid:
                    resolved_sids.append(sid)

        effective_from = self._normalize_date(effective_from) or self._today()

        self.universe_store.batch_set_constituents(
            universe_id=universe_id,
            sids=resolved_sids,
            effective_from=effective_from,
            weights=weights,
        )

    # ============ 指数同步 ============

    def sync_from_index(
        self,
        universe_id: str,
        index_code: str,
        source: str = "tushare",
        asof: str | None = None,
        create_if_not_exists: bool = True,
    ) -> int:
        """
        从指数同步成分股

        Args:
            universe_id: 目标标的池 ID
            index_code: 指数代码
            source: 数据源
            asof: 同步时点
            create_if_not_exists: 自动创建不存在的标的池

        Returns:
            int: 同步的成分数量
        """
        # 获取指数成分
        index_sid = self.security_store.resolve_sid(index_code, source, asof)
        if index_sid is None:
            return 0

        weight_df = self.index_store.read_weight(index_sids=[index_sid])

        if weight_df.is_empty():
            return 0

        # PIT 过滤
        if asof:
            asof_date = self._normalize_date(asof)
            weight_df = weight_df.filter(pl.col("trade_date") <= asof_date)
            if not weight_df.is_empty():
                latest_date = weight_df["trade_date"].max()
                weight_df = weight_df.filter(pl.col("trade_date") == latest_date)

        if weight_df.is_empty():
            return 0

        constituents = weight_df["con_sid"].unique().to_list()
        weights = dict(zip(weight_df["con_sid"].to_list(), weight_df["weight"].to_list()))

        # 创建标的池
        if create_if_not_exists and not self.exists(universe_id):
            self.create(
                universe_id=universe_id,
                name=f"Index {index_code}",
                universe_type="index",
                source_ref=index_code,
            )

        # 设置成分
        effective_from = self._normalize_date(asof) or self._today()
        self.universe_store.batch_set_constituents(
            universe_id=universe_id,
            sids=constituents,
            effective_from=effective_from,
            weights=weights,
        )

        return len(constituents)

    # ============ 历史查询 ============

    def get_history(
        self,
        universe_id: str,
        sid: int | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """
        获取成分变更历史

        Args:
            universe_id: 标的池 ID
            sid: 筛选特定 SID
            start_date/end_date: 日期范围

        Returns:
            pl.DataFrame: 变更历史
        """
        return self.universe_store.get_history(
            universe_id=universe_id,
            sid=sid,
            start_date=self._normalize_date(start_date),
            end_date=self._normalize_date(end_date),
        )

    # ============ 辅助方法 ============

    def _normalize_date(self, date_str: str | None) -> str | None:
        """标准化日期"""
        if not date_str:
            return None
        date_str = str(date_str).replace("-", "")
        if len(date_str) == 8:
            return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
        return date_str

    def _today(self) -> str:
        """获取今天日期"""
        return date.today().isoformat()
```

---

## 十、Store 层实现

### 10.1 SecurityStore（含 PIT）

```python
# src/ditto_data_hub/stores/security_store.py
from __future__ import annotations
from typing import Optional, List, Dict
import polars as pl

from .sqlite_client import SQLiteClient


class SecurityStore:
    """
    证券主数据存储（支持 PIT 标识符解析）

    核心功能：
    - resolve_sid: (source, src_code, asof) → sid
    - 通过 security_mapping 的 effective_from/to 实现历史解析
    """

    def __init__(self, sqlite_client: SQLiteClient):
        self.sqlite_client = sqlite_client

    @lru_cache(maxsize=10000)
    def resolve_sid_cached(self, src_code: str, source: str) -> int | None:
        """缓存当前映射（无 asof 的场景）"""
        return self._resolve_sid_from_db(src_code, source, asof=None)

    def resolve_sid(self, src_code: str, source: str, asof: str | None) -> int | None:
        if asof is None:
            return self.resolve_sid_cached(src_code, source)
        return self._resolve_sid_from_db(src_code, source, asof)

    def _resolve_sid_from_db(
        self,
        src_code: str,
        source: str = "tushare",
        asof: str | None = None,
    ) -> int | None:
        """
        解析 src_code → sid（支持 PIT）

        Args:
            src_code: 数据源代码，如 "600000.SH"
            source: 数据源标识
            asof: 时点（PIT），None 表示当前
        """
        if asof:
            # PIT 模式：查询历史映射
            row = self.sqlite_client.fetchone("""
                SELECT sid FROM security_mapping
                WHERE source = ? AND src_code = ?
                  AND effective_from <= ?
                  AND (effective_to IS NULL OR effective_to > ?)
                ORDER BY effective_from DESC
                LIMIT 1
            """, [source, src_code, asof, asof])
        else:
            # 当前模式：只查有效映射（更快）
            row = self.sqlite_client.fetchone("""
                SELECT sid FROM security_mapping
                WHERE source = ? AND src_code = ?
                  AND effective_to IS NULL
            """, [source, src_code])

        return row["sid"] if row else None

    def resolve_sids_batch(
        self,
        src_codes: list[str],
        source: str = "tushare",
        asof: str | None = None,
    ) -> dict[str, int]:
        """批量解析"""
        result = {}
        for code in src_codes:
            sid = self.resolve_sid(code, source, asof)
            if sid:
                result[code] = sid
        return result

    def resolve_by_symbol(
        self,
        symbol: str,
        source: str = "tushare",
    ) -> list[int]:
        """通过 symbol 查询 sids（可能多解）"""
        rows = self.sqlite_client.fetchall("""
            SELECT DISTINCT s.sid
            FROM security s
            JOIN security_mapping m ON s.sid = m.sid
            WHERE s.symbol = ? AND m.source = ? AND m.effective_to IS NULL
        """, [symbol, source])
        return [r["sid"] for r in rows]

    def get_src_code(
        self,
        sid: int,
        source: str = "tushare",
        asof: str | None = None,
    ) -> str | None:
        """反向查询：sid → src_code"""
        if asof:
            row = self.sqlite_client.fetchone("""
                SELECT src_code FROM security_mapping
                WHERE sid = ? AND source = ?
                  AND effective_from <= ?
                  AND (effective_to IS NULL OR effective_to > ?)
                ORDER BY effective_from DESC
                LIMIT 1
            """, [sid, source, asof, asof])
        else:
            row = self.sqlite_client.fetchone("""
                SELECT src_code FROM security_mapping
                WHERE sid = ? AND source = ?
                  AND effective_to IS NULL
            """, [sid, source])

        return row["src_code"] if row else None

    def get_by_sid(self, sid: int) -> dict | None:
        """获取单只证券信息"""
        row = self.sqlite_client.fetchone("SELECT * FROM security WHERE sid = ?", [sid])
        return dict(row) if row else None

    def find_securities(
        self,
        sids: list[int] | None = None,
        src_codes: list[str] | None = None,
        source: str = "tushare",
        asset_class: str | None = None,
        exchange: str | None = None,
        is_active: bool | None = True,
        asof: str | None = None,
    ) -> pl.DataFrame:
        """查询证券列表"""
        sql = """
            SELECT s.*, m.source, m.src_code
            FROM security s
            LEFT JOIN security_mapping m ON s.sid = m.sid
            WHERE 1=1
        """
        params = []

        if sids:
            placeholders = ",".join("?" * len(sids))
            sql += f" AND s.sid IN ({placeholders})"
            params.extend(sids)

        if src_codes:
            placeholders = ",".join("?" * len(src_codes))
            sql += f" AND m.src_code IN ({placeholders}) AND m.source = ?"
            params.extend(src_codes)
            params.append(source)

            if asof:
                sql += " AND m.effective_from <= ? AND (m.effective_to IS NULL OR m.effective_to > ?)"
                params.extend([asof, asof])
            else:
                sql += " AND m.effective_to IS NULL"

        if asset_class:
            sql += " AND s.asset_class = ?"
            params.append(asset_class)

        if exchange:
            sql += " AND s.exchange = ?"
            params.append(exchange)

        if is_active is not None:
            sql += " AND s.is_active = ?"
            params.append(is_active)

        rows = self.sqlite_client.fetchall(sql, params)

        if not rows:
            return pl.DataFrame()

        return pl.DataFrame([dict(r) for r in rows])

    def list_sids(
        self,
        asset_class: str | None = None,
        exchange: str | None = None,
        is_active: bool = True,
    ) -> list[int]:
        """列出所有 sid"""
        sql = "SELECT sid FROM security WHERE 1=1"
        params = []

        if asset_class:
            sql += " AND asset_class = ?"
            params.append(asset_class)

        if exchange:
            sql += " AND exchange = ?"
            params.append(exchange)

        if is_active is not None:
            sql += " AND is_active = ?"
            params.append(is_active)

        rows = self.sqlite_client.fetchall(sql, params)
        return [r["sid"] for r in rows]

    def get_symbol(self, sid: int) -> str | None:
        """获取 symbol"""
        row = self.sqlite_client.fetchone("SELECT symbol FROM security WHERE sid = ?", [sid])
        return row["symbol"] if row else None

    def get_sid_symbol_map(self, sids: list[int] | None = None) -> dict[int, str]:
        """批量获取 sid → symbol 映射"""
        if sids:
            placeholders = ",".join("?" * len(sids))
            rows = self.sqlite_client.fetchall(
                f"SELECT sid, symbol FROM security WHERE sid IN ({placeholders})",
                sids
            )
        else:
            rows = self.sqlite_client.fetchall(
                "SELECT sid, symbol FROM security WHERE is_active = TRUE"
            )

        return {r["sid"]: r["symbol"] for r in rows}

    def enrich_with_symbol(self, df: pl.DataFrame) -> pl.DataFrame:
        """为 DataFrame 添加 symbol 列"""
        if "sid" not in df.columns or df.is_empty():
            return df

        sids = df["sid"].unique().to_list()
        symbol_map = self.get_sid_symbol_map(sids)

        symbol_df = pl.DataFrame({
            "sid": list(symbol_map.keys()),
            "symbol": list(symbol_map.values()),
        })

        return df.join(symbol_df, on="sid", how="left")

    def register(
        self,
        sid: int,
        source: str,
        src_code: str,
        symbol: str,
        name: str,
        exchange: str,
        asset_class: str,
        list_date: str,
        board: str | None = None,
    ) -> int:
        """注册新证券"""

        try:
            # 插入 security 表
            self.sqlite_client.execute("""
                INSERT INTO security
                (sid, symbol, name, exchange, board, asset_class, list_date, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?, TRUE)
            """, [sid, symbol, name, exchange, board, asset_class, list_date])

            # 插入 mapping 表
            self.sqlite_client.execute("""
                INSERT INTO security_mapping
                (sid, source, src_code, effective_from, is_primary)
                VALUES (?, ?, ?, ?, TRUE)
            """, [sid, source, src_code, list_date])

            self.sqlite_client.commit()
            return sid

        except Exception:
            self.sqlite_client.rollback()
            raise


    def register_batch(self, securities: list[dict]) -> list[int]:
        """批量注册证券"""
        # 1. 批量分配 SID
        sids = [self.sid_allocator.allocate(s["asset_class"]) for s in securities]

        # 2. 批量插入 security 表
        security_params = [
            (sids[i], s["symbol"], s["name"], s["exchange"],
             s["asset_class"], s["list_date"])
            for i, s in enumerate(securities)
        ]
        self.db.executemany("""
            INSERT INTO security (sid, symbol, name, exchange, asset_class, list_date)
            VALUES (?, ?, ?, ?, ?, ?)
        """, security_params)

        # 3. 批量插入 security_mapping 表
        mapping_params = [
            (sids[i], s["source"], s["src_code"], s["list_date"])
            for i, s in enumerate(securities)
        ]
        self.db.executemany("""
            INSERT INTO security_mapping (sid, source, src_code, effective_from)
            VALUES (?, ?, ?, ?)
        """, mapping_params)

        self.db.commit()
        return sids

    def register_code_change(
        self,
        sid: int,
        source: str,
        old_code: str,
        new_code: str | None,
        change_date: str,
    ) -> None:
        """
        注册代码变更

        示例：深赤湾A (000022.SZ) 被吸收合并
        register_code_change(
            sid=12345,
            source="tushare",
            old_code="000022.SZ",
            new_code=None,  # 代码消失
            change_date="2018-12-25"
        )
        """
        try
            # 关闭旧映射
            self.sqlite_client.execute("""
                UPDATE security_mapping
                SET effective_to = ?
                WHERE sid = ? AND source = ? AND src_code = ? AND effective_to IS NULL
            """, [change_date, sid, source, old_code])

            # 如果有新代码，创建新映射
            if new_code:
                self.sqlite_client.execute("""
                    INSERT INTO security_mapping
                    (sid, source, src_code, effective_from, is_primary)
                    VALUES (?, ?, ?, ?, TRUE)
                """, [sid, source, new_code, change_date])

            self.sqlite_client.commit()

        except Exception:
            self.sqlite_client.rollback()
            raise

```

### 10.2 CalendarStore

```python
"""
交易日历存储（内存缓存优化版）

核心优化：
- 启动时全量加载到内存（~7500 条，约 1MB）
- 所有查询操作 O(1) 或 O(log n)
- 无 SQL 查询开销
"""

from __future__ import annotations
from typing import Literal
from dataclasses import dataclass
import bisect
import polars as pl

from .sqlite_client import SQLiteClient
from ..errors import TradingDateNotFoundError


@dataclass(frozen=True)
class CalendarDay:
    """单个交易日数据"""
    trade_date: str
    is_open: bool
    prev_trade_date: str | None
    next_trade_date: str | None
    week_of_year: int | None
    month: int | None
    quarter: int | None
    year: int | None
    is_week_end: bool
    is_month_end: bool
    is_quarter_end: bool


class CalendarStore(BaseSQLiteStore):
    """
    交易日历存储

    优化策略：
    - 启动时加载全部日历数据到内存
    - 维护有序交易日列表，支持 O(log n) 二分查找
    - 所有读操作无 SQL 开销

    使用示例：
        store = CalendarStore(pool)

        # O(1) 查询
        store.is_trading_day("2024-01-02")  # True

        # O(log n) 偏移
        store.offset("2024-01-02", 5)  # "2024-01-09"
        store.offset("2024-01-02", -1)  # "2023-12-29"
    """

    def __init__(self, sqlite_client: SQLiteClient):
        self.sqlite_client = sqlite_client
        # 内存缓存
        self._cache: dict[str, CalendarDay] = {}       # date_str -> CalendarDay
        self._trading_days: list[str] = []             # 有序交易日列表
        self._all_days: list[str] = []                 # 有序全部日期列表

        # 周期末缓存
        self._week_ends: list[str] = []
        self._month_ends: list[str] = []
        self._quarter_ends: list[str] = []

        # 初始化缓存
        self._load_cache()

    def _load_cache(self):
        """加载全部日历数据到内存"""
        rows = self.sqlite_client.fetchall("""
            SELECT trade_date, is_open, prev_trade_date, next_trade_date,
                   week_of_year, month, quarter, year,
                   is_week_end, is_month_end, is_quarter_end
            FROM trading_calendar
            ORDER BY trade_date
        """)

        for r in rows:
            date_str = str(r["trade_date"])

            day = CalendarDay(
                trade_date=date_str,
                is_open=bool(r["is_open"]),
                prev_trade_date=str(r["prev_trade_date"]) if r["prev_trade_date"] else None,
                next_trade_date=str(r["next_trade_date"]) if r["next_trade_date"] else None,
                week_of_year=r["week_of_year"],
                month=r["month"],
                quarter=r["quarter"],
                year=r["year"],
                is_week_end=bool(r["is_week_end"]),
                is_month_end=bool(r["is_month_end"]),
                is_quarter_end=bool(r["is_quarter_end"]),
            )

            self._cache[date_str] = day
            self._all_days.append(date_str)

            if day.is_open:
                self._trading_days.append(date_str)

                if day.is_week_end:
                    self._week_ends.append(date_str)
                if day.is_month_end:
                    self._month_ends.append(date_str)
                if day.is_quarter_end:
                    self._quarter_ends.append(date_str)

    def reload(self):
        """重新加载缓存（日历更新后调用）"""
        self._cache.clear()
        self._trading_days.clear()
        self._all_days.clear()
        self._week_ends.clear()
        self._month_ends.clear()
        self._quarter_ends.clear()
        self._load_cache()

    # ============ 基础查询（O(1)）============

    def is_trading_day(self, date: str) -> bool:
        """判断是否交易日"""
        day = self._cache.get(date)
        return day.is_open if day else False

    def get(self, date: str) -> CalendarDay | None:
        """获取单日日历数据"""
        return self._cache.get(date)

    def get_prev(self, date: str) -> str | None:
        """获取前一交易日（O(1)）"""
        day = self._cache.get(date)
        if day:
            return day.prev_trade_date
        return None

    def get_next(self, date: str) -> str | None:
        """获取后一交易日（O(1)）"""
        day = self._cache.get(date)
        if day:
            return day.next_trade_date
        return None

    # ============ 偏移查询（O(log n)）============

    def offset(self, date: str, n: int) -> str | None:
        """
        偏移 n 个交易日

        Args:
            date: 起始日期
            n: 偏移量（正数向后，负数向前）

        Returns:
            目标交易日，超出范围返回 None

        示例：
            offset("2024-01-02", 0)   # "2024-01-02"（如果是交易日）
            offset("2024-01-02", 1)   # 下一个交易日
            offset("2024-01-02", -1)  # 上一个交易日
            offset("2024-01-02", 250) # 约一年后
        """
        if not self._trading_days:
            return None

        # 找到日期在交易日列表中的位置
        idx = bisect.bisect_left(self._trading_days, date)

        if n == 0:
            # 返回当日（如果是交易日）或 None
            if idx < len(self._trading_days) and self._trading_days[idx] == date:
                return date
            return None

        if n > 0:
            # 向后偏移
            # 如果 date 本身是交易日，idx 指向它，需要从 idx 开始算
            # 如果 date 不是交易日，idx 指向下一个交易日
            if idx < len(self._trading_days) and self._trading_days[idx] == date:
                target_idx = idx + n
            else:
                target_idx = idx + n - 1  # 下一个交易日算第 1 个
        else:
            # 向前偏移
            if idx < len(self._trading_days) and self._trading_days[idx] == date:
                target_idx = idx + n  # n 是负数
            else:
                target_idx = idx + n  # idx 已经是"下一个"，所以直接加

        if 0 <= target_idx < len(self._trading_days):
            return self._trading_days[target_idx]
        return None

    def offset_safe(self, date: str, n: int) -> str:
        """
        偏移 n 个交易日（安全版本，超出范围抛异常）
        """
        result = self.offset(date, n)
        if result is None:
            raise TradingDateNotFoundError(
                f"Cannot offset {n} trading days from {date}",
                date=date,
                direction="next" if n > 0 else "prev",
            )
        return result

    # ============ 范围查询（O(log n)）============

    def get_range(self, start: str, end: str) -> list[str]:
        """获取日期范围内的交易日列表"""
        if not self._trading_days:
            return []

        start_idx = bisect.bisect_left(self._trading_days, start)
        end_idx = bisect.bisect_right(self._trading_days, end)

        return self._trading_days[start_idx:end_idx]

    def get_range_df(
        self,
        start: str,
        end: str,
        only_open: bool = True,
    ) -> pl.DataFrame:
        """获取日期范围的日历 DataFrame"""
        dates = self.get_range(start, end) if only_open else self._get_all_range(start, end)

        if not dates:
            return pl.DataFrame()

        records = []
        for date in dates:
            day = self._cache.get(date)
            if day:
                records.append({
                    "trade_date": day.trade_date,
                    "is_open": day.is_open,
                    "prev_trade_date": day.prev_trade_date,
                    "next_trade_date": day.next_trade_date,
                    "is_week_end": day.is_week_end,
                    "is_month_end": day.is_month_end,
                    "is_quarter_end": day.is_quarter_end,
                })

        return pl.DataFrame(records)

    def _get_all_range(self, start: str, end: str) -> list[str]:
        """获取日期范围内的所有日期（含非交易日）"""
        if not self._all_days:
            return []

        start_idx = bisect.bisect_left(self._all_days, start)
        end_idx = bisect.bisect_right(self._all_days, end)

        return self._all_days[start_idx:end_idx]

    def count_trading_days(self, start: str, end: str) -> int:
        """计算交易日数量"""
        return len(self.get_range(start, end))

    # ============ 周期末查询（O(log n)）============

    def get_period_ends(
        self,
        start: str,
        end: str,
        period: Literal["week", "month", "quarter"],
    ) -> list[str]:
        """获取周期末交易日"""
        period_list = {
            "week": self._week_ends,
            "month": self._month_ends,
            "quarter": self._quarter_ends,
        }.get(period, [])

        if not period_list:
            return []

        start_idx = bisect.bisect_left(period_list, start)
        end_idx = bisect.bisect_right(period_list, end)

        return period_list[start_idx:end_idx]

    def get_month_ends(self, start: str, end: str) -> list[str]:
        """获取月末交易日"""
        return self.get_period_ends(start, end, "month")

    def get_quarter_ends(self, start: str, end: str) -> list[str]:
        """获取季末交易日"""
        return self.get_period_ends(start, end, "quarter")

    # ============ 边界查询 ============

    def get_first_trading_day(self) -> str | None:
        """获取最早交易日"""
        return self._trading_days[0] if self._trading_days else None

    def get_last_trading_day(self) -> str | None:
        """获取最新交易日"""
        return self._trading_days[-1] if self._trading_days else None

    def get_latest_before(self, date: str) -> str | None:
        """获取指定日期之前（含）的最近交易日"""
        if not self._trading_days:
            return None

        idx = bisect.bisect_right(self._trading_days, date)
        if idx > 0:
            return self._trading_days[idx - 1]
        return None

    def get_earliest_after(self, date: str) -> str | None:
        """获取指定日期之后（含）的最近交易日"""
        if not self._trading_days:
            return None

        idx = bisect.bisect_left(self._trading_days, date)
        if idx < len(self._trading_days):
            return self._trading_days[idx]
        return None

    # ============ 写入操作（同时更新缓存）============

    def upsert(self, records: list[dict]) -> int:
        """
        插入或更新日历记录

        Args:
            records: 日历记录列表

        Returns:
            影响的行数
        """
        if not records:
            return 0

        try
            count = 0
            for record in records:
                self.sqlite_client.execute("""
                    INSERT OR REPLACE INTO trading_calendar
                    (trade_date, is_open, prev_trade_date, next_trade_date,
                    week_of_year, month, quarter, year,
                    is_week_end, is_month_end, is_quarter_end)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, [
                    record["trade_date"],
                    record.get("is_open", True),
                    record.get("prev_trade_date"),
                    record.get("next_trade_date"),
                    record.get("week_of_year"),
                    record.get("month"),
                    record.get("quarter"),
                    record.get("year"),
                    record.get("is_week_end", False),
                    record.get("is_month_end", False),
                    record.get("is_quarter_end", False),
                ])
                count += 1

            self.sqlite_client.commit()

            # 重新加载缓存
            self.reload()

            return count

        except Exception:
            self.sqlite_client.rollback()
            raise

```

### 10.3 PipelineStore

```python
# src/ditto_data_hub/stores/pipeline_store.py
from __future__ import annotations
from datetime import datetime
from typing import Optional, List, Dict, Any

from .sqlite_client import SQLiteClient


class PipelineStore:
    """Pipeline 运行记录存储"""

    def __init__(self, sqlite_client: SQLiteClient):
        self.sqlite_client = sqlite_client

    def insert_run(
        self,
        run_id: str,
        task_name: str,
        dataset_id: str,
        year: Optional[int] = None,
        rows_read: Optional[int] = None,
        rows_written: Optional[int] = None,
        status: str = "running",
        error_message: Optional[str] = None,
        dq_passed: Optional[bool] = None,
        dq_fail_count: int = 0,
        dq_warn_count: int = 0,
        started_at: Optional[datetime] = None,
        finished_at: Optional[datetime] = None,
    ) -> None:
        """插入运行记录"""
        duration_sec = None
        if started_at and finished_at:
            duration_sec = (finished_at - started_at).total_seconds()

        try
            self.sqlite_client.execute("""
                INSERT INTO pipeline_run
                (run_id, task_name, dataset_id, year, rows_read, rows_written,
                status, error_message, dq_passed, dq_fail_count, dq_warn_count,
                started_at, finished_at, duration_sec)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                run_id, task_name, dataset_id, year, rows_read, rows_written,
                status, error_message, dq_passed, dq_fail_count, dq_warn_count,
                started_at.isoformat() if started_at else None,
                finished_at.isoformat() if finished_at else None,
                duration_sec,
            ])
            self.sqlite_client.commit()

        except Exception:
            self.sqlite_client.rollback()
            raise

    def insert_dq_issue(
        self,
        run_id: str,
        dataset_id: str,
        rule_name: str,
        severity: str,
        message: str,
        year: Optional[int] = None,
        sid: Optional[int] = None,
        trade_date: Optional[str] = None,
    ) -> None:
        """插入 DQ 异常"""
        self.sqlite_client.execute("""
            INSERT INTO dq_issue
            (run_id, dataset_id, year, sid, trade_date, rule_name, severity, message)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, [run_id, dataset_id, year, sid, trade_date, rule_name, severity, message])
        self.sqlite_client.commit()

    def get_run(self, run_id: str) -> dict | None:
        """获取运行记录"""
        row = self.sqlite_client.fetchone("SELECT * FROM pipeline_run WHERE run_id = ?", [run_id])
        return dict(row) if row else None

    def list_runs(
        self,
        dataset_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict]:
        """列出运行记录"""
        sql = "SELECT * FROM pipeline_run WHERE 1=1"
        params = []

        if dataset_id:
            sql += " AND dataset_id = ?"
            params.append(dataset_id)

        if status:
            sql += " AND status = ?"
            params.append(status)

        sql += " ORDER BY started_at DESC LIMIT ?"
        params.append(limit)

        rows = self.sqlite_client.fetchall(sql, params)
        return [dict(r) for r in rows]
```

### 10.4 BarsStore（年分区）

```python
# src/ditto_data_hub/stores/bars_store.py
from __future__ import annotations
from pathlib import Path
from typing import Optional, List
import polars as pl

from ..utils.io import atomic_write, file_md5


class BarsStore:
    """
    行情数据存储（年分区）

    存储结构：
        stock_daily/
            2020.parquet
            2021.parquet
            ...
        etf_daily/
            2020.parquet
            ...
    """

    def __init__(self, data_root: Path):
        self.data_root = Path(data_root)

    def _get_path(self, dataset: str, year: int) -> Path:
        """获取年分区文件路径"""
        return self.data_root / dataset / f"{year}.parquet"

    def _collect_paths(
        self,
        dataset: str,
        start_year: int,
        end_year: int,
    ) -> list[Path]:
        """收集年分区文件"""
        dataset_dir = self.data_root / dataset
        if not dataset_dir.exists():
            return []

        paths = []
        for year in range(start_year, end_year + 1):
            path = dataset_dir / f"{year}.parquet"
            if path.exists():
                paths.append(path)

        return paths

    def read(
        self,
        dataset: str,
        sids: list[int] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """读取行情数据"""
        # 确定年份范围
        start_year = int(start_date[:4]) if start_date else 1990
        end_year = int(end_date[:4]) if end_date else 2099

        paths = self._collect_paths(dataset, start_year, end_year)

        if not paths:
            return pl.DataFrame()

        # 扫描并过滤
        lf = pl.scan_parquet([str(p) for p in paths])

        if sids:
            lf = lf.filter(pl.col("sid").is_in(sids))

        if start_date:
            lf = lf.filter(pl.col("trade_date") >= start_date)

        if end_date:
            lf = lf.filter(pl.col("trade_date") <= end_date)

        return lf.unique(subset=["sid", "trade_date"]).collect()

    def write(
        self,
        dataset: str,
        df: pl.DataFrame,
        year: int,
    ) -> tuple[str, str]:
        """
        写入年分区文件

        策略：读取现有数据 → 合并去重 → 原子写入

        Returns:
            (file_path, checksum)
        """
        dataset_dir = self.data_root / dataset
        dataset_dir.mkdir(parents=True, exist_ok=True)

        file_path = self._get_path(dataset, year)

        # 合并现有数据
        if file_path.exists():
            existing = pl.read_parquet(file_path)
            combined = pl.concat([existing, df]).unique(
                subset=["sid", "trade_date"],
                keep="last"  # 新数据覆盖
            )
        else:
            combined = df

        # 排序
        combined = combined.sort(["trade_date", "sid"])

        # 原子写入
        atomic_write(combined, file_path)

        # 计算 checksum
        checksum = file_md5(file_path)

        return str(file_path), checksum

    def get_years(self, dataset: str) -> list[int]:
        """获取数据集的所有年份"""
        dataset_dir = self.data_root / dataset
        if not dataset_dir.exists():
            return []

        years = []
        for f in dataset_dir.glob("*.parquet"):
            try:
                year = int(f.stem)
                years.append(year)
            except ValueError:
                continue

        return sorted(years)

    def get_paths_for_view(self, dataset: str) -> list[str]:
        """获取用于 DuckDB View 注册的路径"""
        dataset_dir = self.data_root / dataset
        if not dataset_dir.exists():
            return []

        return [str(p) for p in sorted(dataset_dir.glob("*.parquet"))]
```

### 10.5 IndexStore（年分区）

```python
# src/ditto_data_hub/stores/index_store.py
from __future__ import annotations
from pathlib import Path
from typing import Optional, List
import polars as pl

from ..utils.io import atomic_write, file_md5


class IndexStore:
    """指数数据存储（年分区）"""

    def __init__(self, data_root: Path):
        self.data_root = Path(data_root)

    def _get_path(self, dataset: str, year: int) -> Path:
        return self.data_root / dataset / f"{year}.parquet"

    def _collect_paths(self, dataset: str, start_year: int, end_year: int) -> list[Path]:
        dataset_dir = self.data_root / dataset
        if not dataset_dir.exists():
            return []

        return [
            dataset_dir / f"{year}.parquet"
            for year in range(start_year, end_year + 1)
            if (dataset_dir / f"{year}.parquet").exists()
        ]

    def read_daily(
        self,
        sids: list[int] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """读取指数日线"""
        start_year = int(start_date[:4]) if start_date else 1990
        end_year = int(end_date[:4]) if end_date else 2099

        paths = self._collect_paths("index_daily", start_year, end_year)

        if not paths:
            return pl.DataFrame()

        lf = pl.scan_parquet([str(p) for p in paths])

        if sids:
            lf = lf.filter(pl.col("sid").is_in(sids))

        if start_date:
            lf = lf.filter(pl.col("trade_date") >= start_date)

        if end_date:
            lf = lf.filter(pl.col("trade_date") <= end_date)

        return lf.unique(subset=["sid", "trade_date"]).collect()

    def read_weight(
        self,
        index_sids: list[int] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """读取指数权重"""
        start_year = int(start_date[:4]) if start_date else 1990
        end_year = int(end_date[:4]) if end_date else 2099

        paths = self._collect_paths("index_weight", start_year, end_year)

        if not paths:
            return pl.DataFrame()

        lf = pl.scan_parquet([str(p) for p in paths])

        if index_sids:
            lf = lf.filter(pl.col("index_sid").is_in(index_sids))

        if start_date:
            lf = lf.filter(pl.col("trade_date") >= start_date)

        if end_date:
            lf = lf.filter(pl.col("trade_date") <= end_date)

        return lf.collect()

    def write_daily(self, df: pl.DataFrame, year: int) -> tuple[str, str]:
        """写入指数日线"""
        dataset_dir = self.data_root / "index_daily"
        dataset_dir.mkdir(parents=True, exist_ok=True)

        file_path = self._get_path("index_daily", year)

        if file_path.exists():
            existing = pl.read_parquet(file_path)
            combined = pl.concat([existing, df]).unique(
                subset=["sid", "trade_date"], keep="last"
            )
        else:
            combined = df

        combined = combined.sort(["trade_date", "sid"])
        atomic_write(combined, file_path)

        return str(file_path), file_md5(file_path)

    def write_weight(self, df: pl.DataFrame, year: int) -> tuple[str, str]:
        """写入指数权重"""
        dataset_dir = self.data_root / "index_weight"
        dataset_dir.mkdir(parents=True, exist_ok=True)

        file_path = self._get_path("index_weight", year)

        if file_path.exists():
            existing = pl.read_parquet(file_path)
            combined = pl.concat([existing, df]).unique(
                subset=["index_sid", "con_sid", "trade_date"], keep="last"
            )
        else:
            combined = df

        combined = combined.sort(["trade_date", "index_sid", "con_sid"])
        atomic_write(combined, file_path)

        return str(file_path), file_md5(file_path)

    def get_paths_for_view(self, dataset: str) -> list[str]:
        """获取用于 DuckDB View 的路径"""
        dataset_dir = self.data_root / dataset
        if not dataset_dir.exists():
            return []

        return [str(p) for p in sorted(dataset_dir.glob("*.parquet"))]
```

### 10.6 AdjFactorStore（年分区）

```python
# src/ditto_data_hub/stores/adj_factor_store.py
from __future__ import annotations
from pathlib import Path
from typing import Optional, List
import polars as pl

from ..utils.io import atomic_write, file_md5


class AdjFactorStore:
    """复权因子存储（年分区）"""

    def __init__(self, data_root: Path):
        self.data_root = Path(data_root)
        self.dataset_dir = data_root / "adj_factor"

    def _get_path(self, year: int) -> Path:
        return self.dataset_dir / f"{year}.parquet"

    def read(
        self,
        sids: list[int],
        start_date: str,
        end_date: str,
    ) -> pl.DataFrame:
        """读取复权因子"""
        start_year = int(start_date[:4])
        end_year = int(end_date[:4])

        paths = [
            self._get_path(year)
            for year in range(start_year, end_year + 1)
            if self._get_path(year).exists()
        ]

        if not paths:
            return pl.DataFrame()

        lf = pl.scan_parquet([str(p) for p in paths])
        lf = lf.filter(pl.col("sid").is_in(sids))
        lf = lf.filter(pl.col("trade_date") >= start_date)
        lf = lf.filter(pl.col("trade_date") <= end_date)
        lf = lf.select(["sid", "trade_date", "adj_factor"])

        return lf.unique(subset=["sid", "trade_date"]).collect()

    def get_latest_factor(
        self,
        sids: list[int],
        asof: str | None = None,
    ) -> pl.DataFrame:
        """获取最新复权因子"""
        end_date = asof or "2099-12-31"

        paths = [str(p) for p in sorted(self.dataset_dir.glob("*.parquet"))]

        if not paths:
            return pl.DataFrame()

        lf = pl.scan_parquet(paths)
        lf = lf.filter(pl.col("sid").is_in(sids))

        if asof:
            lf = lf.filter(pl.col("trade_date") <= asof)

        df = lf.collect()

        return df.sort(["sid", "trade_date"]).group_by("sid").agg(
            pl.col("adj_factor").last().alias("adj_factor"),
            pl.col("trade_date").last().alias("trade_date"),
        )

    def write(self, df: pl.DataFrame, year: int) -> tuple[str, str]:
        """写入复权因子"""
        self.dataset_dir.mkdir(parents=True, exist_ok=True)

        file_path = self._get_path(year)

        if file_path.exists():
            existing = pl.read_parquet(file_path)
            combined = pl.concat([existing, df]).unique(
                subset=["sid", "trade_date"], keep="last"
            )
        else:
            combined = df

        combined = combined.sort(["trade_date", "sid"])
        atomic_write(combined, file_path)

        return str(file_path), file_md5(file_path)

    def get_paths_for_view(self) -> list[str]:
        """获取用于 DuckDB View 的路径"""
        if not self.dataset_dir.exists():
            return []

        return [str(p) for p in sorted(self.dataset_dir.glob("*.parquet"))]
```

### 10.7 UniverseStore

``` python
# src/ditto_data_hub/stores/universe_store.py
from __future__ import annotations
from datetime import datetime
from typing import Literal
import polars as pl

from .sqlite_client import SQLiteClient


class UniverseStore:
    """
    标的池存储（支持 PIT）

    核心概念：
    - universe_id: 标的池唯一标识（如 "hs300", "my_stock_pool"）
    - constituent: 成分股，通过 effective_from/to 支持历史查询

    PIT 语义：
    - 查询 asof="2024-06-30" 时，返回在该日期有效的成分
    - effective_from <= asof AND (effective_to IS NULL OR effective_to > asof)
    """

    def __init__(self, sqlite_client: SQLiteClient):
        self.sqlite_client = sqlite_client

    # ============ Universe CRUD ============

    def create_universe(
        self,
        universe_id: str,
        name: str,
        universe_type: Literal["custom", "index", "sector"] = "custom",
        description: str | None = None,
        source_ref: str | None = None,
    ) -> None:
        """创建标的池"""
        self.sqlite_client.execute("""
            INSERT INTO universe (universe_id, name, universe_type, description, source_ref)
            VALUES (?, ?, ?, ?, ?)
        """, [universe_id, name, universe_type, description, source_ref])
        self.sqlite_client.commit()

    def get_universe(self, universe_id: str) -> dict | None:
        """获取标的池信息"""
        row = self.sqlite_client.fetchone(
            "SELECT * FROM universe WHERE universe_id = ?",
            [universe_id]
        )
        return dict(row) if row else None

    def list_universes(
        self,
        universe_type: str | None = None,
    ) -> list[dict]:
        """列出所有标的池"""
        sql = "SELECT * FROM universe WHERE 1=1"
        params = []

        if universe_type:
            sql += " AND universe_type = ?"
            params.append(universe_type)

        sql += " ORDER BY universe_id"
        rows = self.sqlite_client.fetchall(sql, params)
        return [dict(r) for r in rows]

    def delete_universe(self, universe_id: str) -> bool:
        try
            """删除标的池（同时删除所有成分）"""
            self.sqlite_client.execute(
                "DELETE FROM universe_constituent WHERE universe_id = ?",
                [universe_id]
            )
            cursor = self.sqlite_client.execute(
                "DELETE FROM universe WHERE universe_id = ?",
                [universe_id]
            )
            self.sqlite_client.commit()
            return cursor.rowcount > 0
        except Exception:
            self.sqlite_client.rollback()
            raise

    # ============ Constituent 查询 ============

    def get_constituents(
        self,
        universe_id: str,
        asof: str | None = None,
    ) -> list[int]:
        """
        获取成分股 sid 列表（支持 PIT）

        Args:
            universe_id: 标的池 ID
            asof: 时点，None 表示当前

        Returns:
            成分股 sid 列表
        """
        if asof:
            rows = self.sqlite_client.fetchall("""
                SELECT sid FROM universe_constituent
                WHERE universe_id = ?
                  AND effective_from <= ?
                  AND (effective_to IS NULL OR effective_to > ?)
                ORDER BY sid
            """, [universe_id, asof, asof])
        else:
            rows = self.sqlite_client.fetchall("""
                SELECT sid FROM universe_constituent
                WHERE universe_id = ?
                  AND effective_to IS NULL
                ORDER BY sid
            """, [universe_id])

        return [r["sid"] for r in rows]

    def get_constituents_with_weight(
        self,
        universe_id: str,
        asof: str | None = None,
    ) -> pl.DataFrame:
        """获取成分股及权重"""
        if asof:
            rows = self.sqlite_client.fetchall("""
                SELECT sid, weight, effective_from, source, src_code
                FROM universe_constituent
                WHERE universe_id = ?
                  AND effective_from <= ?
                  AND (effective_to IS NULL OR effective_to > ?)
                ORDER BY weight DESC
            """, [universe_id, asof, asof])
        else:
            rows = self.sqlite_client.fetchall("""
                SELECT sid, weight, effective_from, source, src_code
                FROM universe_constituent
                WHERE universe_id = ?
                  AND effective_to IS NULL
                ORDER BY weight DESC
            """, [universe_id])

        if not rows:
            return pl.DataFrame()

        return pl.DataFrame([dict(r) for r in rows])

    def is_constituent(
        self,
        universe_id: str,
        sid: int,
        asof: str | None = None,
    ) -> bool:
        """判断是否为成分股"""
        if asof:
            row = self.sqlite_client.fetchone("""
                SELECT 1 FROM universe_constituent
                WHERE universe_id = ? AND sid = ?
                  AND effective_from <= ?
                  AND (effective_to IS NULL OR effective_to > ?)
            """, [universe_id, sid, asof, asof])
        else:
            row = self.sqlite_client.fetchone("""
                SELECT 1 FROM universe_constituent
                WHERE universe_id = ? AND sid = ?
                  AND effective_to IS NULL
            """, [universe_id, sid])

        return row is not None

    # ============ Constituent 写入 ============

    def add_constituent(
        self,
        universe_id: str,
        sid: int,
        effective_from: str,
        weight: float = 1.0,
        source: str | None = None,
        src_code: str | None = None,
    ) -> None:
        """
        添加成分股

        如果该成分股已存在有效记录，会先关闭前一条记录
        """
        try
            # 1. 关闭已有的有效记录
            self.sqlite_client.execute("""
                UPDATE universe_constituent
                SET effective_to = ?
                WHERE universe_id = ? AND sid = ? AND effective_to IS NULL
            """, [effective_from, universe_id, sid])

            # 2. 插入新记录
            self.sqlite_client.execute("""
                INSERT INTO universe_constituent
                (universe_id, sid, effective_from, weight, source, src_code)
                VALUES (?, ?, ?, ?, ?, ?)
            """, [universe_id, sid, effective_from, weight, source, src_code])

            self.sqlite_client.commit()

        except Exception:
            self.sqlite_client.rollback()
            raise

    def remove_constituent(
        self,
        universe_id: str,
        sid: int,
        effective_date: str,
    ) -> bool:
        """
        移除成分股（关闭有效记录）

        Args:
            universe_id: 标的池 ID
            sid: 成分股 ID
            effective_date: 生效日期（该日起不再是成分）

        Returns:
            是否有记录被更新
        """
        cursor = self.sqlite_client.execute("""
            UPDATE universe_constituent
            SET effective_to = ?
            WHERE universe_id = ? AND sid = ? AND effective_to IS NULL
        """, [effective_date, universe_id, sid])
        self.sqlite_client.commit()
        return cursor.rowcount > 0

    def update_weight(
        self,
        universe_id: str,
        sid: int,
        weight: float,
        effective_from: str,
    ) -> None:
        """
        更新成分股权重

        实现方式：关闭旧记录 + 创建新记录（保留历史）
        """
        # 获取当前记录信息
        row = self.sqlite_client.fetchone("""
            SELECT source, src_code FROM universe_constituent
            WHERE universe_id = ? AND sid = ? AND effective_to IS NULL
        """, [universe_id, sid])

        if row:
            self.add_constituent(
                universe_id=universe_id,
                sid=sid,
                effective_from=effective_from,
                weight=weight,
                source=row["source"],
                src_code=row["src_code"],
            )

    def batch_set_constituents(
        self,
        universe_id: str,
        sids: list[int],
        effective_from: str,
        weights: dict[int, float] | None = None,
    ) -> None:
        """
        批量设置成分股（全量替换）

        关闭所有不在新列表中的成分，添加新成分
        """
        weights = weights or {}
        new_sids = set(sids)

        # 1. 获取当前成分
        current = self.get_constituents(universe_id)
        current_sids = set(current)

        # 2. 移除不再是成分的
        for sid in current_sids - new_sids:
            self.remove_constituent(universe_id, sid, effective_from)

        # 3. 添加新成分
        for sid in new_sids - current_sids:
            self.add_constituent(
                universe_id=universe_id,
                sid=sid,
                effective_from=effective_from,
                weight=weights.get(sid, 1.0),
            )

        # 4. 更新权重变化的（可选）
        for sid in new_sids & current_sids:
            if sid in weights:
                self.update_weight(universe_id, sid, weights[sid], effective_from)

    # ============ 历史查询 ============

    def get_history(
        self,
        universe_id: str,
        sid: int | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """获取成分变更历史"""
        sql = """
            SELECT sid, effective_from, effective_to, weight, source, src_code
            FROM universe_constituent
            WHERE universe_id = ?
        """
        params = [universe_id]

        if sid:
            sql += " AND sid = ?"
            params.append(sid)

        if start_date:
            sql += " AND (effective_to IS NULL OR effective_to >= ?)"
            params.append(start_date)

        if end_date:
            sql += " AND effective_from <= ?"
            params.append(end_date)

        sql += " ORDER BY effective_from, sid"

        rows = self.sqlite_client.fetchall(sql, params)

        if not rows:
            return pl.DataFrame()

        return pl.DataFrame([dict(r) for r in rows])
```

### 10.8 SQLiteClient

```python
# src/ditto_data_hub/stores/splite_client.py
"""
SQLite 客户端（组合模式）
Store 类通过组合 SQLiteClient 来访问数据库。

使用示例：
    client = SQLiteClient(pool)

    # 查询
    row = client.fetchone("SELECT * FROM security WHERE sid = ?", [10001])
    rows = client.fetchall("SELECT * FROM security WHERE is_active = ?", [True])

    # 写入
    client.execute("INSERT INTO security (...) VALUES (...)", [...])
    client.commit()
"""

from __future__ import annotations
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .sqlite_pool import SQLitePool


class SQLiteClient:
    """
    SQLite 数据库客户端

    提供对 SQLite 的基本操作封装，
    Store 类通过组合此类来访问数据库。
    """

    def __init__(self, pool: "SQLitePool"):
        """
        初始化客户端

        Args:
            pool: SQLite 连接池
        """
        self._pool = pool

    @property
    def conn(self):
        """获取当前线程的数据库连接"""
        return self._pool.get_connection()

    def execute(self, sql: str, params: list | tuple | None = None) -> Any:
        """
        执行 SQL 语句

        Args:
            sql: SQL 语句
            params: 参数列表

        Returns:
            Cursor 对象
        """
        if params:
            return self.conn.execute(sql, params)
        return self.conn.execute(sql)

    def executemany(self, sql: str, params_list: list[list | tuple]) -> Any:
        """
        批量执行 SQL

        Args:
            sql: SQL 语句（带占位符）
            params_list: 参数列表的列表

        Returns:
            Cursor 对象
        """
        return self.conn.executemany(sql, params_list)

    def executescript(self, script: str) -> Any:
        """
        执行 SQL 脚本（多条语句）

        Args:
            script: SQL 脚本

        Returns:
            Cursor 对象
        """
        return self.conn.executescript(script)

    def fetchone(self, sql: str, params: list | tuple | None = None) -> Any:
        """
        查询单条记录

        Args:
            sql: SQL 语句
            params: 参数列表

        Returns:
            sqlite3.Row 或 None
        """
        cursor = self.execute(sql, params)
        return cursor.fetchone()

    def fetchall(self, sql: str, params: list | tuple | None = None) -> list:
        """
        查询所有记录

        Args:
            sql: SQL 语句
            params: 参数列表

        Returns:
            sqlite3.Row 列表
        """
        cursor = self.execute(sql, params)
        return cursor.fetchall()

    def fetchval(self, sql: str, params: list | tuple | None = None) -> Any:
        """
        查询单个值

        Args:
            sql: SQL 语句
            params: 参数列表

        Returns:
            第一行第一列的值，或 None
        """
        row = self.fetchone(sql, params)
        if row:
            return row[0]
        return None

    def commit(self):
        """提交事务"""
        self.conn.commit()

    def rollback(self):
        """回滚事务"""
        self.conn.rollback()

    def insert_returning_id(self, sql: str, params: list | tuple | None = None) -> int:
        """
        插入并返回自增 ID

        Args:
            sql: INSERT 语句
            params: 参数列表

        Returns:
            lastrowid
        """
        cursor = self.execute(sql, params)
        self.commit()
        return cursor.lastrowid

    def exists(self, sql: str, params: list | tuple | None = None) -> bool:
        """
        检查记录是否存在

        Args:
            sql: SELECT 语句
            params: 参数列表

        Returns:
            True 如果存在记录
        """
        return self.fetchone(sql, params) is not None

    def count(self, table: str, where: str | None = None, params: list | tuple | None = None) -> int:
        """
        计算记录数

        Args:
            table: 表名
            where: WHERE 子句（不含 WHERE 关键字）
            params: 参数列表

        Returns:
            记录数
        """
        sql = f"SELECT COUNT(*) FROM {table}"
        if where:
            sql += f" WHERE {where}"

        return self.fetchval(sql, params) or 0
```

---

## 十一、Runtime 层实现

### 11.1 SqlEngine（DuckDB View + 复权宏）

```python
# src/ditto_data_hub/runtime/sql_engine.py

from __future__ import annotations
from pathlib import Path
from typing import TYPE_CHECKING
import duckdb
import polars as pl

if TYPE_CHECKING:
    from ..stores.security_store import SecurityStore
    from ..stores.calendar_store import CalendarStore


class SqlEngine:
    """
    DuckDB SQL 引擎

    支持：
    - Parquet 数据 (stock_daily, index_daily, etc.)
    - SQLite 元数据 (security, calendar, etc.) - 按需 ATTACH
    - 复权宏 (qfq, market_hfq)

    使用示例：
        # 1. 纯 Parquet 查询
        hub.sql("SELECT * FROM stock_daily WHERE sid = 10001")

        # 2. 跨库 JOIN（自动 ATTACH SQLite）
        hub.sql('''
            SELECT m.*, s.symbol, s.name
            FROM stock_daily m
            JOIN security s ON m.sid = s.sid
            WHERE m.trade_date = '2024-01-02'
        ''')

        # 3. 前复权 + 证券信息
        hub.sql('''
            SELECT q.*, s.symbol
            FROM qfq($asof) q
            JOIN security s ON q.sid = s.sid
            WHERE s.asset_class = 'stock'
        ''', asof="2024-06-30")
    """

    # SQLite 表名集合，用于自动检测是否需要 ATTACH
    SQLITE_TABLES = frozenset([
        "security", "security_mapping", "trading_calendar",
        "universe", "universe_constituent",
        "pipeline_run", "dq_issue"
    ])

    def __init__(
        self,
        data_root: Path,
        security_store: SecurityStore,
        calendar_store: CalendarStore,
    ):
        self.data_root = Path(data_root)
        self.security_store = security_store
        self.calendar_store = calendar_store

        self.con = duckdb.connect(":memory:")
        self._sqlite_attached = False
        self._setup()

    def _setup(self):
        """初始化配置"""
        self.con.execute("SET enable_progress_bar = false")
        self._register_views()
        self._register_macros()

    def _register_views(self):
        """注册 Parquet 数据为 DuckDB View"""
        datasets = [
            "stock_daily",
            "etf_daily",
            "index_daily",
            "index_weight",
            "adj_factor",
        ]

        for dataset in datasets:
            dataset_dir = self.data_root / dataset
            if dataset_dir.exists():
                paths = sorted(dataset_dir.glob("*.parquet"))
                if paths:
                    self._register_parquet_view(dataset, [str(p) for p in paths])

    def _register_parquet_view(self, name: str, paths: list[str]):
        """注册单个 Parquet View"""
        if not paths:
            return

        files_sql = "[" + ", ".join(f"'{p.replace(chr(92), '/')}'" for p in paths) + "]"
        self.con.execute(f"""
            CREATE OR REPLACE VIEW {name} AS
            SELECT * FROM read_parquet({files_sql}, union_by_name=true)
        """)

    def _register_macros(self):
        """注册复权宏"""
        # HFQ View (后复权)
        self.con.execute("""
            CREATE OR REPLACE VIEW market_hfq AS
            SELECT
                m.sid, m.trade_date,
                m.open * COALESCE(f.adj_factor, 1.0) AS open,
                m.high * COALESCE(f.adj_factor, 1.0) AS high,
                m.low * COALESCE(f.adj_factor, 1.0) AS low,
                m.close * COALESCE(f.adj_factor, 1.0) AS close,
                m.volume, m.amount
            FROM stock_daily m
            LEFT JOIN adj_factor f ON m.sid = f.sid AND m.trade_date = f.trade_date
        """)

        # QFQ Macro (前复权 + PIT)
        self.con.execute("""
            CREATE OR REPLACE MACRO qfq(scan_date) AS TABLE
            WITH baseline AS (
                SELECT sid, last(adj_factor ORDER BY trade_date) as base_factor
                FROM adj_factor
                WHERE trade_date <= cast(scan_date as DATE)
                GROUP BY sid
            )
            SELECT
                m.sid, m.trade_date,
                m.open * COALESCE(f.adj_factor, 1.0) / COALESCE(b.base_factor, 1.0) AS open,
                m.high * COALESCE(f.adj_factor, 1.0) / COALESCE(b.base_factor, 1.0) AS high,
                m.low * COALESCE(f.adj_factor, 1.0) / COALESCE(b.base_factor, 1.0) AS low,
                m.close * COALESCE(f.adj_factor, 1.0) / COALESCE(b.base_factor, 1.0) AS close,
                m.volume, m.amount
            FROM stock_daily m
            LEFT JOIN adj_factor f ON m.sid = f.sid AND m.trade_date = f.trade_date
            LEFT JOIN baseline b ON m.sid = b.sid
            WHERE m.trade_date <= cast(scan_date as DATE)
        """)

        # QFQ Now (当前前复权)
        self.con.execute("""
            CREATE OR REPLACE MACRO qfq_now() AS TABLE
            SELECT * FROM qfq(current_date())
        """)

    def _attach_sqlite(self):
        """挂载 SQLite 元数据库"""
        if self._sqlite_attached:
            return

        sqlite_path = self.data_root / "meta" / "hub.sqlite"
        if not sqlite_path.exists():
            return

        # ATTACH SQLite as 'meta' schema
        path_str = str(sqlite_path).replace("\\", "/")
        self.con.execute(f"ATTACH '{path_str}' AS meta (TYPE sqlite, READ_ONLY)")

        # 创建便捷 View，用户可直接 FROM security
        for table in self.SQLITE_TABLES:
            try:
                self.con.execute(f"CREATE OR REPLACE VIEW {table} AS SELECT * FROM meta.{table}")
            except Exception:
                pass  # 表可能不存在

        self._sqlite_attached = True

    def attach_sqlite(self):
        """公开方法：显式挂载 SQLite"""
        self._attach_sqlite()

    def _needs_sqlite(self, query: str) -> bool:
        """检查 SQL 是否引用了 SQLite 表"""
        query_lower = query.lower()
        # 简单关键词匹配
        for table in self.SQLITE_TABLES:
            # 匹配 "security" 但避免匹配 "security_store" 等
            if f" {table}" in query_lower or f"from {table}" in query_lower or f"join {table}" in query_lower:
                return True
        return False

    def refresh_views(self):
        """刷新 Parquet View（数据更新后调用）"""
        self._register_views()

    def execute(
        self,
        query: str,
        asof: str | None = None,
        params: dict | None = None,
    ) -> pl.DataFrame:
        """
        执行 SQL

        如果 SQL 引用了 SQLite 表（security, calendar 等），会自动 ATTACH。
        """
        # 0. 自动检测是否需要 SQLite
        if self._needs_sqlite(query):
            self._attach_sqlite()

        # 1. 设置 $asof 变量
        if asof:
            self.con.execute(f"SET VARIABLE asof = '{asof}'")
        else:
            self.con.execute("SET VARIABLE asof = current_date()")

        # 2. 设置其他参数
        if params:
            for key, value in params.items():
                if isinstance(value, (int, float)):
                    self.con.execute(f"SET VARIABLE {key} = {value}")
                elif isinstance(value, str):
                    self.con.execute(f"SET VARIABLE {key} = '{value}'")

        # 3. 执行
        try:
            return self.con.execute(query).pl()
        except Exception as e:
            raise RuntimeError(f"SQL execution failed: {e}\nQuery: {query}") from e

    def close(self):
        """关闭连接"""
        self.con.close()
```

### 11.2 FreezeManager

```python
# src/ditto_data_hub/runtime/freeze_manager.py
from __future__ import annotations
from pathlib import Path
from datetime import datetime
import json
import hashlib

from ..types import FreezeManifest


class FreezeManager:
    """
    Freeze 冻结点管理器

    功能：
    - 创建冻结点：记录所有数据文件的 checksum
    - 验证冻结点：对比当前数据与冻结点的 checksum
    - 轻量级实现：不复制文件，只记录元数据

    使用示例：
        # 回测前创建冻结点
        freeze.create("backtest_v1", "首次回测")

        # 后续验证
        is_valid, mismatches = freeze.verify("backtest_v1")
        if not is_valid:
            print(f"数据已变更: {mismatches}")
    """

    def __init__(self, data_root: Path):
        self.data_root = Path(data_root)
        self.freeze_dir = data_root / "freezes"
        self.freeze_dir.mkdir(parents=True, exist_ok=True)

    def create(self, freeze_id: str, description: str = "") -> FreezeManifest:
        """
        创建冻结点

        Args:
            freeze_id: 冻结点 ID（唯一标识）
            description: 描述信息

        Returns:
            FreezeManifest: 冻结点清单
        """
        manifest = FreezeManifest(
            freeze_id=freeze_id,
            description=description,
            created_at=datetime.now().isoformat(),
            files={},
        )

        # 扫描所有 Parquet 文件
        for parquet_file in self.data_root.rglob("*.parquet"):
            # 排除 staging 和 quarantine
            if "staging" in str(parquet_file) or "quarantine" in str(parquet_file):
                continue

            rel_path = parquet_file.relative_to(self.data_root)
            manifest.files[str(rel_path)] = self._md5(parquet_file)

        # 保存 manifest
        manifest_path = self.freeze_dir / f"{freeze_id}.json"
        manifest_path.write_text(json.dumps({
            "freeze_id": manifest.freeze_id,
            "description": manifest.description,
            "created_at": manifest.created_at,
            "files": manifest.files,
        }, indent=2, ensure_ascii=False))

        return manifest

    def verify(self, freeze_id: str) -> tuple[bool, list[str]]:
        """
        验证冻结点

        Args:
            freeze_id: 冻结点 ID

        Returns:
            (is_valid, mismatches): 是否一致，不一致的文件列表
        """
        manifest_path = self.freeze_dir / f"{freeze_id}.json"

        if not manifest_path.exists():
            raise ValueError(f"Freeze point not found: {freeze_id}")

        manifest = json.loads(manifest_path.read_text())

        mismatches = []

        for rel_path, expected_hash in manifest["files"].items():
            file_path = self.data_root / rel_path

            if not file_path.exists():
                mismatches.append(f"{rel_path} (missing)")
                continue

            actual_hash = self._md5(file_path)
            if actual_hash != expected_hash:
                mismatches.append(f"{rel_path} (changed)")

        return len(mismatches) == 0, mismatches

    def list(self) -> list[dict]:
        """列出所有冻结点"""
        freezes = []

        for manifest_path in self.freeze_dir.glob("*.json"):
            try:
                manifest = json.loads(manifest_path.read_text())
                freezes.append({
                    "freeze_id": manifest["freeze_id"],
                    "description": manifest.get("description", ""),
                    "created_at": manifest["created_at"],
                    "file_count": len(manifest["files"]),
                })
            except Exception:
                continue

        return sorted(freezes, key=lambda x: x["created_at"], reverse=True)

    def delete(self, freeze_id: str) -> bool:
        """删除冻结点"""
        manifest_path = self.freeze_dir / f"{freeze_id}.json"

        if manifest_path.exists():
            manifest_path.unlink()
            return True

        return False

    def get(self, freeze_id: str) -> FreezeManifest | None:
        """获取冻结点详情"""
        manifest_path = self.freeze_dir / f"{freeze_id}.json"

        if not manifest_path.exists():
            return None

        data = json.loads(manifest_path.read_text())

        return FreezeManifest(
            freeze_id=data["freeze_id"],
            description=data.get("description", ""),
            created_at=data["created_at"],
            files=data["files"],
        )

    def _md5(self, path: Path) -> str:
        """计算文件 MD5"""
        h = hashlib.md5()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()
```

### 11.3 SQLitePool

```python
# src/ditto_data_hub/runtime/sqlite_pool.py
from __future__ import annotations
import sqlite3
from pathlib import Path
from threading import local


class SQLitePool:
    """SQLite 连接池"""

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self._local = local()

    def get_connection(self) -> sqlite3.Connection:
        """获取连接（线程本地）"""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(
                str(self.db_path),
                check_same_thread=False,
                timeout=30.0,
            )
            self._local.conn.row_factory = sqlite3.Row
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA synchronous=NORMAL")
            self._local.conn.execute("PRAGMA busy_timeout=5000")

        return self._local.conn

    def init_schema(self):
        """初始化表结构"""
        conn = self.get_connection()

        # 读取并执行 schema（这里内联定义）
        schema = self._get_schema()
        conn.executescript(schema)
        conn.commit()

    def _get_schema(self) -> str:
        """获取 DDL"""
        return """
        -- SID 序列
        CREATE TABLE IF NOT EXISTS sid_sequence (
            asset_class TEXT PRIMARY KEY,
            current_max INTEGER NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        INSERT OR IGNORE INTO sid_sequence VALUES ('stock', 100000000, CURRENT_TIMESTAMP);
        INSERT OR IGNORE INTO sid_sequence VALUES ('etf', 200000000, CURRENT_TIMESTAMP);
        INSERT OR IGNORE INTO sid_sequence VALUES ('index', 300000000, CURRENT_TIMESTAMP);
        INSERT OR IGNORE INTO sid_sequence VALUES ('bond', 400000000, CURRENT_TIMESTAMP);
        INSERT OR IGNORE INTO sid_sequence VALUES ('future', 500000000, CURRENT_TIMESTAMP);

        -- 证券主表
        CREATE TABLE IF NOT EXISTS security (
            sid INTEGER PRIMARY KEY,
            symbol TEXT NOT NULL,
            name TEXT,
            display_name TEXT,
            exchange TEXT NOT NULL,
            board TEXT,
            asset_class TEXT NOT NULL,
            list_date DATE NOT NULL,
            delist_date DATE,
            is_st BOOLEAN DEFAULT FALSE,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_security_symbol ON security(symbol);
        CREATE INDEX IF NOT EXISTS idx_security_asset_class ON security(asset_class);

        -- 证券映射（支持 PIT）
        CREATE TABLE IF NOT EXISTS security_mapping (
            sid INTEGER NOT NULL,
            source TEXT NOT NULL,
            src_code TEXT NOT NULL,
            effective_from DATE NOT NULL DEFAULT '1990-01-01',
            effective_to DATE,
            is_primary BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (source, src_code, effective_from),
            FOREIGN KEY (sid) REFERENCES security(sid)
        );
        CREATE INDEX IF NOT EXISTS idx_mapping_current
            ON security_mapping(source, src_code) WHERE effective_to IS NULL;
        CREATE INDEX IF NOT EXISTS idx_mapping_sid ON security_mapping(sid);

        -- 交易日历
        CREATE TABLE IF NOT EXISTS trading_calendar (
            trade_date DATE PRIMARY KEY,
            is_open BOOLEAN NOT NULL,
            prev_trade_date DATE,
            next_trade_date DATE,
            week_of_year INTEGER,
            month INTEGER,
            quarter INTEGER,
            year INTEGER,
            is_week_end BOOLEAN,
            is_month_end BOOLEAN,
            is_quarter_end BOOLEAN
        );

        -- Pipeline 运行
        CREATE TABLE IF NOT EXISTS pipeline_run (
            run_id TEXT PRIMARY KEY,
            task_name TEXT NOT NULL,
            dataset_id TEXT NOT NULL,
            year INTEGER,
            rows_read INTEGER,
            rows_written INTEGER,
            status TEXT NOT NULL,
            error_message TEXT,
            dq_passed BOOLEAN,
            dq_fail_count INTEGER DEFAULT 0,
            dq_warn_count INTEGER DEFAULT 0,
            started_at TIMESTAMP,
            finished_at TIMESTAMP,
            duration_sec REAL
        );

        -- DQ 异常
        CREATE TABLE IF NOT EXISTS dq_issue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL,
            dataset_id TEXT NOT NULL,
            year INTEGER,
            sid INTEGER,
            trade_date DATE,
            rule_name TEXT NOT NULL,
            severity TEXT NOT NULL,
            message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        -- Freeze 冻结点
        CREATE TABLE IF NOT EXISTS freeze_point (
            freeze_id TEXT PRIMARY KEY,
            description TEXT,
            manifest_path TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        -- 涨跌幅配置
        CREATE TABLE IF NOT EXISTS price_limit_config (
            config_id INTEGER PRIMARY KEY AUTOINCREMENT,
            exchange TEXT,
            board TEXT,
            is_st BOOLEAN,
            min_list_days INTEGER,
            max_list_days INTEGER,
            limit_pct REAL NOT NULL,
            priority INTEGER DEFAULT 0,
            description TEXT
        );
        INSERT OR IGNORE INTO price_limit_config
            (config_id, limit_pct, priority, description)
        VALUES
            (1, 1000, 100, '新股前5日'),
            (2, 5, 90, 'ST股'),
            (3, 30, 80, '北交所'),
            (4, 20, 70, '科创板/创业板'),
            (5, 10, 0, '默认');
        -- 标的池定义
        CREATE TABLE IF NOT EXISTS universe (
            universe_id     TEXT PRIMARY KEY,
            name            TEXT NOT NULL,
            description     TEXT,
            universe_type   TEXT NOT NULL,        -- 'custom' | 'index' | 'sector'
            source_ref      TEXT,                  -- 关联来源，如指数代码
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at      TIMESTAMP
        );

        -- 标的池成分（支持 PIT）
        CREATE TABLE IF NOT EXISTS universe_constituent (
            universe_id     TEXT NOT NULL,
            sid             INTEGER NOT NULL,
            effective_from  DATE NOT NULL,
            effective_to    DATE,                  -- NULL = 当前有效
            weight          REAL DEFAULT 1.0,
            source          TEXT,
            src_code        TEXT,
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            PRIMARY KEY (universe_id, sid, effective_from),
            FOREIGN KEY (universe_id) REFERENCES universe(universe_id),
            FOREIGN KEY (sid) REFERENCES security(sid)
        );

        -- 当前有效成分快速查询
        CREATE INDEX IF NOT EXISTS idx_constituent_current
            ON universe_constituent(universe_id, sid) WHERE effective_to IS NULL;

        -- PIT 查询优化
        CREATE INDEX IF NOT EXISTS idx_constituent_pit
            ON universe_constituent(universe_id, effective_from, effective_to);
        """

    def close(self):
        """关闭连接"""
        if hasattr(self._local, "conn") and self._local.conn:
            self._local.conn.close()
            self._local.conn = None
```

### 11.4 SidAllocator

```python
# src/ditto_data_hub/runtime/sid_allocator.py
from __future__ import annotations
from ..types import AssetSidRange


class SidAllocator:
    """SID 分配器"""

    def __init__(self, sqlite_client: SQLiteClient):
        self._sqlite_client = sqlite_client

    def allocate(self, asset_class: str) -> int:
        """分配新的 SID（原子操作）"""
        min_sid, max_sid = AssetSidRange.get_range(asset_class)

        try:
            self._sqlite_client.execute("BEGIN IMMEDIATE")

            row = self._sqlite_client.execute(
                "SELECT current_max FROM sid_sequence WHERE asset_class = ?",
                [asset_class]
            ).fetchone()

            if not row:
                self._sqlite_client.execute(
                    "INSERT INTO sid_sequence (asset_class, current_max) VALUES (?, ?)",
                    [asset_class, min_sid]
                )
                self._sqlite_client.commit()
                return min_sid

            new_sid = row["current_max"] + 1

            if new_sid > max_sid:
                raise OverflowError(f"SID exhausted for {asset_class}")

            self._sqlite_client.execute(
                "UPDATE sid_sequence SET current_max = ?, updated_at = CURRENT_TIMESTAMP WHERE asset_class = ?",
                [new_sid, asset_class]
            )

            self._sqlite_client.commit()
            return new_sid

        except Exception:
            self._sqlite_client.rollback()
            raise
```

### 11.5 FileLockManager

```python
# src/ditto_data_hub/runtime/file_lock.py

# 安装：pip install filelock
from filelock import FileLock, Timeout

class FileLockManager:
    def __init__(self, lock_dir: Path):
        self.lock_dir = Path(lock_dir)
        self.lock_dir.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def acquire(self, name: str, timeout: float = 30.0):
        lock_path = self.lock_dir / f"{name}.lock"
        lock = FileLock(lock_path, timeout=timeout)

        try:
            with lock:
                yield
        except Timeout:
            raise LockAcquisitionError(
                f"Failed to acquire lock within {timeout}s",
                lock_name=name,
                timeout_seconds=timeout,
            )
```

---

## 十二、工具函数

```python
# src/ditto_data_hub/utils/io.py
from __future__ import annotations
import os
import time
import hashlib
from pathlib import Path
import polars as pl


def file_md5(path: Path, chunk_size: int = 8192) -> str:
    """计算文件 MD5"""
    md5 = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            md5.update(chunk)
    return md5.hexdigest()


def atomic_write(
    df: pl.DataFrame,
    path: Path,
    compression: str = "zstd",
    compression_level: int = 3,
    retries: int = 5,
    backoff_ms: int = 100,
) -> None:
    """
    原子写入 Parquet 文件

    策略：写入临时文件 → 原子替换
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    tmp_path = path.with_suffix(".tmp")

    # 写入临时文件
    df.write_parquet(
        tmp_path,
        compression=compression,
        compression_level=compression_level,
    )

    # 原子替换（带重试）
    last_exc = None
    for i in range(retries):
        try:
            os.replace(str(tmp_path), str(path))
            return
        except Exception as e:
            last_exc = e
            time.sleep((backoff_ms * (2 ** i)) / 1000.0)

    raise RuntimeError(f"Atomic write failed: {path}") from last_exc
```

---

## 十三、使用示例

### 13.1 初始化

```python
from ditto_data_hub import DataHub

# 创建实例
hub = DataHub.create("data")

# 或使用上下文管理器
with DataHub.create("data") as hub:
    bars = hub.bars.get(src_codes=["600000.SH"], start="2024-01-01")
```

### 13.2 读取行情

```python
# 推荐：使用 src_code
bars = hub.bars.get(
    src_codes=["600000.SH", "000001.SZ"],
    start="2024-01-01",
    end="2024-12-31",
    columns=["open", "high", "low", "close", "volume"],
    adj="qfq",
    with_symbol=True,
)

# 单只股票
bars = hub.bars.get_single("600000.SH", start="2024-01-01", adj="qfq")

# PIT 模式（回测用）
# asof 同时用于：
# 1. 标识符解析（查询历史代码映射）
# 2. 数据过滤（trade_date <= asof）
bars_pit = hub.bars.get(
    src_codes=["000022.SZ"],  # 深赤湾A（2018年被吸收合并）
    start="2015-01-01",
    end="2017-12-31",
    asof="2017-12-31",        # 站在2017年底视角
)

# ETF 行情
etf_bars = hub.bars.get(
    src_codes=["510300.SH", "159915.SZ"],
    start="2024-01-01",
    asset_class="etf",
)
```

### 13.3 交易日历

```python
# 判断交易日
is_open = hub.calendar.is_trading_day("2024-01-01")

# 列出交易日
trading_days = hub.calendar.list_trading_days("2024-01-01", "2024-01-31")

# 偏移交易日
next_day = hub.calendar.get_next("2024-01-01")
prev_day = hub.calendar.get_prev("2024-01-01")
day_offset = hub.calendar.offset("2024-01-01", 5)

# 获取月末交易日
month_ends = hub.calendar.get_period_ends("2024-01-01", "2024-12-31", period="month")
```

### 13.4 指数数据

```python
# 指数日线
index_bars = hub.index.get_daily(
    src_codes=["000300.SH", "000905.SH"],
    start="2024-01-01",
)

# 指数成分权重（PIT）
weights = hub.index.get_weight(
    index_code="000300.SH",
    asof="2024-06-30",
)

# 获取成分股
constituents = hub.index.get_constituents(
    index_code="000300.SH",
    asof="2024-06-30",
)
```

### 13.5 写入数据

```python
# 写入股票日线
result = hub.bars.write(
    df=df,
    year=2024,
    dataset="stock_daily",
    dq_fail_action="reject",
)

print(f"Status: {result.status}")
print(f"DQ Passed: {result.dq_passed}")

# 写入指数日线
hub.index.write_daily(df=index_df, year=2024)

# 写入指数权重
hub.index.write_weight(df=weight_df, year=2024)
```

### 13.6 SQL 查询（支持复权）

```python
# 查询原始数据（手动 PIT）
df = hub.sql("SELECT * FROM stock_daily WHERE sid = 10001 AND trade_date <= $asof", asof="2024-06-01")

# PIT 查询（自动应用 trade_date <= asof）
df = hub.sql(
    "SELECT * FROM stock_daily WHERE sid = 100000001",
    asof="2024-06-30"
)

# 查询后复权数据（HFQ），直接查 View，像查普通表一样
df = hub.sql("""
    "SELECT * FROM market_hfq WHERE sid = 10001 AND trade_date <= $asof",
    asof="2024-06-01"
""")

# 查询前复权数据（QFQ + PIT）
# 这是最强大的地方。你可以查询**“站在 2024-01-01 这一天看回去的前复权价格”**（这在回测中非常关键，避免用到未来的除权信息）。
# 使用宏，传入 $asof 变量
df = hub.sql("SELECT * FROM qfq($asof) WHERE sid = 1000", asof="2024-01-01")

# 跨年查询
df = hub.sql("""
    SELECT sid, trade_date, close
    FROM stock_daily
    WHERE trade_date >= '2020-01-01'
    ORDER BY trade_date
""")

# 跨库 JOIN（自动 ATTACH SQLite）
df = hub.sql("""
    SELECT m.trade_date, m.close, s.symbol, s.name
    FROM stock_daily m
    JOIN security s ON m.sid = s.sid
    WHERE m.trade_date = '2024-06-28'
    ORDER BY m.close DESC
    LIMIT 10
""")
```

### 13.7 Freeze 管理

```python
# 回测前创建冻结点
manifest = hub.freeze.create("backtest_v1", "首次回测版本")
print(f"Files frozen: {len(manifest.files)}")

# 查看所有冻结点
freezes = hub.freeze.list()
for f in freezes:
    print(f"{f['freeze_id']}: {f['description']} ({f['file_count']} files)")

# 验证数据一致性
is_valid, mismatches = hub.freeze.verify("backtest_v1")
if is_valid:
    print("✓ 数据与冻结点一致，可复现")
else:
    print(f"✗ 数据已变更: {mismatches}")

# 删除冻结点
hub.freeze.delete("backtest_v1")
```

### 13.8 证券主数据管理

```python
# 注册新证券
sid = hub.securities.register(
    source="tushare",
    src_code="688001.SH",
    symbol="688001",
    name="华兴源创",
    exchange="SSE",
    asset_class="stock",
    list_date="2019-07-22",
    board="科创板",
)

# 注册代码变更（如被吸收合并）
hub.securities.register_code_change(
    sid=12345,
    source="tushare",
    old_code="000022.SZ",
    new_code=None,  # 代码消失
    change_date="2018-12-25",
)

# 查询证券信息
info = hub.securities.get_by_sid(sid)

# 解析代码（支持 PIT）
sid = hub.resolve_sid("000022.SZ", asof="2017-01-01")  # 返回 12345
sid = hub.resolve_sid("000022.SZ", asof="2019-01-01")  # 返回 None（代码已消失）
```

### 13.9 标的池数据管理

``` python
from ditto_data_hub import DataHub

hub = DataHub.create("data")

# ========== 创建自定义标的池 ==========
hub.universe.create("my_pool", "我的核心持仓", description="长期价值投资")

# ========== 添加成分 ==========
# 方式 1：使用 src_code
hub.universe.add(
    "my_pool",
    src_codes=["600000.SH", "000001.SZ", "600519.SH"],
    effective_from="2024-01-01",
)

# 方式 2：使用 sid + 权重
hub.universe.add(
    "my_pool",
    sids=[100000001, 100000002],
    effective_from="2024-01-01",
    weights={100000001: 0.6, 100000002: 0.4},
)

# ========== 查询成分（PIT）==========
# 当前成分
current_sids = hub.universe.get_constituents("my_pool")

# 历史时点成分
sids_2024q2 = hub.universe.get_constituents("my_pool", asof="2024-06-30")

# 带权重的 DataFrame
df = hub.universe.get_constituents_df("my_pool", asof="2024-06-30", with_symbol=True)
print(df)
# shape: (3, 4)
# ┌───────────┬────────┬────────────────┬────────┐
# │ sid       ┆ weight ┆ effective_from ┆ symbol │
# │ ---       ┆ ---    ┆ ---            ┆ ---    │
# │ i64       ┆ f64    ┆ date           ┆ str    │
# ╞═══════════╪════════╪════════════════╪════════╡
# │ 100000001 ┆ 1.0    ┆ 2024-01-01     ┆ 600000 │
# │ 100000002 ┆ 1.0    ┆ 2024-01-01     ┆ 000001 │
# │ 100000003 ┆ 1.0    ┆ 2024-01-01     ┆ 600519 │
# └───────────┴────────┴────────────────┴────────┘

# ========== 从指数同步成分 ==========
count = hub.universe.sync_from_index(
    universe_id="hs300",
    index_code="000300.SH",
    asof="2024-06-30",
)
print(f"同步了 {count} 只成分股")

# ========== 成分变更 ==========
# 移除成分
hub.universe.remove("my_pool", src_codes=["600000.SH"], effective_date="2024-07-01")

# 全量替换
hub.universe.set_constituents(
    "my_pool",
    src_codes=["000001.SZ", "600519.SH", "601318.SH"],
    effective_from="2024-07-01",
)

# ========== 查看变更历史 ==========
history = hub.universe.get_history("my_pool")
print(history)
# shape: (5, 6)
# ┌───────────┬────────────────┬──────────────┬────────┬────────┬──────────┐
# │ sid       ┆ effective_from ┆ effective_to ┆ weight ┆ source ┆ src_code │
# │ ---       ┆ ---            ┆ ---          ┆ ---    ┆ ---    ┆ ---      │
# │ i64       ┆ date           ┆ date         ┆ f64    ┆ str    ┆ str      │
# ╞═══════════╪════════════════╪══════════════╪════════╪════════╪══════════╡
# │ 100000001 ┆ 2024-01-01     ┆ 2024-07-01   ┆ 1.0    ┆ null   ┆ null     │  ← 已移除
# │ 100000002 ┆ 2024-01-01     ┆ null         ┆ 1.0    ┆ null   ┆ null     │
# │ 100000003 ┆ 2024-01-01     ┆ null         ┆ 1.0    ┆ null   ┆ null     │
# │ 100000004 ┆ 2024-07-01     ┆ null         ┆ 1.0    ┆ null   ┆ null     │  ← 新增
# └───────────┴────────────────┴──────────────┴────────┴────────┴──────────┘
```

---

## 十四、Sources 数据源接入

### 14.1 DataSource 基类

```python
# src/ditto_data_hub/sources/base.py

from abc import ABC, abstractmethod
from typing import Literal
import polars as pl


class DataSourceError(Exception):
    """数据源错误基类"""
    pass


class RateLimitError(DataSourceError):
    """API 限流错误（可重试）"""
    pass


class AuthenticationError(DataSourceError):
    """认证错误（不可重试）"""
    pass


class DataSource(ABC):
    """
    数据源基类

    所有外部数据源（Tushare/AkShare）继承此类
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """数据源标识"""
        pass

    # ============ 日历 ============

    @abstractmethod
    def fetch_calendar(
        self,
        start_date: str,
        end_date: str,
    ) -> pl.DataFrame:
        """
        获取交易日历

        Returns:
            DataFrame[cal_date, is_open, pretrade_date]
        """
        pass

    # ============ 证券主数据 ============

    @abstractmethod
    def fetch_etf_basic(self) -> pl.DataFrame:
        """获取 ETF 基本信息"""
        pass

    @abstractmethod
    def fetch_stock_basic(self) -> pl.DataFrame:
        """获取股票基本信息"""
        pass

    @abstractmethod
    def fetch_index_basic(self) -> pl.DataFrame:
        """获取指数基本信息"""
        pass

    # ============ K线数据 ============

    @abstractmethod
    def fetch_etf_daily(
        self,
        trade_date: str | None = None,
        src_code: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """
        获取 ETF 日线

        Returns:
            DataFrame[src_code, trade_date, open, high, low, close, volume, amount]
        """
        pass

    @abstractmethod
    def fetch_stock_daily(self, ...) -> pl.DataFrame:
        """获取股票日线"""
        pass

    @abstractmethod
    def fetch_index_daily(self, ...) -> pl.DataFrame:
        """获取指数日线"""
        pass

    # ============ 复权因子 ============

    @abstractmethod
    def fetch_adj_factor(
        self,
        src_code: str,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """获取复权因子"""
        pass


# ============ 工厂函数 ============

_sources: dict[str, DataSource] = {}


def get_source(name: Literal["tushare", "akshare"]) -> DataSource:
    """获取数据源实例（单例）"""
    if name not in _sources:
        if name == "tushare":
            from .tushare import TushareSource
            _sources[name] = TushareSource()
        elif name == "akshare":
            from .akshare import AkShareSource
            _sources[name] = AkShareSource()
        else:
            raise ValueError(f"Unknown source: {name}")
    return _sources[name]
```

### 14.2 Tushare 实现

```python
# src/ditto_data_hub/sources/tushare/client.py

import tushare as ts
import time
from threading import Lock


class RateLimiter:
    """滑动窗口限流器"""

    def __init__(self, calls_per_minute: int = 200):
        self.calls_per_minute = calls_per_minute
        self.window_size = 60.0
        self.calls: list[float] = []
        self.lock = Lock()

    def wait(self):
        """等待直到可以发起请求"""
        with self.lock:
            now = time.time()
            self.calls = [t for t in self.calls if now - t < self.window_size]

            if len(self.calls) >= self.calls_per_minute:
                sleep_time = self.calls[0] + self.window_size - now
                if sleep_time > 0:
                    time.sleep(sleep_time)

            self.calls.append(time.time())


class TushareClient:
    """
    Tushare 客户端（带 Token 安全配置）

    Token 获取优先级：
    1. keyring（推荐）
    2. ~/.ditto/secrets.toml（备用）
    3. TUSHARE_TOKEN 环境变量（仅开发）
    """

    def __init__(self, token: str | None = None, calls_per_minute: int = 200):
        # Token 获取详见：14.2.1 Token 安全配置
        self._token = _get_tushare_token(token)
        self._api = ts.pro_api(self._token)
        self._rate_limiter = RateLimiter(calls_per_minute)

    def query(self, api_name: str, **kwargs):
        """执行 Tushare API 查询（带限流）"""
        self._rate_limiter.wait()
        return self._api.query(api_name, **kwargs)


# src/ditto_data_hub/sources/tushare/source.py

class TushareSource(DataSource):
    """Tushare Pro 数据源"""

    def __init__(self, token: str | None = None):
        self._client = TushareClient(token)

    @property
    def name(self) -> str:
        return "tushare"

    def fetch_calendar(self, start_date: str, end_date: str) -> pl.DataFrame:
        df = self._client.query(
            "trade_cal",
            exchange="SSE",
            start_date=start_date.replace("-", ""),
            end_date=end_date.replace("-", ""),
        )
        return pl.from_pandas(df).select([
            pl.col("cal_date").str.to_date("%Y%m%d").alias("cal_date"),
            (pl.col("is_open") == 1).alias("is_open"),
            pl.col("pretrade_date").str.to_date("%Y%m%d").alias("pretrade_date"),
        ])

    def fetch_etf_daily(self, trade_date: str | None = None, ...) -> pl.DataFrame:
        params = {}
        if trade_date:
            params["trade_date"] = trade_date.replace("-", "")
        # ... 其他参数

        df = self._client.query("fund_daily", **params)
        return self._normalize_ohlcv(df)

    # ... 其他方法实现
```

#### 14.2.1 Token 安全配置

**设计目标**：保护 Tushare API Token 不被泄露，同时提供灵活的配置方式。

**三层优先级机制**：

| 优先级 | 来源 | 适用场景 | 推荐度 |
|-------|------|---------|--------|
| 1 | keyring | 生产环境（Windows 凭据管理器 / macOS Keychain / Linux Secret Service） | ⭐⭐⭐ |
| 2 | ~/.ditto/secrets.toml | 跨平台备用方案 | ⭐⭐ |
| 3 | TUSHARE_TOKEN 环境变量 | 仅开发环境 | ⭐ |

**实现代码**：

```python
# src/ditto_data_hub/sources/tushare/client.py

import os
import tomllib
from pathlib import Path


def _get_tushare_token(token: str | None = None) -> str:
    """
    获取 Tushare Token（三层优先级）

    Args:
        token: 显式传入的 token（最高优先级）

    Returns:
        str: Tushare API Token

    Raises:
        SourceConfigurationError: 所有来源均未配置 token
    """
    # 1. 显式参数
    if token:
        logger.debug("Token from parameter", event="token_loaded", source="parameter")
        return token

    # 2. keyring（推荐）
    try:
        import keyring
        if keyring_token := keyring.get_password("ditto", "tushare"):
            logger.debug("Token from keyring", event="token_loaded", source="keyring")
            return keyring_token
    except Exception:
        pass  # keyring 不可用，继续尝试下一个

    # 3. ~/.ditto/secrets.toml（备用）
    config_file = Path.home() / ".ditto" / "secrets.toml"
    if config_file.exists():
        try:
            config = tomllib.loads(config_file.read_text())
            if config_token := config.get("tushare", {}).get("token"):
                logger.debug("Token from secrets.toml", event="token_loaded", source="secrets.toml")
                return config_token
        except Exception:
            pass

    # 4. TUSHARE_TOKEN 环境变量（仅开发）
    if env_token := os.getenv("TUSHARE_TOKEN"):
        logger.debug("Token from env var", event="token_loaded", source="env_var")
        return env_token

    # 所有来源均未找到 token
    raise SourceConfigurationError(
        message=(
            "Tushare token not configured. "
            "Use keyring: keyring.set_password('ditto', 'tushare', 'YOUR_TOKEN') "
            "or create ~/.ditto/secrets.toml with [tushare] token = 'YOUR_TOKEN'"
        )
    )
```

**配置方式示例**：

```bash
# 方式 1 - keyring（推荐）
python -c "import keyring; keyring.set_password('ditto', 'tushare', 'YOUR_TOKEN')"
```

```toml
# 方式 2 - ~/.ditto/secrets.toml（备用）
[tushare]
token = "YOUR_TOKEN"
```

```bash
# 方式 3 - 环境变量（仅开发）
export TUSHARE_TOKEN="YOUR_TOKEN"
```

**安全性要求**：

| 要求 | 说明 |
|------|------|
| 日志脱敏 | 日志中不打印完整 token |
| 错误隔离 | 错误消息不包含 token 值 |
| 最小权限 | 使用最小够用的 Tushare 积分级别 |
| 文件保护 | ~/.ditto/secrets.toml 权限设置为 600 |

**异常处理**：

```python
# Token 配置错误
SourceConfigurationError: Tushare token not configured

# Token 认证失败
SourceAuthenticationError: Tushare authentication failed
```

**测试要点**：

- [ ] 测试 keyring 获取成功
- [ ] 测试 secrets.toml fallback
- [ ] 测试环境变量 fallback
- [ ] 测试所有来源均失败时抛出异常
- [ ] 测试日志不包含完整 token
- [ ] 测试显式参数覆盖其他来源

### 14.3 DataSources:
``` python
class DataSources:
    """
    数据源提供器

    使用示例：
    """

    @cached_property
    def tushare(self) -> DataSource:
        """Tushare Pro 数据源"""
        return get_source("tushare")

    @cached_property
    def akshare(self) -> DataSource:
        """AkShare 数据源"""
        return get_source("akshare")

    def get(self, name: Literal["tushare", "akshare"]) -> DataSource:
        """按名称获取数据源"""
        return get_source(name)
```

### 14.4 TuShare 接口对照表

| Ditto 数据集 | TuShare 接口 | 关键字段映射 |
|---|---|---|
| security (stock) | stock_basic | ts_code→src_code, name, list_date |
| security (etf) | fund_basic | ts_code→src_code, name, fund_type |
| security (index) | index_basic | ts_code→src_code, name, market |
| trading_calendar | trade_cal | cal_date, is_open, pretrade_date |
| stock_daily | daily | ts_code, trade_date, OHLCV |
| adj_factor | adj_factor | ts_code, trade_date, adj_factor |
| etf_daily | fund_daily | ts_code, trade_date, OHLCV |
| index_daily | index_daily | ts_code, trade_date, OHLCV |
| index_weight | index_weight | index_code, con_code, weight |

---

## 十五、Implementation Checklist

### P0 必须做（MVP）

- [ ] **SQLite DDL 初始化**：所有元数据表
- [ ] **SQLitePool 实现**：连接池 + schema 初始化
- [ ] **Store 层实现**：
  - [ ] SecurityStore（含 PIT 标识符解析）
  - [ ] CalendarStore
  - [ ] PipelineStore
  - [ ] BarsStore（年分区）
  - [ ] IndexStore（年分区）
  - [ ] AdjFactorStore（年分区）
- [ ] **SidAllocator 实现**：SID 分配器
- [ ] **FileLockManager 实现**：跨平台文件锁
- [ ] **DQChecker 实现**：YAML 配置 + 规则执行
- [ ] **DataHub Facade 实现**：统一入口
- [ ] **Accessor 层实现**：
  - [ ] BarsAccessor（行情读写 + 复权 + PIT）
  - [ ] CalendarAccessor（日历查询）
  - [ ] SecuritiesAccessor（证券主数据 + 代码变更）
  - [ ] IndexAccessor（指数日线 + 权重）

### P1 强烈建议

- [ ] **SqlEngine 实现**：DuckDB View + 复权宏
- [ ] **FreezeManager 实现**：冻结点创建/验证
- [ ] **UniverseAccessor 实现**：标的池管理

### P2 可选增强

- [ ] **多数据源适配器**：RiceQuant / AkShare
- [ ] **CLI 工具**：数据同步、DQ 检查
- [ ] **监控指标**：写入延迟、DQ 失败率

---

## 十六、关键语义固化

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           关键语义（v4.0）                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  sid               = 内部唯一身份标识，永不改变，按资产类别分区               │
│  (source, src_code) = 外部稳定键，Ingestion 主通道                          │
│  symbol            = 展示代码，按需派生，不存入事实表                         │
│                                                                             │
│  asof              = PIT 截断点，同时用于：                                  │
│                      1. 标识符解析（查询历史代码映射）                        │
│                      2. 数据过滤（trade_date <= asof）                      │
│                                                                             │
│  年分区存储         = 每年一个 Parquet 文件，平衡读写与管理复杂度             │
│                                                                             │
│  Freeze            = 轻量级可复现：只记录 checksum，不复制文件               │
│                                                                             │
│  DQ 硬失败         = 阻断写入（主键重复、OHLC 负数、sid 缺失）               │
│  DQ 软失败         = 记录但允许写入（涨跌幅异常、量额不一致）                │
│                                                                             │
│  可复现性保证      = 代码版本（git）+ PIT 正确性（asof）+ Freeze 验证        │
│                                                                             │
│  Accessor        = 业务聚合根，封装读写逻辑，处理 PIT/复权等语义           │
│  Store             = 数据存取层，处理物理存储细节                            │
│  Runtime           = 技术组件，无业务逻辑                                   │
│  DataHub           = 纯 Facade，路由到 Accessor                           │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

**文档结束**
