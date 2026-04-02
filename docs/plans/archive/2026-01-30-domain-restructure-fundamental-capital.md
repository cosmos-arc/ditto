# Domain Restructure: Fundamental & Capital 域重构实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将当前 Capital 域重新划分为 Fundamental（基本面）和 Capital（资金面）两个独立的域，实现清晰的架构边界。

**Architecture:**
- **Fundamental 域**: 企业经营与财务数据（三大报表、分红、公司行为、业绩预告/快报）
- **Capital 域**: 资金面与筹码数据（融资融券、股权质押、持仓数据）
- 使用 SQLiteClient + PIT 模式，保持与现有架构一致
- 数据摄入使用 Tushare Adapter

**Tech Stack:** Python 3.12+, Polars, Pydantic, Pyright Strict, SQLite

---

## 背景与现状

### 当前问题
- Capital 域混合了"基本面"和"资金面"两类不同驱动变量的数据
- 财务报表、估值指标属于 Fundamental（企业经营）
- 融资融券、股权质押属于 Capital（资金供需）
- 架构边界不清，不利于后续扩展

### 域划分原则
| 域 | 核心特征 | 数据类型 |
|---|---------|---------|
| **Fundamental** | 企业经营与内在价值 | 财务报表、分红、公司行为、业绩预告 |
| **Capital** | 资金供需与筹码结构 | 融资融券、股权质押、持仓数据 |

---

## 数据迁移清单

### Fundamental 域（新增，7 个数据集）

| # | 数据类型 | 来源 | Tushare API | PIT |
|---|---------|------|-------------|-----|
| 1 | balance_sheet | Capital 迁移 | balancesheet | ✅ |
| 2 | income_statement | Capital 迁移 | income | ✅ |
| 3 | cash_flow | Capital 迁移 | cashflow | ✅ |
| 4 | dividend | Capital 迁移 | div_oper | ✅ |
| 5 | corporate_actions | Capital 迁移 | ba | ❌ |
| 6 | forecast | 新增 | forecast | ✅ |
| 7 | express | 新增 | express | ✅ |

### Capital 域（重构后，5 个数据集）

| # | 数据类型 | 变更 | Tushare API | 说明 |
|---|---------|------|-------------|------|
| 1 | margin_trading | 保留 | margin | 融资融券 |
| 2 | pledge_ratio | 保留 | pledge | 股权质押 |
| 3 | fund_holding | 新增 | 待定 | 公募基金持仓 |
| 4 | inst_holding | 新增 | 待定 | 机构持仓 |
| 5 | shareholder | 新增 | 待定 | 大股东持股 |

### 移除/暂不实现

| 数据类型 | 原位置 | 处理 |
|---------|--------|------|
| valuation_metrics | Capital | 移除（属于 features） |
| futures | Capital | 暂不实现 |
| index_composition | Capital | 待讨论（Market 已有 index_constituent） |

---

## 目录结构

```
packages/data/src/ditto_data/domains/
├── fundamental/              # 新增
│   ├── __init__.py
│   ├── financial/           # 财务报表子域
│   │   ├── __init__.py
│   │   ├── balance_sheet_store.py
│   │   ├── income_statement_store.py
│   │   └── cash_flow_store.py
│   ├── corporate/           # 公司行为子域
│   │   ├── __init__.py
│   │   ├── dividend_store.py
│   │   └── corporate_actions_store.py
│   ├── forecast/            # 业绩预告/快报子域
│   │   ├── __init__.py
│   │   ├── forecast_store.py
│   │   └── express_store.py
│   ├── fundamental_store.py      # 域级统一入口
│   └── fundamental_ingestion.py  # 数据摄入服务
├── capital/                 # 重构后
│   ├── __init__.py
│   ├── margin/              # 融资融券子域
│   │   ├── __init__.py
│   │   └── margin_trading_store.py
│   ├── pledge/              # 股权质押子域
│   │   ├── __init__.py
│   │   └── pledge_ratio_store.py
│   ├── holding/             # 持仓数据子域（新增）
│   │   ├── __init__.py
│   │   ├── fund_holding_store.py
│   │   ├── inst_holding_store.py
│   │   └── shareholder_store.py
│   ├── capital_store.py
│   └── capital_ingestion.py
├── market/                  # 不变
└── metadata/                # 不变
```

---

## 任务清单

### 阶段 1：创建 Fundamental 域基础结构

#### Task 1: 创建 Fundamental 域目录和 __init__.py

**Files:**
- Create: `packages/data/src/ditto_data/domains/fundamental/__init__.py`
- Create: `packages/data/src/ditto_data/domains/fundamental/financial/__init__.py`
- Create: `packages/data/src/ditto_data/domains/fundamental/corporate/__init__.py`
- Create: `packages/data/src/ditto_data/domains/fundamental/forecast/__init__.py`

**Step 1: 创建域级 __init__.py**

```python
# packages/data/src/ditto_data/domains/fundamental/__init__.py
"""Fundamental Domain - 企业基本面数据域。

提供财务报表、分红、公司行为、业绩预告等数据的存储和查询，
支持完整的 PIT（Point-in-Time）能力。

命名映射：
- instrument_id: 标的 ID（统一标识符）
- PIT 时间: effective_from, effective_to
"""

from ditto_data.domains.fundamental.fundamental_store import FundamentalStore

__all__ = ["FundamentalStore"]
```

**Step 2: 创建子域 __init__.py 文件**

```python
# packages/data/src/ditto_data/domains/fundamental/financial/__init__.py
"""Financial 子域 - 财务报表数据。"""

# 导入将在后续任务中添加

# packages/data/src/ditto_data/domains/fundamental/corporate/__init__.py
"""Corporate 子域 - 公司行为数据。"""

# packages/data/src/ditto_data/domains/fundamental/forecast/__init__.py
"""Forecast 子域 - 业绩预告/快报数据。"""
```

**Step 3: 运行类型检查**

```bash
pixi run -e dev type
```

Expected: PASS

**Step 4: 提交**

```bash
git add packages/data/src/ditto_data/domains/fundamental/
git commit -m "feat(fundamental): create fundamental domain structure"
```

---

#### Task 2: 实现 FundamentalStore 基础结构

**Files:**
- Create: `packages/data/src/ditto_data/domains/fundamental/fundamental_store.py`
- Test: `packages/data/tests/unit/domains/fundamental/test_fundamental_store_unit.py`

**Step 1: 编写测试 - 基础结构**

```python
# packages/data/tests/unit/domains/fundamental/test_fundamental_store_unit.py
"""Unit tests for FundamentalStore."""

from __future__ import annotations

import pytest
from ditto_data.domains.fundamental.fundamental_store import FundamentalStore
from ditto_data.stores.sqlite_client import SQLiteClient
from ditto_foundation import SQLitePool


@pytest.fixture
def in_memory_db() -> SQLiteClient:
    """创建内存数据库用于测试."""
    pool = SQLitePool(":memory:")
    client = SQLiteClient(pool)
    return client


@pytest.fixture
def store(in_memory_db: SQLiteClient) -> FundamentalStore:
    """创建 FundamentalStore 实例."""
    return FundamentalStore(sqlite_client=in_memory_db)


def test_fundamental_store_init(store: FundamentalStore) -> None:
    """测试 FundamentalStore 初始化."""
    assert store is not None
    assert store._client is not None
```

**Step 2: 运行测试确认失败**

```bash
pixi run -e dev pytest tests/unit/domains/fundamental/test_fundamental_store_unit.py::test_fundamental_store_init -v
```

Expected: FAIL with "FundamentalStore not defined"

**Step 3: 实现 FundamentalStore 基础结构**

```python
# packages/data/src/ditto_data/domains/fundamental/fundamental_store.py
"""FundamentalStore for fundamental data with PIT support."""

from __future__ import annotations

from ditto_data.stores.sqlite_client import SQLiteClient


class FundamentalStore:
    """
    Fundamental domain data storage with PIT support.

    Core functionality:
    - Financial statements (balance sheet, income statement, cash flow)
    - Corporate actions (dividend, corporate actions)
    - Performance forecast (forecast, express)

    All PIT-enabled datasets support querying data as of a specific date.
    """

    def __init__(
        self,
        sqlite_client: SQLiteClient,
    ) -> None:
        """
        Initialize FundamentalStore.

        Args:
            sqlite_client: SQLite client for database operations.

        """
        self._client = sqlite_client

    def close(self) -> None:
        """Close the underlying SQLite client."""
        self._client.close()
```

**Step 4: 运行测试确认通过**

```bash
pixi run -e dev pytest tests/unit/domains/fundamental/test_fundamental_store_unit.py::test_fundamental_store_init -v
```

Expected: PASS

**Step 5: 提交**

```bash
git add tests/unit/domains/fundamental/ packages/data/src/ditto_data/domains/fundamental/fundamental_store.py
git commit -m "feat(fundamental): implement FundamentalStore base structure"
```

---

### 阶段 2：迁移财务报表功能（Capital → Fundamental）

#### Task 3: 迁移 balance_sheet 功能

**Files:**
- Modify: `packages/data/src/ditto_data/domains/fundamental/fundamental_store.py`
- Test: `packages/data/tests/unit/domains/fundamental/test_fundamental_store_unit.py`

**Step 1: 编写测试 - balance_sheet**

```python
# 添加到 test_fundamental_store_unit.py
from datetime import date
import polars as pl


@pytest.fixture
def balance_sheet_table(in_memory_db: SQLiteClient) -> None:
    """创建 balance_sheet 表."""
    in_memory_db.execute("""
        CREATE TABLE IF NOT EXISTS balance_sheet (
            instrument_id TEXT NOT NULL,
            report_date DATE NOT NULL,
            knowledge_date DATE NOT NULL,
            effective_from DATE NOT NULL,
            effective_to DATE,
            total_assets REAL,
            total_liabilities REAL,
            net_assets REAL,
            current_assets REAL,
            current_liabilities REAL,
            PRIMARY KEY (instrument_id, report_date, effective_from)
        )
    """)
    in_memory_db.commit()


def test_write_balance_sheet(balance_sheet_table: None, store: FundamentalStore) -> None:
    """测试写入资产负债表数据."""
    df = pl.DataFrame({
        "instrument_id": ["600000.SH"],
        "report_date": [date(2024, 3, 31)],
        "knowledge_date": [date(2024, 4, 25)],
        "effective_from": [date(2024, 4, 26)],
        "effective_to": [None],
        "total_assets": [1000000.0],
        "total_liabilities": [500000.0],
        "net_assets": [500000.0],
        "current_assets": [300000.0],
        "current_liabilities": [200000.0],
    })

    count = store.write_balance_sheet(df)
    assert count == 1


def test_get_balance_sheet_pit(balance_sheet_table: None, store: FundamentalStore) -> None:
    """测试 PIT 查询资产负债表."""
    # 先写入数据
    df = pl.DataFrame({
        "instrument_id": ["600000.SH"],
        "report_date": [date(2024, 3, 31)],
        "knowledge_date": [date(2024, 4, 25)],
        "effective_from": [date(2024, 4, 26)],
        "effective_to": [None],
        "total_assets": [1000000.0],
        "total_liabilities": [500000.0],
        "net_assets": [500000.0],
        "current_assets": [300000.0],
        "current_liabilities": [200000.0],
    })
    store.write_balance_sheet(df)

    # 查询
    result = store.get_balance_sheet("600000.SH", date(2024, 5, 1))
    assert len(result) == 1
    assert result["total_assets"][0] == 1000000.0
```

**Step 2: 运行测试确认失败**

```bash
pixi run -e dev pytest tests/unit/domains/fundamental/test_fundamental_store_unit.py::test_write_balance_sheet -v
```

Expected: FAIL with "method not defined"

**Step 3: 实现 balance_sheet 方法**

```python
# 添加到 fundamental_store.py
from datetime import date
import polars as pl
from ditto_foundation import M, logger, traced

@traced("data.fundamental_write")
def write_balance_sheet(self, df: pl.DataFrame) -> int:
    """
    Write balance sheet data to database.

    Args:
        df: DataFrame with balance sheet data including PIT columns.

    Returns:
        Number of records written.
    """
    logger.info("Starting balance sheet data write", record_count=len(df))

    try:
        records = df.to_dicts()
        self._client.executemany(
            """INSERT INTO balance_sheet
            (instrument_id, report_date, knowledge_date,
             effective_from, effective_to,
             total_assets, total_liabilities, net_assets,
             current_assets, current_liabilities)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT DO NOTHING""",
            [
                (
                    r["instrument_id"],
                    r["report_date"],
                    r["knowledge_date"],
                    r["effective_from"],
                    r.get("effective_to"),
                    r["total_assets"],
                    r["total_liabilities"],
                    r["net_assets"],
                    r["current_assets"],
                    r["current_liabilities"],
                )
                for r in records
            ],
        )
        self._client.commit()

        logger.info("Balance sheet data written successfully", record_count=len(records))
        M.data_records.add(len(records), {"dataset": "balance_sheet", "status": "success"})
        return len(records)

    except Exception as e:
        self._client.rollback()
        logger.error("Balance sheet write failed", error=str(e))
        M.data_records.add(len(df), {"dataset": "balance_sheet", "status": "failed"})
        raise


@traced("data.fundamental_query")
def get_balance_sheet(
    self,
    instrument_id: str,
    as_of_date: date,
) -> pl.DataFrame:
    """
    Query balance sheet data as of a specific date (PIT query).

    Args:
        instrument_id: Instrument identifier.
        as_of_date: Point-in-time query date.

    Returns:
        DataFrame with balance sheet data valid as of as_of_date.
    """
    logger.debug("Querying balance sheet with PIT", instrument_id=instrument_id, as_of_date=as_of_date)

    rows = self._client.fetchall(
        """SELECT instrument_id, report_date, knowledge_date,
                  effective_from, effective_to,
                  total_assets, total_liabilities, net_assets,
                  current_assets, current_liabilities
           FROM balance_sheet
           WHERE instrument_id = ?
             AND effective_from <= ?
             AND (effective_to IS NULL OR effective_to > ?)
           ORDER BY report_date DESC""",
        [instrument_id, as_of_date, as_of_date],
    )

    return pl.DataFrame(rows) if rows else pl.DataFrame()
```

**Step 4: 运行测试确认通过**

```bash
pixi run -e dev pytest tests/unit/domains/fundamental/test_fundamental_store_unit.py::test_write_balance_sheet -v
pixi run -e dev pytest tests/unit/domains/fundamental/test_fundamental_store_unit.py::test_get_balance_sheet_pit -v
```

Expected: PASS

**Step 5: 提交**

```bash
git add packages/data/src/ditto_data/domains/fundamental/fundamental_store.py tests/unit/domains/fundamental/test_fundamental_store_unit.py
git commit -m "feat(fundamental): migrate balance_sheet from capital"
```

---

#### Task 4: 迁移 income_statement 功能

**Pattern 同 Task 3，迁移 income_statement 的 write/get 方法**

**关键代码位置参考：**
- 源文件：`packages/data/src/ditto_data/domains/capital/capital_store.py:224-363`
- 测试：`packages/data/tests/unit/domains/capital/test_capital_store_unit.py`

**提交：**
```bash
git commit -m "feat(fundamental): migrate income_statement from capital"
```

---

#### Task 5: 迁移 cash_flow 功能

**Pattern 同 Task 3，迁移 cash_flow 的 write/get 方法**

**关键代码位置参考：**
- 源文件：`packages/data/src/ditto_data/domains/capital/capital_store.py:366-505`
- 测试：`packages/data/tests/unit/domains/capital/test_capital_store_unit.py`

**提交：**
```bash
git commit -m "feat(fundamental): migrate cash_flow from capital"
```

---

### 阶段 3：迁移公司行为功能（Capital → Fundamental）

#### Task 6: 迁移 dividend 功能

**Files:**
- Modify: `packages/data/src/ditto_data/domains/fundamental/fundamental_store.py`
- Test: `packages/data/tests/unit/domains/fundamental/test_fundamental_store_unit.py`

**Step 1: 编写测试 - dividend**

```python
# 添加到 test_fundamental_store_unit.py
@pytest.fixture
def dividend_table(in_memory_db: SQLiteClient) -> None:
    """创建 dividend 表."""
    in_memory_db.execute("""
        CREATE TABLE IF NOT EXISTS dividend (
            instrument_id TEXT NOT NULL,
            ex_dividend_date DATE NOT NULL,
            knowledge_date DATE NOT NULL,
            effective_from DATE NOT NULL,
            effective_to DATE,
            dividend_per_share REAL,
            dividend_yield REAL,
            PRIMARY KEY (instrument_id, ex_dividend_date, effective_from)
        )
    """)
    in_memory_db.commit()


def test_write_dividend(dividend_table: None, store: FundamentalStore) -> None:
    """测试写入分红数据."""
    df = pl.DataFrame({
        "instrument_id": ["600000.SH"],
        "ex_dividend_date": [date(2024, 5, 1)],
        "knowledge_date": [date(2024, 4, 25)],
        "effective_from": [date(2024, 4, 26)],
        "effective_to": [None],
        "dividend_per_share": [0.5],
        "dividend_yield": [0.02],
    })

    count = store.write_dividend(df)
    assert count == 1


def test_get_dividend_pit(dividend_table: None, store: FundamentalStore) -> None:
    """测试 PIT 查询分红数据."""
    df = pl.DataFrame({
        "instrument_id": ["600000.SH"],
        "ex_dividend_date": [date(2024, 5, 1)],
        "knowledge_date": [date(2024, 4, 25)],
        "effective_from": [date(2024, 4, 26)],
        "effective_to": [None],
        "dividend_per_share": [0.5],
        "dividend_yield": [0.02],
    })
    store.write_dividend(df)

    result = store.get_dividend("600000.SH", date(2024, 5, 2))
    assert len(result) == 1
    assert result["dividend_per_share"][0] == 0.5
```

**Step 2-5: 运行测试 → 实现 → 验证 → 提交**

**实现代码参考：**
- 源文件：`packages/data/src/ditto_data/domains/capital/capital_store.py:943-1078`

**提交：**
```bash
git commit -m "feat(fundamental): migrate dividend from capital"
```

---

#### Task 7: 迁移 corporate_actions 功能

**Pattern 同上，注意 corporate_actions 是非 PIT 数据**

**源文件参考：**
- `packages/data/src/ditto_data/domains/capital/capital_store.py:1376-1512`

**提交：**
```bash
git commit -m "feat(fundamental): migrate corporate_actions from capital"
```

---

### 阶段 4：实现业绩预告/快报功能（新增）

#### Task 8: 实现 forecast 功能

**Files:**
- Create: `packages/data/src/ditto_data/domains/fundamental/forecast/forecast_store.py`
- Modify: `packages/data/src/ditto_data/domains/fundamental/fundamental_store.py`
- Test: `packages/data/tests/unit/domains/fundamental/forecast/test_forecast_store_unit.py`

**Step 1: 编写测试 - forecast**

```python
# packages/data/tests/unit/domains/fundamental/forecast/test_forecast_store_unit.py
"""Unit tests for ForecastStore."""

from datetime import date
import polars as pl
import pytest
from ditto_data.domains.fundamental.forecast.forecast_store import ForecastStore
from ditto_data.stores.sqlite_client import SQLiteClient
from ditto_foundation import SQLitePool


@pytest.fixture
def in_memory_db() -> SQLiteClient:
    """创建内存数据库."""
    pool = SQLitePool(":memory:")
    client = SQLiteClient(pool)
    # 创建表
    client.execute("""
        CREATE TABLE IF NOT EXISTS forecast (
            instrument_id TEXT NOT NULL,
            report_date DATE NOT NULL,
            knowledge_date DATE NOT NULL,
            effective_from DATE NOT NULL,
            effective_to DATE,
            type TEXT,
            profit_range_min REAL,
            profit_range_max REAL,
            PRIMARY KEY (instrument_id, report_date, effective_from)
        )
    """)
    client.commit()
    return client


@pytest.fixture
def store(in_memory_db: SQLiteClient) -> ForecastStore:
    """创建 ForecastStore 实例."""
    return ForecastStore(in_memory_db)


def test_write_forecast(store: ForecastStore) -> None:
    """测试写入业绩预告数据."""
    df = pl.DataFrame({
        "instrument_id": ["600000.SH"],
        "report_date": [date(2024, 6, 30)],
        "knowledge_date": [date(2024, 4, 20)],
        "effective_from": [date(2024, 4, 21)],
        "effective_to": [None],
        "type": ["预增"],
        "profit_range_min": [1000000.0],
        "profit_range_max": [1200000.0],
    })

    count = store.write(df)
    assert count == 1


def test_get_forecast_pit(store: ForecastStore) -> None:
    """测试 PIT 查询业绩预告."""
    df = pl.DataFrame({
        "instrument_id": ["600000.SH"],
        "report_date": [date(2024, 6, 30)],
        "knowledge_date": [date(2024, 4, 20)],
        "effective_from": [date(2024, 4, 21)],
        "effective_to": [None],
        "type": ["预增"],
        "profit_range_min": [1000000.0],
        "profit_range_max": [1200000.0],
    })
    store.write(df)

    result = store.get("600000.SH", date(2024, 5, 1))
    assert len(result) == 1
    assert result["type"][0] == "预增"
```

**Step 2: 运行测试确认失败**

```bash
pixi run -e dev pytest tests/unit/domains/fundamental/forecast/test_forecast_store_unit.py -v
```

Expected: FAIL

**Step 3: 实现 ForecastStore**

```python
# packages/data/src/ditto_data/domains/fundamental/forecast/forecast_store.py
"""ForecastStore for performance forecast data with PIT support."""

from __future__ import annotations

from datetime import date

import polars as pl
from ditto_foundation import logger, traced

from ditto_data.stores.sqlite_client import SQLiteClient


class ForecastStore:
    """
    Performance forecast data storage with PIT support.

    Stores company performance forecast/announcement data.
    """

    def __init__(self, sqlite_client: SQLiteClient) -> None:
        """Initialize ForecastStore."""
        self._client = sqlite_client

    @traced("data.forecast_write")
    def write(self, df: pl.DataFrame) -> int:
        """
        Write forecast data to database.

        Args:
            df: DataFrame with forecast data including PIT columns.

        Returns:
            Number of records written.
        """
        logger.info("Starting forecast data write", record_count=len(df))

        try:
            records = df.to_dicts()
            self._client.executemany(
                """INSERT INTO forecast
                (instrument_id, report_date, knowledge_date,
                 effective_from, effective_to, type,
                 profit_range_min, profit_range_max)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT DO NOTHING""",
                [
                    (
                        r["instrument_id"],
                        r["report_date"],
                        r["knowledge_date"],
                        r["effective_from"],
                        r.get("effective_to"),
                        r["type"],
                        r.get("profit_range_min"),
                        r.get("profit_range_max"),
                    )
                    for r in records
                ],
            )
            self._client.commit()

            logger.info("Forecast data written successfully", record_count=len(records))
            return len(records)

        except Exception as e:
            self._client.rollback()
            logger.error("Forecast write failed", error=str(e))
            raise

    @traced("data.forecast_query")
    def get(
        self,
        instrument_id: str,
        as_of_date: date,
    ) -> pl.DataFrame:
        """
        Query forecast data as of a specific date (PIT query).

        Args:
            instrument_id: Instrument identifier.
            as_of_date: Point-in-time query date.

        Returns:
            DataFrame with forecast data valid as of as_of_date.
        """
        logger.debug("Querying forecast with PIT", instrument_id=instrument_id, as_of_date=as_of_date)

        rows = self._client.fetchall(
            """SELECT instrument_id, report_date, knowledge_date,
                      effective_from, effective_to, type,
                      profit_range_min, profit_range_max
               FROM forecast
               WHERE instrument_id = ?
                 AND effective_from <= ?
                 AND (effective_to IS NULL OR effective_to > ?)
               ORDER BY report_date DESC""",
            [instrument_id, as_of_date, as_of_date],
        )

        return pl.DataFrame(rows) if rows else pl.DataFrame()

    def close(self) -> None:
        """Close the underlying SQLite client."""
        self._client.close()
```

**Step 4: 运行测试确认通过**

```bash
pixi run -e dev pytest tests/unit/domains/fundamental/forecast/test_forecast_store_unit.py -v
```

Expected: PASS

**Step 5: 集成到 FundamentalStore**

```python
# 添加到 fundamental_store.py
from ditto_data.domains.fundamental.forecast.forecast_store import ForecastStore

class FundamentalStore:
    def __init__(self, sqlite_client: SQLiteClient) -> None:
        self._client = sqlite_client
        self._forecast_store = ForecastStore(sqlite_client)

    @traced("data.fundamental_write")
    def write_forecast(self, df: pl.DataFrame) -> int:
        """Write forecast data."""
        return self._forecast_store.write(df)

    @traced("data.fundamental_query")
    def get_forecast(self, instrument_id: str, as_of_date: date) -> pl.DataFrame:
        """Query forecast data with PIT."""
        return self._forecast_store.get(instrument_id, as_of_date)
```

**Step 6: 提交**

```bash
git add packages/data/src/ditto_data/domains/fundamental/forecast/
git add tests/unit/domains/fundamental/forecast/
git commit -m "feat(fundamental): implement forecast store"
```

---

#### Task 9: 实现 express 功能

**Pattern 同 Task 8**

**提交：**
```bash
git commit -m "feat(fundamental): implement express store"
```

---

### 阶段 5：重构 Capital 域

#### Task 10: 清理 CapitalStore - 移除已迁移的功能

**Files:**
- Modify: `packages/data/src/ditto_data/domains/capital/capital_store.py`
- Modify: `packages/data/tests/unit/domains/capital/test_capital_store_unit.py`

**Step 1: 从 CapitalStore 移除以下方法**
- `write_balance_sheet / get_balance_sheet`
- `write_income_statement / get_income_statement`
- `write_cash_flow / get_cash_flow`
- `write_dividend / get_dividend`
- `write_corporate_actions / get_corporate_actions`
- `write_valuation_metrics / get_valuation_metrics`
- `write_futures / get_futures`
- `write_index_composition / get_index_composition`

**Step 2: 更新测试**
- 移除相关测试用例
- 保留 `margin_trading` 和 `pledge_ratio` 测试

**Step 3: 验证测试通过**

```bash
pixi run -e dev pytest tests/unit/domains/capital/ -v
```

**Step 4: 提交**

```bash
git commit -m "refactor(capital): remove migrated fundamental features"
```

---

#### Task 11: 重构 Capital 域为子域结构

**Files:**
- Create: `packages/data/src/ditto_data/domains/capital/margin/__init__.py`
- Create: `packages/data/src/ditto_data/domains/capital/margin/margin_trading_store.py`
- Create: `packages/data/src/ditto_data/domains/capital/pledge/__init__.py`
- Create: `packages/data/src/ditto_data/domains/capital/pledge/pledge_ratio_store.py`
- Modify: `packages/data/src/ditto_data/domains/capital/capital_store.py`

**Step 1: 创建 margin 子域**

```python
# packages/data/src/ditto_data/domains/capital/margin/margin_trading_store.py
"""Margin trading data storage with PIT support."""

from __future__ import annotations

from datetime import date

import polars as pl
from ditto_foundation import logger, traced

from ditto_data.stores.sqlite_client import SQLiteClient


class MarginTradingStore:
    """Margin trading data storage with PIT support."""

    def __init__(self, sqlite_client: SQLiteClient) -> None:
        """Initialize MarginTradingStore."""
        self._client = sqlite_client

    @traced("data.capital_write")
    def write(self, df: pl.DataFrame) -> int:
        """Write margin trading data."""
        # 实现从原 CapitalStore 迁移
        ...

    @traced("data.capital_query")
    def get(self, instrument_id: str, as_of_date: date) -> pl.DataFrame:
        """Query margin trading data with PIT."""
        # 实现从原 CapitalStore 迁移
        ...
```

**Step 2: 创建 pledge 子域**

```python
# packages/data/src/ditto_data/domains/capital/pledge/pledge_ratio_store.py
"""Pledge ratio data storage with PIT support."""

# Pattern 同 MarginTradingStore
```

**Step 3: 重构 CapitalStore 为组合入口**

```python
# packages/data/src/ditto_data/domains/capital/capital_store.py
"""CapitalStore - Capital domain unified entry point."""

from ditto_data.domains.capital.margin.margin_trading_store import MarginTradingStore
from ditto_data.domains.capital.pledge.pledge_ratio_store import PledgeRatioStore
from ditto_data.stores.sqlite_client import SQLiteClient


class CapitalStore:
    """
    Capital domain data storage with PIT support.

    Core functionality:
    - Margin trading (融资融券)
    - Pledge ratio (股权质押)

    Delegates to sub-domain stores.
    """

    def __init__(self, sqlite_client: SQLiteClient) -> None:
        """Initialize CapitalStore."""
        self._margin_store = MarginTradingStore(sqlite_client)
        self._pledge_store = PledgeRatioStore(sqlite_client)

    # Margin trading delegation
    def write_margin_trading(self, df: pl.DataFrame) -> int:
        return self._margin_store.write(df)

    def get_margin_trading(self, instrument_id: str, as_of_date: date) -> pl.DataFrame:
        return self._margin_store.get(instrument_id, as_of_date)

    # Pledge ratio delegation
    def write_pledge_ratio(self, df: pl.DataFrame) -> int:
        return self._pledge_store.write(df)

    def get_pledge_ratio(self, instrument_id: str, as_of_date: date) -> pl.DataFrame:
        return self._pledge_store.get(instrument_id, as_of_date)
```

**Step 4: 验证测试通过**

```bash
pixi run -e dev pytest tests/unit/domains/capital/ -v
```

**Step 5: 提交**

```bash
git commit -m "refactor(capital): restructure as sub-domain architecture"
```

---

### 阶段 6：更新 Source 和 Ingestion 层

#### Task 12: 拆分 CapitalTushareAdapter

**Files:**
- Create: `packages/data/src/ditto_data/sources/tushare/adapters/fundamental.py`
- Modify: `packages/data/src/ditto_data/sources/tushare/adapters/capital.py`
- Create: `packages/data/src/ditto_data/sources/schemas/fundamental_schemas.py`
- Modify: `packages/data/src/ditto_data/sources/schemas/capital_schemas.py`

**Step 1: 创建 fundamental_schemas.py**

```python
# packages/data/src/ditto_data/sources/schemas/fundamental_schemas.py
"""Fundamental SourceSchema definitions."""

import polars as pl
from ditto_data.sources.source_schema import SourceSchema

__all__ = [
    "BALANCE_SHEET_SOURCE_SCHEMA",
    "INCOME_STATEMENT_SOURCE_SCHEMA",
    "CASH_FLOW_SOURCE_SCHEMA",
    "DIVIDEND_SOURCE_SCHEMA",
    "CORPORATE_ACTIONS_SOURCE_SCHEMA",
    "FORECAST_SOURCE_SCHEMA",
    "EXPRESS_SOURCE_SCHEMA",
]

# 从 capital_schemas.py 迁移相关 Schema
# ...
```

**Step 2: 创建 FundamentalTushareAdapter**

```python
# packages/data/src/ditto_data/sources/tushare/adapters/fundamental.py
"""Fundamental domain Tushare adapter implementation."""

# 从 capital.py 迁移相关方法
# fetch_balance_sheet, fetch_income_statement, fetch_cash_flow
# fetch_dividend, fetch_corporate_actions
# 新增 fetch_forecast, fetch_express
```

**Step 3: 更新 CapitalTushareAdapter**

```python
# 从 capital.py 移除已迁移的方法
# 保留 fetch_margin_trading, fetch_pledge_ratio
```

**Step 4: 提交**

```bash
git commit -m "refactor(sources): split adapters into fundamental and capital"
```

---

#### Task 13: 创建 FundamentalIngestion 服务

**Files:**
- Create: `packages/data/src/ditto_data/domains/fundamental/fundamental_ingestion.py`
- Test: `packages/data/tests/unit/domains/fundamental/test_fundamental_ingestion_unit.py`

**Pattern 参考：** `capital_ingestion.py`

**提交：**
```bash
git commit -m "feat(fundamental): implement FundamentalIngestion service"
```

---

#### Task 14: 更新 CapitalIngestion 服务

**Files:**
- Modify: `packages/data/src/ditto_data/domains/capital/capital_ingestion.py`
- Test: `packages/data/tests/unit/domains/capital/test_capital_ingestion_unit.py`

**Step 1: 移除已迁移的 ingest 方法**

移除：
- `ingest_balance_sheet`
- `ingest_income_statement`
- `ingest_cash_flow`
- `ingest_dividend`
- `ingest_corporate_actions`
- `ingest_valuation_metrics`
- `ingest_futures`
- `ingest_index_composition`

保留：
- `ingest_margin_trading`
- `ingest_pledge_ratio`

**Step 2: 验证测试通过**

```bash
pixi run -e dev pytest tests/unit/domains/capital/test_capital_ingestion_unit.py -v
```

**Step 3: 提交**

```bash
git commit -m "refactor(capital): remove migrated ingestion methods"
```

---

### 阶段 7：更新集成和文档

#### Task 15: 更新 domains/__init__.py

**Files:**
- Modify: `packages/data/src/ditto_data/domains/__init__.py`

**Step 1: 添加 Fundamental 域导出**

```python
# packages/data/src/ditto_data/domains/__init__.py
"""DataHub domains - organized by business domain."""

from ditto_data.domains import capital
from ditto_data.domains import fundamental  # 新增
from ditto_data.domains import market
from ditto_data.domains import metadata

__all__ = ["capital", "fundamental", "market", "metadata"]
```

**Step 2: 提交**

```bash
git commit -m "feat(domains): add fundamental domain export"
```

---

#### Task 16: 更新 README 和文档

**Files:**
- Modify: `packages/data/README.md`
- Create: `docs/design/05_domain_architecture.md`

**Step 1: 更新 DataHub README**

添加 Fundamental 域说明，更新域划分描述。

**Step 2: 创建域架构文档**

```markdown
# DataHub 域架构

## 域划分

| 域 | 职责 | 数据类型 |
|---|------|---------|
| **Fundamental** | 企业基本面 | 财务报表、分红、公司行为、业绩预告 |
| **Capital** | 资金面 | 融资融券、股权质押、持仓数据 |
| **Market** | 行情数据 | K线、复权因子、成分股、市场状态 |
| **Metadata** | 元数据 | 日历、标的身份、行业分类 |
```

**Step 3: 提交**

```bash
git commit -m "docs: update domain architecture documentation"
```

---

### 阶段 8：最终验证和清理

#### Task 17: 运行完整测试套件

**Step 1: 运行所有测试**

```bash
pixi run -e dev pytest
```

Expected: All tests pass

**Step 2: 运行类型检查**

```bash
pixi run -e dev type
```

Expected: 0 errors

**Step 3: 运行代码质量检查**

```bash
pixi run -e dev lint
pixi run -e dev fmt --check
```

Expected: All checks pass

---

#### Task 18: 清理和最终提交

**Step 1: 检查是否有遗漏的文件**

```bash
git status
```

**Step 2: 确认所有更改已提交**

**Step 3: 创建合并请求**

```bash
# 推送到远程
git push origin feature/fundamental-domain
```

---

## 待讨论问题

### 1. index_composition/index_constituent 重复

**现状：**
- Market 域已有 `market/index/constituent/` (使用 `index_sid`, `stock_sid`)
- Capital 域有 `index_composition` (使用 `index_id`, `instrument_id`)

**问题：**
这是两套不同的系统，还是重复实现？需要确认：
1. 是否需要保留两套？
2. 如果合并，保留哪一套？
3. 如何处理数据迁移？

**建议：** 待用户确认后再处理。

---

## 附录：文件清单

### 新增文件

```
packages/data/src/ditto_data/domains/fundamental/
├── __init__.py
├── financial/
│   ├── __init__.py
│   ├── balance_sheet_store.py
│   ├── income_statement_store.py
│   └── cash_flow_store.py
├── corporate/
│   ├── __init__.py
│   ├── dividend_store.py
│   └── corporate_actions_store.py
├── forecast/
│   ├── __init__.py
│   ├── forecast_store.py
│   └── express_store.py
├── fundamental_store.py
└── fundamental_ingestion.py

packages/data/src/ditto_data/domains/capital/
├── margin/
│   ├── __init__.py
│   └── margin_trading_store.py
├── pledge/
│   ├── __init__.py
│   └── pledge_ratio_store.py

packages/data/src/ditto_data/sources/tushare/adapters/
└── fundamental.py

packages/data/src/ditto_data/sources/schemas/
└── fundamental_schemas.py

packages/data/tests/unit/domains/fundamental/
├── __init__.py
├── test_fundamental_store_unit.py
├── test_fundamental_ingestion_unit.py
├── financial/
├── corporate/
└── forecast/
```

### 修改文件

```
packages/data/src/ditto_data/domains/__init__.py
packages/data/src/ditto_data/domains/capital/capital_store.py
packages/data/src/ditto_data/domains/capital/capital_ingestion.py
packages/data/src/ditto_data/sources/tushare/adapters/capital.py
packages/data/src/ditto_data/sources/schemas/capital_schemas.py
packages/data/tests/unit/domains/capital/test_capital_store_unit.py
packages/data/tests/unit/domains/capital/test_capital_ingestion_unit.py
```

### 删除文件

无（通过重构完成）

---

## 预计工作量

| 阶段 | 任务数 | 预计时间 |
|-----|-------|---------|
| 阶段 1 | 2 | 0.5 天 |
| 阶段 2 | 3 | 1 天 |
| 阶段 3 | 2 | 0.5 天 |
| 阶段 4 | 2 | 1 天 |
| 阶段 5 | 2 | 1 天 |
| 阶段 6 | 3 | 1 天 |
| 阶段 7 | 2 | 0.5 天 |
| 阶段 8 | 2 | 0.5 天 |
| **总计** | **18** | **6 天** |
