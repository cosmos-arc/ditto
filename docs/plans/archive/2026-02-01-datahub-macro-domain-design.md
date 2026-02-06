# DataHub Macro 域设计文档

**日期**: 2026-02-01
**状态**: 设计完成，待实施
**预计时间**: 3-4 个工作日

---

## 1. 概述

### 1.1 目标

实现完整的 Macro 域，支持宏观数据的存储和查询，包括：
- 经济指标（GDP、CPI、PPI、PMI、工业增加值等）
- 利率指标（SHIBOR、LPR、国债收益率、MLF利率等）
- 汇率指标（美元/人民币汇率、欧元汇率等）
- 货币供应量（M1、M2、社会融资规模等）

### 1.2 核心特性

| 特性 | 说明 |
|------|------|
| **多频率支持** | 支持日度、月度、季度数据，保持原始频率 |
| **PIT 支持** | 混合模式 - 部分指标需要 PIT（如 GDP），部分不需要 |
| **窄表存储** | 使用 Parquet 年分区窄表存储 |
| **统一查询** | MacroService 提供统一查询入口 |

### 1.3 依赖关系

```
MacroService
    ├── IndicatorStore (Parquet 年分区)
    └── IndicatorMetadataStore (SQLite meta.db)
```

---

## 2. 目录结构

```
packages/datahub/src/ditto_datahub/domains/macro/
├── __init__.py                    # 域入口
├── indicator/
│   ├── __init__.py               # 导出 Store 类
│   ├── indicator_store.py        # 宏观指标数据存储
│   └── metadata_store.py         # 指标元数据存储
└── macro_service.py              # 统一查询服务
```

---

## 3. 数据模型

### 3.1 指标数据表（Parquet 窄表）

**存储路径**: `data/macro/indicator/YYYY.parquet`

| 列名 | 类型 | 说明 |
|------|------|------|
| `indicator_id` | int | 指标 ID（外键） |
| `date` | date | 指标日期 |
| `value` | float | 指标值 |
| `knowledge_date` | date | **可选**，数据已知日期（PIT 用） |
| `_valid_from` | date | PIT 有效期起始（内部使用） |
| `_valid_to` | date | PIT 有效期结束（内部使用） |

**频率处理**:
- 日度数据: `date` 存储实际日期
- 月度数据: `date` 存储每月第一天（如 `2024-01-01`）
- 季度数据: `date` 存储每季度第一天（如 `2024-01-01` 代表 Q1）

### 3.2 元数据表（SQLite）

```sql
CREATE TABLE macro_indicators (
    indicator_id INTEGER PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,        -- 如 'CPI_YOY', 'SHIBOR_1M'
    name TEXT NOT NULL,               -- 如 'CPI同比', 'SHIBOR 1个月'
    category TEXT NOT NULL,           -- 'economic', 'interest_rate', 'exchange_rate', 'money_supply'
    frequency TEXT NOT NULL,          -- 'daily', 'monthly', 'quarterly'
    need_pit BOOLEAN NOT NULL,        -- 是否需要 PIT 记录
    source TEXT,                      -- 数据源
    unit TEXT,                        -- 单位（'%', '亿元'等）
    description TEXT
);
```

**类别枚举**:
- `economic`: 经济指标
- `interest_rate`: 利率指标
- `exchange_rate`: 汇率指标
- `money_supply`: 货币供应量

---

## 4. API 设计

### 4.1 IndicatorStore

```python
class IndicatorStore(ParquetStoreBase):
    """宏观指标数据存储."""

    def write(
        self,
        df: pl.DataFrame,
        on_duplicate: OnDuplicate = OnDuplicate.UPSERT,
    ) -> int:
        """
        写入宏观指标数据.

        Args:
            df: 必须包含列 [indicator_id, date, value]
                可选列: knowledge_date (PIT 指标需要)
            on_duplicate: 重复处理策略

        Returns:
            写入行数
        """

    def get(
        self,
        indicator_ids: list[int] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        as_of_date: str | None = None,
    ) -> pl.DataFrame:
        """
        查询宏观指标数据（PIT 安全）.

        Args:
            indicator_ids: 指标 ID 列表（None = 全部）
            start_date: 开始日期
            end_date: 结束日期
            as_of_date: PIT 查询日期

        Returns:
            包含列 [indicator_id, date, value] 的 DataFrame
        """
```

### 4.2 IndicatorMetadataStore

```python
class IndicatorMetadataStore:
    """宏观指标元数据存储."""

    def upsert(
        self,
        code: str,
        name: str,
        category: Literal["economic", "interest_rate", "exchange_rate", "money_supply"],
        frequency: Literal["daily", "monthly", "quarterly"],
        need_pit: bool,
        source: str | None = None,
        unit: str | None = None,
        description: str | None = None,
    ) -> int:
        """注册或更新指标元数据."""

    def get_by_id(self, indicator_id: int) -> pl.DataFrame:
        """按 ID 查询."""

    def get_by_code(self, code: str) -> pl.DataFrame:
        """按代码查询."""

    def list_by_category(self, category: str | None = None) -> pl.DataFrame:
        """按类别列出所有指标."""

    def is_pit_indicator(self, indicator_id: int) -> bool:
        """判断指标是否需要 PIT."""

    def get_frequency(self, indicator_id: int) -> str:
        """获取指标频率."""
```

### 4.3 MacroService

```python
@dataclass(frozen=True)
class MacroQuery:
    """宏观指标查询参数."""

    indicators: list[int] | list[str] | None = None  # ID 或 code
    start: str | None = None
    end: str | None = None
    asof: str | None = None
    category: str | None = None
    frequency: str | None = None


class MacroService:
    """Macro 域统一查询服务."""

    def __init__(
        self,
        indicator_store: IndicatorStore,
        metadata_store: IndicatorMetadataStore,
    ) -> None:
        self._indicator_store = indicator_store
        self._metadata_store = metadata_store

    def get_indicators(self, query: MacroQuery) -> pl.DataFrame:
        """
        查询宏观指标数据.

        Args:
            query: MacroQuery 查询对象

        Returns:
            包含列 [indicator_id, code, name, date, value, ...] 的 DataFrame
        """
```

---

## 5. 错误处理

| 错误场景 | 处理方式 |
|----------|----------|
| 指标 code 不存在 | 返回空 DataFrame |
| 日期范围无效 | `ValueError`（start > end） |
| PIT 查询日期无效 | 使用当前日期 |
| 空结果 | 返回空 DataFrame（不抛异常） |
| 元数据缺失 | 警告日志，继续执行 |

### 边界情况

**混合频率查询**:
```python
# 同时查询日度（SHIBOR）和月度（CPI）指标
query = MacroQuery(indicators=["SHIBOR_1M", "CPI_YOY"])
# 结果中 date 列包含不同粒度，由调用者处理
```

**PIT 指标的非 PIT 查询**:
```python
# PIT 指标（如 GDP）不指定 asof 时，返回最新值
query = MacroQuery(indicators=["GDP_QOQ"])
# 等价于: asof=date.today()
```

---

## 6. 测试策略

### 6.1 测试文件结构

```
tests/unit/domains/macro/
├── __init__.py
├── test_indicator_store.py
├── test_metadata_store.py
└── test_macro_service.py
```

### 6.2 核心测试用例

**IndicatorStore**:
- `test_write_single_indicator()`
- `test_write_multiple_indicators()`
- `test_write_pit_indicator_with_knowledge_date()`
- `test_get_by_indicator_id()`
- `test_get_by_date_range()`
- `test_pit_query_with_asof_date()`
- `test_upsert_replaces_existing_data()`

**IndicatorMetadataStore**:
- `test_register_new_indicator()`
- `test_upsert_existing_indicator()`
- `test_get_by_code()`
- `test_get_by_id()`
- `test_list_by_category()`
- `test_is_pit_indicator()`

**MacroService**:
- `test_get_indicators_by_code()`
- `test_get_indicators_by_id()`
- `test_get_indicators_with_category_filter()`
- `test_get_indicators_with_pit_query()`
- `test_mixed_frequency_query()`
- `test_empty_result_returns_empty_dataframe()`

### 6.3 覆盖率目标

- 单元测试覆盖率: ≥ 80%
- 关键路径覆盖: 100%（读写、PIT 查询）

---

## 7. 集成

### 7.1 域导出

```python
# packages/datahub/src/ditto_datahub/domains/macro/__init__.py

from ditto_datahub.domains.macro.indicator.indicator_store import IndicatorStore
from ditto_datahub.domains.macro.indicator.metadata_store import IndicatorMetadataStore
from ditto_datahub.domains.macro.macro_service import MacroService

__all__ = [
    "IndicatorStore",
    "IndicatorMetadataStore",
    "MacroService",
]
```

### 7.2 DataHub 集成

```python
# packages/datahub/src/ditto_datahub/__init__.py

class DataHub:
    def __init__(self, ...) -> None:
        # ... 现有域 ...

        # Macro 域
        self.indicator_store = IndicatorStore(self._data_root)
        self.metadata_store = IndicatorMetadataStore(self._meta_db_path)
        self.macro = MacroService(
            indicator_store=self.indicator_store,
            metadata_store=self.metadata_store,
        )
```

---

## 8. 实施检查清单

### Phase 6: Macro 域重构

- [ ] 创建 Macro 域目录结构
- [ ] 实现 IndicatorStore
  - [ ] 继承 ParquetStoreBase
  - [ ] 实现 write() 方法
  - [ ] 实现 get() 方法（PIT 安全）
- [ ] 实现 IndicatorMetadataStore
  - [ ] 创建 SQLite 表
  - [ ] 实现 upsert() 方法
  - [ ] 实现查询方法
- [ ] 实现 MacroService
  - [ ] 实现 MacroQuery 数据类
  - [ ] 实现 get_indicators() 方法
- [ ] 更新 DataHub 集成
- [ ] 编写单元测试（覆盖率 ≥ 80%）
- [ ] 运行所有测试
- [ ] 运行类型检查 (basedpyright)
- [ ] 运行代码检查 (ruff)
- [ ] 创建 Git Tag

---

## 9. 预计工作量

| 任务 | 预计时间 |
|------|----------|
| 目录结构 + 基类 | 0.5 天 |
| IndicatorStore 实现 | 0.5 天 |
| IndicatorMetadataStore 实现 | 0.5 天 |
| MacroService 实现 | 0.5 天 |
| 单元测试 | 1 天 |
| 集成与验证 | 0.5 天 |
| **总计** | **3-4 天** |
