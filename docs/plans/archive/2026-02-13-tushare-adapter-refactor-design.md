# Tushare Adapter 重构设计

**日期**: 2026-02-13
**状态**: Completed
**关联审计**: [2026-02-13-architecture-audit.md](../reviews/2026-02-13-architecture-audit.md)

---

## 背景

架构审计发现以下问题：

1. **Mapping 位置不一致**
   - transformer.py 定义了 8 个通用 Mapping（正确）
   - capital.py 自己定义了 11 个 Mapping（违规）
   - fundamental.py 从 capital.py 导入 Mapping（跨 adapter 依赖）

2. **重复代码**
   - `_record_metrics` 在 4 个 adapter 中重复定义
   - `_add_pit_columns` 在 2 个 adapter 中重复定义

3. **防御式编程位置错误**
   - `M.data_records.add()` 需要 try-except 保护
   - 防御责任被推给每个调用方（17 处）
   - 应该在 `M` 内部处理

---

## 设计目标

1. **Mapping 集中管理**：所有 ColumnMapping 放在 `mappings/` 模块
2. **防御式编程下沉**：`M.data_records.add()` 内部处理未初始化情况
3. **消除重复代码**：删除 `_record_metrics` 和 `_add_pit_columns`
4. **解除跨 adapter 依赖**：fundamental.py 不再依赖 capital.py

---

## Part 1: SafeCounter 防御式改造

### 1.1 新增 SafeCounter 类

**文件**: `packages/infra/src/ditto_infra/foundation/observability/metrics.py`

```python
class SafeCounter:
    """防御式 Counter，未初始化时静默跳过。"""

    def __init__(self, counter: Counter | None = None) -> None:
        self._counter = counter

    def add(self, amount: int | float, attributes: dict | None = None) -> None:
        """记录计数，未初始化时静默跳过。"""
        if self._counter is not None:
            self._counter.add(amount, attributes or {})

    def set_counter(self, counter: Counter) -> None:
        """设置实际的 Counter（setup 时调用）。"""
        self._counter = counter
```

### 1.2 修改 M 类

```python
class M:
    # 预初始化为 SafeCounter，无需 setup 即可安全调用
    data_records: SafeCounter = SafeCounter()
    data_errors: SafeCounter = SafeCounter()
    # ... 所有 Counter 类型

    @classmethod
    def setup(cls, meter: metrics.Meter) -> None:
        for metric_def in METRIC_DEFINITIONS:
            if metric_type == "counter":
                counter = meter.create_counter(instrument_name, description=description)
                getattr(cls, name).set_counter(counter)  # 设置而非替换
```

### 1.3 调用方变更

```python
# 前：需要 try-except 包装
def _record_metrics(row_count: int, dataset: str) -> None:
    try:
        M.data_records.add(row_count, {"source": "tushare", "dataset": dataset})
    except (AttributeError, TypeError):
        pass

# 后：直接调用，无需防御
M.data_records.add(row_count, {"source": "tushare", "dataset": "valuation_metrics"})
```

---

## Part 2: Mapping 模块拆分

### 2.1 新目录结构

```
packages/data/src/ditto_data/sources/tushare/processors/
├── __init__.py
├── transformer.py          # TushareDataTransformer 类 + ColumnMapping 定义
├── error_handler.py        # (现有)
├── merger.py               # (现有)
└── mappings/
    ├── __init__.py         # 重新导出所有 Mapping
    ├── common.py           # 通用 Mapping: DAILY_OHLCV, CALENDAR, ADJ_FACTOR, FUND_ADJ
    ├── basic.py            # 基本信息: STOCK_BASIC, ETF_BASIC, INDEX_BASIC, STOCK_LIMIT
    └── capital.py          # 资本域: 估值、分红、融资融券、财务报表等 11 个
```

### 2.2 Mapping 分组

| 模块 | Mapping | 来源 |
|------|---------|------|
| common.py | DAILY_OHLCV_MAPPING | transformer.py |
| common.py | CALENDAR_MAPPING | transformer.py |
| common.py | ADJ_FACTOR_MAPPING | transformer.py |
| common.py | FUND_ADJ_MAPPING | transformer.py |
| basic.py | STOCK_BASIC_MAPPING | transformer.py |
| basic.py | ETF_BASIC_MAPPING | transformer.py |
| basic.py | INDEX_BASIC_MAPPING | transformer.py |
| basic.py | STOCK_LIMIT_MAPPING | transformer.py |
| capital.py | VALUATION_METRICS_MAPPING | capital.py |
| capital.py | DIVIDEND_MAPPING | capital.py |
| capital.py | MARGIN_TRADING_MAPPING | capital.py |
| capital.py | PLEDGE_RATIO_MAPPING | capital.py |
| capital.py | FUTURES_MAPPING | capital.py |
| capital.py | INDEX_COMPOSITION_MAPPING | capital.py |
| capital.py | CORPORATE_ACTIONS_MAPPING | capital.py |
| capital.py | BALANCE_SHEET_MAPPING | capital.py |
| capital.py | INCOME_STATEMENT_MAPPING | capital.py |
| capital.py | CASH_FLOW_MAPPING | capital.py |

### 2.3 mappings/__init__.py

```python
from .basic import (
    ETF_BASIC_MAPPING,
    INDEX_BASIC_MAPPING,
    STOCK_BASIC_MAPPING,
    STOCK_LIMIT_MAPPING,
)
from .capital import (
    BALANCE_SHEET_MAPPING,
    CASH_FLOW_MAPPING,
    CORPORATE_ACTIONS_MAPPING,
    DIVIDEND_MAPPING,
    FUTURES_MAPPING,
    INCOME_STATEMENT_MAPPING,
    INDEX_COMPOSITION_MAPPING,
    MARGIN_TRADING_MAPPING,
    PLEDGE_RATIO_MAPPING,
    VALUATION_METRICS_MAPPING,
)
from .common import (
    ADJ_FACTOR_MAPPING,
    CALENDAR_MAPPING,
    DAILY_OHLCV_MAPPING,
    FUND_ADJ_MAPPING,
)

__all__ = [
    "ADJ_FACTOR_MAPPING",
    "BALANCE_SHEET_MAPPING",
    "CALENDAR_MAPPING",
    "CASH_FLOW_MAPPING",
    "CORPORATE_ACTIONS_MAPPING",
    "DAILY_OHLCV_MAPPING",
    "DIVIDEND_MAPPING",
    "ETF_BASIC_MAPPING",
    "FUND_ADJ_MAPPING",
    "FUTURES_MAPPING",
    "INCOME_STATEMENT_MAPPING",
    "INDEX_BASIC_MAPPING",
    "INDEX_COMPOSITION_MAPPING",
    "MARGIN_TRADING_MAPPING",
    "PLEDGE_RATIO_MAPPING",
    "STOCK_BASIC_MAPPING",
    "STOCK_LIMIT_MAPPING",
    "VALUATION_METRICS_MAPPING",
]
```

---

## Part 3: Adapter 变更

### 3.1 capital.py 变更

| 操作 | 内容 |
|------|------|
| 删除 | 11 个 Mapping 定义（行 19-261） |
| 删除 | `_record_metrics` 函数 |
| 删除 | `_add_pit_columns` 函数 |
| 新增导入 | `from .mappings import BALANCE_SHEET_MAPPING, ...` |
| 内联 | `_add_pit_columns(result)` → `result.with_columns(...)` |
| 替换 | `_record_metrics(...)` → `M.data_records.add(...)` |

**预计行数减少**: ~300 行（1063 → ~760 行）

### 3.2 fundamental.py 变更

| 操作 | 内容 |
|------|------|
| 修改导入 | `from capital import ...` → `from .mappings import ...` |
| 删除 | `_record_metrics` 函数 |
| 删除 | `_add_pit_columns` 函数 |
| 内联 | 同上 |
| 替换 | 同上 |

**解除依赖**: fundamental.py 不再依赖 capital.py

### 3.3 其他 Adapter 变更

| 文件 | 变更 |
|------|------|
| stock.py | 删除 `_record_metrics`，修改导入路径 |
| index.py | 修改导入路径 |
| etf.py | 修改导入路径 |
| calendar.py | 修改导入路径 |
| industry.py | 删除 `_record_metrics` |

---

## Part 4: 内联 _add_pit_columns

### 4.1 原函数

```python
def _add_pit_columns(df: pl.DataFrame, date_col: str = "knowledge_date") -> pl.DataFrame:
    return df.with_columns(
        pl.col(date_col).alias("effective_from"),
        pl.lit(None, dtype=pl.Date).alias("effective_to"),
    )
```

### 4.2 内联后

```python
# 默认情况
result = result.with_columns(
    pl.col("knowledge_date").alias("effective_from"),
    pl.lit(None, dtype=pl.Date).alias("effective_to"),
)

# 指定 date_col 的情况
result = result.with_columns(
    pl.col("report_date").alias("effective_from"),
    pl.lit(None, dtype=pl.Date).alias("effective_to"),
)
```

**理由**: 函数逻辑简单（2 行），内联后可读性不减，减少函数调用开销。

---

## Part 5: 合并 stock_status.py 到 stock.py

### 5.1 背景

`stock_status.py` (130 行) 是 `stock.py` 的辅助模块，只被 `stock.py` 的 `fetch_stock_status` 方法使用。

```python
# stock.py 中的使用
def fetch_stock_status(self, trade_date: str) -> pl.DataFrame:
    # 使用 Adapter 获取状态数据
    adapter = StockStatusAdapter(client=self._client)
    suspend_df = adapter.fetch_suspend_data(ts_date)
    st_df = adapter.fetch_st_data()
    list_status_df = adapter.fetch_list_status_data()
    # ...
```

### 5.2 合并方案

将 `StockStatusAdapter` 的三个方法作为私有方法合并到 `StockTushareAdapter` 类中：

```python
# 合并后的 stock.py
class StockTushareAdapter(BaseTushareAdapter):
    # 现有方法...

    def fetch_stock_status(self, trade_date: str) -> pl.DataFrame:
        # 直接调用私有方法，无需创建额外 adapter
        suspend_df = self._fetch_suspend_data(ts_date)
        st_df = self._fetch_st_data()
        list_status_df = self._fetch_list_status_data()
        # ...

    def _fetch_suspend_data(self, ts_date: str) -> pl.DataFrame:
        """获取停牌数据（内部方法）。"""
        # 原 StockStatusAdapter.fetch_suspend_data 逻辑

    def _fetch_st_data(self) -> pl.DataFrame:
        """获取 ST 状态数据（内部方法）。"""
        # 原 StockStatusAdapter.fetch_st_data 逻辑

    def _fetch_list_status_data(self) -> pl.DataFrame:
        """获取上市状态数据（内部方法）。"""
        # 原 StockStatusAdapter.fetch_list_status_data 逻辑
```

### 5.3 变更内容

| 操作 | 内容 |
|------|------|
| 删除 | `stock_status.py` 文件 |
| 合并 | 三个方法移到 `StockTushareAdapter` 作为私有方法 |
| 修改 | `fetch_stock_status` 直接调用私有方法 |
| 更新 | `adapters/__init__.py` 移除 `StockStatusAdapter` 导出 |

**收益**：
- 减少一个文件
- 减少类实例化开销
- 代码更集中，易于维护

---

## 变更摘要

| 类型 | 文件 | 操作 |
|------|------|------|
| 修改 | metrics.py | 添加 SafeCounter，修改 M 类 |
| 新增 | mappings/__init__.py | 导出所有 Mapping |
| 新增 | mappings/common.py | 4 个通用 Mapping |
| 新增 | mappings/basic.py | 4 个基本信息 Mapping |
| 新增 | mappings/capital.py | 11 个资本域 Mapping |
| 修改 | transformer.py | 从 mappings 导入，删除 Mapping 定义 |
| 修改 | capital.py | 删除 Mapping/辅助函数，修改导入，预计减少 ~300 行 |
| 修改 | fundamental.py | 解除 capital 依赖，删除辅助函数 |
| 修改 | stock.py | 合并 stock_status，删除 _record_metrics，修改导入 |
| **删除** | **stock_status.py** | **合并到 stock.py** |
| 修改 | index.py | 修改导入路径 |
| 修改 | etf.py | 修改导入路径 |
| 修改 | calendar.py | 修改导入路径 |
| 修改 | industry.py | 删除 _record_metrics |

---

## 验证命令

```bash
# 完整检查
pixi run -e dev check

# 架构边界检查
pixi run -e dev arch-check

# 代码规模检查（capital.py 应 < 800 行）
pixi run -e dev python scripts/check_code_size.py

# 测试覆盖率
pixi run -e dev test --unit --cov --cov-report=html
```

---

## 风险评估

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 导入路径变更导致运行时错误 | 高 | 运行完整测试套件验证 |
| SafeCounter 遗漏某些 Counter | 中 | 检查所有 Counter 类型定义 |
| 内联后代码不一致 | 低 | 统一使用相同模式 |

---

## 实施顺序

1. **Part 1**: SafeCounter 改造（独立，无依赖）
2. **Part 2**: 创建 mappings/ 模块
3. **Part 3**: 修改 transformer.py 导入
4. **Part 4**: 修改各 adapter（按依赖顺序：先 capital，再 fundamental）
5. **Part 5**: 合并 stock_status.py 到 stock.py
6. **验证**: 运行测试和检查命令

---

## 实施结果

### 完成时间
2026-02-13

### 变更摘要

| Part | 状态 | 主要变更 |
|------|------|----------|
| Part 1 | ✅ 完成 | 添加 SafeCounter/SafeHistogram/SafeGauge 防御式包装类 |
| Part 2 | ✅ 完成 | 创建 `mappings/` 模块，包含 `column_mapping.py`、`common.py`、`basic.py`、`capital.py` |
| Part 3 | ✅ 完成 | transformer.py 从 column_mapping.py 导入 ColumnMapping，从 mappings 导入所有 Mapping |
| Part 4 | ✅ 完成 | capital.py/fundamental.py/stock.py 删除重复函数，内联 PIT 列逻辑 |
| Part 5 | ✅ 完成 | stock_status.py 合并到 stock.py，删除原文件 |

### 额外修复

1. **循环导入问题**: 创建独立的 `column_mapping.py` 文件，解决 mappings 模块与 transformer.py 之间的循环导入

### 验证结果

```
pixi run -e dev check
✅ lint: All checks passed
✅ fmt: 588 files left unchanged
✅ type: 0 errors, 0 warnings, 0 notes
✅ arch-check: 6 kept, 0 broken
✅ test: 1667 passed, 1 skipped
```

### 代码规模变化

- 删除 `stock_status.py` (-130 行)
- `capital.py` 减少约 250 行
- `fundamental.py` 减少约 40 行
- 新增 `mappings/` 模块 (+350 行)
- 新增 `column_mapping.py` (+38 行)
