# 架构审计问题分析与重构方案

## 讨论主题

基于 `docs/plans/2026-01-17-architecture-audit.md`，针对以下问题进行详细分析：

1. **P0 - apps/port → Store 层穿透**：创建 IngestionLogAccessor，通过 provider 代理 source 依赖
2. **第 6 点 - 引入 Protocol** 减少动态调用
3. **第 7 点 - 减少重复代码**（日志装饰器）
4. **第 4 点 - BarsRepository 改造**：详细分析其他 repo 是否有类似问题

---

## 一、P0 问题分析：IngestionLogAccessor 设计

### 1.1 当前穿透情况

**Store 层穿透** (3 个文件):
- [metadata.py:11](apps/port/src/ditto_port/services/ingestion/metadata.py#L11) → `IngestionLogStore`
- [backfill.py:6,7,34](apps/port/src/ditto_port/services/ingestion/backfill.py#L6-L7) → `CalendarStore`, `IngestionLogStore`
- [retry.py:10,38](apps/port/src/ditto_port/services/ingestion/retry.py#L10) → `IngestionLogStore`

**Source 层穿透** (2 个文件):
- [coordinator.py:15-16](apps/port/src/ditto_port/services/ingestion/coordinator.py#L15-L16) → `DataSource`, `SourceFetchError`, `IngestionLog`
- [metadata.py:10](apps/port/src/ditto_port/services/ingestion/metadata.py#L10) → `IngestionLog`

### 1.2 用户建议方案

> 提供 ingestionlog 的 repo，source 的依赖目前不是有 provider 嘛，直接通过 provider 代理

**当前已有 DataSources** ([hub.py:228](packages/data/src/ditto_data/hub.py#L228)):
```python
@cached_property
def sources(self) -> DataSources:
    """External data sources provider (Tushare, Akshare, etc.)."""
    return DataSources()
```

### 1.3 设计方案

#### 方案 A：创建 IngestionLogAccessor（推荐）

```python
# packages/data/src/ditto_data/accessors/ingestion_log.py

from typing import Literal

from ditto_data.sources.metadata import IngestionLog, IngestionStatus
from ditto_data.stores.ingestion_log import IngestionLogStore
from ditto_foundation import logger


class IngestionLogAccessor:
    """
    摄取日志访问器。

    提供 Accessor 层的抽象，封装 IngestionLogStore 的访问。

    职责：
    - 摄取日志的 CRUD 操作
    - 摄取状态查询和统计
    - 提供业务友好的查询接口
    """

    def __init__(self, log_store: IngestionLogStore) -> None:
        self._log_store = log_store

    # ========== 写入 ==========

    def save(
        self,
        dataset: str,
        source: str,
        trade_date: str,
        status: IngestionStatus,
        checksum: str | None = None,
        rows: int | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> IngestionLog:
        """保存摄取日志记录。"""
        log = IngestionLog(
            dataset=dataset,
            source=source,
            trade_date=trade_date,
            status=status,
            checksum=checksum,
            rows=rows,
            error_code=error_code,
            error_message=error_message,
        )
        return self._log_store.save_log(log)

    # ========== 查询 ==========

    def get(
        self,
        dataset: str,
        source: str,
        trade_date: str,
    ) -> IngestionLog | None:
        """获取指定日期的摄取日志。"""
        return self._log_store.get_log(dataset, source, trade_date)

    def exists(
        self,
        dataset: str,
        source: str,
        trade_date: str,
    ) -> bool:
        """检查指定日期的摄取日志是否存在。"""
        return self._log_store.get_log(dataset, source, trade_date) is not None

    def is_success(
        self,
        dataset: str,
        source: str,
        trade_date: str,
    ) -> bool:
        """检查指定日期是否摄取成功。"""
        log = self._log_store.get_log(dataset, source, trade_date)
        return log is not None and log.status == IngestionStatus.SUCCESS

    # ========== 批量查询 ==========

    def get_ingested_dates(
        self,
        dataset: str,
        source: str = "tushare",
        status: IngestionStatus | None = None,
    ) -> list[str]:
        """获取已摄取的日期列表。"""
        return self._log_store.get_ingested_dates(dataset, source, status)

    def get_failed_dates(
        self,
        dataset: str,
        source: str = "tushare",
        limit: int = 10,
        max_attempts: int = 3,
    ) -> list[str]:
        """获取需要重试的失败日期列表。"""
        return self._log_store.get_failed_dates(dataset, source, limit, max_attempts)

    def get_last_success_date(
        self,
        dataset: str,
        source: str = "tushare",
    ) -> str | None:
        """获取最后成功的交易日期。"""
        return self._log_store.get_last_success_date(dataset, source)

    # ========== 统计 ==========

    def get_stats(
        self,
        dataset: str,
        source: str = "tushare",
    ) -> dict[str, int]:
        """获取摄取统计信息。"""
        return self._log_store.get_stats(dataset, source)

    def get_success_rate(
        self,
        dataset: str,
        source: str = "tushare",
        start_date: str | None = None,
    ) -> float:
        """获取成功率。"""
        return self._log_store.get_success_rate(dataset, source, start_date)
```

#### DataHub 修改

```python
# packages/data/src/ditto_data/hub.py

@cached_property
def ingestion_log(self) -> IngestionLogAccessor:
    """摄取日志访问器。"""
    return IngestionLogAccessor(
        log_store=self.ingestion_log,
    )
```

### 1.4 Source 依赖处理（用户方案）

**用户决定**：
1. **`IngestionLog`** - 定义在 `datahub.models` 包，通过 accessor 暴露给上层
2. **`DataSource` 等** - 保留在 sources 层，通过 provider 代理

**新的分层结构**：
```
packages/data/
├── models/                    # 新增：领域类型层
│   ├── __init__.py
│   ├── ingestion.py           # IngestionLog, IngestionStatus
│   └── ...
├── sources/                   # 数据源层
│   ├── base.py                # DataSource, SourceFetchError
│   └── provider.py            # DataSources
├── accessors/                 # 访问器层
│   └── ingestion_log.py       # 使用 models.IngestionLog
└── stores/                    # 存储层
    └── ingestion_log.py       # 使用 models.IngestionLog
```

**迁移计划**：
1. 创建 `packages/data/src/ditto_data/models/` 目录
2. 移动 `IngestionLog`, `IngestionStatus` 到 `models.ingestion`
3. 更新所有引用：
   - `sources.metadata` → `models.ingestion`
   - `stores.ingestion_log` → 使用 `models.ingestion`
   - `accessors.ingestion_log` → 使用 `models.ingestion`
4. apps/port 从 `models` 导入类型，从 accessors 导入 Accessor

---

## 二、第 6 点：减少动态调用（✅ 已完成）

### 2.1 当前问题

[coordinator.py:331-353](apps/port/src/ditto_port/services/ingestion/coordinator.py#L331-L353):
```python
def _fetch_data(self, dataset: str, trade_date: str) -> pl.DataFrame:
    method_name = self._DATASET_METHODS.get(dataset)
    source_method = getattr(self._source, method_name, None)
    if source_method is None or not callable(source_method):
        raise ValueError(f"Source 方法不存在: {method_name}")

    # 动态调用（需要 # type: ignore）
    result = source_method(trade_date)  # type: ignore[call-arg]
```

### 2.2 match/case 方案（用户选择）

```python
# coordinator.py 修改后
def _fetch_data(self, dataset: str, trade_date: str) -> pl.DataFrame:
    """根据数据集类型调用对应的 Source 方法获取数据（使用 match/case）。"""
    match dataset:
        case "calendar":
            return self._source.fetch_calendar(trade_date, trade_date)
        case "etf_basic" | "stock_basic":
            # basic 类数据集不需要 trade_date 参数
            if dataset == "etf_basic":
                return self._source.fetch_etf_basic()
            else:  # stock_basic
                return self._source.fetch_stock_basic()
        case "etf_daily":
            return self._source.fetch_etf_daily(trade_date)
        case "stock_daily":
            return self._source.fetch_stock_daily(trade_date)
        case "adj_factor":
            return self._source.fetch_adj_factor(trade_date)
        case "fund_adj":
            return self._source.fetch_fund_adj(trade_date)
        case _:
            raise ValueError(f"不支持的数据集: {dataset}")
```

**优势**：
1. 编译期类型检查，无需 `# type: ignore`
2. 代码更直观，每个分支清晰
3. 容易添加新数据集
4. 不需要维护 `_DATASET_METHODS` 字典

### 2.3 实现总结（2026-01-17 完成）

**最终实现方式**：使用字典映射（而非 match/case）

```python
# packages/data/src/ditto_data/models/common.py
class Dataset(str, Enum):
    """支持的数据集类型。"""
    STOCK_BASIC = "stock_basic"
    ETF_BASIC = "etf_basic"
    CALENDAR = "calendar"
    STOCK_DAILY = "stock_daily"
    ETF_DAILY = "etf_daily"
    ADJ_FACTOR = "adj_factor"
    FUND_ADJ = "fund_adj"

# apps/port/src/ditto_port/services/ingestion/coordinator.py
def _fetch_data(self, dataset: str, trade_date: str) -> pl.DataFrame:
    """使用字典映射替代动态 getattr 调用，易于扩展新数据集。"""
    handlers: dict[str, Callable[[], pl.DataFrame]] = {
        Dataset.CALENDAR.value: lambda: self._source.fetch_calendar(
            trade_date, trade_date
        ),
        Dataset.STOCK_BASIC.value: lambda: self._source.fetch_stock_basic(),
        # ... 其他数据集
    }

    if dataset not in handlers:
        raise ValueError(f"不支持的数据集: {dataset}")

    return handlers[dataset]()
```

**改动文件**：
- ✅ `packages/data/src/ditto_data/models/common.py` - 新增 Dataset 枚举
- ✅ `packages/data/src/ditto_data/models/__init__.py` - 导出 Dataset
- ✅ `packages/data/tests/unit/models/test_common_unit.py` - 新增测试
- ✅ `apps/port/src/ditto_port/services/ingestion/coordinator.py` - 重构 _fetch_data
- ✅ 移除 `_DATASET_METHODS` 字典和动态 getattr 调用

**验证结果**：
- ✅ 所有测试通过（37 个 coordinator 测试）
- ✅ pyright 类型检查通过（0 错误）
- ✅ ruff 代码检查通过（0 警告，无 noqa）

---

## 三、第 7 点：减少重复代码（日志装饰器）- 业界最佳实践

### 3.1 当前情况分析

审计报告显示 **134 处日志记录**，当前模式：
```python
logger.info(
    "开始摄取数据",
    event="ingestion_start",
    dataset=dataset,
    trade_date=trade_date,
)
```

**评估**：
- ✅ 已经是结构化日志格式（使用键值对）
- ✅ loguru 本身是业界推荐的库
- ⚠️ 存在重复的日志模式（开始/完成/失败）

### 3.2 业界最佳实践参考

根据 [Python Logging Best Practices](https://www.carmatec.com/blog/python-logging-best-practices-complete-guide/)、[Signoz 指南](https://signoz.io/guides/python-logging-best-practices/) 和 [Structured Logging](https://www.itguyjournals.com/structured-logging-in-python/)：

| 实践 | 推荐方案 | 当前状态 |
|------|----------|----------|
| 结构化日志 | JSON 键值对 | ✅ 已使用 loguru |
| 日志级别 | 正确使用 DEBUG/INFO/WARNING/ERROR | ✅ 已正确使用 |
| 上下文绑定 | 使用 logger.bind() | ⚠️ 可改进 |
| 装饰器 | 标准操作使用装饰器 | ❌ 未使用 |

### 3.3 推荐方案：混合策略

**方案**：
1. **工具函数** - 用于一次性日志（如业务逻辑中的特定事件）
2. **装饰器** - 用于标准 CRUD 操作（如 Repository 方法）

**不推荐过度使用装饰器**，因为：
- 业界建议只在标准操作（get/write/delete）使用
- 复杂业务逻辑应该显式记录日志，便于调试

```python
# packages/foundation/src/ditto_foundation/logging/context.py

from contextlib import contextmanager
from typing import Any, Generator

from ditto_foundation import logger


def log_event(
    message: str,
    event: str,
    level: str = "info",
    **context: Any,
) -> None:
    """
    结构化日志记录工具函数（用于一次性日志）。

    业界推荐：保持简单，直接使用 logger.info() 也是可接受的方式。
    这个工具函数主要用于统一 event 命名规范。

    Examples:
        >>> log_event(
        ...     "开始摄取数据",
        ...     event="ingestion_start",
        ...     dataset="stock_daily",
        ... )
    """
    log_func = getattr(logger, level)
    log_func(message, event=event, **context)


@contextmanager
def log_operation(
    operation: str,
    **context: Any,
) -> Generator[None, None, None]:
    """
    操作日志上下文管理器（用于需要自动记录开始/结束的场景）。

    业界推荐：用于明确的操作边界，如文件读写、网络请求等。

    Examples:
        >>> with log_operation("write_bars", dataset="stock_daily", year=2024):
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
```

**关键原则**：
- **不过度抽象** - 保持代码可读性比减少几行日志代码更重要
- **显式优于隐式** - 业务逻辑中的关键日志应该显式写出
- **装饰器只用于标准模式** - 如 Repository CRUD、API 端点等

---

## 四、第 4 点：BarsRepository 详细分析 - 共用函数提取

### 4.1 各 Repository 对比分析

| Repository | 行数 | 职责 | 问题分析 |
|-----------|------|------|----------|
| **BarsRepository** | 1081 | 行情数据访问 | ⚠️ 最大，职责过多 |
| **SecurityRepository** | ~495 | 证券主数据 | ✅ 职责清晰 |
| **CalendarRepository** | ~198 | 日历数据 | ✅ 职责清晰，主要是代理 |
| **UniverseRepository** | ~301 | 成分股数据 | ✅ 职责清晰 |
| **AdjFactorRepository** | ~96 | 复权因子 | ✅ 职责清晰 |

**结论**：只有 BarsRepository 有明显问题，其他 Repository 结构良好。

### 4.2 共用函数模式分析

#### 1. 日志记录模式（所有 Repository 都有）

**当前重复代码**：
```python
# BarsRepository:312-318
logger.info("Writing bars data", event="bars_write_start", ...)

# AdjFactorRepository:58-64
logger.info("Writing adj_factor data", event="adj_factor_write_start", ...)

# SecurityRepository:227-233
logger.info("Registering new security", event="security_register_start", ...)
```

**提取方案**：使用 `log_operation` 上下文管理器（已在第三部分定义）

#### 2. 标识符解析模式

**BarsRepository** 和 **SecurityRepository** 都有 SID 解析逻辑：

```python
# BarsRepository:494-519
def _resolve_sids(
    self,
    sids: list[int] | None,
    src_codes: list[str] | None,
    symbols: list[str] | None,
    asof: str | None,
    source: str = "tushare",
) -> list[int]:
    """解析标识符为 SID 列表。"""
    ...
```

**提取方案**：创建通用的标识符解析工具
```python
# packages/data/src/ditto_data/repositories/common/identifier.py

def resolve_sids(
    sids: list[int] | None,
    src_codes: list[str] | None,
    symbols: list[str] | None,
    security_store: SecurityStore,
    asof: str | None,
    source: str = "tushare",
) -> list[int]:
    """
    通用的标识符解析函数。

    Args:
        sids: SID 列表
        src_codes: 源代码列表
        symbols: 代码列表
        security_store: SecurityStore 实例
        asof: 时间点查询日期
        source: 数据源标识符

    Returns:
        解析后的 SID 列表
    """
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

#### 3. 指标记录模式（所有 Repository 都有）

**当前重复代码**：
```python
# 所有 Repository 都有
M.data_records.add(len(result), {"dataset": "xxx", "operation": "get"})
```

**提取方案**：创建装饰器或工具函数
```python
# packages/foundation/src/ditto_foundation/metrics/tracking.py

from functools import wraps
from ditto_foundation import M

def track_metrics(dataset: str, operation: str):
    """
    指标记录装饰器。

    Examples:
        >>> @track_metrics("bars", "get")
        ... def get(self, query: BarsQuery) -> pl.DataFrame:
        ...     ...
    """
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

#### 4. 文件锁 + 写入模式（多个 Repository 都有）

**当前重复代码**：
```python
# BarsRepository:320-322
lock_name = f"bars_write_{dataset}_{year}"
with self._file_lock.acquire(lock_name, timeout=60.0):
    result = self._bars_store.write(dataset, df, year, on_duplicate=on_duplicate)

# AdjFactorRepository:67-72
lock_name = f"adj_factor_write_{dataset}_{year}"
with self._file_lock.acquire(lock_name, timeout=60.0):
    result = self._adj_factor_store.write(dataset, df, year, on_duplicate=on_duplicate)
```

**提取方案**：创建通用的写入上下文管理器
```python
# packages/data/src/ditto_data/runtime/write_guard.py

from contextlib import contextmanager
from ditto_data.runtime.file_lock import FileLockManager
from ditto_foundation import logger

@contextmanager
def write_with_lock(
    file_lock: FileLockManager,
    lock_name: str,
    operation: str,
    **context: Any,
):
    """
    带文件锁的写入上下文管理器。

    Examples:
        >>> with write_with_lock(
        ...     self._file_lock,
        ...     f"bars_write_{dataset}_{year}",
        ...     "bars_write",
        ...     dataset=dataset,
        ...     year=year,
        ... ):
        ...     result = self._bars_store.write(...)
    """
    logger.info(f"{operation} start", event=f"{operation}_start", **context)
    with file_lock.acquire(lock_name, timeout=60.0):
        try:
            yield
            logger.info(f"{operation} complete", event=f"{operation}_complete", **context)
        except Exception as e:
            logger.error(f"{operation} failed", event=f"{operation}_failed", error=str(e))
            raise
```

### 4.3 BarsRepository 特有提取（✅ 2026-01-17 已完成）

这些是 BarsRepository 独有的复杂逻辑，已提取为独立模块：

#### 1. 资产类别检测 → AssetSidRange.detect_asset_class()

**用户建议方案**：将资产类别检测作为 `SidRange` 的方法，实现双向映射。

**最终实现**：
- 重命名 `SidRange` → `AssetSidRange`
- 添加 `detect_asset_class(sids)` 类方法
- 更新所有引用（14 个文件）

**优势**：
- 内聚性高：`get_range()` 和 `detect_asset_class()` 形成对称映射
- 减少文件：无需新建独立模块
- 领域逻辑正确：属于模型层而非数据访问层

#### 2. 复权计算 → adjustment.py（✅ 已完成）
```python
# packages/data/src/ditto_data/repositories/bars/adjustment.py
"""
复权计算纯函数模块。

包含 QFQ/HFQ 公式实现，可独立测试。
"""
```

**提取函数**：
- `parse_asof_date()` - 解析 asof 参数
- `filter_baseline_by_asof()` - 过滤 baseline 数据
- `apply_qfq_adj()` - 前复权计算
- `apply_hfq_adj()` - 后复权计算

**代码统计**：151 行（纯函数，易于测试）

#### 3. DQ 过滤函数 → dq_filters.py（✅ 已完成）
```python
# packages/data/src/ditto_data/repositories/bars/dq_filters.py
"""
DQ 违规数据过滤函数。

根据不同 DQ 规则类型过滤失败的数据行。
"""
```

**提取函数**：
- `filter_not_null_violations()` - 过滤非空违规
- `filter_unique_violations()` - 过滤唯一性违规
- `filter_foreign_key_violations()` - 外键违规处理
- `filter_type_check_violations()` - 类型检查违规处理
- `filter_failed_rows()` - 根据规则类型分发

**代码统计**：126 行（纯函数，易于测试）

**验证结果**：
- ✅ pyright 类型检查：0 错误
- ✅ ruff 代码检查：全部通过
- ✅ 单元测试：1398 passed
- ✅ 覆盖率：84.75%（超过 80% 要求）

### 4.4 DQ 编排逻辑移除（~170 行）

**当前问题**：BarsRepository 包含 DQ 检查、隔离、报告生成逻辑（~170 行）

**移除方案**：
1. 删除 `run_dq_check` 参数
2. 删除 `_save_to_quarantine_from_result` 方法
3. 删除 `_generate_dq_report` 方法
4. Repository 只负责纯写入
5. DQ 检查移至 apps/port 的 IngestionCoordinator

**重构后**：1081 行 → ~650 行

---

## 五、实施计划总结

### 5.1 优先级排序

| 优先级 | 任务 | 影响范围 | 预计工作量 |
|--------|------|----------|------------|
| **P0** | 创建 models 包 + IngestionLogAccessor | 架构层级 | 中 |
| **P1** | coordinator.py match/case 重构 | 单文件 | 小 |
| **P2** | 共用函数提取（日志/指标/写入） | 多文件 | 中 |
| **P2** | BarsRepository 重构 | bars.py | 大 |

### 5.2 实施顺序

1. **P0 - 创建 models 包**
   - 创建 `packages/data/src/ditto_data/models/` 目录
   - 移动 `IngestionLog`, `IngestionStatus` 到 `models.ingestion`
   - 创建 `IngestionLogAccessor`
   - 更新 DataHub

2. **P1 - coordinator.py 重构**
   - 使用 match/case 替换动态调用
   - 移除 `_DATASET_METHODS` 字典

3. **P2 - 共用函数提取**
   - 创建 `log_operation` 上下文管理器
   - 创建 `write_with_lock` 上下文管理器
   - 创建 `track_metrics` 装饰器
   - 创建 `resolve_sids` 工具函数

4. **P2 - BarsRepository 重构**
   - 提取复权计算到 `adjustment.py`
   - 提取资产类别检测到 `asset_class.py`
   - 提取 DQ 过滤函数到 `dq_filters.py`
   - 移除 DQ 编排逻辑

### 5.3 验证命令

```bash
# 类型检查
pixi run -e dev type

# 代码检查
pixi run -e dev lint

# 单元测试
pixi run -e dev test --unit

# 完整检查
pixi run -e dev ci
```

---

## 六、关键文件清单

### 6.1 需要新建的文件

| 文件 | 用途 |
|------|------|
| `packages/data/src/ditto_data/models/__init__.py` | 领域类型包 |
| `packages/data/src/ditto_data/models/ingestion.py` | IngestionLog, IngestionStatus |
| `packages/data/src/ditto_data/accessors/ingestion_log.py` | IngestionLogAccessor |
| `packages/foundation/src/ditto_foundation/logging/context.py` | log_operation, log_event |
| `packages/foundation/src/ditto_foundation/metrics/tracking.py` | track_metrics 装饰器 |
| `packages/data/src/ditto_data/runtime/write_guard.py` | write_with_lock |
| `packages/data/src/ditto_data/repositories/common/identifier.py` | resolve_sids |
| `packages/data/src/ditto_data/repositories/bars/adjustment.py` | 复权计算 |
| `packages/data/src/ditto_data/repositories/bars/asset_class.py` | 资产类别检测 |
| `packages/data/src/ditto_data/repositories/bars/dq_filters.py` | DQ 过滤函数 |

### 6.2 需要修改的文件

| 文件 | 修改内容 |
|------|----------|
| `packages/data/src/ditto_data/hub.py` | 添加 ingestion_log |
| `apps/port/src/ditto_port/services/ingestion/coordinator.py` | match/case 重构 |
| `apps/port/src/ditto_port/services/ingestion/metadata.py` | 使用 models.ingestion |
| `apps/port/src/ditto_port/services/ingestion/backfill.py` | 使用 Accessor |
| `apps/port/src/ditto_port/services/ingestion/retry.py` | 使用 Repository |
| `packages/data/src/ditto_data/accessors/bars.py` | 重构提取共用函数 |
| `packages/data/src/ditto_data/stores/ingestion_log.py` | 使用 models.ingestion |
| `packages/data/src/ditto_data/sources/metadata.py` | 迁移到 models.ingestion |
