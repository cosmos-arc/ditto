# Ditto 项目架构审计报告

> 注：本文档为历史归档，配置项已统一为无前缀键名 + config/{env}/*.env，仅在 apps/port 读取；文中提及的环境变量/前缀请视为配置键名示例。


**审计日期**: 2026-01-18
**审计范围**: packages/、apps/、tests/（269个Python文件，~57,952行代码）
**审计方法**: LSP语义分析 + 静态代码扫描 + 人工审查
**审计人员**: Claude (Architecture Audit Agent)

---

## Executive Summary

**整体评分**: 8.7/10 ⭐⭐⭐⭐

### 关键统计

| 严重度 | 数量 | 类别 |
|--------|------|------|
| 🔴 Blocker | 0 | - |
| 🟠 High | 13 | 架构违规(6) + 类规模(7) |
| 🟡 Medium | 20 | 类型标注(8) + 异常处理(5) + 重复代码(5) + 环境配置(2) |
| 🟢 Low | 9 | 命名一致性(1) + 依赖(1) + 文档(7) |

**总计**: 42个问题（整合了现有重构计划的问题）

### Top 6 高优先级问题

1. **[ARCH-001]** Port层5处跨层访问Store（破坏分层架构）+ 详细解决方案
2. **[ARCH-003]** 环境值类型安全缺失（Environment枚举缺失）
3. **[ENG-001]** BarsAccessor类819行职责过重（可维护性风险）
4. **[ENG-002]** TushareSource类648行高度重复代码（技术债务）
5. **[ENG-003]** DQ Checkers中`hub: Any`类型滥用（运行时风险）
6. **[ENG-004]** 多处`except Exception`过宽异常捕获（错误掩盖风险）

### 架构优势

✅ **依赖方向清晰**: 严格遵循 `foundation ← datahub ← port` 单向依赖
✅ **无循环依赖**: 未发现任何循环依赖
✅ **无禁止库使用**: 未发现pandas/sqlalchemy等禁止依赖
✅ **资源管理优秀**: 所有文件操作、数据库连接、线程锁都使用context manager
✅ **PIT安全意识强**: rolling操作全部正确使用`closed="left"`
✅ **命名一致性**: 9.5/10，仅1个单复数不一致问题
✅ **已完成优化**: match/case重构、复权函数提取、DQ过滤函数提取

### 与现有重构计划对照

| 重构计划 | 文档 | 覆盖问题 |
|---------|------|---------|
| 环境架构改进计划 | [2026-01-17-environment-architecture-improvement.md](../plans/2026-01-17-environment-architecture-improvement.md) | ARCH-003, ENG-013 |
| 架构重构计划 | [2026-01-17-architecture-refactor-plan.md](../plans/2026-01-17-architecture-refactor-plan.md) | ARCH-001, ARCH-004, ENG-001, ENG-011, ENG-012 |

---

## Inferred Architecture

### 现状分层图

```
┌─────────────────────────────────────────────────────────────┐
│                    apps/port (FastAPI)                      │
│  - CLI命令、Jobs编排、Services层、API层                      │
└──────────────────────────┬──────────────────────────────────┘
                           │ 依赖
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                   packages/core (待实现)                     │
│  - RegimeEngine, FactorEngine, Strategy, Portfolio          │
└──────────────────────────┬──────────────────────────────────┘
                           │ 依赖
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                  packages/datahub                           │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  DataHub (统一Facade)                                  │ │
│  │  ├─ Accessor层: 6个业务封装                            │ │
│  │  ├─ Store层: 10个数据存储                              │ │
│  │  ├─ Runtime层: 8个基础设施                             │ │
│  │  └─ Sources层: 外部数据源适配                          │ │
│  └────────────────────────────────────────────────────────┘ │
└──────────────────────────┬──────────────────────────────────┘
                           │ 依赖
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                 packages/foundation                         │
│  - Config, Observability, DB Pool, Cache, Concurrency       │
└─────────────────────────────────────────────────────────────┘
```

### 关键依赖方向

**允许的单向依赖**: `Server Flow → Server Service → DataHub Accessor → DataHub Store/Runtime → Foundation`

**禁止的依赖模式**:
- ❌ Server → DataHub Store (跨层访问) - **发现5处违规**
- ❌ Server → DataHub Runtime (跨层访问)
- ❌ DataHub → Server (反向依赖)
- ❌ 同层组件间的循环依赖

---

## Findings

### [ARCH-001] Port层直接访问Store层（跨层穿透）

**Severity**: 🟠 High
**Category**: Layering
**Location**: 5个文件

| 文件 | 行号 | 问题 |
|------|------|------|
| `apps/port/src/ditto_port/services/ingestion/backfill.py` | 6-7 | `from ...stores.calendar_store import CalendarStore` |
| `apps/port/src/ditto_port/services/ingestion/metadata.py` | 11 | `from ...stores.ingestion_log import IngestionLogStore` |
| `apps/port/src/ditto_port/services/ingestion/retry.py` | 10 | `from ...stores.ingestion_log import IngestionLogStore` |
| `apps/port/src/ditto_port/services/ingestion/coordinator.py` | 17 | `from ...sources.base import DataSource` |
| `apps/port/src/ditto_port/jobs/tasks/dq_batch.py` | 10 | `from ...repositories.bars import BarsQuery` |

**Evidence**:
```python
# ❌ 当前做法
from ditto_datahub.stores.calendar_store import CalendarStore
from ditto_datahub.stores.ingestion_log import IngestionLogStore
```

**Why it matters**:
- 破坏分层架构，导致职责边界模糊
- 难以在不影响Port层的情况下重构Store层
- 违反"应用层不应直接访问存储层"的原则（core.md:319）

**Fix**:

**方案A: 创建 IngestionLogAccessor（推荐）**
```python
# ✅ 创建 Accessor 层
# packages/datahub/src/ditto_datahub/accessors/ingestion_log.py
class IngestionLogAccessor:
    """摄取日志访问器."""
    def __init__(self, log_store: IngestionLogStore) -> None:
        self._log_store = log_store

    def save(self, dataset: str, source: str, trade_date: str,
             status: IngestionStatus, **kwargs) -> IngestionLog:
        """保存摄取日志记录."""

    def get_last_success_date(self, dataset: str, source: str = "tushare") -> str | None:
        """获取最后成功的交易日期."""

# ✅ Port 层通过 DataHub 访问
hub = DataHub()
last_date = hub.ingestion_log.get_last_success_date("stock_daily")
```

**方案B: 通过 DataHub 代理访问**
```python
# ✅ 简单场景：直接通过 DataHub 访问 Store
hub = DataHub()
calendar_store = hub.calendar_store  # 通过 DataHub 访问
```

**详细方案**: 参见 [docs/plans/2026-01-17-architecture-refactor-plan.md](../plans/2026-01-17-architecture-refactor-plan.md)

**Effort**: M (1天，创建models层+IngestionLogAccessor)

---

### [ARCH-002] SecuritiesAccessor命名单复数不一致

**Severity**: 🟡 Medium
**Category**: Naming
**Location**: `packages/datahub/src/ditto_datahub/repositories/security.py:15`

**Evidence**:
```python
# ❌ 不一致
class SecuritiesAccessor:  # 复数形式
    ...

# ✅ 其他Accessor都是单数
class BarsAccessor: ...
class CalendarAccessor: ...
class UniverseAccessor: ...
```

**Why it matters**:
- 命名不一致影响代码可读性
- 对应的`SecurityStore`是单数形式，造成概念不统一

**Fix**:
重命名为 `SecurityAccessor`，更新：
- 类定义
- 4处导入语句
- 测试文件
- 文档字符串

**Effort**: S (<1小时)

---

### [ARCH-003] 环境值类型安全缺失（Environment枚举）

**Severity**: 🟠 High
**Category**: Config / Typing
**Location**: `packages/foundation/src/ditto_foundation/config/settings.py`

**Evidence**:
```python
# ❌ 当前：环境值是字符串，无类型约束
class SystemSettings(BaseSettings):
    ditto_env: str = Field(default="development", ...)  # 字符串，易拼写错误

# ❌ 检测逻辑不完整
def detect_mode() -> Mode:
    if os.getenv("DITTO_ENV") == "production":
        return Mode.PRODUCTION
    # testing 环境会被误判为 DEVELOPMENT
    return Mode.DEVELOPMENT

# ❌ ObservabilityConfig.environment 默认值缩写不一致
class ObservabilityConfig:
    environment: str = "dev"  # 应为 "development"
```

**Why it matters**:
- 字符串无类型约束，容易出现拼写错误（"dev" vs "development"）
- testing 环境会被误判为 DEVELOPMENT，导致测试时启用追踪和指标
- `ditto_env` 和 `ObservabilityConfig.environment` 概念重复
- 违反项目规范："环境值必须使用 Environment 枚举"

**Fix**:

**步骤1：创建 Environment 枚举**
```python
# packages/foundation/src/ditto_foundation/config/settings.py
from enum import Enum

class Environment(str, Enum):
    """系统运行环境枚举（类型安全的环境值定义）."""
    DEVELOPMENT = "development"
    TESTING = "testing"
    PRODUCTION = "production"

    @classmethod
    def from_str(cls, value: str) -> "Environment":
        """从字符串解析环境值，提供清晰的错误信息."""
        try:
            return cls(value.lower())
        except ValueError:
            valid = ", ".join(e.value for e in cls)
            raise ValueError(
                f"无效的环境值: '{value}'. 有效值为: {valid}"
            ) from None
```

**步骤2：采用 OTEL 风格的独立开关**
```python
# packages/foundation/src/ditto_foundation/observability/config.py
@dataclass
class ObservabilityConfig:
    """可观测性配置类（OTEL 风格独立开关）."""

    # === 日志配置 ===
    log_level: str = "INFO"
    log_format: Literal["console", "json"] = "console"
    log_to_console: bool = True
    log_to_file: bool = True

    # === 追踪配置 ===
    tracing_enabled: bool = True
    tracing_exporter: Literal["otlp", "none"] = "otlp"
    tracing_sample_rate: float = 1.0

    # === 指标配置 ===
    metrics_enabled: bool = True
    metrics_exporter: Literal["victoriametrics", "none"] = "victoriametrics"

    # === 兼容性方法 ===
    def is_testing_mode(self) -> bool:
        """判断是否为测试模式（最小化配置）."""
        return (
            self.tracing_exporter == "none"
            and self.metrics_exporter == "none"
            and not self.log_to_file
        )
```

**参考文档**: [docs/plans/2026-01-17-environment-architecture-improvement.md](../plans/2026-01-17-environment-architecture-improvement.md)

**Effort**: M (1-2天，需创建配置文件结构并更新相关代码)

---

### [ARCH-004] IngestionLog模型位置不当（架构层级问题）

**Severity**: 🟡 Medium
**Category**: Layering
**Location**: `packages/datahub/src/ditto_datahub/sources/metadata.py`

**Evidence**:
```python
# ❌ 当前：IngestionLog 定义在 sources 层
# packages/datahub/src/ditto_datahub/sources/metadata.py
class IngestionLog(TypedDict):
    ...

# ❌ Port 层直接导入 sources 层
# apps/port/src/ditto_port/services/ingestion/metadata.py
from ditto_datahub.sources.metadata import IngestionLog
```

**Why it matters**:
- `IngestionLog` 是领域模型，不应属于 `sources` 层
- Port 层为了使用 `IngestionLog` 而穿透到 sources 层
- 违反分层架构原则

**Fix**:

**创建 models 层（领域类型层）**
```
packages/datahub/
├── models/                    # 新增：领域类型层
│   ├── __init__.py
│   ├── ingestion.py           # IngestionLog, IngestionStatus
│   └── common.py              # 共享模型
├── sources/                   # 数据源层（保留）
├── accessors/                 # 访问器层
│   └── ingestion_log.py       # 使用 models.IngestionLog
└── stores/                    # 存储层
    └── ingestion_log.py       # 使用 models.IngestionLog
```

**迁移步骤**：
1. 创建 `packages/datahub/src/ditto_datahub/models/` 目录
2. 移动 `IngestionLog`, `IngestionStatus` 到 `models.ingestion`
3. 创建 `IngestionLogAccessor`（详见 ARCH-001）
4. 更新所有引用：
   - `sources.metadata` → `models.ingestion`
   - Port 层从 `models` 导入类型，从 `accessors` 导入 Accessor

**参考文档**: [docs/plans/2026-01-17-architecture-refactor-plan.md](../plans/2026-01-17-architecture-refactor-plan.md)

**Effort**: M (1天，创建models层+IngestionLogAccessor)

---

### [ENG-001] BarsAccessor类职责过重（819行）

**Severity**: 🟠 High
**Category**: SRP / Complexity
**Location**: `packages/datahub/src/ditto_datahub/repositories/bars/repository.py`

**Evidence**:
```python
class BarsAccessor:  # 819行，13个方法
    # 职责1: 标识符解析 (5个方法)
    def _resolve_query(...) ...
    def _resolve_sids(...) ...

    # 职责2: 复权处理 (2个方法)
    def _apply_adjustment(...) ...

    # 职责3: 状态增强 (1个方法)
    def _enrich_with_status(...) ...

    # 职责4: DQ检查 (2个方法)
    def _save_to_quarantine(...) ...

    # 职责5: 数据写入 (1个方法)
    def write(...) ...
```

**Why it matters**:
- 单一类承担过多职责，违反单一职责原则
- 难以测试、难以维护、修改影响范围大
- 是被依赖最多的"热点模块"

**Fix**:
```python
# 拆分为5个独立的类
class BarsIdentifierResolver:
    """标识符解析器"""
    def resolve_query(...) -> ResolvedQuery
    def resolve_sids(...) -> list[int]

class BarsAdjustmentService:
    """复权服务"""
    def apply_qfq(df, adj_factors) -> pl.DataFrame
    def apply_hfq(df, adj_factors) -> pl.DataFrame

class BarsStatusEnricher:
    """状态增强器"""
    def enrich_with_status(df, sids, start, end) -> pl.DataFrame

# 简化的Repository
class BarsAccessor:
    def __init__(self, resolver, adjustment_service, enricher, ...):
        self._resolver = resolver
        self._adjustment = adjustment_service
        self._enricher = enricher
```

**已完成部分** (2026-01-17):
- ✅ `adjustment.py` - 复权计算函数
- ✅ `dq_filters.py` - DQ过滤函数
- ✅ `AssetSidRange.detect_asset_class()` - 资产类别检测

**待完成**:
- 拆分为独立的类
- 移除 DQ 编排逻辑（~170行）

**Effort**: L (2-3天，需要重构+测试)

---

### [ENG-002] TushareSource类重复代码过多（648行）

**Severity**: 🟠 High
**Category**: Duplication
**Location**: `packages/datahub/src/ditto_datahub/sources/tushare/source.py`

**Evidence**:
```python
class TushareSource:  # 648行，11个fetch方法
    # 高度重复的模式
    @traced("source.tushare.fetch_calendar")
    def fetch_calendar(...) -> pl.DataFrame:
        with self._tushare_fetch_error_handler("calendar", "trade_cal"):
            response = self._client.query(...)
            return TushareDataTransformer.transform(...)

    @traced("source.tushare.fetch_etf_basic")
    def fetch_etf_basic(...) -> pl.DataFrame:
        with self._tushare_fetch_error_handler("etf_basic", "fund_basic"):
            response = self._client.query(...)
            return TushareDataTransformer.transform(...)
    # 重复9次...
```

**Why it matters**:
- 11个fetch方法结构高度重复
- 添加新数据源需要复制大量代码
- 违反DRY原则

**Fix**:
```python
# 使用模板方法模式
class TushareSource(DataSource):
    def _fetch_with_transform(
        self,
        dataset: str,
        api_name: str,
        mapping: ColumnMapping,
        **query_params
    ) -> pl.DataFrame:
        """统一的fetch模板方法"""
        with self._tushare_fetch_error_handler(dataset, api_name):
            response = self._client.query(api_name, **query_params)
            return TushareDataTransformer.transform(response, dataset, mapping)

    # 简化的具体方法
    def fetch_calendar(self, start_date: str, end_date: str) -> pl.DataFrame:
        return self._fetch_with_transform(
            "calendar", "trade_cal", CALENDAR_MAPPING,
            exchange="SSE",
            start_date=start_date.replace("-", ""),
            end_date=end_date.replace("-", ""),
        )
```

**Effort**: M (1天)

---

### [ENG-003] DQ Checkers中`hub: Any`类型滥用

**Severity**: 🟠 High
**Category**: Typing
**Location**: `packages/datahub/src/ditto_datahub/dq/checkers/statistical.py:20`

**Evidence**:
```python
class StatisticalChecker:
    def check(
        self,
        dataset: str,
        trade_date: str,
        rules: list[dict[str, Any]],
        hub: Any,  # ❌ DataHub实例未类型化
        ...
    ) -> list[DQIssue]:
```

**Why it matters**:
- 运行时错误风险（访问不存在的属性）
- IDE无法提供自动补全
- 违反core.md:269类型标注规范

**Fix**:
```python
from typing import Protocol

class DataHubProtocol(Protocol):
    """DataHub访问协议"""
    def bars_get(
        self,
        sids: list[int] | None = None,
        start_date: str | None = None,
    ) -> pl.DataFrame: ...

class StatisticalChecker:
    def check(
        self,
        dataset: str,
        trade_date: str,
        rules: list[dict[str, Any]],
        hub: DataHubProtocol,  # ✅ 类型安全
        ...
    ) -> list[DQIssue]:
```

**Effort**: M (1天，需定义Protocol并更新所有checkers)

---

### [ENG-004] 过宽的异常捕获

**Severity**: 🟠 High
**Category**: ErrorHandling
**Location**: 多个文件

| 文件 | 行号 | 问题 |
|------|------|------|
| `sources/tushare/source.py` | 105, 402, 430, 459 | `except Exception as e:` |
| `stores/bars_store.py` | 74 | `except Exception:` (空块) |
| `config/initializer.py` | 216 | `except Exception as e:` |

**Evidence**:
```python
# ❌ 问题：捕获所有异常
@contextmanager
def _tushare_fetch_error_handler(self, dataset: str, api_name: str):
    try:
        yield
    except SourceAuthenticationError:
        raise
    except SourceRateLimitError:
        raise
    except Exception as e:  # ❌ 捕获所有异常，包括KeyboardInterrupt
        logger.error(...)
        raise SourceFetchError(...) from e

# ❌ 问题：空异常块
def _ensure_date_column(self, df: pl.DataFrame) -> pl.DataFrame:
    try:
        return df.with_columns(pl.col("trade_date").cast(pl.String).str.to_date())
    except Exception:  # ❌ 空块，掩盖错误
        return df
```

**Why it matters**:
- 捕获系统异常（如KeyboardInterrupt、SystemExit）
- 空异常块掩盖错误，难以调试
- 违反core.md:139异常处理规范

**Fix**:
```python
# ✅ 定义明确的可预期异常
TUSHARE_EXPECTED_ERRORS = (
    SourceAuthenticationError,
    SourceRateLimitError,
    requests.RequestException,
    orjson.JSONDecodeError,
    KeyError,
    ValueError,
)

@contextmanager
def _tushare_fetch_error_handler(self, dataset: str, api_name: str):
    try:
        yield
    except TUSHARE_EXPECTED_ERRORS as e:  # ✅ 明确的异常列表
        logger.error(...)
        raise SourceFetchError(...) from e
```

**Effort**: M (1天)

---

### [ENG-005] Metrics配置数据硬编码（567行）

**Severity**: 🟡 Medium
**Category**: Config
**Location**: `packages/foundation/src/ditto_foundation/observability/metrics.py:81-290`

**Evidence**:
```python
# 290行的配置硬编码在Python中
METRIC_DEFINITIONS: list[MetricDefinition] = [
    {
        "name": "data_update_duration",
        "instrument_name": "ditto.data.update.duration",
        "type": "histogram",
        "description": "Data update operation duration in seconds",
    },
    # ... 重复24次
]
```

**Why it matters**:
- 配置数据应与代码分离
- 修改配置需要重新部署
- 违反配置管理最佳实践

**Fix**:
```yaml
# config/metrics.yaml
metrics:
  data_update_duration:
    instrument_name: ditto.data.update.duration
    type: histogram
    description: Data update operation duration in seconds
```

```python
# 简化的metrics.py
def load_metric_definitions(config_path: Path) -> list[MetricDefinition]:
    with open(config_path) as f:
        config = yaml.safe_load(f)
    return [MetricDefinition(**m) for m in config["metrics"]]

METRIC_DEFINITIONS = load_metric_definitions(get_paths().config_subdir("metrics.yaml"))
```

**Effort**: S (0.5天)

---

### [ENG-006] CalendarStore类方法过多（23个方法）

**Severity**: 🟡 Medium
**Category**: Complexity
**Location**: `packages/datahub/src/ditto_datahub/stores/calendar_store.py`

**Evidence**:
```python
class CalendarStore:  # 610行，23个方法
    # 查询方法 (10个)
    def get(...) ...
    def get_all(...) ...
    def is_trading_day(...) ...
    # ... 重复7个

    # 过滤方法 (5个)
    def filter_open_days(...) ...
    def filter_close_days(...) ...
    # ...

    # 缓存管理 (3个)
    def reload(...) ...
    # ...

    # SQL构建 (5个)
    def _build_where(...) ...
    # ...
```

**Why it matters**:
- 单一类方法过多，难以理解和维护
- SQL构建逻辑复杂，应提取

**Fix**:
提取 `CalendarQueryBuilder` 类处理SQL构建逻辑。

**Effort**: M (1天)

---

### [ENG-007] 日期列归一化逻辑重复

**Severity**: 🟡 Medium
**Category**: Duplication
**Location**: 多个Store类

**Evidence**:
```python
# 在BarsStore、AdjFactorStore等多个文件中重复
class BarsStore(ParquetStoreBase):
    def _ensure_date_column(self, df: pl.DataFrame) -> pl.DataFrame:
        dtype = df["trade_date"].dtype
        if dtype == pl.Date:
            return df
        if dtype == pl.String:
            return df.with_columns(pl.col("trade_date").str.to_date())
        # ... 30行重复逻辑
```

**Why it matters**:
- 违反DRY原则
- 修改需要同步多处

**Fix**:
```python
# 提取到共享工具类
class DateColumnNormalizer:
    @staticmethod
    def normalize(df: pl.DataFrame, date_column: str = "trade_date") -> pl.DataFrame:
        dtype = df[date_column].dtype
        if dtype == pl.Date:
            return df
        if dtype == pl.String:
            return df.with_columns(pl.col(date_column).str.to_date())
        # ... 统一实现

# 使用
class BarsStore(ParquetStoreBase):
    def _ensure_date_column(self, df: pl.DataFrame) -> pl.DataFrame:
        return DateColumnNormalizer.normalize(df)
```

**Effort**: S (1天)

---

### [ENG-008] 超大测试文件

**Severity**: 🟡 Medium
**Category**: Testing
**Location**: 3个测试文件

| 文件 | 行数 | 问题 |
|------|------|------|
| `test_bars_repository_unit.py` | 1801 | 单个测试文件过大 |
| `test_source_unit.py` | 1472 | 单个测试文件过大 |
| `test_coordinator_unit.py` | 1400 | 单个测试文件过大 |

**Why it matters**:
- 测试执行速度慢
- 难以定位测试问题
- 违反测试组织最佳实践

**Fix**:
按功能拆分测试文件：
```
test/bars/
  ├─ test_identifier_resolver_unit.py   (400行)
  ├─ test_adjustment_service_unit.py    (600行)
  ├─ test_status_enricher_unit.py       (400行)
  └─ test_dq_integration_unit.py        (401行)
```

**Effort**: M (2-3天)

---

### [ENG-009] 其他`Any`类型使用

**Severity**: 🟡 Medium
**Category**: Typing
**Location**: 多个文件

| 位置 | 代码 | 问题 |
|------|------|------|
| `observability/tracing.py:59` | `self._span: Any` | Span类型不明确 |
| `observability/tracing.py:76` | `def __exit__(self, exc_type: Any, ...` | 过于宽泛 |
| `observability/metrics.py:314` | `def callback(options: Any) -> ...` | 回调参数类型不明确 |
| `app_initializer.py:72` | `def _create_directories(self, settings: Any)` | 配置对象未类型化 |

**Fix**:
使用具体类型替代 `Any`：
```python
# ❌
self._span: Any
def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None

# ✅
from types import TracebackType
self._span: SpanType | None
def __exit__(
    self,
    exc_type: type[BaseException] | None,
    exc_val: BaseException | None,
    exc_tb: TracebackType | None,
) -> bool | None
```

**Effort**: S (0.5天)

---

### [ENG-010] pandas依赖声明但未使用

**Severity**: 🟢 Low
**Category**: Dependencies
**Location**: `pixi.toml:25`

**Evidence**:
```toml
[pypi-dependencies]
pandas = "*"  # ❌ 声明了依赖但源码中未使用
```

**Why it matters**:
- 增加不必要的依赖体积
- 违反项目依赖规范（禁止pandas）

**Fix**:
从 `pixi.toml` 中移除 pandas 依赖声明。

**Effort**: S (5分钟)

---

### [ENG-011] 日志装饰器缺失（重复日志模式）

**Severity**: 🟡 Medium
**Category**: Duplication
**Location**: 多个Accessor/Repository类

**Evidence**:
```python
# ❌ 当前：134处重复的日志记录模式
logger.info("Writing bars data", event="bars_write_start", dataset=dataset, ...)
# ... 执行操作
logger.info("Write complete", event="bars_write_complete", ...)

# AdjFactorRepository
logger.info("Writing adj_factor data", event="adj_factor_write_start", ...)

# SecurityRepository
logger.info("Registering new security", event="security_register_start", ...)
```

**Why it matters**:
- 大量重复的"开始/完成/失败"日志模式
- 违反DRY原则
- 业界推荐使用装饰器统一标准CRUD操作日志

**Fix**:
```python
# packages/foundation/src/ditto_foundation/logging/context.py
@contextmanager
def log_operation(
    operation: str,
    **context: Any,
) -> Generator[None, None, None]:
    """
    操作日志上下文管理器（用于需要自动记录开始/结束的场景）.

    业界推荐：用于明确的操作边界，如文件读写、网络请求等。

    Examples:
        >>> with log_operation("write_bars", dataset="stock_daily"):
        ...     # 执行写入操作
        ...     pass
    """
    logger.info(f"{operation} start", event=f"{operation}_start", **context)
    try:
        yield
        logger.info(f"{operation} complete", event=f"{operation}_complete", **context)
    except Exception as e:
        logger.error(f"{operation} failed", event=f"{operation}_failed", error=str(e), **context)
        raise

# 使用
class BarsAccessor:
    def write(self, dataset: str, df: pl.DataFrame):
        with log_operation("write_bars", dataset=dataset, rows=len(df)):
            # 执行写入
            result = self._bars_store.write(dataset, df, year, on_duplicate)
        return result
```

**参考文档**: [docs/plans/2026-01-17-architecture-refactor-plan.md](../plans/2026-01-17-architecture-refactor-plan.md)

**Effort**: M (1天，创建工具函数+迁移现有日志)

---

### [ENG-012] 共用函数缺失（标识符解析、指标记录、写入锁）

**Severity**: 🟡 Medium
**Category**: Duplication
**Location**: 多个Repository类

**Evidence**:
```python
# ❌ 标识符解析逻辑在 BarsRepository 和 SecurityRepository 重复
def _resolve_sids(self, sids, src_codes, symbols, asof, source="tushare"):
    resolved = set()
    if sids:
        resolved.update(sids)
    if src_codes:
        mapping = self._security_store.resolve_sids_batch(src_codes, source, asof)
        resolved.update(mapping.values())
    # ... 30行重复逻辑

# ❌ 指标记录在所有 Repository 重复
M.data_records.add(len(result), {"dataset": "xxx", "operation": "get"})

# ❌ 文件锁+写入模式重复
lock_name = f"bars_write_{dataset}_{year}"
with self._file_lock.acquire(lock_name, timeout=60.0):
    result = self._bars_store.write(dataset, df, year, on_duplicate)
```

**Why it matters**:
- 多个Repository重复实现相同逻辑
- 修改需要同步多处
- 违反DRY原则

**Fix**:

**提取标识符解析工具**:
```python
# packages/datahub/src/ditto_datahub/repositories/common/identifier.py
def resolve_sids(
    sids: list[int] | None,
    src_codes: list[str] | None,
    symbols: list[str] | None,
    security_store: SecurityStore,
    asof: str | None,
    source: str = "tushare",
) -> list[int]:
    """通用的标识符解析函数."""
    resolved: set[int] = set()
    if sids:
        resolved.update(sids)
    if src_codes:
        mapping = security_store.resolve_sids_batch(src_codes, source, asof)
        resolved.update(mapping.values())
    if symbols:
        for symbol in symbols:
            sids_from_symbol = security_store.resolve_by_symbol(symbol, source)
            resolved.update(sids_from_symbol)
    return sorted(resolved)
```

**提取指标记录装饰器**:
```python
# packages/foundation/src/ditto_foundation/metrics/tracking.py
def track_metrics(dataset: str, operation: str):
    """指标记录装饰器."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            result = func(*args, **kwargs)
            if hasattr(result, '__len__'):
                M.data_records.add(len(result), {"dataset": dataset, "operation": operation})
            return result
        return wrapper
    return decorator
```

**提取写入锁上下文管理器**:
```python
# packages/datahub/src/ditto_datahub/runtime/write_guard.py
@contextmanager
def write_with_lock(
    file_lock: FileLockManager,
    lock_name: str,
    operation: str,
    **context: Any,
):
    """带文件锁的写入上下文管理器."""
    logger.info(f"{operation} start", event=f"{operation}_start", **context)
    with file_lock.acquire(lock_name, timeout=60.0):
        try:
            yield
            logger.info(f"{operation} complete", event=f"{operation}_complete", **context)
        except Exception as e:
            logger.error(f"{operation} failed", event=f"{operation}_failed", error=str(e))
            raise
```

**参考文档**: [docs/plans/2026-01-17-architecture-refactor-plan.md](../docs/2026-01-17-architecture-refactor-plan.md)

**Effort**: M (1-2天，创建3个工具模块+迁移)

---

### [ENG-013] 配置目录结构缺失（config/{environment}/）

**Severity**: 🟡 Medium
**Category**: Config
**Location**: 项目根目录

**Evidence**:
```
# ❌ 当前：缺少按环境分组的配置目录
config/
└── (空或缺少)
```

**Why it matters**:
- 不同环境的配置难以管理
- 无法直观看到某个环境的所有配置
- 违反最佳实践（按环境分组配置）

**Fix**:
```
# ✅ 创建 config/{environment}/ 结构
config/
├── development/
│   ├── observability.env
│   ├── database.env
│   ├── api.env
│   └── data_source.env
├── testing/
│   ├── observability.env
│   └── database.env
└── production/
    ├── observability.env
    └── database.env
```

**配置示例**:
```bash
# config/development/observability.env
LOG_LEVEL=DEBUG
LOG_FORMAT=console
TRACING_ENABLED=true
TRACING_EXPORTER=otlp
METRICS_ENABLED=true
```

**参考文档**: [docs/plans/2026-01-17-environment-architecture-improvement.md](../plans/2026-01-17-environment-architecture-improvement.md)

**Effort**: S (0.5天，创建配置文件)

---

## Refactor Plan

### P0 - 必须修（阻塞性问题）

无（无Blocker级别问题）

### P1 - 应该修（高优先级）

#### PR-1: 创建 models 层 + IngestionLogAccessor
**目标**: 修复 ARCH-001（跨层访问）和 ARCH-004（模型位置不当）

**改动范围**:
- 新建 `packages/datahub/src/ditto_datahub/models/` 目录
- 新建 `packages/datahub/src/ditto_datahub/accessors/ingestion_log.py`
- 更新 `packages/datahub/src/ditto_datahub/hub.py`
- 更新所有引用 `IngestionLog` 的文件

**修改内容**:
1. 创建 `models.ingestion` 模块，移动 `IngestionLog`, `IngestionStatus`
2. 创建 `IngestionLogAccessor` 类
3. 更新 DataHub 添加 `ingestion_log` 属性
4. Port 层通过 `DataHub.ingestion_log` 访问

**风险**: 中（涉及跨层访问修复，需仔细测试）

**回滚策略**: revert commit

**工作量**: 1天

**参考**: [docs/plans/2026-01-17-architecture-refactor-plan.md](../plans/2026-01-17-architecture-refactor-plan.md)

---

#### PR-2: 实现 Environment 枚举 + OTEL 风格配置
**目标**: 修复 ARCH-003（环境值类型安全缺失）

**改动范围**:
- `packages/foundation/src/ditto_foundation/config/settings.py`
- `packages/foundation/src/ditto_foundation/observability/config.py`
- `packages/foundation/src/ditto_foundation/observability/__init__.py`
- `packages/foundation/src/ditto_foundation/app_initializer.py`
- `apps/port/src/ditto_port/main.py`

**修改内容**:
1. 创建 `Environment` 枚举类型
2. 重构 `ObservabilityConfig` 为独立开关（移除 Mode 枚举）
3. 更新 `ObservabilitySettings` 添加新字段
4. 更新 `init()` 函数接受独立配置项
5. 更新 `app_initializer.py` 传递独立配置

**风险**: 中（影响配置加载流程）

**回滚策略**: revert commit

**工作量**: 1-2天

**参考**: [docs/plans/2026-01-17-environment-architecture-improvement.md](../plans/2026-01-17-environment-architecture-improvement.md)

---

#### PR-3: 创建 config/{environment}/ 配置文件
**目标**: 修复 ENG-013（配置目录结构缺失）

**改动范围**:
- 新建 `config/development/` 目录及配置文件
- 新建 `config/testing/` 目录及配置文件
- 新建 `config/production/` 目录及配置文件
- 更新 `.gitignore`

**配置文件内容**:
```bash
# config/development/observability.env
LOG_LEVEL=DEBUG
LOG_FORMAT=console
TRACING_ENABLED=true
TRACING_EXPORTER=otlp
METRICS_ENABLED=true

# config/testing/observability.env
LOG_LEVEL=WARNING
LOG_TO_FILE=false
TRACING_ENABLED=false
TRACING_EXPORTER=none
METRICS_ENABLED=false

# config/production/observability.env
LOG_LEVEL=INFO
LOG_FORMAT=json
TRACING_SAMPLE_RATE=0.1
```

**风险**: 低（仅新增配置文件）

**工作量**: 0.5天

**参考**: [docs/plans/2026-01-17-environment-architecture-improvement.md](../plans/2026-01-17-environment-architecture-improvement.md)

---

#### PR-4: 修复DQ Checkers类型安全
**目标**: 修复 ENG-003（`hub: Any` 类型滥用）

**改动范围**:
- `packages/datahub/src/ditto_datahub/dq/checkers/`
- 新建 `packages/datahub/src/ditto_datahub/protocols.py`

**修改内容**:
1. 定义 `DataHubProtocol` 协议
2. 更新所有Checker使用协议类型
3. 添加类型测试

**风险**: 中（可能影响现有调用）

**回滚策略**: revert commit

**工作量**: 1天

---

#### PR-5: 修复过宽异常捕获
**目标**: 修复 ENG-004（过宽异常捕获）

**改动范围**:
- `packages/datahub/src/ditto_datahub/sources/tushare/source.py`
- `packages/datahub/src/ditto_datahub/stores/bars_store.py`

**修改内容**:
1. 定义明确的异常列表
2. 修复空异常块
3. 添加错误日志上下文

**风险**: 低（仅改善错误处理）

**回滚策略**: 简单git revert

**工作量**: 1天

---

#### PR-6: 重构BarsAccessor类
**目标**: 修复 ENG-001（BarsAccessor 819行职责过重）

**改动范围**:
- `packages/datahub/src/ditto_datahub/repositories/bars/`
- `packages/datahub/tests/unit/repositories/test_bars_repository_unit.py`

**修改内容**:
1. 创建 `BarsIdentifierResolver` 类
2. 创建 `BarsAdjustmentService` 类（部分已完成：adjustment.py）
3. 创建 `BarsStatusEnricher` 类
4. 简化 `BarsAccessor` 为协调器
5. 拆分测试文件

**已完成部分**:
- ✅ `adjustment.py` - 复权计算函数
- ✅ `dq_filters.py` - DQ过滤函数
- ✅ `AssetSidRange.detect_asset_class()` - 资产类别检测

**待完成**:
- 拆分为独立的类
- 移除 DQ 编排逻辑（~170行）

**风险**: 中（大重构，需确保测试覆盖）

**回滚策略**: revert commit + 分支保护

**工作量**: 2-3天

**参考**: [docs/plans/2026-01-17-architecture-refactor-plan.md](../plans/2026-01-17-architecture-refactor-plan.md)

---

### P2 - 可优化（中优先级）

#### PR-7: 重构TushareSource
**目标**: 修复 ENG-002（重复fetch方法）

**改动范围**:
- `packages/datahub/src/ditto_datahub/sources/tushare/source.py`

**修改内容**:
使用模板方法模式统一fetch逻辑

**工作量**: 1天

---

#### PR-8: 修复命名不一致
**目标**: 修复 ARCH-002（SecuritiesAccessor 命名）

**改动范围**:
- `packages/datahub/src/ditto_datahub/repositories/security.py`
- `packages/datahub/src/ditto_datahub/hub.py`
- `packages/datahub/tests/unit/repositories/test_security_repository_unit.py`
- 相关文档

**工作量**: <1小时

---

#### PR-9: 提取共用函数（日志装饰器+标识符解析+指标记录）
**目标**: 修复 ENG-011, ENG-012（重复代码）

**改动范围**:
- 新建 `packages/foundation/src/ditto_foundation/logging/context.py`
- 新建 `packages/foundation/src/ditto_foundation/metrics/tracking.py`
- 新建 `packages/datahub/src/ditto_datahub/repositories/common/identifier.py`
- 新建 `packages/datahub/src/ditto_datahub/runtime/write_guard.py`
- 更新所有 Repository 类使用新工具

**修改内容**:
1. 创建 `log_operation` 上下文管理器
2. 创建 `track_metrics` 装饰器
3. 创建 `resolve_sids` 工具函数
4. 创建 `write_with_lock` 上下文管理器

**工作量**: 1-2天

**参考**: [docs/plans/2026-01-17-architecture-refactor-plan.md](../plans/2026-01-17-architecture-refactor-plan.md)

---

#### PR-10: 提取日期列归一化工具
**目标**: 修复 ENG-007（日期归一化重复）

**改动范围**:
- 新建 `packages/datahub/src/ditto_datahub/util/date_normalizer.py`
- 更新所有Store类

**工作量**: 1天

---

#### PR-11: 将Metrics配置移至YAML
**目标**: 修复 ENG-005（硬编码配置）

**改动范围**:
- `packages/foundation/src/ditto_foundation/observability/metrics.py`
- 新建 `config/metrics.yaml`

**工作量**: 0.5天

---

#### PR-12: 拆分超大测试文件
**目标**: 修复 ENG-008（测试文件过大）

**改动范围**:
- `packages/datahub/tests/unit/repositories/test_bars_repository_unit.py`
- `packages/datahub/tests/unit/sources/tushare/test_source_unit.py`
- `apps/port/tests/unit/ingestion/test_coordinator_unit.py`

**工作量**: 2-3天

---

### P3 - 长期优化（低优先级）

- 重构 `CalendarStore` 和 `SecurityStore`（引入QueryBuilder）
- 统一SQL构建逻辑（创建SQLBuilder工具类）
- 清理pandas未使用依赖
- 其他 `Any` 类型修复

---

## 验证清单

### 自动化验证

```bash
# 代码质量检查
pixi run -e dev lint
pixi run -e dev type
pixi run -e dev test --unit

# 覆盖率检查
pixi run -e dev test --cov --cov-report=term-missing --cov-fail-under=80
```

### 人工验证

- [ ] 架构分层：Port层无直接导入Store
- [ ] 类型检查：pyright无error/warning
- [ ] 测试覆盖：所有分支覆盖率 >= 80%
- [ ] 文档更新：README/design doc同步更新
- [ ] 向后兼容：API接口保持兼容

---

## 附录

### A. 热点模块Top 5

| 模块 | 复杂度 | 风险点 |
|------|--------|--------|
| `DataHub` | ★★★★★ | 单点入口，15+依赖 |
| `BarsAccessor` | ★★★★★ | 819行，PIT安全关键路径 |
| `IngestionCoordinator` | ★★★★☆ | 协调多个组件，状态管理复杂 |
| `DQEngine` | ★★★★☆ | 配置驱动，阻断vs警告判断 |
| `CalendarStore` | ★★★★☆ | 全内存缓存，被几乎所有模块依赖 |

### B. 技术债务量化

| 类别 | 严重 | 中等 | 轻微 | 总计 |
|------|------|------|------|------|
| 架构分层 | 6 | 1 | 1 | 8 |
| 类规模/复杂度 | 7 | 2 | 3 | 12 |
| 类型标注 | 8 | 4 | 12 | 24 |
| 异常处理 | 5 | 6 | 3 | 14 |
| 代码重复 | 3 | 8 | 2 | 13 |
| 命名一致性 | 0 | 1 | 0 | 1 |
| 环境配置 | 2 | 0 | 0 | 2 |
| **总计** | **31** | **22** | **21** | **74** |

**与现有重构计划对照**:
- **环境架构改进计划** (2026-01-17): 对应 ARCH-003, ENG-013
- **架构重构计划** (2026-01-17): 对应 ARCH-001, ARCH-004, ENG-001, ENG-011, ENG-012

### C. 工具统计

| 指标 | 数量 |
|------|------|
| 源码文件 | 269个 |
| 代码行数 | ~57,952行 |
| `# type: ignore` | 17次（13文件） |
| `# noqa` | 109次（34文件） |
| `except *:` | 0次 |
| `Any` 类型 | 174次（38文件） |

---

**报告生成**: 2026-01-18
**下次审计建议**: PR-1至PR-6完成后进行复审
