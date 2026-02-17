# 领域术语重构实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将 `symbol` 统一重命名为 `ticker`，建立清晰的证券标识术语体系

**Architecture:** 自底向上重构，从数据库层 → 模型层 → Store层 → Service层 → Source层，最后同步测试

**Tech Stack:** Python 3.12, Polars, SQLite, Pytest

---

## Phase 1: 数据库层

### Task 1: 更新 schema.sql

**Files:**
- Modify: `packages/datahub/src/ditto_datahub/scripts/schema.sql`

**Step 1: 修改 instrument 表字段名**

将第 25 行的 `symbol TEXT NOT NULL` 改为 `ticker TEXT NOT NULL`

```sql
-- 修改前
symbol TEXT NOT NULL,

-- 修改后
ticker TEXT NOT NULL,
```

**Step 2: 修改索引名**

将第 38 行的索引名从 `idx_instrument_symbol` 改为 `idx_instrument_ticker`

```sql
-- 修改前
CREATE INDEX IF NOT EXISTS idx_instrument_symbol ON instrument(symbol);

-- 修改后
CREATE INDEX IF NOT EXISTS idx_instrument_ticker ON instrument(ticker);
```

**Step 3: 验证修改**

Run: `grep -n "symbol\|ticker" packages/datahub/src/ditto_datahub/scripts/schema.sql`

Expected: 只有 `ticker` 和 `source_ticker`，没有单独的 `symbol`

**Step 4: Commit**

```bash
git add packages/datahub/src/ditto_datahub/scripts/schema.sql
git commit -m "refactor(db): symbol → ticker 字段重命名"
```

---

### Task 2: 更新 sqlite_pool.py 的 schema 验证

**Files:**
- Modify: `packages/foundation/src/ditto_foundation/db/sqlite_pool.py:212`

**Step 1: 修改 required_instrument_columns**

将第 212 行的 `"symbol"` 改为 `"ticker"`

```python
# 修改前
required_instrument_columns = {
    "instrument_id",
    "symbol",
    "asset_class",
    "exchange",
}

# 修改后
required_instrument_columns = {
    "instrument_id",
    "ticker",
    "asset_class",
    "exchange",
}
```

**Step 2: 运行类型检查**

Run: `pixi run -e dev type packages/foundation/src/ditto_foundation/db/sqlite_pool.py`

Expected: PASS

**Step 3: Commit**

```bash
git add packages/foundation/src/ditto_foundation/db/sqlite_pool.py
git commit -m "refactor(foundation): schema 验证 symbol → ticker"
```

---

## Phase 2: Models 层

### Task 3: 更新 InstrumentRegistration 模型

**Files:**
- Modify: `packages/datahub/src/ditto_datahub/models/metadata.py:129-131`
- Test: `packages/datahub/tests/unit/models/test_security_unit.py`

**Step 1: 修改 InstrumentRegistration 字段**

```python
# 修改前
source_ticker: str
symbol: str
name: str

# 修改后
source_ticker: str
ticker: str
name: str
```

**Step 2: 更新文档字符串中的 symbol 引用**

在第 117-119 行的文档字符串中：

```python
# 修改前
    Attributes:
        source_ticker: 源代码（如 "600000.SH"），数据库中存储为 source_ticker
        symbol: 显示符号（如 "600000"）
        name: 证券名称

# 修改后
    Attributes:
        source_ticker: 源代码（如 "600000.SH"），数据库中存储为 source_ticker
        ticker: 裸代码（如 "600000"）
        name: 证券名称
```

**Step 3: 运行类型检查**

Run: `pixi run -e dev type packages/datahub/src/ditto_datahub/models/metadata.py`

Expected: PASS（可能有下游引用错误，后续 Task 修复）

**Step 4: 更新测试文件断言**

修改 `packages/datahub/tests/unit/models/test_security_unit.py`:

```python
# 修改前
assert registration.symbol == "600000"

# 修改后
assert registration.ticker == "600000"
```

**Step 5: 运行测试验证**

Run: `pixi run -e dev pytest packages/datahub/tests/unit/models/test_security_unit.py -v`

Expected: PASS

**Step 6: Commit**

```bash
git add packages/datahub/src/ditto_datahub/models/metadata.py
git add packages/datahub/tests/unit/models/test_security_unit.py
git commit -m "refactor(models): InstrumentRegistration.symbol → ticker"
```

---

## Phase 3: Store 层

### Task 4: 重构 InstrumentReader 方法名

**Files:**
- Modify: `packages/datahub/src/ditto_datahub/stores/metadata/instrument/instrument_reader.py`
- Test: `packages/datahub/tests/unit/stores/test_security_store_unit.py`

**Step 1: 重命名 get_symbol → get_ticker**

修改第 387-401 行：

```python
# 修改前
def get_symbol(self, instrument_id: int) -> str | None:
    """
    获取 symbol。

    Args:
        instrument_id: 证券 ID

    Returns:
        symbol 或 None（未找到时）

    """
    row = self._client.fetchone(
        "SELECT symbol FROM instrument WHERE instrument_id = ?", [instrument_id]
    )
    return cast(str, row["symbol"]) if row else None

# 修改后
def get_ticker(self, instrument_id: int) -> str | None:
    """
    获取 ticker（裸代码）。

    Args:
        instrument_id: 证券 ID

    Returns:
        ticker 或 None（未找到时）

    """
    row = self._client.fetchone(
        "SELECT ticker FROM instrument WHERE instrument_id = ?", [instrument_id]
    )
    return cast(str, row["ticker"]) if row else None
```

**Step 2: 重命名 get_instrument_id_symbol_map → get_instrument_id_ticker_map**

修改第 403-447 行，将所有 `symbol` 替换为 `ticker`：

```python
# 修改前
def get_instrument_id_symbol_map(
    self, instrument_ids: list[int] | None = None
) -> dict[int, str]:
    """
    批量获取 instrument_id 到 symbol 的映射。
    ...
    """
    cache_key = (
        f"instrument_id_symbol_map:{','.join(map(str, sorted(instrument_ids)))}"
    )
    ...
    rows = self._client.fetchall(
        f"SELECT instrument_id, symbol FROM instrument WHERE {in_clause}",
        sids_list,
    )
    ...
    result = {cast(int, r["instrument_id"]): cast(str, r["symbol"]) for r in rows}

# 修改后
def get_instrument_id_ticker_map(
    self, instrument_ids: list[int] | None = None
) -> dict[int, str]:
    """
    批量获取 instrument_id 到 ticker 的映射。
    ...
    """
    cache_key = (
        f"instrument_id_ticker_map:{','.join(map(str, sorted(instrument_ids)))}"
    )
    ...
    rows = self._client.fetchall(
        f"SELECT instrument_id, ticker FROM instrument WHERE {in_clause}",
        sids_list,
    )
    ...
    result = {cast(int, r["instrument_id"]): cast(str, r["ticker"]) for r in rows}
```

**Step 3: 重命名 enrich_with_symbol → enrich_with_ticker**

修改第 465-487 行：

```python
# 修改前
def enrich_with_symbol(self, df: pl.DataFrame) -> pl.DataFrame:
    """
    向 DataFrame 添加 symbol 列。
    ...
    """
    ...
    mapping = self.get_instrument_id_symbol_map(instrument_ids)
    return df.with_columns(
        pl.col("instrument_id")
        .map_elements(lambda x: mapping.get(x, None), return_dtype=pl.String)
        .alias("symbol")
    )

# 修改后
def enrich_with_ticker(self, df: pl.DataFrame) -> pl.DataFrame:
    """
    向 DataFrame 添加 ticker 列。
    ...
    """
    ...
    mapping = self.get_instrument_id_ticker_map(instrument_ids)
    return df.with_columns(
        pl.col("instrument_id")
        .map_elements(lambda x: mapping.get(x, None), return_dtype=pl.String)
        .alias("ticker")
    )
```

**Step 4: 运行类型检查**

Run: `pixi run -e dev type packages/datahub/src/ditto_datahub/stores/metadata/instrument/`

Expected: 可能有下游引用错误，后续 Task 修复

**Step 5: Commit**

```bash
git add packages/datahub/src/ditto_datahub/stores/metadata/instrument/instrument_reader.py
git commit -m "refactor(store): InstrumentReader symbol → ticker 方法重命名"
```

---

### Task 5: 更新 InstrumentWriter

**Files:**
- Modify: `packages/datahub/src/ditto_datahub/stores/metadata/instrument/instrument_writer.py`

**Step 1: 修改 register 方法中的 SQL**

修改第 88-96 行：

```python
# 修改前
self._client.execute(
    """INSERT INTO instrument
    (
        instrument_id, symbol, name, exchange, board, asset_class,
        list_date, is_active
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, TRUE)""",
    [
        instrument_id,
        registration.symbol,
        ...
    ],
)

# 修改后
self._client.execute(
    """INSERT INTO instrument
    (
        instrument_id, ticker, name, exchange, board, asset_class,
        list_date, is_active
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, TRUE)""",
    [
        instrument_id,
        registration.ticker,
        ...
    ],
)
```

**Step 2: 更新日志中的字段名**

修改第 78 行和其他 `symbol=` 日志：

```python
# 修改前
symbol=registration.symbol,

# 修改后
ticker=registration.ticker,
```

**Step 3: 运行类型检查**

Run: `pixi run -e dev type packages/datahub/src/ditto_datahub/stores/metadata/instrument/`

Expected: PASS

**Step 4: Commit**

```bash
git add packages/datahub/src/ditto_datahub/stores/metadata/instrument/instrument_writer.py
git commit -m "refactor(store): InstrumentWriter symbol → ticker"
```

---

## Phase 4: Service 层

### Task 6: 更新 MetadataService

**Files:**
- Modify: `packages/datahub/src/ditto_datahub/services/metadata_service.py`

**Step 1: 重命名 get_symbol → get_ticker**

修改第 309-321 行：

```python
# 修改前
@traced("metadata.instrument.get_symbol")
def get_symbol(self, instrument_id: int) -> str | None:
    """
    根据 instrument_id 获取交易代码。

    Args:
        instrument_id: instrument_id.

    Returns:
        交易代码 或 None.

    """
    return self._instrument_reader.get_symbol(instrument_id)

# 修改后
@traced("metadata.instrument.get_ticker")
def get_ticker(self, instrument_id: int) -> str | None:
    """
    根据 instrument_id 获取裸代码。

    Args:
        instrument_id: instrument_id.

    Returns:
        裸代码 或 None.

    """
    return self._instrument_reader.get_ticker(instrument_id)
```

**Step 2: 运行类型检查**

Run: `pixi run -e dev type packages/datahub/src/ditto_datahub/services/metadata_service.py`

Expected: PASS

**Step 3: Commit**

```bash
git add packages/datahub/src/ditto_datahub/services/metadata_service.py
git commit -m "refactor(service): MetadataService.get_symbol → get_ticker"
```

---

### Task 7: 更新 MarketService

**Files:**
- Modify: `packages/datahub/src/ditto_datahub/services/market_service.py`

**Step 1: 搜索 symbol 引用并替换**

Run: `grep -n "symbol" packages/datahub/src/ditto_datahub/services/market_service.py`

根据搜索结果，将所有 `symbol` 替换为 `ticker`，包括：
- 方法名中的 `symbol`
- SQL 查询中的 `symbol`
- 日志中的 `symbol`

**Step 2: 运行类型检查**

Run: `pixi run -e dev type packages/datahub/src/ditto_datahub/services/market_service.py`

Expected: PASS

**Step 3: Commit**

```bash
git add packages/datahub/src/ditto_datahub/services/market_service.py
git commit -m "refactor(service): MarketService symbol → ticker"
```

---

## Phase 5: Source 层

### Task 8: 更新 TushareDataTransformer

**Files:**
- Modify: `packages/datahub/src/ditto_datahub/sources/tushare/processors/transformer.py`

**Step 1: 更新 ETF_BASIC_MAPPING 的 computed_columns**

修改第 117-129 行：

```python
# 修改前
ETF_BASIC_MAPPING = ColumnMapping(
    rename={"ts_code": "source_ticker"},
    date_columns={"list_date": "%Y%m%d"},
    float_columns=[],
    computed_columns={
        "symbol": pl.col("source_ticker").str.split(".").list.get(0),
        "exchange": pl.col("source_ticker")
        .str.split(".")
        .list.get(1)
        .replace({"SH": "SSE", "SZ": "SZSE"}),
    },
    output_columns=("source_ticker", "symbol", "name", "exchange", "list_date"),
)

# 修改后
ETF_BASIC_MAPPING = ColumnMapping(
    rename={"ts_code": "source_ticker"},
    date_columns={"list_date": "%Y%m%d"},
    float_columns=[],
    computed_columns={
        "ticker": pl.col("source_ticker").str.split(".").list.get(0),
        "exchange": pl.col("source_ticker")
        .str.split(".")
        .list.get(1)
        .replace({"SH": "SSE", "SZ": "SZSE"}),
    },
    output_columns=("source_ticker", "ticker", "name", "exchange", "list_date"),
)
```

**Step 2: 更新 STOCK_BASIC_MAPPING 的 output_columns**

修改第 131-137 行：

```python
# 修改前
STOCK_BASIC_MAPPING = ColumnMapping(
    rename={"ts_code": "source_ticker"},
    date_columns={"list_date": "%Y%m%d"},
    float_columns=[],
    output_columns=("source_ticker", "symbol", "name", "exchange", "list_date"),
)

# 修改后
STOCK_BASIC_MAPPING = ColumnMapping(
    rename={"ts_code": "source_ticker"},
    date_columns={"list_date": "%Y%m%d"},
    float_columns=[],
    output_columns=("source_ticker", "ticker", "name", "exchange", "list_date"),
)
```

**Step 3: 更新测试文件**

修改 `packages/datahub/tests/unit/sources/tushare/test_transformer_unit.py` 中的相关断言。

**Step 4: 运行测试**

Run: `pixi run -e dev pytest packages/datahub/tests/unit/sources/tushare/test_transformer_unit.py -v`

Expected: PASS

**Step 5: Commit**

```bash
git add packages/datahub/src/ditto_datahub/sources/tushare/processors/transformer.py
git add packages/datahub/tests/unit/sources/tushare/test_transformer_unit.py
git commit -m "refactor(source): transformer symbol → ticker"
```

---

### Task 9: 清理 Source Schema 中的模糊 ticker 字段

**Files:**
- Modify: `packages/datahub/src/ditto_datahub/sources/schemas/metadata_schemas.py`

**Step 1: 移除 INSTRUMENT_SOURCE_SCHEMA 中冗余的 ticker 字段**

修改第 18-31 行：

```python
# 修改前
INSTRUMENT_SOURCE_SCHEMA = SourceSchema(
    dataset="instrument",
    key_columns=("instrument_id",),
    schema={
        "instrument_id": pl.String,
        "source_ticker": pl.String,
        "ticker": pl.String,  # ← 移除这行，含义模糊
        "name": pl.String,
        "exchange": pl.String,
        "list_date": pl.Date,
        "delist_date": pl.Date,
        "instrument_type": pl.String,
    },
)

# 修改后
INSTRUMENT_SOURCE_SCHEMA = SourceSchema(
    dataset="instrument",
    key_columns=("instrument_id",),
    schema={
        "instrument_id": pl.String,
        "source_ticker": pl.String,
        "name": pl.String,
        "exchange": pl.String,
        "list_date": pl.Date,
        "delist_date": pl.Date,
        "instrument_type": pl.String,
    },
)
```

**Step 2: 运行类型检查**

Run: `pixi run -e dev type packages/datahub/src/ditto_datahub/sources/schemas/metadata_schemas.py`

Expected: PASS

**Step 3: Commit**

```bash
git add packages/datahub/src/ditto_datahub/sources/schemas/metadata_schemas.py
git commit -m "refactor(source): 移除 INSTRUMENT_SOURCE_SCHEMA 中冗余的 ticker 字段"
```

---

## Phase 6: 展示层 - 新增

### Task 10: 添加 get_standard_ticker 工具函数

**Files:**
- Create: `packages/foundation/src/ditto_foundation/util/ticker_utils.py`
- Test: `packages/foundation/tests/unit/util/test_ticker_utils_unit.py`

**Step 1: 创建工具函数**

```python
"""Ticker 相关工具函数."""

from __future__ import annotations

__all__ = ["get_standard_ticker"]


def get_standard_ticker(ticker: str, exchange: str) -> str:
    """
    生成标准可读编码（仅展示层使用）.

    Args:
        ticker: 裸代码（如 "600000"）
        exchange: 交易所代码（如 "SSE"）

    Returns:
        标准可读编码（如 "600000.SSE"）

    Examples:
        >>> get_standard_ticker("600000", "SSE")
        '600000.SSE'
        >>> get_standard_ticker("000001", "SZSE")
        '000001.SZSE'

    """
    return f"{ticker}.{exchange}"
```

**Step 2: 导出函数**

在 `packages/foundation/src/ditto_foundation/util/__init__.py` 中添加导出。

**Step 3: 编写单元测试**

```python
"""test_ticker_utils_unit.py"""

import pytest
from ditto_foundation.util.ticker_utils import get_standard_ticker


class TestGetStandardTicker:
    def test_sse_ticker(self) -> None:
        """测试上交所代码."""
        result = get_standard_ticker("600000", "SSE")
        assert result == "600000.SSE"

    def test_szse_ticker(self) -> None:
        """测试深交所代码."""
        result = get_standard_ticker("000001", "SZSE")
        assert result == "000001.SZSE"

    def test_bse_ticker(self) -> None:
        """测试北交所代码."""
        result = get_standard_ticker("830799", "BSE")
        assert result == "830799.BSE"
```

**Step 4: 运行测试**

Run: `pixi run -e dev pytest packages/foundation/tests/unit/util/test_ticker_utils_unit.py -v`

Expected: PASS

**Step 5: Commit**

```bash
git add packages/foundation/src/ditto_foundation/util/ticker_utils.py
git add packages/foundation/src/ditto_foundation/util/__init__.py
git add packages/foundation/tests/unit/util/test_ticker_utils_unit.py
git commit -m "feat(foundation): 添加 get_standard_ticker 工具函数"
```

---

## Phase 7: 测试同步

### Task 11: 更新 Store 层测试

**Files:**
- Modify: `packages/datahub/tests/unit/stores/test_security_store_unit.py`
- Modify: `packages/datahub/tests/integration/stores/test_security_store_integration.py`

**Step 1: 批量替换 symbol → ticker**

Run: `grep -n "symbol" packages/datahub/tests/unit/stores/test_security_store_unit.py`

将所有 `symbol` 替换为 `ticker`，包括：
- 断言中的字段名
- mock 数据中的字段名
- 方法调用

**Step 2: 运行测试**

Run: `pixi run -e dev pytest packages/datahub/tests/unit/stores/test_security_store_unit.py -v`

Expected: PASS

**Step 3: 对集成测试做同样操作**

**Step 4: Commit**

```bash
git add packages/datahub/tests/unit/stores/test_security_store_unit.py
git add packages/datahub/tests/integration/stores/test_security_store_integration.py
git commit -m "test: Store 层测试 symbol → ticker"
```

---

### Task 12: 更新其他测试文件

**Files:**
- Modify: `packages/datahub/tests/integration/runtime/test_sql_engine_integration.py`
- Modify: `apps/port/tests/unit/services/ingestion/quality/test_reconciliation_service_unit.py`
- Modify: `apps/port/tests/unit/services/ingestion/quality/conftest.py`
- Modify: `apps/port/src/ditto_port/services/ingestion/quality/reconciliation_service.py`

**Step 1: 逐个文件检查并替换**

对每个文件执行：
1. `grep -n "symbol" <file>` 查找所有 symbol 引用
2. 将 `symbol` 替换为 `ticker`
3. 将 `enrich_with_symbol` 替换为 `enrich_with_ticker`
4. 将 `get_symbol` 替换为 `get_ticker`

**Step 2: 运行受影响的测试**

Run: `pixi run -e dev pytest packages/datahub/tests/integration/runtime/test_sql_engine_integration.py -v`

Run: `pixi run -e dev pytest apps/port/tests/unit/services/ingestion/quality/ -v`

Expected: PASS

**Step 3: Commit**

```bash
git add packages/datahub/tests/integration/runtime/test_sql_engine_integration.py
git add apps/port/tests/unit/services/ingestion/quality/
git add apps/port/src/ditto_port/services/ingestion/quality/reconciliation_service.py
git commit -m "test: 剩余测试文件 symbol → ticker"
```

---

## Phase 8: 验证

### Task 13: 完整验证

**Step 1: 运行完整检查**

Run: `pixi run -e dev check`

Expected: ALL PASS

**Step 2: 确认无遗漏的 symbol 引用**

Run: `grep -r "\bsymbol\b" packages/ apps/ --include="*.py" | grep -v "# " | grep -v "test_" | head -20`

Expected: 无结果或只有注释中的 symbol

**Step 3: 最终 Commit**

```bash
git add -A
git commit -m "refactor: 领域术语重构完成 - symbol → ticker"
```

---

## 注意事项

1. **数据库迁移**: 此重构需要重建 SQLite 数据库，因为 SQLite 不支持 `ALTER COLUMN`。生产环境需要：
   - 备份现有数据库
   - 使用新的 schema.sql 重建
   - 迁移数据（如需保留）

2. **API 兼容性**: `get_symbol()` → `get_ticker()` 是 breaking change，如有外部调用方需要通知

3. **测试优先**: 每个 Task 都要先运行测试确保通过再 Commit
