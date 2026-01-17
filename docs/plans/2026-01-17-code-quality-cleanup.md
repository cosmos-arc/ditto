# Ditto 代码质量优化计划

## 概述

基于架构审计报告，本计划修复代码库中的工程实践问题和架构约束问题（排除 BarsRepository 拆分、TODO 实现和 DQ Checkers Any 类型污染）。

**创建日期**：2026-01-17
**预计工作量**：12 个 PR，涉及约 35 个文件

---

## 问题详细说明

### 1. ARCH-003: Coordinator type:ignore（保留现状）

**详细分析**：
```python
# coordinator.py:335-356
def _fetch_data(self, dataset: str, trade_date: str) -> pl.DataFrame:
    method_name = self._DATASET_METHODS.get(dataset)
    source_method = getattr(self._source, method_name, None)

    # 根据 dataset 动态调用不同方法，参数签名不同
    if dataset == "calendar":
        result = source_method(trade_date, trade_date)  # 2参数
    elif dataset in ("etf_basic", "stock_basic"):
        result = source_method()  # 0参数
    else:
        result = source_method(trade_date)  # 1参数
```

**为何需要 type:ignore**：
- 使用 `getattr()` 动态获取方法，类型检查器无法推断返回类型
- 不同方法的参数签名不同（0/1/2 个参数）
- 这是 Python 动态特性的典型场景

**评估结论**：✅ **保留 type:ignore** - 修改会增加大量样板代码（`@overload`）但收益很小。

---

### 2. ENG-010: WriteResult 重复定义（统一为 WriteResultStore）

**问题分析**：
```python
# types.py:20-28 - 外层使用的 WriteResult
@dataclass(frozen=True)
class WriteResult:
    file_path: str
    checksum: str
    rows_written: int
    rows_total: int
    blocked: bool
    dq_result: DQResultNew | None

# types.py:31-40 - 存储层使用的 WriteResultStore
@dataclass(frozen=True)
class WriteResultStore:
    file_path: str
    checksum: str
    added: int
    updated: int
    skipped: int
    is_merge: bool

# parquet_store_base.py:24-32 - 重复定义（应使用 WriteResultStore）
@dataclass(frozen=True)
class WriteResult:  # ← 重复！
    file_path: str
    checksum: str
    added: int
    updated: int
    skipped: int
    is_merge: bool
```

**字段对比**：
| 关注点 | types.WriteResult | types.WriteResultStore |
|--------|-------------------|------------------------|
| 用途 | Repository/上层返回 | Store 层内部使用 |
| 写入统计 | rows_written/rows_total | added/updated/skipped |
| DQ 结果 | ✅ 包含 | ❌ 不包含 |
| 合并信息 | is_merge | is_merge |

**修复方案**：
- 删除 `parquet_store_base.py` 中的 `WriteResult` 定义
- 导入并使用 `types.WriteResultStore`
- 更新 `__all__` 导出列表

---

### 3. ENG-006: TYPE_CHECKING 全面清理（必须重构）

**重要发现**：经过全面分析，**不存在循环依赖**，但存在 **15 处不必要的 TYPE_CHECKING 使用**！

#### 依赖关系验证
```bash
# 在 packages/datahub 中搜索 "from ditto_port" 或 "import ditto_port"
# 结果：0 个匹配 ✅

# DataHub 完全不依赖 Port 层
# 依赖方向：Port → DataHub（单向，符合架构设计）
```

#### TYPE_CHECKING 使用分类统计

**🔴 P0：必须删除（5 个）** - 空的 `if TYPE_CHECKING: pass` 代码块

| 文件 | 行号 | 操作 |
|------|------|------|
| `apps/port/src/ditto_port/jobs/flows/repair.py` | 18 | 删除空块 |
| `apps/port/src/ditto_port/jobs/flows/helpers.py` | 16 | 删除空块 |
| `apps/port/src/ditto_port/jobs/flows/daily.py` | 36 | 删除空块 |
| `apps/port/src/ditto_port/jobs/flows/backfill.py` | 19 | 删除空块 |
| `packages/datahub/src/ditto_datahub/sources/accessor.py` | 13 | 删除空块 |

**🟡 P1：应该删除（10 个）** - 可安全改为直接导入

| 文件 | 行号 | 导入内容 | 原因 |
|------|------|---------|------|
| `packages/foundation/src/ditto_foundation/util/checksum.py` | 13 | `from collections.abc import Sequence` | 标准库类型 |
| `apps/port/src/ditto_port/services/ingestion/retry.py` | 21 | `IngestionLogStore` | port → datahub 单向依赖 |
| `apps/port/src/ditto_port/services/ingestion/coordinator.py` | 23 | `DataHub` | port → datahub 单向依赖 |
| `apps/port/src/ditto_port/services/ingestion/config/datasets.py` | 22 | `from collections.abc import Iterator` | 标准库类型 |
| `packages/datahub/src/ditto_datahub/repositories/universe.py` | 18 | `SidAllocator` | repository → runtime 单向依赖 |
| `packages/datahub/src/ditto_datahub/repositories/security.py` | 13 | `SidAllocator` | repository → runtime 单向依赖 |
| `packages/datahub/src/ditto_datahub/runtime/sql_engine.py` | 15 | `CalendarStore`, `SecurityStore` | runtime → stores 单向依赖 |
| `packages/datahub/src/ditto_datahub/runtime/sid_allocator.py` | 9 | `SQLitePool` | 同层内部依赖 |
| `packages/datahub/src/ditto_datahub/repositories/bars.py` | 27 | `DQIssue` | repository → dq 单向依赖 |
| `apps/port/src/ditto_port/services/ingestion/backfill.py` | 14 | `CalendarStore`, `IngestionLogStore` | port → datahub 单向依赖 |
| `apps/port/src/ditto_port/cli/executor.py` | 12 | `DataHub` | port → datahub 单向依赖 |

**关于 GaugeWrapper Protocol 的分析**：
- `SimpleGauge` 类定义在 line 312，`M` 类定义在 line 382
- 不存在循环依赖问题
- `GaugeWrapper` 是不必要的抽象层，可直接使用 `SimpleGauge` 作为类型注解

#### 重构原则
根据项目规范：
> "禁止使用`TYPE_CHECKING`的延迟导入方式解决循环依赖（必须重构代码及架构解决），非必要`禁止延迟导入`"

**当前状态**：
- ✅ 无循环依赖 - 所有 TYPE_CHECKING 都不是必须的
- ❌ 过度使用 - 15 处使用中，15 处全部可以删除
- 🎯 行动：删除所有 TYPE_CHECKING

---

## 修复任务清单

### PR-1: 修复异常处理缺失上下文（ENG-002）【P0】

**文件**：
- `packages/datahub/src/ditto_datahub/stores/calendar_store.py:597`
- `packages/datahub/src/ditto_datahub/stores/security_store.py:586`
- `packages/datahub/src/ditto_datahub/stores/quarantine_store.py:156`
- `packages/datahub/src/ditto_datahub/stores/bars_store.py:70`
- `packages/datahub/src/ditto_datahub/runtime/sid_allocator.py:85`

**修改**：
```python
# 修改前
except Exception:
    self._client.rollback()
    logger.error("Operation failed", event="op_failed")
    raise

# 修改后
except Exception as e:
    self._client.rollback()
    logger.error(
        "Operation failed",
        event="op_failed",
        error_type=type(e).__name__,
        error_message=str(e),
    )
    raise
```

---

### PR-2: 统一 enrich_with_symbol 实现（ENG-001）【P1】

**文件**：
- `packages/datahub/src/ditto_datahub/repositories/index.py`

**修改**：
```python
# 删除 _enrich_with_symbol 方法
# 改为调用 SecurityStore.enrich_with_symbol
def get_constituents(self, ...) -> pl.DataFrame:
    df = self._security_store.find_securities(...)
    return self._security_store.enrich_with_symbol(df)
```

---

### PR-3: TushareClient 资源管理（ENG-003）【P1】

**文件**：
- `packages/datahub/src/ditto_datahub/sources/tushare/client.py`

**修改**：
```python
def close(self) -> None:
    """显式关闭 HTTP 客户端"""
    if hasattr(self, "_client"):
        self._client.close()

def __enter__(self) -> "TushareClient":
    return self

def __exit__(self, *args):  # type: ignore
    self.close()
```

---

### PR-4: 替换 MD5 为 xxhash（ENG-004）【P2】

**文件**：
- `packages/datahub/src/ditto_datahub/runtime/sql_engine.py:248`

**修改**：
```python
import xxhash
cache_key = xxhash.xxh3_64_hexdigest(normalized.encode())
```

---

### PR-5: 硬编码日期提取为常量（ENG-005）【P2】

**文件**：
- `packages/datahub/src/ditto_datahub/stores/bars_store.py:154-155`

**修改**：
```python
# 在文件顶部添加常量
DEFAULT_START_YEAR = 1990
DEFAULT_END_YEAR = 2099

# 使用常量
start_year = int(start_date[:4]) if start_date else DEFAULT_START_YEAR
end_year = int(end_date[:4]) if end_date else DEFAULT_END_YEAR
```

---

### PR-6: QuarantineStore 吞异常（ENG-007）【P1】

**文件**：
- `packages/datahub/src/ditto_datahub/stores/quarantine_store.py:156`

**修改**：
```python
try:
    data_dicts = orjson.loads(row[0])
    return pl.DataFrame(data_dicts)
except (orjson.JSONDecodeError, pl.SchemaError) as e:
    logger.error(
        "Failed to parse quarantined data",
        event="quarantine_parse_failed",
        row_id=row_id,
        error=str(e),
    )
    return pl.DataFrame()  # 返回空 DataFrame 而非 None
```

---

### PR-7: 统一 WriteResult 定义（ENG-010）【P1】

**文件**：
- `packages/datahub/src/ditto_datahub/stores/parquet_store_base.py`
- `packages/datahub/src/ditto_datahub/types.py`

**修改**：
```python
# parquet_store_base.py: 删除本地 WriteResult 定义
# 从 types.py 导入 WriteResultStore
from ditto_datahub.types import WriteResultStore as WriteResult

# 或者统一使用 WriteResultStore 作为返回类型
```

---

### PR-8: 删除未使用的 DataSourceMethods Protocol【P0】

**文件**：
- `packages/datahub/src/ditto_datahub/sources/base.py:12-41`

**问题**：
```python
# line 12-41: DataSourceMethods Protocol - 完全未使用
class DataSourceMethods(Protocol):
    """数据源方法协议（类型检查用）."""

    @abstractmethod
    def fetch_calendar(self, start_date: str, end_date: str) -> pl.DataFrame: ...

    # ... 更多方法定义
```

**分析**：
- 全局搜索显示 `DataSourceMethods` 从未被引用
- `DataSource` ABC 已经提供了完整的接口定义
- `DataSourceMethods` 是冗余的抽象层

**修改**：直接删除 `DataSourceMethods` Protocol 定义（line 12-41）。

---

### PR-9: 删除未使用的 get_source() 工厂函数【P1】

**文件**：
- `packages/datahub/src/ditto_datahub/sources/factory.py`（整个文件）
- `packages/datahub/src/ditto_datahub/sources/__init__.py:13,26`（移除导入和导出）

**问题**：
```python
# factory.py:9-33
def get_source(name: str) -> DataSource:
    """Factory function to get DataSource instance."""
    normalized_name = name.lower().strip()
    if normalized_name == "tushare":
        return TushareSource()
    if normalized_name == "akshare":
        raise ValueError(...)
    raise ValueError(...)
```

**分析**：
- 全局搜索生产代码：**0 处使用**
- 测试代码：仅 `test_base_unit.py` 中测试此函数
- 功能与 `SourcesAccessor` 重复
- `DataHub` 使用 `SourcesAccessor`，不是 `get_source()`

**修改**：
1. 删除 `factory.py` 整个文件
2. 从 `sources/__init__.py` 移除 `get_source` 的导入和导出
3. 删除 `test_base_unit.py` 中对 `get_source` 的测试（line 195-230）

---

### PR-10: 清理 Any 类型滥用（ENG-008）【P2】

**文件**：
- `packages/datahub/src/ditto_datahub/dq/engine.py:125`
- `packages/datahub/src/ditto_datahub/alerts/manager.py:33`

**修改**：
```python
# Cache 使用泛型
T = TypeVar("T")
def get(self, key: str, default: T | None = None) -> T | None: ...

# AlertManager context 使用具体类型
def send_alert(
    self,
    level: AlertLevel,
    message: str,
    context: dict[str, str | int | float | bool],  # 具体类型而非 Any
) -> None: ...
```

---

### PR-11: 清理 TYPE_CHECKING（ENG-006）【P0/P1】

#### PR-11.1: 删除空的 TYPE_CHECKING 块【P0】

**文件**（5 个）：
- `apps/port/src/ditto_port/jobs/flows/repair.py:18`
- `apps/port/src/ditto_port/jobs/flows/helpers.py:16`
- `apps/port/src/ditto_port/jobs/flows/daily.py:36`
- `apps/port/src/ditto_port/jobs/flows/backfill.py:19`
- `packages/datahub/src/ditto_datahub/sources/accessor.py:13`

**修改**：直接删除 `if TYPE_CHECKING: pass` 代码块和对应的 `from typing import TYPE_CHECKING` 导入。

#### PR-11.2: 删除不必要的 TYPE_CHECKING，改为直接导入【P1】

**文件**（11 个）：
- `packages/foundation/src/ditto_foundation/util/checksum.py:13`
- `packages/foundation/src/ditto_foundation/observability/metrics.py:71` ← **删除 GaugeWrapper Protocol**
- `apps/port/src/ditto_port/services/ingestion/retry.py:21`
- `apps/port/src/ditto_port/services/ingestion/coordinator.py:23`
- `apps/port/src/ditto_port/services/ingestion/config/datasets.py:22`
- `packages/datahub/src/ditto_datahub/repositories/universe.py:18`
- `packages/datahub/src/ditto_datahub/repositories/security.py:13`
- `packages/datahub/src/ditto_datahub/runtime/sql_engine.py:15`
- `packages/datahub/src/ditto_datahub/runtime/sid_allocator.py:9`
- `packages/datahub/src/ditto_datahub/repositories/bars.py:27`
- `apps/port/src/ditto_port/services/ingestion/backfill.py:14`
- `apps/port/src/ditto_port/cli/executor.py:12`

**修改**：

**通用模式**：
```python
# 修改前
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from ditto_datahub.hub import DataHub

class Foo:
    hub: "DataHub"

# 修改后
from ditto_datahub.hub import DataHub

class Foo:
    hub: DataHub
```

**metrics.py 特殊处理**：
```python
# 删除 line 71-86 的 GaugeWrapper Protocol 定义
# 修改 M 类的类型注解，从 "GaugeWrapper" 改为 SimpleGauge

# 修改前
if TYPE_CHECKING:
    class GaugeWrapper(Protocol):
        def set(self, value: float) -> None: ...
        ...

class M:
    data_freshness: "GaugeWrapper"
    ...

# 修改后（删除 GaugeWrapper，直接使用 SimpleGauge）
class M:
    data_freshness: SimpleGauge
    factor_ic: SimpleGauge
    portfolio_value: SimpleGauge
    ...
```

---

## PR 执行顺序

| PR | 优先级 | 依赖 | 风险 | 工作量 | 说明 |
|----|--------|------|------|--------|------|
| PR-1 | P0 | 无 | 低 | S | 异常处理 |
| PR-8 | P0 | 无 | 低 | S | 删除 DataSourceMethods Protocol |
| PR-11.1 | P0 | 无 | 低 | S | 删除空 TYPE_CHECKING 块 |
| PR-2 | P1 | 无 | 低 | S | 统一 enrich_with_symbol |
| PR-3 | P1 | 无 | 低 | S | TushareClient 资源管理 |
| PR-6 | P1 | 无 | 低 | S | QuarantineStore 吞异常 |
| PR-9 | P1 | 无 | 低 | M | 删除 get_source() 工厂函数 |
| PR-11.2 | P1 | 无 | 低 | M | TYPE_CHECKING 改为直接导入（含删除 GaugeWrapper）|
| PR-7 | P1 | 无 | 中 | M | 统一 WriteResult |
| PR-4 | P2 | 无 | 低 | S | MD5 → xxhash |
| PR-5 | P2 | 无 | 低 | S | 硬编码日期提取常量 |
| PR-10 | P2 | 无 | 中 | M | 清理 Any 类型 |

**总计**：12 个 PR，涉及约 35 个文件

---

## 验证计划

### 测试命令
```bash
# 完整检查
pixi run -e dev ci

# 单独测试
pixi run -e dev test --unit
pixi run -e dev type
pixi run -e dev lint

# PIT 测试
pixi run -e dev test-pit
```

### 关键测试文件
- `tests/unit/datahub/stores/test_calendar_store.py`
- `tests/unit/datahub/stores/test_security_store.py`
- `tests/unit/datahub/stores/test_quarantine_store.py`
- `tests/unit/datahub/runtime/test_sid_allocator.py`
- `tests/unit/datahub/sources/test_tushare_client.py`
- `tests/unit/datahub/sources/test_base_unit.py`

---

## 执行状态

| PR | 状态 | 完成日期 | 备注 |
|----|------|---------|------|
| PR-1 | ✅ 完成 | 2026-01-17 | 修复异常处理缺失上下文（3 个文件） |
| PR-2 | ✅ 完成 | 2026-01-17 | 统一 enrich_with_symbol 实现 |
| PR-3 | ✅ 完成 | 2026-01-17 | TushareClient 资源管理 |
| PR-4 | 待执行 | | |
| PR-5 | 待执行 | | |
| PR-6 | ✅ 完成 | 2026-01-17 | QuarantineStore 吞异常 |
| PR-7 | ✅ 完成 | 2026-01-17 | 统一 WriteResult 定义 |
| PR-8 | ✅ 完成 | 2026-01-17 | 删除 DataSourceMethods Protocol |
| PR-9 | ✅ 完成 | 2026-01-17 | 删除 get_source() 工厂函数 |
| PR-10 | 待执行 | | |
| PR-11.1 | ✅ 完成 | 2026-01-17 | 删除空 TYPE_CHECKING 块（5 个文件） |
| PR-11.2 | ✅ 完成 | 2026-01-17 | 清理 TYPE_CHECKING（12 个文件） |

---

## 参考文档

- [项目核心规范](../../.claude/rules/core.md)
- [数据访问层规范](../../.claude/rules/datahub.md)
- [Python 测试规范](../../.claude/rules/python-test.md)
- [noqa/ignore 规范](../../.claude/rules/noqa-ignore.md)
- [架构设计文档](../design/02_data_design.md)
