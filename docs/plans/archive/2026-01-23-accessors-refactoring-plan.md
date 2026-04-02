# DataHub Accessors 模块重构实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**目标:** 重构 DataHub accessors 模块，提升架构清晰度，拆分可复用逻辑到纯函数模块

**架构:** 采用 DataHub 双层 API（便捷方法 + 底层方法），将标识符转换逻辑统一到门面层，Accessor 只接受 SID；提取 enrichment 和 PIT 纯函数模块

**技术栈:** polars, pytest, dishka (依赖注入)

---

## 概述

**Sprint:** Feature/Dishka Migration
**创建:** 2026-01-23
**状态:** 待实施

### 重构目标

| 阶段 | 目标 | 优先级 |
|------|------|--------|
| **阶段 1** | enrichment 纯函数提取 | 高 |
| **阶段 2** | 标识符处理重构（DataHub 双层 API） | 高 |
| **阶段 3** | PIT 纯函数提取 | 中 |

### 核心原则

- **Accessor 只接受 SID** - 数据访问层职责单一
- **DataHub 提供双层 API** - 便捷 API（支持混合标识符）+ 底层 API（直接访问 Accessor，只接受 SID）
- **纯函数模块** - enrichment、pit 作为可复用的纯函数模块
- **TDD 流程** - RED → GREEN → REFACTOR
- **频繁提交** - 每完成一个子任务立即 commit

---

## 技术方案总结

### 1. 标识符处理 - DataHub 双层 API

```
用户代码
    ├─ 便捷 API（推荐）: hub.get_bars(src_codes=["000001.SZ"], ...)
    │   ↓ 内部转换 SID
    │   └─ hub.bars.get(sids=[1, ...])
    │
    └─ 底层 API（性能敏感）: hub.bars.get(sids=[1, 2, 3], ...)
```

**关键变更:**
- `BarsAccessor.get()` 移除 `src_codes`、`symbols` 参数，只接受 `sids`
- `DataHub` 添加便捷方法：`get_bars(src_codes, symbols, sids, ...)`
- `DataHub` 添加标识符转换方法：`resolve_sid()`, `resolve_identifiers()`, `resolve_sids_from_inputs()`

### 2. 数据增强 - enrichment 纯函数模块

**目标模块:** `packages/data/src/ditto_data/accessors/internal/enrichment.py`

```python
def enrich_with_sid(df: pl.DataFrame, sid_mapping: dict[str, int], ...) -> pl.DataFrame
def enrich_with_symbol(df: pl.DataFrame, symbol_map: pl.DataFrame) -> pl.DataFrame
def enrich_with_status(df: pl.DataFrame, status_df: pl.DataFrame, ...) -> pl.DataFrame
```

### 3. PIT 查询 - pit 纯函数模块

**目标模块:** `packages/data/src/ditto_data/accessors/internal/pit.py`

```python
def parse_asof_date(asof: date | str) -> date
def filter_by_knowledge_date(df: pl.DataFrame, pit_dt: date, ...) -> pl.DataFrame
```

---

## 阶段 1: enrichment 纯函数提取

### Task 1.1: 创建 enrichment.py 模块

**文件:**
- 创建: `packages/data/src/ditto_data/accessors/internal/enrichment.py`
- 测试: `packages/data/tests/unit/accessors/internal/test_enrichment_unit.py`

**Step 1: 编写失败的测试**

创建测试文件 `packages/data/tests/unit/accessors/internal/test_enrichment_unit.py`:

```python
"""Enrichment 纯函数模块单元测试。"""

import polars as pl
import pytest

from ditto_data.accessors.internal.enrichment import (
    enrich_with_sid,
    enrich_with_symbol,
    enrich_with_status,
)


def test_enrich_with_sid_basic():
    """测试 enrich_with_sid 基本功能。"""
    df = pl.DataFrame({
        "ts_code": ["000001.SZ", "000002.SZ"],
        "close": [10.0, 20.0],
    })
    sid_mapping = {
        "000001.SZ": 1,
        "000002.SZ": 2,
    }

    result = enrich_with_sid(df, sid_mapping, source="tushare")

    assert result.columns == ["ts_code", "close", "sid", "source"]
    assert result["sid"].to_list() == [1, 2]
    assert result["source"].to_list() == ["tushare", "tushare"]


def test_enrich_with_sid_custom_column():
    """测试自定义源代码列名。"""
    df = pl.DataFrame({
        "code": ["000001.SZ", "000002.SZ"],
        "close": [10.0, 20.0],
    })
    sid_mapping = {"000001.SZ": 1, "000002.SZ": 2}

    result = enrich_with_sid(df, sid_mapping, src_code_col="code", source="tushare")

    assert result["sid"].to_list() == [1, 2]


def test_enrich_with_sid_empty_dataframe():
    """测试空 DataFrame。"""
    df = pl.DataFrame(schema={"ts_code": pl.String, "close": pl.Float64})
    sid_mapping = {"000001.SZ": 1}

    result = enrich_with_sid(df, sid_mapping)

    assert len(result) == 0


def test_enrich_with_symbol():
    """测试 enrich_with_symbol。"""
    df = pl.DataFrame({
        "sid": [1, 2],
        "close": [10.0, 20.0],
    })
    symbol_map = pl.DataFrame({
        "sid": [1, 2],
        "symbol": ["平安银行", "万科A"],
    })

    result = enrich_with_symbol(df, symbol_map)

    assert "symbol" in result.columns
    assert result["symbol"].to_list() == ["平安银行", "万科A"]


def test_enrich_with_symbol_empty_df():
    """测试空 DataFrame 的 symbol 增强。"""
    df = pl.DataFrame()
    symbol_map = pl.DataFrame({"sid": [1], "symbol": ["平安银行"]})

    result = enrich_with_symbol(df, symbol_map)

    assert len(result) == 0


def test_enrich_with_status():
    """测试 enrich_with_status。"""
    df = pl.DataFrame({
        "sid": [1, 2],
        "trade_date": ["2024-01-02", "2024-01-02"],
        "close": [10.0, 20.0],
    })
    status_df = pl.DataFrame({
        "sid": [1, 2],
        "trade_date": ["2024-01-02", "2024-01-02"],
        "is_suspended": [False, True],
        "is_st": [False, False],
        "st_type": ["", ""],
        "list_status": ["L", "L"],
        "suspend_timing": ["", ""],
    })

    result = enrich_with_status(df, status_df)

    assert "is_suspended" in result.columns
    assert result["is_suspended"].to_list() == [False, True]
    assert result["is_st"].to_list() == [False, False]


def test_enrich_with_status_empty_df():
    """测试空 DataFrame 的状态增强。"""
    df = pl.DataFrame()
    status_df = pl.DataFrame({
        "sid": [1],
        "trade_date": ["2024-01-02"],
        "is_suspended": [False],
    })

    result = enrich_with_status(df, status_df)

    assert len(result) == 0
```

**Step 2: 运行测试验证失败**

```bash
pixi run -e dev pytest packages/data/tests/unit/accessors/internal/test_enrichment_unit.py -v
```

预期: FAIL - "ModuleNotFoundError: No module named 'ditto_data.accessors.internal.enrichment'"

**Step 3: 实现最小代码**

创建 `packages/data/src/ditto_data/accessors/internal/enrichment.py`:

```python
"""
数据增强纯函数模块。

提供 DataFrame 的列增强逻辑，纯数据操作，无 side effect。
"""

import polars as pl


def enrich_with_sid(
    df: pl.DataFrame,
    sid_mapping: dict[str, int],
    src_code_col: str = "ts_code",
    source: str = "tushare",
) -> pl.DataFrame:
    """
    使用 sid 映射字典为 DataFrame 添加 sid 列。

    Args:
        df: 输入 DataFrame，必须包含 src_code_col 指定的列。
        sid_mapping: {src_code: sid} 映射字典。
        src_code_col: 源代码列名。
        source: 数据源标识符。

    Returns:
        添加了 sid 和 source 列的 DataFrame。
    """
    src_codes = df[src_code_col].to_list()
    sids = [sid_mapping.get(code) for code in src_codes]

    return df.with_columns(
        pl.Series(sids, dtype=pl.Int32).alias("sid"),
        pl.lit(source).alias("source"),
    )


def enrich_with_symbol(
    df: pl.DataFrame,
    symbol_map: pl.DataFrame,
) -> pl.DataFrame:
    """
    使用 symbol 映射表为 DataFrame 添加 symbol 列。

    Args:
        df: 输入 DataFrame，必须包含 sid 列。
        symbol_map: symbol 映射表，包含 sid 和 symbol 列。

    Returns:
        添加了 symbol 列的 DataFrame。
    """
    if "sid" not in df.columns or df.is_empty():
        return df

    return df.join(symbol_map, on="sid", how="left")


def enrich_with_status(
    df: pl.DataFrame,
    status_df: pl.DataFrame,
    on: list[str] | None = None,
) -> pl.DataFrame:
    """
    使用状态数据表为 DataFrame 添加状态列。

    Args:
        df: 输入 DataFrame（通常包含 sid 和 trade_date）。
        status_df: 状态数据表，包含 is_suspended, is_st, st_type, list_status 等列。
        on: 连接键，默认 ["sid", "trade_date"]。

    Returns:
        添加了状态列的 DataFrame，缺失值填充为默认值。
    """
    if df.is_empty():
        return df

    join_keys = on or ["sid", "trade_date"]

    # Select only status columns
    status_cols = ["sid", "trade_date", "is_suspended", "suspend_timing",
                   "is_st", "st_type", "list_status"]
    status_to_join = status_df.select(
        [c for c in status_cols if c in status_df.columns]
    )

    result = df.join(status_to_join, on=join_keys, how="left")

    # Fill null values with defaults
    return result.with_columns(
        pl.col("is_suspended").fill_null(False),
        pl.col("suspend_timing").fill_null(""),
        pl.col("is_st").fill_null(False),
        pl.col("st_type").fill_null(""),
        pl.col("list_status").fill_null("L"),
    )
```

更新 `packages/data/src/ditto_data/accessors/internal/__init__.py`:

```python
"""Internal accessor utilities."""

from ditto_data.accessors.internal.adjustment import (
    apply_hfq_adj,
    apply_qfq_adj,
)
from ditto_data.accessors.internal.enrichment import (
    enrich_with_sid,
    enrich_with_status,
    enrich_with_symbol,
from ditto_data.accessors.internal.pit import (
    filter_by_knowledge_date,
    parse_asof_date,
)

__all__ = [
    # adjustment
    "apply_hfq_adj",
    "apply_qfq_adj",
    # enrichment
    "enrich_with_sid",
    "enrich_with_symbol",
    "enrich_with_status",
    # pit
    "filter_by_knowledge_date",
    "parse_asof_date",
]
```

**Step 4: 运行测试验证通过**

```bash
pixi run -e dev pytest packages/data/tests/unit/accessors/internal/test_enrichment_unit.py -v
```

预期: PASS

**Step 5: 提交**

```bash
git add packages/data/src/ditto_data/accessors/internal/enrichment.py
git add packages/data/src/ditto_data/accessors/internal/__init__.py
git add packages/data/tests/unit/accessors/internal/test_enrichment_unit.py
git commit -m "feat(accessors): add enrichment pure function module

- Add enrich_with_sid, enrich_with_symbol, enrich_with_status
- Pure functions for data enrichment operations
- Unit tests for all enrichment functions"
```

---

### Task 1.2: 重构 SecuritiesAccessor 使用 enrichment 纯函数

**文件:**
- 修改: `packages/data/src/ditto_data/accessors/security_accessor.py:433-494`
- 测试: `packages/data/tests/unit/accessors/test_security_accessor_unit.py`

**Step 1: 编写失败的测试（验证现有行为）**

在 `packages/data/tests/unit/accessors/test_security_accessor_unit.py` 中添加:

```python
def test_enrich_dataframe_with_sid_returns_correct_columns():
    """验证 enrich_dataframe_with_sid 返回正确的列。"""
    # 使用 fixture 获取 accessor
    accessor = securities_accessor  # 假设存在此 fixture

    df = pl.DataFrame({
        "ts_code": ["000001.SZ", "000002.SZ"],
        "symbol": ["平安银行", "万科A"],
        "name": ["平安银行", "万科A"],
        "exchange": ["SZ", "SZ"],
        "list_date": ["1991-04-03", "1991-01-29"],
    })

    result = accessor.enrich_dataframe_with_sid(
        df,
        source="tushare",
        asset_class="stock",
        src_code_col="ts_code",
    )

    assert "sid" in result.columns
    assert "source" in result.columns
    assert result["source"].to_list() == ["tushare", "tushare"]
```

**Step 2: 运行测试验证通过（现有实现应该通过）**

```bash
pixi run -e dev pytest packages/data/tests/unit/accessors/test_security_accessor_unit.py::test_enrich_dataframe_with_sid_returns_correct_columns -v
```

**Step 3: 重构代码使用 enrichment 纯函数**

修改 `packages/data/src/ditto_data/accessors/security_accessor.py`:

```python
# 在文件顶部添加导入
from ditto_data.accessors.internal.enrichment import enrich_with_sid

# 修改 enrich_dataframe_with_sid 方法 (第 433-494 行)
def enrich_dataframe_with_sid(
    self,
    df: pl.DataFrame,
    source: str,
    asset_class: Literal["stock", "etf"],
    src_code_col: str = "ts_code",
) -> pl.DataFrame:
    """
    为 DataFrame 添加 sid 和 source 列。

    不存在的证券会自动创建。

    Args:
        df: 输入 DataFrame，必须包含 src_code_col 指定的列
        source: 数据源标识符（如 "tushare"）
        asset_class: 资产类别（"stock" 或 "etf"）
        src_code_col: 源代码列名，默认 "ts_code"

    Returns:
        添加了 sid 和 source 列的 DataFrame

    """
    logger.debug(
        "Enriching DataFrame with SID",
        event="security_enrich_start",
        source=source,
        asset_class=asset_class,
        row_count=len(df),
    )

    # 处理空 DataFrame
    if len(df) == 0:
        return df.with_columns(
            pl.lit(None, dtype=pl.Int32).alias("sid"),
            pl.lit(source).alias("source"),
        )

    # 批量解析或创建证券（获取映射数据）
    sid_mapping = self.resolve_or_create_batch(
        df=df,
        source=source,
        asset_class=asset_class,
        src_code_col=src_code_col,
    )

    # 使用纯函数进行数据增强（新代码）
    result = enrich_with_sid(df, sid_mapping, src_code_col, source)

    logger.debug(
        "DataFrame enrichment completed",
        event="security_enrich_complete",
        row_count=len(result),
    )

    return result
```

**Step 4: 运行测试验证通过**

```bash
pixi run -e dev pytest packages/data/tests/unit/accessors/test_security_accessor_unit.py -v
```

**Step 5: 提交**

```bash
git add packages/data/src/ditto_data/accessors/security_accessor.py
git commit -m "refactor(accessors): use enrichment pure function in SecuritiesAccessor

- Refactor enrich_dataframe_with_sid to use enrich_with_sid
- Keep mapping logic in Accessor, data merge in enrichment module"
```

---

### Task 1.3: 重构 SecurityStore 使用 enrichment 纯函数

**文件:**
- 修改: `packages/data/src/ditto_data/stores/security_store.py`
- 测试: `packages/data/tests/unit/stores/test_security_store_unit.py`

**Step 1: 查找 SecurityStore.enrich_with_symbol 方法**

使用 LSP 或 Read 找到该方法位置。

**Step 2: 如果存在，重构使用 enrichment.enrich_with_symbol**

**Step 3: 运行测试验证**

```bash
pixi run -e dev pytest packages/data/tests/unit/stores/test_security_store_unit.py -v
```

**Step 4: 提交**

```bash
git add packages/data/src/ditto_data/stores/security_store.py
git commit -m "refactor(stores): use enrichment.enrich_with_symbol in SecurityStore"
```

---

### Task 1.4: 重构 BarsAccessor 使用 enrichment 纯函数

**文件:**
- 修改: `packages/data/src/ditto_data/accessors/bars_accessor.py`
- 测试: `packages/data/tests/unit/accessors/test_bars_accessor_unit.py`

**Step 1: 找到 _enrich_with_status 方法**

使用 Read 或 LSP 查看 BarsAccessor._enrich_with_status 方法。

**Step 2: 编写失败的测试（验证现有行为）**

**Step 3: 重构使用 enrichment.enrich_with_status**

修改 `bars_accessor.py`:

```python
# 在顶部添加导入
from ditto_data.accessors.internal.enrichment import enrich_with_status

# 重构 _enrich_with_status 方法
def _enrich_with_status(
    self,
    df: pl.DataFrame,
    resolved: _ResolvedQuery,
) -> pl.DataFrame:
    """为 K 线数据添加状态列（使用 enrichment 纯函数）。"""
    status_df = self._stock_status_store.get(
        sids=resolved.sids,
        start=resolved.start.strftime("%Y-%m-%d") if resolved.start else None,
        end=resolved.end.strftime("%Y-%m-%d") if resolved.end else None,
    )

    return enrich_with_status(df, status_df, on=["sid", "trade_date"])
```

**Step 4: 运行测试验证**

```bash
pixi run -e dev pytest packages/data/tests/unit/accessors/test_bars_accessor_unit.py -v
```

**Step 5: 提交**

```bash
git add packages/data/src/ditto_data/accessors/bars_accessor.py
git commit -m "refactor(accessors): use enrichment.enrich_with_status in BarsAccessor"
```

---

### Task 1.5: 运行完整测试套件验证阶段 1

**Step 1: 运行单元测试**

```bash
pixi run -e dev pytest packages/data/tests/unit/ -v
```

**Step 2: 运行集成测试**

```bash
pixi run -e dev pytest packages/data/tests/integration/ -v
```

**Step 3: 运行类型检查**

```bash
pixi run -e dev type --path packages/data
```

**Step 4: 如果全部通过，标记阶段 1 完成**

---

## 阶段 2: 标识符处理重构（DataHub 双层 API）

### Task 2.1: 简化 BarsAccessor 接口（移除 src_codes/symbols）

**文件:**
- 修改: `packages/data/src/ditto_data/accessors/bars_accessor.py`
- 测试: `packages/data/tests/unit/accessors/test_bars_accessor_unit.py`

**Step 1: 编写测试验证新接口（只接受 sids）**

创建测试:

```python
def test_bars_accessor_only_accepts_sids():
    """验证 BarsQuery 只接受 sids 参数。"""
    # TODO: 这个测试需要在新实现后添加
    pass
```

**Step 2: 修改 BarsQuery 数据类**

修改 `packages/data/src/ditto_data/accessors/bars_accessor.py` 中的 `BarsQuery`:

```python
@dataclass(frozen=True)
class BarsQuery:
    """
    行情查询参数。

    注意: 只接受 sids 参数，不再接受 src_codes/symbols。
    请使用 DataHub 的便捷方法进行标识符转换。
    """
    sids: list[int] | None = None
    start: str | None = None
    end: str | None = None
    adj: AdjType = AdjType.NONE
    asof: str | None = None
    asset_class: Literal["stock", "etf", "index"] | None = None
    with_symbol: bool = False
    with_status: bool = False
    market_wide: bool = False
    raw: bool = False

    # 移除 src_codes 和 symbols 参数
```

**Step 3: 移除 _resolve_query 中的标识符解析逻辑**

修改 `BarsAccessor._resolve_query` 方法，移除对 `src_codes` 和 `symbols` 的处理。

**Step 4: 运行测试**

```bash
pixi run -e dev pytest packages/data/tests/unit/accessors/test_bars_accessor_unit.py -v
```

**Step 5: 提交**

```bash
git add packages/data/src/ditto_data/accessors/bars_accessor.py
git commit -m "refactor(accessors): simplify BarsAccessor to only accept sids

- Remove src_codes and symbols from BarsQuery
- Move identifier resolution to DataHub layer
- Accessor now has single responsibility for data access"
```

---

### Task 2.2: 简化 IndexAccessor 接口

**文件:**
- 修改: `packages/data/src/ditto_data/accessors/index_accessor.py`
- 测试: `packages/data/tests/unit/accessors/test_index_accessor_unit.py`

**Step 1: 查看当前 IndexAccessor 接口**

```python
# 使用 Read 查看当前实现
```

**Step 2: 移除 symbols 参数，只接受 sids**

**Step 3: 运行测试**

```bash
pixi run -e dev pytest packages/data/tests/unit/accessors/test_index_accessor_unit.py -v
```

**Step 4: 提交**

```bash
git add packages/data/src/ditto_data/accessors/index_accessor.py
git commit -m "refactor(accessors): simplify IndexAccessor to only accept sids"
```

---

### Task 2.3: 增强 DataHub 添加标识符转换门面

**文件:**
- 修改: `packages/data/src/ditto_data/hub.py`
- 测试: `packages/data/tests/unit/test_hub_unit.py`

**Step 1: 编写失败的测试**

在 `packages/data/tests/unit/test_hub_unit.py` 中添加:

```python
def test_resolve_identifiers_batch():
    """测试批量标识符解析。"""
    hub = datahub  # 假设存在此 fixture

    result = hub.resolve_identifiers(
        identifiers=["000001.SZ", "000002.SZ"],
        source="tushare",
        asof=None,
    )

    assert isinstance(result, dict)
    assert "000001.SZ" in result


def test_resolve_sids_from_inputs_mixed():
    """测试混合输入解析 SID。"""
    hub = datahub

    result = hub.resolve_sids_from_inputs(
        sids=[1, 2],
        src_codes=["000001.SZ"],
        symbols=["平安银行"],
    )

    assert len(result) >= 3  # 至少有 3 个 SID


def test_get_sid_symbol_mapping():
    """测试批量获取 SID 到 symbol 的映射。"""
    hub = datahub

    result = hub.get_sid_symbol_mapping([1, 2, 3])

    assert isinstance(result, dict)
    assert len(result) <= 3  # 可能有些 SID 不存在
```

**Step 2: 运行测试验证失败**

```bash
pixi run -e dev pytest packages/data/tests/unit/test_hub_unit.py::test_resolve_identifiers_batch -v
```

**Step 3: 在 DataHub 添加标识符转换方法**

修改 `packages/data/src/ditto_data/hub.py`:

```python
# 在 DataHub 类中添加以下方法

def resolve_identifiers(
    self,
    identifiers: list[str],
    source: str = "tushare",
    asof: str | None = None,
) -> dict[str, int]:
    """
    批量解析标识符为 SID。

    Args:
        identifiers: 标识符列表（src_code 或 symbol）。
        source: 数据源标识符。
        asof: Point-in-time 查询日期。

    Returns:
        {identifier: sid} 映射字典（只包含找到的标识符）。

    """
    return self.securities.resolve_identifiers_batch(identifiers, source, asof)


def resolve_sids_from_inputs(
    self,
    sids: list[int] | None = None,
    src_codes: list[str] | None = None,
    symbols: list[str] | None = None,
    source: str = "tushare",
    asof: str | None = None,
) -> list[int]:
    """
    从多种输入类型解析 SID 列表。

    Args:
        sids: SID 列表（已知的 SID，无需转换）。
        src_codes: src_code 列表（需要转换）。
        symbols: symbol 列表（需要转换）。
        source: 数据源标识符。
        asof: Point-in-time 查询日期。

    Returns:
        去重后的 SID 列表（排序）。

    """
    resolved: set[int] = set()

    if sids:
        resolved.update(sids)

    if src_codes:
        mapping = self.resolve_identifiers(src_codes, source, asof)
        resolved.update(mapping.values())

    if symbols:
        for symbol in symbols:
            sid = self.resolve_sid(symbol, source, asof)
            if sid:
                resolved.add(sid)

    return sorted(resolved)


def get_symbol(self, sid: int) -> str | None:
    """获取 SID 对应的 symbol。"""
    return self.securities.get_symbol(sid)


def get_src_code(
    self,
    sid: int,
    source: str = "tushare",
    asof: str | None = None,
) -> str | None:
    """获取 SID 对应的 src_code。"""
    return self.securities.get_src_code(sid, source, asof)


def get_sid_symbol_mapping(self, sids: list[int]) -> dict[int, str]:
    """批量获取 SID 到 symbol 的映射。"""
    result: dict[int, str] = {}
    for sid in sids:
        symbol = self.get_symbol(sid)
        if symbol:
            result[sid] = symbol
    return result
```

**Step 4: 运行测试验证通过**

```bash
pixi run -e dev pytest packages/data/tests/unit/test_hub_unit.py::test_resolve_identifiers_batch -v
pixi run -e dev pytest packages/data/tests/unit/test_hub_unit.py::test_resolve_sids_from_inputs_mixed -v
pixi run -e dev pytest packages/data/tests/unit/test_hub_unit.py::test_get_sid_symbol_mapping -v
```

**Step 5: 提交**

```bash
git add packages/data/src/ditto_data/hub.py
git add packages/data/tests/unit/test_hub_unit.py
git commit -m "feat(datahub): add identifier resolution facade methods

- Add resolve_identifiers, resolve_sids_from_inputs
- Add get_symbol, get_src_code, get_sid_symbol_mapping
- Support mixed identifier inputs (sids, src_codes, symbols)"
```

---

### Task 2.4: 添加 DataHub 便捷 API 方法

**文件:**
- 修改: `packages/data/src/ditto_data/hub.py`
- 测试: `packages/data/tests/unit/test_hub_unit.py`

**Step 1: 编写失败的测试**

```python
def test_get_bars_convenience_with_src_codes():
    """测试便捷 API 使用 src_codes 获取 K 线。"""
    hub = datahub

    result = hub.get_bars(
        src_codes=["000001.SZ"],
        start="2024-01-01",
        end="2024-01-31",
    )

    assert not result.is_empty()
    assert "sid" in result.columns


def test_get_bars_convenience_mixed_inputs():
    """测试便捷 API 使用混合输入。"""
    hub = datahub

    result = hub.get_bars(
        sids=[1, 2],
        src_codes=["000001.SZ"],
        symbols=["平安银行"],
        start="2024-01-01",
    )

    assert not result.is_empty()
```

**Step 2: 运行测试验证失败**

```bash
pixi run -e dev pytest packages/data/tests/unit/test_hub_unit.py::test_get_bars_convenience_with_src_codes -v
```

**Step 3: 实现便捷 API 方法**

在 `DataHub` 类中添加:

```python
# ========== 便捷 API（支持混合标识符）==========

def get_bars(
    self,
    sids: list[int] | None = None,
    src_codes: list[str] | None = None,
    symbols: list[str] | None = None,
    start: str | None = None,
    end: str | None = None,
    adj: Literal["none", "qfq", "hfq"] = "none",
    asof: str | None = None,
    asset_class: Literal["stock", "etf", "index"] | None = None,
    with_symbol: bool = False,
    with_status: bool = False,
    raw: bool = False,
) -> pl.DataFrame:
    """
    获取 K 线数据（便捷 API，支持混合标识符）。

    内部自动将标识符转换为 SID，然后调用底层 Accessor。

    Args:
        sids: SID 列表（已知的 SID，无需转换）。
        src_codes: src_code 列表（需要转换）。
        symbols: symbol 列表（需要转换）。
        start: 开始日期 (YYYY-MM-DD)。
        end: 结束日期 (YYYY-MM-DD)。
        adj: 复权类型 (none/qfq/hfq)。
        asof: Point-in-time 查询日期。
        asset_class: 资产类别过滤。
        with_symbol: 是否添加 symbol 列。
        with_status: 是否添加状态列（仅股票）。
        raw: 是否跳过复权和状态增强。

    Returns:
        K 线数据 DataFrame。

    Examples:
        >>> # 使用 src_code
        >>> bars = hub.get_bars(src_codes=["000001.SZ"], start="2024-01-01")

        >>> # 混合输入
        >>> bars = hub.get_bars(
        ...     sids=[1, 2],
        ...     src_codes=["000003.SZ"],
        ...     symbols=["万科A"],
        ... )

    """
    from ditto_data.accessors.bars_accessor import AdjType, BarsQuery

    # 解析 SID
    resolved_sids = self.resolve_sids_from_inputs(sids, src_codes, symbols, asof=asof)

    if not resolved_sids:
        return pl.DataFrame()

    # 构造查询对象
    query = BarsQuery(
        sids=resolved_sids,
        start=start,
        end=end,
        adj=AdjType(adj),
        asof=asof,
        asset_class=asset_class,
        with_symbol=with_symbol,
        with_status=with_status,
        raw=raw,
    )

    return self.bars.get(query)


def get_securities(
    self,
    sids: list[int] | None = None,
    src_codes: list[str] | None = None,
    symbols: list[str] | None = None,
    source: str = "tushare",
    asset_class: str | None = None,
    exchange: str | None = None,
    is_active: bool | None = True,
    asof: str | None = None,
) -> pl.DataFrame:
    """获取证券数据（便捷 API）。"""
    resolved_sids = self.resolve_sids_from_inputs(sids, src_codes, symbols, source, asof)
    return self.securities.get(
        sids=resolved_sids if resolved_sids else None,
        source=source,
        asset_class=asset_class,
        exchange=exchange,
        is_active=is_active,
        asof=asof,
    )


def get_index_bars(
    self,
    sids: list[int] | None = None,
    symbols: list[str] | None = None,
    start: str | None = None,
    end: str | None = None,
    adj: Literal["none", "qfq", "hfq"] = "none",
    asof: str | None = None,
    with_symbol: bool = False,
) -> pl.DataFrame:
    """获取指数 K 线（便捷 API）。"""
    resolved_sids = self.resolve_sids_from_inputs(sids=sids, symbols=symbols, asof=asof)

    if not resolved_sids:
        return pl.DataFrame()

    return self.index.get_bars(
        sids=resolved_sids,
        start=start,
        end=end,
        adj=adj,
        asof=asof,
        with_symbol=with_symbol,
    )
```

**Step 4: 运行测试验证通过**

```bash
pixi run -e dev pytest packages/data/tests/unit/test_hub_unit.py -k "convenience" -v
```

**Step 5: 提交**

```bash
git add packages/data/src/ditto_data/hub.py
git add packages/data/tests/unit/test_hub_unit.py
git commit -m "feat(datahub): add convenience API methods for mixed identifiers

- Add get_bars, get_securities, get_index_bars
- Support mixed identifier inputs (sids, src_codes, symbols)
- Auto-resolve identifiers internally"
```

---

### Task 2.5: 更新用户代码使用便捷 API

**文件:**
- 修改: `apps/port/src/ditto_port/**/*.py`
- 测试: `apps/port/tests/**/*.py`

**Step 1: 查找使用旧接口的代码**

使用 Grep 查找:

```bash
# 在 apps/port 中查找使用 BarsAccessor 的地方
grep -r "bars_accessor" apps/port/src --include="*.py"
grep -r "index_accessor" apps/port/src --include="*.py"
```

**Step 2: 更新使用便捷 API**

示例:

```python
# 之前
bars = hub.bars.get(
    BarsQuery(
        src_codes=["000001.SZ"],
        start="2024-01-01",
    )
)

# 之后
bars = hub.get_bars(
    src_codes=["000001.SZ"],
    start="2024-01-01",
)
```

**Step 3: 运行集成测试验证**

```bash
pixi run -e dev pytest apps/port/tests/integration/ -v
```

**Step 4: 提交**

```bash
git add apps/port/src
git commit -m "refactor(port): use DataHub convenience API for identifier resolution

- Migrate from Accessor direct calls to DataHub convenience methods
- Simplify identifier handling in application code"
```

---

### Task 2.6: 运行完整测试套件验证阶段 2

**Step 1: 运行所有单元测试**

```bash
pixi run -e dev pytest --unit -v
```

**Step 2: 运行所有集成测试**

```bash
pixi run -e dev pytest --integration -v
```

**Step 3: 运行类型检查**

```bash
pixi run -e dev type
```

**Step 4: 如果全部通过，标记阶段 2 完成**

---

## 阶段 3: PIT 纯函数提取

### Task 3.1: 创建 pit.py 模块

**文件:**
- 创建: `packages/data/src/ditto_data/accessors/internal/pit.py`
- 测试: `packages/data/tests/unit/accessors/internal/test_pit_unit.py`

**Step 1: 编写失败的测试**

创建测试文件 `packages/data/tests/unit/accessors/internal/test_pit_unit.py`:

```python
"""PIT 纯函数模块单元测试。"""

from datetime import date

import polars as pl
import pytest

from ditto_data.accessors.internal.pit import (
    filter_by_knowledge_date,
    parse_asof_date,
)


def test_parse_asof_date_from_string():
    """测试从字符串解析日期。"""
    result = parse_asof_date("2024-01-15")
    assert result == date(2024, 1, 15)


def test_parse_asof_date_from_date():
    """测试从 date 对象返回。"""
    input_date = date(2024, 1, 15)
    result = parse_asof_date(input_date)
    assert result == input_date


def test_filter_by_knowledge_date():
    """测试根据 knowledge_date 过滤。"""
    df = pl.DataFrame({
        "sid": [1, 1, 1],
        "knowledge_date": [
            date(2024, 1, 1),
            date(2024, 1, 15),
            date(2024, 2, 1),
        ],
        "value": [10, 20, 30],
    })

    result = filter_by_knowledge_date(df, date(2024, 1, 20))

    assert len(result) == 2
    assert result["value"].to_list() == [10, 20]


def test_filter_by_knowledge_date_fallback_to_trade_date(caplog):
    """测试缺少 knowledge_date 时回退到 trade_date。"""
    df = pl.DataFrame({
        "sid": [1, 1],
        "trade_date": [date(2024, 1, 1), date(2024, 1, 15)],
        "value": [10, 20],
    })

    result = filter_by_knowledge_date(df, date(2024, 1, 10))

    assert len(result) == 1
    assert result["value"].to_list() == [10]
    # 验证记录了警告
    assert "using trade_date (not PIT-safe)" in caplog.text
```

**Step 2: 运行测试验证失败**

```bash
pixi run -e dev pytest packages/data/tests/unit/accessors/internal/test_pit_unit.py -v
```

**Step 3: 实现最小代码**

创建 `packages/data/src/ditto_data/accessors/internal/pit.py`:

```python
"""
PIT (Point-in-Time) 查询纯函数模块。

提供 PIT 安全的日期过滤逻辑。
"""

from datetime import date

import polars as pl
from ditto_foundation import logger


def parse_asof_date(asof: date | str) -> date:
    """
    解析 asof 参数为 date 对象。

    Args:
        asof: date 对象或 ISO 格式字符串。

    Returns:
        解析后的 date 对象。
    """
    if isinstance(asof, str):
        return date.fromisoformat(asof)
    return asof


def filter_by_knowledge_date(
    df: pl.DataFrame,
    pit_dt: date,
    date_column: str = "knowledge_date",
) -> pl.DataFrame:
    """
    根据 PIT 日期过滤数据（优先使用 knowledge_date）。

    Args:
        df: 输入 DataFrame。
        pit_dt: Point-in-Time 日期。
        date_column: 日期列名，默认 knowledge_date。

    Returns:
        过滤后的 DataFrame。
    """
    if date_column in df.columns:
        return df.filter(pl.col(date_column) <= pit_dt)

    # Fallback to trade_date (会记录警告)
    if "trade_date" in df.columns:
        logger.warning(
            f"Data missing {date_column}, using trade_date (not PIT-safe)",
            event="pit_missing_knowledge_date",
        )
        return df.filter(pl.col("trade_date") <= pit_dt)

    return df
```

**Step 4: 运行测试验证通过**

```bash
pixi run -e dev pytest packages/data/tests/unit/accessors/internal/test_pit_unit.py -v
```

**Step 5: 提交**

```bash
git add packages/data/src/ditto_data/accessors/internal/pit.py
git add packages/data/tests/unit/accessors/internal/test_pit_unit.py
git commit -m "feat(accessors): add PIT pure function module

- Add parse_asof_date, filter_by_knowledge_date
- Pure functions for PIT-safe date filtering
- Fallback to trade_date with warning"
```

---

### Task 3.2: 重构 adjustment.py 使用 pit 纯函数

**文件:**
- 修改: `packages/data/src/ditto_data/accessors/internal/adjustment.py`
- 测试: `packages/data/tests/unit/accessors/internal/test_adjustment_unit.py`

**注意:** adjustment.py 已经有 `parse_asof_date` 和 `filter_baseline_by_asof`。需要重构使用 pit 模块。

**Step 1: 查看当前 adjustment.py 实现**

已经读取，发现它有自己的 `parse_asof_date` 和 `filter_baseline_by_asof`。

**Step 2: 重构 adjustment.py 导入并使用 pit 模块**

修改 `packages/data/src/ditto_data/accessors/internal/adjustment.py`:

```python
# 移除本地的 parse_asof_date，使用 pit 模块的
from ditto_data.accessors.internal.pit import (
    filter_by_knowledge_date,
    parse_asof_date,
)

# 删除本地的 parse_asof_date 函数（第 13-26 行）

# 重构 filter_baseline_by_asof 使用 pit 模块
def filter_baseline_by_asof(adj_df: pl.DataFrame, pit_dt: date) -> pl.DataFrame:
    """
    根据 asof 日期过滤调整因子数据（用于计算 baseline）。

    优先使用 knowledge_date，如果不存在则使用 trade_date（会记录警告）。

    Args:
        adj_df: 调整因子数据。
        pit_dt: Point-in-Time 日期。

    Returns:
        过滤后的调整因子数据。
    """
    return filter_by_knowledge_date(adj_df, pit_dt, date_column="knowledge_date")

# 更新 apply_qfq_adj 中的 parse_asof_date 调用
# 第 84-86 行
pit_dt = parse_asof_date(asof)
baseline_df = filter_baseline_by_asof(adj_df, pit_dt)
```

**Step 3: 运行测试验证**

```bash
pixi run -e dev pytest packages/data/tests/unit/accessors/internal/ -v
```

**Step 4: 提交**

```bash
git add packages/data/src/ditto_data/accessors/internal/adjustment.py
git commit -m "refactor(accessors): use pit.parse_asof_date in adjustment module

- Remove duplicate parse_asof_date
- Use pit module for PIT date filtering
- Keep adjustment-specific logic in adjustment module"
```

---

### Task 3.3: 运行完整测试套件验证阶段 3

**Step 1: 运行所有单元测试**

```bash
pixi run -e dev pytest --unit -v
```

**Step 2: 运行所有集成测试**

```bash
pixi run -e dev pytest --integration -v
```

**Step 3: 运行类型检查**

```bash
pixi run -e dev type
```

**Step 4: 如果全部通过，标记阶段 3 完成**

---

## 最终验证

### Task 4.1: 运行 CI 完整检查

**Step 1: 运行完整 CI**

```bash
pixi run -e dev ci
```

**Step 2: 检查测试覆盖率**

```bash
pixi run -e dev pytest --cov=packages/data --cov-report=term-missing
```

**Step 3: 确认覆盖率 >= 80%**

### Task 4.2: 代码质量检查

**Step 1: 运行 ruff lint**

```bash
pixi run -e dev lint
```

**Step 2: 运行 ruff format**

```bash
pixi run -e dev fmt
```

### Task 4.3: 最终提交

**Step 1: 查看所有变更**

```bash
git status
git diff --stat
```

**Step 2: 创建最终总结 commit**

```bash
git commit --allow-empty -m "feat(accessors): complete accessors refactoring

Summary of changes:
- Added enrichment pure function module (enrich_with_sid, enrich_with_symbol, enrich_with_status)
- Added PIT pure function module (parse_asof_date, filter_by_knowledge_date)
- Refactored SecuritiesAccessor, SecurityStore, BarsAccessor to use enrichment
- Refactored adjustment.py to use pit module
- Implemented DataHub dual-layer API:
  * Convenience API: get_bars(src_codes, symbols, sids, ...)
  * Low-level API: bars.get(sids=[...]) - SID only
- Added identifier resolution facade methods to DataHub
- Simplified BarsAccessor and IndexAccessor to accept only sids
- Updated app/port code to use convenience API

Architecture improvements:
- Clear separation: DataHub handles identifier conversion, Accessors handle data
- Reusable pure functions for enrichment and PIT operations
- Better testability with pure functions
- PIT safety with centralized date filtering logic
- Reduced code duplication across accessors

All tests pass, coverage >= 80%, type checking clean."
```

---

## 文件清单

### 新增文件

| 文件 | 用途 |
|------|------|
| `packages/data/src/ditto_data/accessors/internal/enrichment.py` | 数据增强纯函数 |
| `packages/data/src/ditto_data/accessors/internal/pit.py` | PIT 查询纯函数 |
| `packages/data/tests/unit/accessors/internal/test_enrichment_unit.py` | enrichment 单元测试 |
| `packages/data/tests/unit/accessors/internal/test_pit_unit.py` | pit 单元测试 |

### 修改文件

| 文件 | 修改内容 |
|------|----------|
| `packages/data/src/ditto_data/accessors/internal/__init__.py` | 导出 enrichment 和 pit 函数 |
| `packages/data/src/ditto_data/accessors/internal/adjustment.py` | 使用 pit.parse_asof_date |
| `packages/data/src/ditto_data/accessors/security_accessor.py` | 使用 enrichment.enrich_with_sid |
| `packages/data/src/ditto_data/accessors/bars_accessor.py` | 使用 enrichment.enrich_with_status，简化接口 |
| `packages/data/src/ditto_data/accessors/index_accessor.py` | 简化接口 |
| `packages/data/src/ditto_data/stores/security_store.py` | 使用 enrichment.enrich_with_symbol |
| `packages/data/src/ditto_data/hub.py` | 添加标识符转换门面和便捷 API |
| `packages/data/tests/unit/test_hub_unit.py` | DataHub 新方法测试 |
| `apps/port/src/ditto_port/**/*.py` | 使用便捷 API |

---

## 架构收益

| 方面 | 改进 |
|------|------|
| **职责清晰** | DataHub 处理标识符转换，Accessor 只处理数据 |
| **代码复用** | enrichment、pit 纯函数可被多处复用 |
| **可测试性** | 纯函数易于单元测试 |
| **PIT 安全** | PIT 逻辑集中管理，减少出错风险 |
| **维护性** | 标识符转换逻辑统一，不再分散重复 |

---

## 执行顺序

1. **阶段 1 (高优先级)**: enrichment 纯函数提取
2. **阶段 2 (高优先级)**: 标识符处理重构
3. **阶段 3 (中优先级)**: PIT 纯函数提取
4. **最终验证**: 完整 CI + 代码质量检查
