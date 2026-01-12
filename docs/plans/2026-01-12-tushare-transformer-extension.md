# Tushare Transformer 统一扩展设计

**日期**: 2026-01-12
**状态**: 设计完成
**目标**: 扩展 transformer 支持所有 Tushare API 的数据转换

---

## 概述

扩展 `TushareDataTransformer` 以支持所有 Tushare API 的数据转换，消除 `source.py` 中剩余的 ~162 行重复代码。

**当前状态**: Phase 1.1 已完成 `fetch_etf_daily` 和 `fetch_stock_daily` 使用 transformer
**目标**: 将其余 6 个 fetch 方法也改用 transformer 统一处理

---

## 架构设计

### 1. 扩展 ColumnMapping

```python
@dataclass(frozen=True)
class ColumnMapping:
    """列映射配置."""
    rename: dict[str, str]
    date_columns: dict[str, str]  # 列名 -> 格式
    float_columns: list[str]
    int_columns: tuple[str, ...] = ()
    boolean_columns: tuple[str, ...] = ()  # 新增
    computed_columns: dict[str, pl.Expr] = field(default_factory=dict)  # 新增
    output_columns: tuple[str, ...] | None = None
```

### 2. 通用 transform() 方法

```python
@staticmethod
def transform(
    df: pl.DataFrame,
    dataset_name: str,
    mapping: ColumnMapping,
) -> pl.DataFrame:
    """统一转换 Tushare 数据."""
    # 1. 空处理
    # 2. 应用 rename
    # 3. 应用类型转换 (date/float/int/boolean)
    # 4. 应用 computed_columns
    # 5. 选择 output_columns
    # 6. 记录日志和指标
```

### 3. 预定义映射配置

| 配置名 | 数据集 | 特殊处理 |
|--------|--------|----------|
| `CALENDAR_MAPPING` | 交易日历 | boolean_columns |
| `ADJ_FACTOR_MAPPING` | 复权因子 | computed_columns 复制 trade_date |
| `ETF_BASIC_MAPPING` | ETF 基本信息 | computed_columns 提取 symbol/exchange |
| `STOCK_BASIC_MAPPING` | 股票基本信息 | 简单重命名 |
| `STOCK_LIMIT_MAPPING` | 涨跌停 | float_columns |
| `DAILY_OHLCV_MAPPING` | 日线 (已存在) | - |

---

## 实施步骤 (TDD)

### RED 阶段

1. **扩展 ColumnMapping**
   - 添加 `boolean_columns: tuple[str, ...] = ()`
   - 添加 `computed_columns: dict[str, pl.Expr] = field(default_factory=dict)`

2. **编写测试**
   - `test_column_mapping_with_boolean_columns()`
   - `test_column_mapping_with_computed_columns()`
   - `test_transform_with_boolean_columns()`
   - `test_transform_with_computed_columns()` (symbol/exchange 提取)
   - `test_transform_calendar_empty()`
   - `test_transform_adj_factor_empty()`

### GREEN 阶段

1. **更新 `_build_schema_from_mapping()`**
   - 支持 `boolean_columns` → `pl.Boolean`
   - 支持 `computed_columns` 推断类型

2. **实现通用 `transform()` 方法**
   - 合并现有 `transform_daily_ohlcv()` 逻辑
   - 添加 `boolean_columns` 转换
   - 添加 `computed_columns` 应用

### REFACTOR 阶段

1. **创建预定义配置** (transformer.py)
   ```python
   CALENDAR_MAPPING = ColumnMapping(...)
   ADJ_FACTOR_MAPPING = ColumnMapping(...)
   FUND_ADJ_MAPPING = ColumnMapping(...)
   ETF_BASIC_MAPPING = ColumnMapping(...)
   STOCK_BASIC_MAPPING = ColumnMapping(...)
   STOCK_LIMIT_MAPPING = ColumnMapping(...)
   ```

2. **重构 source.py fetch 方法**
   - `fetch_calendar()` → 使用 `CALENDAR_MAPPING`
   - `fetch_adj_factor()` → 使用 `ADJ_FACTOR_MAPPING`
   - `fetch_fund_adj()` → 使用 `FUND_ADJ_MAPPING`
   - `fetch_etf_basic()` → 使用 `ETF_BASIC_MAPPING`
   - `fetch_stock_basic()` → 使用 `STOCK_BASIC_MAPPING`
   - `fetch_stock_limit()` → 使用 `STOCK_LIMIT_MAPPING`

3. **保持向后兼容**
   ```python
   @staticmethod
   def transform_daily_ohlcv(df, dataset_name, mapping=None):
       """向后兼容的包装方法."""
       if mapping is None:
           mapping = DAILY_OHLCV_MAPPING
       return TushareDataTransformer.transform(df, dataset_name, mapping)
   ```

4. **更新 __all__ 导出**
   ```python
   __all__ = [
       "DAILY_OHLCV_MAPPING",
       "CALENDAR_MAPPING",
       "ADJ_FACTOR_MAPPING",
       "FUND_ADJ_MAPPING",
       "ETF_BASIC_MAPPING",
       "STOCK_BASIC_MAPPING",
       "STOCK_LIMIT_MAPPING",
       "ColumnMapping",
       "TushareDataTransformer",
   ]
   ```

---

## 关键文件

### 修改的文件

| 文件 | 修改内容 |
|------|----------|
| `packages/datahub/src/ditto_datahub/sources/tushare/transformer.py` | 扩展 ColumnMapping，实现 transform()，添加 6 个映射配置 |
| `packages/datahub/tests/unit/sources/tushare/test_transformer_unit.py` | 添加新功能测试 |

### 简化的文件

| 文件 | 简化内容 |
|------|----------|
| `packages/datahub/src/ditto_datahub/sources/tushare/source.py` | 6 个 fetch 方法简化，减少 ~162 行 |

---

## 预期收益

| 指标 | 值 |
|------|------|
| 代码减少 | ~162 行 (52%) |
| 新增映射配置 | 6 个 |
| 新增测试 | ~6 个 |
| 统一转换方法 | 1 个通用 transform() |

---

## 验证步骤

### 单元测试
```bash
pixi run -e dev pytest packages/datahub/tests/unit/sources/tushare/test_transformer_unit.py -v
```

### 集成测试
```bash
pixi run -e dev pytest packages/datahub/tests/unit/sources/tushare/test_source_unit.py -v
```

### 完整测试
```bash
pixi run -e dev pytest -m unit
pixi run -e dev pre-commit-run
```

### Schema 验证
确保所有 fetch 方法返回的 DataFrame schema 不变：
- `fetch_calendar()` → `trade_date: Date, is_open: Boolean`
- `fetch_adj_factor()` → `src_code, trade_date, knowledge_date, adj_factor`
- `fetch_etf_basic()` → `src_code, symbol, name, exchange, list_date`
- 等

---

## 风险与缓解

| 风险 | 缓解措施 |
|------|----------|
| computed_columns 类型推断错误 | 先写测试验证，再实现 |
| ETF symbol/exchange 提取逻辑错误 | 单独测试 computed_columns |
| 向后兼容性破坏 | 保留 `transform_daily_ohlcv()` 包装方法 |
| Schema 变化影响下游 | 运行完整集成测试验证 |
