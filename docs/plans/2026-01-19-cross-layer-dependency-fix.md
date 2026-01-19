# 跨层依赖修复计划

## 背景

根据 2026-01-18 架构审计报告 [ARCH-001]，发现 Port 层存在 5 处跨层访问 Store 的问题。经分析确认：

- **实际违规**: 3 处（backfill.py, metadata.py, retry.py）
- **合理设计**: 1 处（coordinator.py - 摄取协调器需要直接使用 DataSource）
- **已正确使用 Accessor**: 1 处（dq_batch.py - 使用 BarsQuery）

## 架构问题分析

### 当前问题

```
Port 层                      DataHub 层
──────────────────────────────────────────────────────
backfill.py          ──→      CalendarStore        ❌
metadata.py          ──→      IngestionLogStore    ❌
retry.py             ──→      IngestionLogStore    ❌
coordinator.py       ──→      DataSource         ✅ (合理)
dq_batch.py          ──→      BarsQuery            ✅ (正确)
```

### 目标架构

```
Port 层                      DataHub 层
──────────────────────────────────────────────────────
backfill.py          ──→      CalendarAccessor      ✅
                             IngestionLogAccessor   ✅

metadata.py          ──→      IngestionLogAccessor  ✅
                             models.ingestion       ✅

retry.py             ──→      IngestionLogAccessor   ✅
```

## 解决方案

### Phase 1: 创建 models 层（领域模型层）

**目的**: 修复 ARCH-004（IngestionLog 模型位置不当）

#### 1.1 创建目录结构

```
packages/datahub/src/ditto_datahub/
├── models/                    # 新增：领域类型层
│   ├── __init__.py
│   ├── ingestion.py           # IngestionLog, IngestionStatus
│   └── common.py              # 共享模型（预留）
```

#### 1.2 移动 IngestionLog

**从**: `packages/datahub/src/ditto_datahub/sources/metadata.py`
**到**: `packages/datahub/src/ditto_datahub/models/ingestion.py`

**更新导出**:
- `sources/metadata.py`: 从 `models.ingestion` 导入并重新导出（向后兼容）
- `models/__init__.py`: 导出 `IngestionLog`, `IngestionStatus`

#### 1.3 更新所有引用

| 文件 | 改动 |
|------|------|
| `stores/ingestion_log.py` | `from ..models.ingestion import IngestionLog, IngestionStatus` |
| `hub.py` | `from .models.ingestion import IngestionLog, IngestionStatus` |
| `accessors/*.py` | 统一从 models 导入 |
| Port 层文件 | `from ditto_datahub.models import IngestionLog, IngestionStatus` |
| 测试文件 | 同样更新导入 |

---

### Phase 2: 创建 IngestionLogAccessor

**目的**: 修复 ARCH-001（Port 层跨层访问 IngestionLogStore）

#### 2.1 创建 Accessor

**文件**: `packages/datahub/src/ditto_datahub/accessors/ingestion_log.py`

```python
"""摄取日志访问器."""

from loguru import logger
from opentelemetry import trace

from ditto_datahub.models.ingestion import IngestionLog, IngestionStatus
from ditto_datahub.stores.ingestion_log import IngestionLogStore
from ditto_foundation.observability.tracing import traced


class IngestionLogAccessor:
    """摄取日志访问器.

    提供摄取日志的查询和管理接口。
    """

    def __init__(self, ingestion_log_store: IngestionLogStore) -> None:
        """初始化访问器.

        Args:
            ingestion_log_store: 摄取日志存储
        """
        self._ingestion_log_store = ingestion_log_store

    @traced("accessor.ingestion_log.save_log")
    def save_log(self, log: IngestionLog) -> IngestionLog:
        """保存摄取日志.

        Args:
            log: 摄取日志记录

        Returns:
            保存后的日志记录
        """
        logger.info(
            "Saving ingestion log",
            event="ingestion_log_save_start",
            dataset=log.dataset,
            source=log.source,
            trade_date=log.trade_date,
            status=log.status.value,
        )
        result = self._ingestion_log_store.save_log(log)
        logger.info(
            "Ingestion log saved",
            event="ingestion_log_save_complete",
            dataset=log.dataset,
            trade_date=log.trade_date,
        )
        return result

    @traced("accessor.ingestion_log.get_log")
    def get_log(
        self,
        dataset: str,
        source: str,
        trade_date: str,
    ) -> IngestionLog | None:
        """获取指定日期的摄取日志.

        Args:
            dataset: 数据集名称
            source: 数据源标识
            trade_date: 交易日期 (YYYY-MM-DD)

        Returns:
            摄取日志记录，不存在则返回 None
        """
        return self._ingestion_log_store.get_log(dataset, source, trade_date)

    @traced("accessor.ingestion_log.get_failed_dates")
    def get_failed_dates(
        self,
        dataset: str,
        source: str = "tushare",
        limit: int = 10,
        max_attempts: int = 3,
    ) -> list[str]:
        """获取失败的交易日期.

        Args:
            dataset: 数据集名称
            source: 数据源标识
            limit: 返回数量限制
            max_attempts: 最大尝试次数

        Returns:
            失败的交易日期列表 (YYYY-MM-DD)
        """
        return self._ingestion_log_store.get_failed_dates(
            dataset, source, limit, max_attempts
        )

    @traced("accessor.ingestion_log.get_ingested_dates")
    def get_ingested_dates(
        self,
        dataset: str,
        source: str = "tushare",
    ) -> list[str]:
        """获取已摄取的日期列表.

        Args:
            dataset: 数据集名称
            source: 数据源标识

        Returns:
            已成功摄取的交易日期列表
        """
        return self._ingestion_log_store.get_ingested_dates(dataset, source)

    @traced("accessor.ingestion_log.get_stats")
    def get_stats(
        self,
        dataset: str,
        source: str = "tushare",
    ) -> dict[str, int]:
        """获取摄取统计.

        Args:
            dataset: 数据集名称
            source: 数据源标识

        Returns:
            统计信息字典
        """
        return self._ingestion_log_store.get_stats(dataset, source)

    @traced("accessor.ingestion_log.get_last_success_date")
    def get_last_success_date(
        self,
        dataset: str,
        source: str = "tushare",
    ) -> str | None:
        """获取最后成功的交易日期.

        Args:
            dataset: 数据集名称
            source: 数据源标识

        Returns:
            最后成功的交易日期 (YYYY-MM-DD)，无记录则返回 None
        """
        return self._ingestion_log_store.get_last_success_date(dataset, source)
```

#### 2.2 更新 DataHub

**文件**: `packages/datahub/src/ditto_datahub/hub.py`

```python
# 将现有的 ingestion_log 属性重命名为 ingestion_log_store
@cached_property
def ingestion_log_store(self) -> IngestionLogStore:
    """摄取日志存储."""
    return IngestionLogStore(
        sqlite_pool=self.sqlite_pool,
        sql_engine=self.sql_engine,
    )

# 新增 ingestion_log Accessor 属性
@cached_property
def ingestion_log(self) -> IngestionLogAccessor:
    """摄取日志访问器."""
    return IngestionLogAccessor(
        ingestion_log_store=self.ingestion_log_store,
    )
```

#### 2.3 更新 accessors/__init__.py

```python
from .ingestion_log import IngestionLogAccessor

__all__ = [
    "BarsAccessor",
    "CalendarAccessor",
    # ...
    "IngestionLogAccessor",
]
```

---

### Phase 3: 修复 Port 层跨层依赖

#### 3.1 修复 backfill.py

**文件**: `apps/port/src/ditto_port/services/ingestion/backfill.py`

**改动**:
```python
# 删除
# from ditto_datahub.stores.calendar_store import CalendarStore
# from ditto_datahub.stores.ingestion_log import IngestionLogStore

# 修改构造函数签名
def __init__(
    self,
    hub: DataHub,  # 改为使用 DataHub
    # calendar_store: CalendarStore,  # 删除
    # ingestion_log_store: IngestionLogStore,  # 删除
    source: DataSource = ...,  # 保留
) -> None:
    self._hub = hub
    self._source = source
    # 删除
    # self._calendar_store = calendar_store
    # self._ingestion_log_store = ingestion_log_store

# 更新方法调用
# 原来: self._calendar_store.get_range(...)
# 改为: self._hub.calendar.get(...)

# 原来: self._ingestion_log_store.get_ingested_dates(...)
# 改为: self._hub.ingestion_log.get_ingested_dates(...)
```

#### 3.2 修复 metadata.py

**文件**: `apps/port/src/ditto_port/services/ingestion/metadata.py`

**改动**:
```python
# 删除
# from ditto_datahub.stores.ingestion_log import IngestionLogStore

# 修改导入（从 models 导入类型）
from ditto_datahub.models.ingestion import IngestionLog, IngestionStatus

# 修改构造函数
def __init__(self, hub: DataHub) -> None:  # 改为使用 DataHub
    self._hub = hub
    # 删除 self._log_store

# 更新方法调用
# 原来: self._log_store.get_log(...)
# 改为: self._hub.ingestion_log.get_log(...)
```

#### 3.3 修复 retry.py

**文件**: `apps/port/src/ditto_port/services/ingestion/retry.py`

**改动**:
```python
# 删除
# from ditto_datahub.stores.ingestion_log import IngestionLogStore

# 修改构造函数
def __init__(
    self,
    hub: DataHub,  # 改为使用 DataHub
    coordinator: IngestionCoordinator,  # 保留
    source: str = "tushare",  # 保留
) -> None:
    self._hub = hub
    self._coordinator = coordinator
    self._source = source
    # 删除 self._ingestion_log_store

# 更新方法调用
# 原来: self._ingestion_log_store.get_failed_dates(...)
# 改为: self._hub.ingestion_log.get_failed_dates(...)
```

---

## 修改文件清单

### 新增文件

| 文件 | 行数估算 |
|------|----------|
| `packages/datahub/src/ditto_datahub/models/__init__.py` | ~10 |
| `packages/datahub/src/ditto_datahub/models/ingestion.py` | ~60 |
| `packages/datahub/src/ditto_datahub/models/common.py` | ~10（预留） |
| `packages/datahub/src/ditto_datahub/accessors/ingestion_log.py` | ~150 |

### 修改文件

| 文件 | 改动类型 | 说明 |
|------|----------|------|
| `packages/datahub/src/ditto_datahub/sources/metadata.py` | 修改 | 从 models 导入并重新导出 |
| `packages/datahub/src/ditto_datahub/stores/ingestion_log.py` | 修改 | 更新导入 |
| `packages/datahub/src/ditto_datahub/hub.py` | 修改 | 重命名属性 + 新增 Accessor |
| `packages/datahub/src/ditto_datahub/accessors/__init__.py` | 修改 | 导出新 Accessor |
| `apps/port/src/ditto_port/services/ingestion/backfill.py` | 修改 | 使用 Accessor |
| `apps/port/src/ditto_port/services/ingestion/metadata.py` | 修改 | 使用 Accessor |
| `apps/port/src/ditto_port/services/ingestion/retry.py` | 修改 | 使用 Accessor |

### 测试文件更新

| 文件 | 改动类型 |
|------|----------|
| `packages/datahub/tests/unit/stores/test_ingestion_log_store_unit.py` | 更新导入 |
| `packages/datahub/tests/integration/stores/test_ingestion_log_concurrent_integration.py` | 更新导入 |
| `apps/port/tests/unit/ingestion/test_metadata_unit.py` | 更新导入 + Mock |
| `apps/port/tests/unit/ingestion/test_coordinator_unit.py` | 更新导入 |
| `apps/port/tests/unit/ingestion/test_backfill_unit.py` | 更新导入 + Mock |
| `apps/port/tests/unit/ingestion/test_retry_unit.py` | 更新导入 + Mock |
| `apps/port/tests/integration/ingestion/test_coordinator_dq_blocking_integration.py` | 更新导入 |

---

## 验证方案

### 代码质量检查

```bash
# 类型检查
pixi run -e dev type

# 代码检查
pixi run -e dev lint

# 格式检查
pixi run -e dev fmt --check
```

### 单元测试

```bash
# DataHub 单元测试
pixi run -e dev test packages/datahub/tests/unit/ -k "ingestion_log"

# Port 层单元测试
pixi run -e dev test apps/port/tests/unit/ingestion/ -v
```

### 集成测试

```bash
# 摄取日志集成测试
pixi run -e dev test apps/port/tests/integration/ingestion/ -v
```

### 架构验证

```bash
# 确认 Port 层不再直接导入 Store
grep -r "from.*stores" apps/port/src/
# 应该只找到注释或已删除的导入

# 确认 IngestionLog 从 models 导入
grep -r "from.*models.*ingestion" apps/port/src/
# 应该找到多处引用
```

---

## 风险评估

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 破坏现有导入 | 高 | 在 `sources/metadata.py` 保留重新导出（向后兼容） |
| 测试 Mock 失效 | 中 | 更新所有测试文件中的 Mock 配置 |
| DataHub 属性重命名冲突 | 低 | 分两步进行：先新增Accessor，再重命名Store |
| 循环导入 | 低 | models 层不依赖任何其他层 |

---

## 实施步骤

- [x] **创建 models 层**（已完成，models 层已存在）
- [x] **创建 IngestionLogAccessor**（✅ 完成）
- [x] **更新 DataHub**（✅ 完成）
- [x] **更新 Port 层文件**（✅ 完成）
- [x] **更新测试文件**（✅ 完成）
- [x] **运行验证**（✅ 完成）
- [ ] **清理兼容性代码**（未执行，无必要）

---

## 实施完成记录

### 执行时间

2026-01-19

### 执行分支

`feature/pyright-cleanup-batch-0`

### 完成任务

#### Phase 1: Models 层 ✅

**状态**: 已完成（models 层已存在）

- [x] `models/ingestion.py` 存在，包含 `IngestionLog`、`IngestionStatus`、`IngestionCursor`
- [x] `models/__init__.py` 导出所有模型

#### Phase 2: 创建 IngestionLogAccessor ✅

**状态**: 已完成

**Commits**:
- `eecfc98` - feat: 添加 IngestionLogAccessor（初始实现）
- `716c56e` - feat: 导出 IngestionLogAccessor
- `d906f4a` - refactor: 将 DataHub.ingestion_log 改为返回 Accessor

**文件变更**:
- 新增: `packages/datahub/src/ditto_datahub/accessors/ingestion_log.py`
- 修改: `packages/datahub/src/ditto_datahub/accessors/__init__.py`
- 修改: `packages/datahub/src/ditto_datahub/hub.py`

#### Phase 3: 修复 Port 层跨层依赖 ✅

**状态**: 已完成

**Commits**:
- backfill.py 修复（包含 CalendarAccessor.get_first_trading_day() 添加）
- `0cd3b0b` - refactor: metadata.py 改用 DataHub Accessor
- `6504976` - refactor: retry.py 改用 DataHub Accessor

**文件变更**:
- 修改: `apps/port/src/ditto_port/services/ingestion/backfill.py`
- 修改: `apps/port/src/ditto_port/services/ingestion/metadata.py`
- 修改: `apps/port/src/ditto_port/services/ingestion/retry.py`
- 修改: `apps/port/src/ditto_port/jobs/flows/backfill.py`
- 修改: `apps/port/src/ditto_port/jobs/flows/repair.py`
- 修改: `apps/port/src/ditto_port/cli/executor.py`
- 修改: `packages/datahub/src/ditto_datahub/accessors/calendar.py`（添加 `get_first_trading_day()`）
- 修改: 所有相关测试文件

#### Phase 4: 验证 ✅

**状态**: 已完成

**测试结果**:
- ✅ backfill 单元测试: 11/11 通过
- ✅ metadata 单元测试: 13/13 通过
- ✅ retry 单元测试: 12/12 通过
- ✅ Pyright 类型检查: 0 errors
- ✅ Ruff 代码检查: 通过

### 架构改进

**修改前**:
```
Port 层                      DataHub 层
──────────────────────────────────────────────────────
backfill.py          ──→      CalendarStore        ❌
                             IngestionLogStore    ❌

metadata.py          ──→      IngestionLogStore    ❌

retry.py             ──→      IngestionLogStore    ❌
```

**修改后**:
```
Port 层                      DataHub 层
──────────────────────────────────────────────────────
backfill.py          ──→      DataHub.calendar     ✅
                             DataHub.ingestion_log ✅

metadata.py          ──→      DataHub.ingestion_log ✅

retry.py             ──→      DataHub.ingestion_log ✅
```

### 影响范围

**新增文件**: 1 个
- `packages/datahub/src/ditto_datahub/accessors/ingestion_log.py`

**修改文件**: 15+ 个
- DataHub 层: 3 个文件
- Port 层服务: 3 个文件
- Port 层 flows: 2 个文件
- Port 层 CLI: 1 个文件
- 测试文件: 6+ 个

### 下一步

1. 合并到 `main` 分支
2. 运行完整架构审计确认 ARCH-001 已解决
3. 更新相关 README 文档
