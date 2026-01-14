# Tushare Transformer 统一扩展设计

**日期**: 2026-01-12
**状态**: ✅ 已完成
**目标**: 扩展 transformer 支持所有 Tushare API 的数据转换

---

## 概述

扩展 `TushareDataTransformer` 以支持所有 Tushare API 的数据转换，消除 `source.py` 中剩余的 ~162 行重复代码。

**当前状态**: ✅ 已完成
**结果**: 所有 6 个 fetch 方法已改用 transformer 统一处理

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

### RED 阶段 ✅ 已完成

1. **扩展 ColumnMapping** ✅
   - [x] 添加 `boolean_columns: tuple[str, ...] = ()`
   - [x] 添加 `computed_columns: dict[str, pl.Expr] = field(default_factory=dict)`

2. **编写测试** ✅
   - [x] `test_column_mapping_with_boolean_columns()`
   - [x] `test_column_mapping_with_computed_columns()`
   - [x] `test_transform_with_boolean_columns()`
   - [x] `test_transform_with_computed_columns()` (symbol/exchange 提取)
   - [x] `test_transform_calendar_empty()`
   - [x] `test_transform_adj_factor_empty()`

### GREEN 阶段 ✅ 已完成

1. **更新 `_build_schema_from_mapping()`** ✅
   - [x] 支持 `boolean_columns` → `pl.Boolean`
   - [x] 支持 `computed_columns` 推断类型（使用 dummy 数据执行转换）

2. **实现通用 `transform()` 方法** ✅
   - [x] 合并现有 `transform_daily_ohlcv()` 逻辑
   - [x] 添加 `boolean_columns` 转换
   - [x] 添加 `computed_columns` 应用（使用 `**kwargs` 展开）
   - [x] 提取 `_transform_impl()` 内部方法

### REFACTOR 阶段 ✅ 已完成

1. **创建预定义配置** (transformer.py) ✅ 已完成
   ```python
   CALENDAR_MAPPING = ColumnMapping(...)      # ✅
   ADJ_FACTOR_MAPPING = ColumnMapping(...)    # ✅
   FUND_ADJ_MAPPING = ColumnMapping(...)      # ✅
   ETF_BASIC_MAPPING = ColumnMapping(...)     # ✅
   STOCK_BASIC_MAPPING = ColumnMapping(...)   # ✅
   STOCK_LIMIT_MAPPING = ColumnMapping(...)   # ✅
   ```

2. **重构 source.py fetch 方法** ✅ 已完成
   - [x] `fetch_calendar()` → 使用 `CALENDAR_MAPPING`
   - [x] `fetch_adj_factor()` → 使用 `ADJ_FACTOR_MAPPING`
   - [x] `fetch_fund_adj()` → 使用 `FUND_ADJ_MAPPING`
   - [x] `fetch_etf_basic()` → 使用 `ETF_BASIC_MAPPING`
   - [x] `fetch_stock_basic()` → 使用 `STOCK_BASIC_MAPPING`
   - [x] `fetch_stock_limit()` → 使用 `STOCK_LIMIT_MAPPING`

3. **保持向后兼容** ✅ 已完成（transform_daily_ohlcv 已保留）

4. **更新 __all__ 导出** ✅ 已完成
   ```python
   __all__ = [
       "ADJ_FACTOR_MAPPING",
       "CALENDAR_MAPPING",
       "DAILY_OHLCV_MAPPING",
       "ETF_BASIC_MAPPING",
       "FUND_ADJ_MAPPING",
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

---

## 进度日志

| 日期 | 提交 | 内容 |
|------|------|------|
| 2026-01-12 | `8156976` | feat(tushare): 扩展 ColumnMapping 添加 boolean_columns 字段 |
| 2026-01-12 | `a256a78` | feat(tushare): 扩展 ColumnMapping 添加 computed_columns |
| 2026-01-12 | `29950d4` | test(tushare): 编写 transform 相关测试 (boolean/computed/empty) |
| 2026-01-12 | `af7e19c` | test(tushare): 修复 ETF_BASIC_MAPPING 测试配置 |
| 2026-01-12 | `b5f9667` | feat(tushare): 添加预定义映射配置并修复 transform 方法 |
| 2026-01-12 | `861c56d` | docs(plans): 更新 tushare-transformer-extension 进度 |

### 待完成工作

✅ 所有任务已完成！

**验证结果**：
- ✅ 9 个 transformer 单元测试通过
- ✅ 22 个 source 集成测试通过
- ✅ pre-commit 所有检查通过
- ✅ `_record_metrics` 函数保留（`fetch_stock_status` 仍需要使用）
