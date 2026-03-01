# FX/Commodity 写入链路及国债收益率异常值修复 - 实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 修复 FX/Commodity 写入链路缺失、API 路由不可达、国债收益率异常值静默污染数据的问题

**Architecture:** 创建 FxBarsReader/Writer 和 CommodityBarsReader/Writer，扩展 MarketService 支持新资产类别，修改 data_writer.py 添加 handlers，实现 API 查询逻辑

**Tech Stack:** Python 3.12, Polars, Parquet, FastAPI, Pytest

---

## Task 1: 创建 FX Store 层

**Files:**
- Create: `packages/datahub/src/ditto_datahub/stores/market/fx/__init__.py`
- Create: `packages/datahub/src/ditto_datahub/stores/market/fx/bars/__init__.py`
- Create: `packages/datahub/src/ditto_datahub/stores/market/fx/bars/bars_reader.py`
- Create: `packages/datahub/src/ditto_datahub/stores/market/fx/bars/bars_writer.py`
- Create: `packages/datahub/tests/unit/stores/market/fx/test_bars_reader.py`

**Step 1: Create directory structure**

```bash
mkdir -p packages/datahub/src/ditto_datahub/stores/market/fx/bars
mkdir -p packages/datahub/tests/unit/stores/market/fx
```

**Step 2: Write fx/__init__.py**

```python
"""FX domain market data stores."""

__all__ = []
```

**Step 3: Write fx/bars/__init__.py**

```python
"""FX bars data store."""

from ditto_datahub.stores.market.fx.bars.bars_reader import FxBarsReader
from ditto_datahub.stores.market.fx.bars.bars_writer import FxBarsWriter

__all__ = ["FxBarsReader", "FxBarsWriter"]
```

**Step 4: Write fx/bars/bars_reader.py**

```python
"""
FX daily bars reader.

Provides read-only access to FX daily bars data stored in Parquet files
with year partitioning.
"""

from __future__ import annotations

from pathlib import Path

import polars as pl

from ditto_datahub.stores.base import ParquetStore, YearlyPartition


class FxBarsReader:
    """
    FX daily bars data reader.

    Provides read-only access to FX daily bars data with year partitioning.
    Uses composition pattern with ParquetStore for all data operations.

    Storage structure:
        data_root/
            market/fx/bars/
                2020.parquet
                2021.parquet
                ...

    Attributes:
        DATASET: Dataset name for FX bars.

    """

    DATASET: str = "market/fx/bars"

    def __init__(self, data_root: Path) -> None:
        """
        Initialize FxBarsReader.

        Args:
            data_root: Root directory for data storage.

        """
        self._store = ParquetStore(data_root, YearlyPartition())

    def read(
        self,
        instrument_ids: list[int] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """
        Read bars data from the store.

        Args:
            instrument_ids: Filter by instrument IDs.
            start_date: Start date (YYYY-MM-DD).
            end_date: End date (YYYY-MM-DD).

        Returns:
            DataFrame with matching records.

        """
        return self._store.read(
            self.DATASET,
            instrument_ids=instrument_ids,
            start_date=start_date,
            end_date=end_date,
        )

    def count(
        self,
        instrument_ids: list[int] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> int:
        """
        Count records in the dataset.

        Args:
            instrument_ids: Filter by instrument IDs.
            start_date: Start date (YYYY-MM-DD).
            end_date: End date (YYYY-MM-DD).

        Returns:
            Number of matching records.

        """
        return self._store.count(
            self.DATASET,
            instrument_ids=instrument_ids,
            start_date=start_date,
            end_date=end_date,
        )

    def get_years(self) -> list[int]:
        """Get available years for this dataset."""
        return self._store.get_years(self.DATASET)

    def get_checksum(self, partition_key: str) -> str:
        """Get MD5 checksum of a partition."""
        return self._store.get_checksum(self.DATASET, partition_key)

    def get_date_range(self) -> tuple[str | None, str | None]:
        """Get overall date range for the dataset."""
        return self._store.get_date_range(self.DATASET)

    def list_instrument_ids(self) -> list[int]:
        """List unique instrument IDs in the dataset."""
        return self._store.list_instrument_ids(self.DATASET)

    @property
    def data_root(self) -> Path:
        """Get the data root directory."""
        return self._store.data_root
```

**Step 5: Write fx/bars/bars_writer.py**

```python
"""
FX daily bars writer.

Provides write access to FX daily bars data stored in Parquet files
with year partitioning.
"""

from __future__ import annotations

from pathlib import Path

import polars as pl

from ditto_datahub.models import OnDuplicate
from ditto_datahub.models.storage import WriteStoreResult
from ditto_datahub.stores.base import ParquetStore, YearlyPartition


class FxBarsWriter:
    """
    FX daily bars data writer.

    Provides write access to FX daily bars data with year partitioning.
    Uses composition pattern with ParquetStore for all data operations.

    Storage structure:
        data_root/
            market/fx/bars/
                2020.parquet
                2021.parquet
                ...

    Attributes:
        DATASET: Dataset name for FX bars.

    """

    DATASET: str = "market/fx/bars"

    def __init__(self, data_root: Path) -> None:
        """
        Initialize FxBarsWriter.

        Args:
            data_root: Root directory for data storage.

        """
        self._store = ParquetStore(data_root, YearlyPartition())

    def write(
        self,
        df: pl.DataFrame,
        year: int,
        on_duplicate: OnDuplicate = OnDuplicate.ERROR,
    ) -> WriteStoreResult:
        """
        Write bars data to the store.

        Args:
            df: DataFrame to write.
            year: Year partition.
            on_duplicate: Duplicate data handling strategy.

        Returns:
            Write result statistics.

        """
        return self._store.write(
            self.DATASET,
            df,
            on_duplicate.value,
            year=year,
        )

    def delete(
        self,
        instrument_ids: list[int] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> int:
        """
        Delete bars data from the store.

        Args:
            instrument_ids: Filter by instrument IDs.
            start_date: Start date (YYYY-MM-DD).
            end_date: End date (YYYY-MM-DD).

        Returns:
            Number of deleted records.

        """
        return self._store.delete(
            self.DATASET,
            instrument_ids=instrument_ids,
            start_date=start_date,
            end_date=end_date,
        )

    def delete_partition(self, partition_key: str) -> bool:
        """Delete a partition by key."""
        return self._store.delete_partition(self.DATASET, partition_key)

    def get_checksum(self, partition_key: str) -> str:
        """Get MD5 checksum of a partition."""
        return self._store.get_checksum(self.DATASET, partition_key)

    @property
    def data_root(self) -> Path:
        """Get the data root directory."""
        return self._store.data_root
```

**Step 6: Write failing test for FxBarsReader**

```python
# packages/datahub/tests/unit/stores/market/fx/test_bars_reader.py
"""Unit tests for FX bars reader."""

from pathlib import Path

import polars as pl
import pytest

from ditto_datahub.stores.market.fx.bars import FxBarsReader, FxBarsWriter


@pytest.fixture
def fx_bars_reader(tmp_path: Path) -> FxBarsReader:
    """Create FxBarsReader with temporary data root."""
    return FxBarsReader(tmp_path)


@pytest.fixture
def fx_bars_writer(tmp_path: Path) -> FxBarsWriter:
    """Create FxBarsWriter with temporary data root."""
    return FxBarsWriter(tmp_path)


class TestFxBarsReader:
    """Tests for FxBarsReader."""

    def test_read_empty_dataset(self, fx_bars_reader: FxBarsReader) -> None:
        """Reading from empty dataset returns empty DataFrame."""
        result = fx_bars_reader.read()
        assert result.is_empty()

    def test_dataset_name(self, fx_bars_reader: FxBarsReader) -> None:
        """Dataset name is correct."""
        assert fx_bars_reader.DATASET == "market/fx/bars"


class TestFxBarsWriter:
    """Tests for FxBarsWriter."""

    def test_write_and_read(
        self,
        fx_bars_reader: FxBarsReader,
        fx_bars_writer: FxBarsWriter,
    ) -> None:
        """Written data can be read back."""
        df = pl.DataFrame({
            "instrument_id": [4_000_001, 4_000_001],
            "trade_date": [pl.date(2024, 1, 1), pl.date(2024, 1, 2)],
            "open": [7.1000, 7.1100],
            "high": [7.1200, 7.1300],
            "low": [7.0900, 7.1000],
            "close": [7.1100, 7.1200],
        })

        result = fx_bars_writer.write(df, 2024)
        assert result.added == 2

        read_df = fx_bars_reader.read()
        assert len(read_df) == 2
```

**Step 7: Run test to verify it passes**

Run: `pixi run -e dev pytest packages/datahub/tests/unit/stores/market/fx/test_bars_reader.py -v`

Expected: All tests pass

**Step 8: Commit**

```bash
git add packages/datahub/src/ditto_datahub/stores/market/fx/
git add packages/datahub/tests/unit/stores/market/fx/
git commit -m "feat(datahub): add FxBarsReader/Writer for FX daily bars storage"
```

---

## Task 2: 创建 Commodity Store 层

**Files:**
- Create: `packages/datahub/src/ditto_datahub/stores/market/commodity/__init__.py`
- Create: `packages/datahub/src/ditto_datahub/stores/market/commodity/bars/__init__.py`
- Create: `packages/datahub/src/ditto_datahub/stores/market/commodity/bars/bars_reader.py`
- Create: `packages/datahub/src/ditto_datahub/stores/market/commodity/bars/bars_writer.py`
- Create: `packages/datahub/tests/unit/stores/market/commodity/test_bars_reader.py`

**Step 1: Create directory structure**

```bash
mkdir -p packages/datahub/src/ditto_datahub/stores/market/commodity/bars
mkdir -p packages/datahub/tests/unit/stores/market/commodity
```

**Step 2: Write commodity/__init__.py**

```python
"""Commodity domain market data stores."""

__all__ = []
```

**Step 3: Write commodity/bars/__init__.py**

```python
"""Commodity Bars data store."""

from ditto_datahub.stores.market.commodity.bars.bars_reader import (
    CommodityBarsReader,
)
from ditto_datahub.stores.market.commodity.bars.bars_writer import (
    CommodityBarsWriter,
)

__all__ = ["CommodityBarsReader", "CommodityBarsWriter"]
```

**Step 4: Write commodity/bars/bars_reader.py**

```python
"""
Commodity daily bars reader.

Provides read-only access to commodity daily bars data stored in Parquet files
with year partitioning.
"""

from __future__ import annotations

from pathlib import Path

import polars as pl

from ditto_datahub.stores.base import ParquetStore, YearlyPartition


class CommodityBarsReader:
    """
    Commodity daily bars data reader.

    Storage structure:
        data_root/
            market/commodity/bars/
                2020.parquet
                2021.parquet
                ...

    """

    DATASET: str = "market/commodity/bars"

    def __init__(self, data_root: Path) -> None:
        self._store = ParquetStore(data_root, YearlyPartition())

    def read(
        self,
        instrument_ids: list[int] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        return self._store.read(
            self.DATASET,
            instrument_ids=instrument_ids,
            start_date=start_date,
            end_date=end_date,
        )

    def count(
        self,
        instrument_ids: list[int] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> int:
        return self._store.count(
            self.DATASET,
            instrument_ids=instrument_ids,
            start_date=start_date,
            end_date=end_date,
        )

    def get_years(self) -> list[int]:
        return self._store.get_years(self.DATASET)

    def get_checksum(self, partition_key: str) -> str:
        return self._store.get_checksum(self.DATASET, partition_key)

    def get_date_range(self) -> tuple[str | None, str | None]:
        return self._store.get_date_range(self.DATASET)

    def list_instrument_ids(self) -> list[int]:
        return self._store.list_instrument_ids(self.DATASET)

    @property
    def data_root(self) -> Path:
        return self._store.data_root
```

**Step 5: Write commodity/bars/bars_writer.py**

```python
"""
Commodity daily bars writer.

Provides write access to commodity daily bars data stored in Parquet files
with year partitioning.
"""

from __future__ import annotations

from pathlib import Path

import polars as pl

from ditto_datahub.models import OnDuplicate
from ditto_datahub.models.storage import WriteStoreResult
from ditto_datahub.stores.base import ParquetStore, YearlyPartition


class CommodityBarsWriter:
    """Commodity daily bars data writer."""

    DATASET: str = "market/commodity/bars"

    def __init__(self, data_root: Path) -> None:
        self._store = ParquetStore(data_root, YearlyPartition())

    def write(
        self,
        df: pl.DataFrame,
        year: int,
        on_duplicate: OnDuplicate = OnDuplicate.ERROR,
    ) -> WriteStoreResult:
        return self._store.write(
            self.DATASET,
            df,
            on_duplicate.value,
            year=year,
        )

    def delete(
        self,
        instrument_ids: list[int] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> int:
        return self._store.delete(
            self.DATASET,
            instrument_ids=instrument_ids,
            start_date=start_date,
            end_date=end_date,
        )

    def delete_partition(self, partition_key: str) -> bool:
        return self._store.delete_partition(self.DATASET, partition_key)

    def get_checksum(self, partition_key: str) -> str:
        return self._store.get_checksum(self.DATASET, partition_key)

    @property
    def data_root(self) -> Path:
        return self._store.data_root
```

**Step 6: Write test for CommodityBarsReader**

```python
# packages/datahub/tests/unit/stores/market/commodity/test_bars_reader.py
"""Unit tests for Commodity bars reader."""

from pathlib import Path

import polars as pl
import pytest

from ditto_datahub.stores.market.commodity.bars import (
    CommodityBarsReader,
    CommodityBarsWriter,
)


@pytest.fixture
def commodity_bars_reader(tmp_path: Path) -> CommodityBarsReader:
    return CommodityBarsReader(tmp_path)


@pytest.fixture
def commodity_bars_writer(tmp_path: Path) -> CommodityBarsWriter:
    return CommodityBarsWriter(tmp_path)


class TestCommodityBarsReader:
    def test_read_empty_dataset(
        self, commodity_bars_reader: CommodityBarsReader
    ) -> None:
        result = commodity_bars_reader.read()
        assert result.is_empty()

    def test_dataset_name(self, commodity_bars_reader: CommodityBarsReader) -> None:
        assert commodity_bars_reader.DATASET == "market/commodity/bars"


class TestCommodityBarsWriter:
    def test_write_and_read(
        self,
        commodity_bars_reader: CommodityBarsReader,
        commodity_bars_writer: CommodityBarsWriter,
    ) -> None:
        df = pl.DataFrame({
            "instrument_id": [5_000_001, 5_000_001],
            "trade_date": [pl.date(2024, 1, 1), pl.date(2024, 1, 2)],
            "open": [75.50, 76.00],
            "high": [76.00, 76.50],
            "low": [75.00, 75.50],
            "close": [75.80, 76.20],
        })

        result = commodity_bars_writer.write(df, 2024)
        assert result.added == 2

        read_df = commodity_bars_reader.read()
        assert len(read_df) == 2
```

**Step 7: Run test**

Run: `pixi run -e dev pytest packages/datahub/tests/unit/stores/market/commodity/test_bars_reader.py -v`

**Step 8: Commit**

```bash
git add packages/datahub/src/ditto_datahub/stores/market/commodity/
git add packages/datahub/tests/unit/stores/market/commodity/
git commit -m "feat(datahub): add CommodityBarsReader/Writer for commodity daily bars storage"
```

---

## Task 3: 扩展 MarketService 支持 FX/Commodity

**Files:**
- Modify: `packages/datahub/src/ditto_datahub/services/market_service.py`

**Step 1: Add FX/Commodity reader/writer imports**

在文件顶部导入区域添加：

```python
from ditto_datahub.stores.market.fx.bars import FxBarsReader, FxBarsWriter
from ditto_datahub.stores.market.commodity.bars import (
    CommodityBarsReader,
    CommodityBarsWriter,
)
```

**Step 2: Extend __init__ parameters**

在 `__init__` 方法中添加新参数（约第 130-150 行）：

```python
def __init__(  # noqa: PLR0913
    self,
    # ... existing parameters ...
    fx_bars_reader: FxBarsReader | None = None,
    fx_bars_writer: FxBarsWriter | None = None,
    commodity_bars_reader: CommodityBarsReader | None = None,
    commodity_bars_writer: CommodityBarsWriter | None = None,
) -> None:
    # ... existing assignments ...
    self._fx_bars_reader = fx_bars_reader
    self._fx_bars_writer = fx_bars_writer
    self._commodity_bars_reader = commodity_bars_reader
    self._commodity_bars_writer = commodity_bars_writer
```

**Step 3: Extend save_bars type hint**

修改 `save_bars` 方法的 `dataset` 参数类型（约第 620-623 行）：

```python
def save_bars(
    self,
    dataset: Literal["stock_daily", "etf_daily", "index_daily", "fx_daily", "commodity_daily"],
    df: pl.DataFrame,
    year: int,
    on_duplicate: OnDuplicate = OnDuplicate.ERROR,
) -> int:
```

**Step 4: Add FX/Commodity cases in save_bars**

在 `save_bars` 方法的条件分支中添加（约第 665-676 行之后）：

```python
        elif dataset == "fx_daily":
            if self._fx_bars_writer is None:
                raise ValueError("FxBarsWriter not configured")
            write_result = self._fx_bars_writer.write(
                storage_df,
                year,
                on_duplicate=on_duplicate_enum,
            )
        elif dataset == "commodity_daily":
            if self._commodity_bars_writer is None:
                raise ValueError("CommodityBarsWriter not configured")
            write_result = self._commodity_bars_writer.write(
                storage_df,
                year,
                on_duplicate=on_duplicate_enum,
            )
```

**Step 5: Extend _load_bars_core for FX/Commodity**

在 `_load_bars_core` 方法中添加分支（约第 343-387 行）：

```python
    def _load_bars_core(
        self,
        instrument_ids: list[int],
        start: date | None,
        end: date | None,
        asset_class: Literal["stock", "etf", "index", "fx", "commodity"],
    ) -> pl.DataFrame:
        # ... existing code ...
        elif asset_class == "fx":
            if self._fx_bars_reader is None:
                return pl.DataFrame()
            return self._fx_bars_reader.read(
                instrument_ids=instrument_ids,
                start_date=start_str,
                end_date=end_str,
            )
        elif asset_class == "commodity":
            if self._commodity_bars_reader is None:
                return pl.DataFrame()
            return self._commodity_bars_reader.read(
                instrument_ids=instrument_ids,
                start_date=start_str,
                end_date=end_str,
            )
```

**Step 6: Update MarketBarsQuery asset_class type**

修改 `MarketBarsQuery` 的 `asset_class` 类型（约第 102 行）：

```python
asset_class: Literal["stock", "etf", "index", "fx", "commodity"] | None = None
```

**Step 7: Run type check**

Run: `pixi run -e dev type packages/datahub/src/ditto_datahub/services/market_service.py`

**Step 8: Commit**

```bash
git add packages/datahub/src/ditto_datahub/services/market_service.py
git commit -m "feat(datahub): extend MarketService to support FX/Commodity asset classes"
```

---

## Task 4: 扩展 data_writer.py 添加 FX/Commodity handlers

**Files:**
- Modify: `apps/port/src/ditto_port/services/ingestion/data_writer.py`

**Step 1: Add imports for FX/Commodity mappings**

在文件顶部添加导入（约第 15-22 行）：

```python
from ditto_datahub.sources.fred.adapters.commodity import (
    COMMODITY_CODE_TO_INSTRUMENT_ID,
    VIX_CODE_TO_INSTRUMENT_ID,
)
from ditto_datahub.sources.tushare.adapters.fx import FX_CODE_TO_INSTRUMENT_ID
```

**Step 2: Add _write_fx_bars method**

在类中添加新方法（约第 357 行之后）：

```python
    def _write_fx_bars(
        self,
        dataset: str,
        df: pl.DataFrame,
        year: int,
        on_duplicate: OnDuplicate,
    ) -> WriteResult:
        """Write FX daily bars data."""
        rows_written = self._market_service.save_bars(
            dataset="fx_daily",
            df=df,
            year=year,
            on_duplicate=on_duplicate,
        )
        return _to_write_result(dataset, year, df, rows_written)
```

**Step 3: Add _write_commodity_bars method**

```python
    def _write_commodity_bars(
        self,
        dataset: str,
        df: pl.DataFrame,
        year: int,
        on_duplicate: OnDuplicate,
    ) -> WriteResult:
        """Write Commodity daily bars data."""
        rows_written = self._market_service.save_bars(
            dataset="commodity_daily",
            df=df,
            year=year,
            on_duplicate=on_duplicate,
        )
        return _to_write_result(dataset, year, df, rows_written)
```

**Step 4: Add handlers to the handlers dict**

在 `write_data` 方法的 handlers 字典中添加（约第 265-268 行）：

```python
            Dataset.FX_DAILY: lambda: self._write_fx_bars(
                dataset,
                df,
                year,
                on_duplicate,
            ),
            Dataset.COMMODITY_DAILY: lambda: self._write_commodity_bars(
                dataset,
                df,
                year,
                on_duplicate,
            ),
```

**Step 5: Run type check**

Run: `pixi run -e dev type apps/port/src/ditto_port/services/ingestion/data_writer.py`

**Step 6: Commit**

```bash
git add apps/port/src/ditto_port/services/ingestion/data_writer.py
git commit -m "feat(port): add FX/Commodity daily bars write handlers to data_writer"
```

---

## Task 5: 修复国债收益率异常值处理

**Files:**
- Modify: `packages/datahub/src/ditto_datahub/sources/tushare/adapters/bond_yield.py`
- Create: `packages/datahub/tests/unit/sources/tushare/adapters/test_bond_yield_error_handling.py`

**Step 1: Write failing test for error handling**

```python
# packages/datahub/tests/unit/sources/tushare/adapters/test_bond_yield_error_handling.py
"""Tests for bond yield adapter error handling."""

import polars as pl
import pytest

from ditto_datahub.sources.tushare.adapters.bond_yield import BondYieldTushareAdapter


class TestBondYieldErrorHandling:
    """Tests for handling invalid data in bond yield responses."""

    def test_parse_row_skips_invalid_curve_term(self) -> None:
        """Rows with non-numeric curve_term should be skipped, not defaulted to 0.0."""
        # This test verifies the fix for silent 0.0 pollution
        adapter = BondYieldTushareAdapter.__new__(BondYieldTushareAdapter)

        # Mock row with invalid curve_term
        row = {
            "curve_term": "--",  # Invalid: string that can't be parsed as float
            "trade_date": "20240101",
            "yield": 2.5,
        }

        from ditto_datahub.sources.tushare.adapters.bond_yield import CN_BOND_YIELD_INDICATORS

        term_to_indicator = {
            1.0: ("CN_BOND_YIELD_1Y", CN_BOND_YIELD_INDICATORS["CN_BOND_YIELD_1Y"]),
        }

        result = adapter._parse_row(row, term_to_indicator)
        # Should return None, NOT a tuple with value=0.0
        assert result is None

    def test_parse_row_skips_invalid_yield(self) -> None:
        """Rows with non-numeric yield should be skipped, not defaulted to 0.0."""
        adapter = BondYieldTushareAdapter.__new__(BondYieldTushareAdapter)

        row = {
            "curve_term": 1.0,
            "trade_date": "20240101",
            "yield": "--",  # Invalid
        }

        from ditto_datahub.sources.tushare.adapters.bond_yield import CN_BOND_YIELD_INDICATORS

        term_to_indicator = {
            1.0: ("CN_BOND_YIELD_1Y", CN_BOND_YIELD_INDICATORS["CN_BOND_YIELD_1Y"]),
        }

        result = adapter._parse_row(row, term_to_indicator)
        # Should return None
        assert result is None

    def test_parse_row_accepts_valid_data(self) -> None:
        """Valid data should be parsed correctly."""
        adapter = BondYieldTushareAdapter.__new__(BondYieldTushareAdapter)

        row = {
            "curve_term": 1.0,
            "trade_date": "20240101",
            "yield": 2.5,
        }

        from ditto_datahub.sources.tushare.adapters.bond_yield import CN_BOND_YIELD_INDICATORS

        term_to_indicator = {
            1.0: ("CN_BOND_YIELD_1Y", CN_BOND_YIELD_INDICATORS["CN_BOND_YIELD_1Y"]),
        }

        result = adapter._parse_row(row, term_to_indicator)
        assert result is not None
        code, indicator, date_obj, value = result
        assert value == 2.5
```

**Step 2: Run test to verify it fails**

Run: `pixi run -e dev pytest packages/datahub/tests/unit/sources/tushare/adapters/test_bond_yield_error_handling.py -v`

Expected: Tests FAIL because current code returns 0.0 for invalid values

**Step 3: Modify _parse_row to skip invalid data**

修改 `_parse_row` 方法（约第 225-254 行）：

```python
    def _parse_row(
        self,
        row: dict[str, object],
        term_to_indicator: dict[float, tuple[str, CnBondYieldIndicator]],
    ) -> tuple[str, CnBondYieldIndicator, date, float] | None:
        """解析单行数据，返回指标信息或 None。"""
        curve_term = row.get("curve_term")
        if curve_term is None:
            return None

        # 严格解析 curve_term，无效值返回 None
        try:
            term_float = float(curve_term)
        except (TypeError, ValueError):
            logger.warning(
                "Invalid curve_term value, skipping row",
                event="bond_yield_invalid_curve_term",
                curve_term=curve_term,
            )
            return None

        indicator_data = term_to_indicator.get(term_float)
        if indicator_data is None:
            return None

        code, indicator = indicator_data
        trade_date = row.get("trade_date")
        value = row.get("yield")

        if trade_date is None or value is None:
            return None

        date_obj = _parse_trade_date(trade_date)
        if date_obj is None:
            return None

        # 严格解析 value，无效值返回 None
        try:
            value_float = float(value)
        except (TypeError, ValueError):
            logger.warning(
                "Invalid yield value, skipping row",
                event="bond_yield_invalid_value",
                value=value,
                trade_date=trade_date,
            )
            return None

        return code, indicator, date_obj, value_float
```

**Step 4: Run test to verify it passes**

Run: `pixi run -e dev pytest packages/datahub/tests/unit/sources/tushare/adapters/test_bond_yield_error_handling.py -v`

Expected: All tests PASS

**Step 5: Commit**

```bash
git add packages/datahub/src/ditto_datahub/sources/tushare/adapters/bond_yield.py
git add packages/datahub/tests/unit/sources/tushare/adapters/test_bond_yield_error_handling.py
git commit -m "fix(datahub): skip invalid bond yield data instead of defaulting to 0.0"
```

---

## Task 6: 修复 FRED 配置错误分支

**Files:**
- Modify: `apps/port/src/ditto_port/services/ingestion/coordinator.py`

**Step 1: Modify COMMODITY_DAILY handler to return error when FRED not configured**

修改 `_fetch_data` 方法中的 `Dataset.COMMODITY_DAILY` handler（约第 807-816 行）：

```python
            Dataset.COMMODITY_DAILY: lambda: (
                self._fred_source.fetch_commodities(
                    codes=list(COMMODITY_CODE_TO_INSTRUMENT_ID.keys())
                    + list(VIX_CODE_TO_INSTRUMENT_ID.keys()),
                    start_date=trade_date,
                    end_date=trade_date,
                )
                if self._fred_source
                else self._raise_fred_not_configured()
            ),
```

**Step 2: Add _raise_fred_not_configured helper method**

在类中添加辅助方法：

```python
    @staticmethod
    def _raise_fred_not_configured() -> pl.DataFrame:
        """Raise error when FRED source is not configured."""
        raise SourceFetchError(
            message="FRED data source not configured. Set FRED_API_KEY environment variable.",
            source="fred",
        )
```

**Step 3: Run type check**

Run: `pixi run -e dev type apps/port/src/ditto_port/services/ingestion/coordinator.py`

**Step 4: Commit**

```bash
git add apps/port/src/ditto_port/services/ingestion/coordinator.py
git commit -m "fix(port): raise clear error when FRED not configured for commodity data"
```

---

## Task 7: 实现 API 路由 - 挂载和查询

**Files:**
- Modify: `apps/port/src/ditto_port/main.py`
- Modify: `apps/port/src/ditto_port/api/routes/fx.py`
- Modify: `apps/port/src/ditto_port/api/routes/commodity.py`

**Step 1: Mount FX and commodity routers in main.py**

在路由挂载区域添加（约第 185-192 行）：

```python
from ditto_port.api.routes import (
    capital,
    commodity,  # Add
    fundamental,
    fx,  # Add
    ingestion,
    macro,
    market,
    metadata,
    portfolio,
    source,
)

# ... later in file ...
app.include_router(capital.router, prefix="/api/v1")
app.include_router(commodity.router, prefix="/api/v1")  # Add
app.include_router(fundamental.router, prefix="/api/v1")
app.include_router(fx.router, prefix="/api/v1")  # Add
app.include_router(ingestion.router, prefix="/api/v1")
# ... rest ...
```

**Step 2: Implement fx.py query logic**

```python
"""FX (外汇) 域 API 路由."""

from typing import Annotated

from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, Query

from ditto_datahub.services.market_service import MarketService
from ditto_datahub.sources.tushare.adapters.fx import FX_CODE_TO_INSTRUMENT_ID
from ditto_port.models.common import APIResponse
from ditto_port.models.fx import FxBar, FxQuery

router = APIRouter(prefix="/fx", tags=["fx"])


def _to_fx_bars(df) -> list[FxBar]:
    """Convert DataFrame to FxBar list."""
    if df.is_empty():
        return []
    return [
        FxBar(
            instrument_id=row["instrument_id"],
            trade_date=row["trade_date"].isoformat(),
            open=row["open"],
            high=row["high"],
            low=row["low"],
            close=row["close"],
        )
        for row in df.to_dicts()
    ]


@router.post("/bars", response_model=APIResponse[list[FxBar]])
@inject
async def post_bars(
    query: FxQuery,
    market_service: Annotated[MarketService, FromDishka()],
) -> APIResponse[list[FxBar]]:
    """
    查询外汇 K 线数据.

    Args:
        query: 查询参数
        market_service: MarketService 实例

    Returns:
        APIResponse 包含外汇 K 线数据列表

    """
    # 获取 instrument_ids
    if query.pairs:
        instrument_ids = [
            FX_CODE_TO_INSTRUMENT_ID[pair]
            for pair in query.pairs
            if pair in FX_CODE_TO_INSTRUMENT_ID
        ]
    else:
        instrument_ids = list(FX_CODE_TO_INSTRUMENT_ID.values())

    if not instrument_ids:
        return APIResponse(data=[])

    # 查询数据
    df = market_service.list_bars(
        instrument_ids=instrument_ids,
        start=query.start_date.isoformat() if query.start_date else None,
        end=query.end_date.isoformat() if query.end_date else None,
    )

    # 应用 limit
    bars = _to_fx_bars(df)
    if query.limit:
        bars = bars[:query.limit]

    return APIResponse(data=bars)
```

**Step 3: Implement commodity.py query logic**

```python
"""Commodity (商品) 域 API 路由."""

from typing import Annotated

from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter

from ditto_datahub.services.market_service import MarketService
from ditto_datahub.sources.fred.adapters.commodity import (
    COMMODITY_CODE_TO_INSTRUMENT_ID,
    VIX_CODE_TO_INSTRUMENT_ID,
)
from ditto_port.models.commodity import CommodityBar, CommodityQuery
from ditto_port.models.common import APIResponse

router = APIRouter(prefix="/commodity", tags=["commodity"])


def _to_commodity_bars(df) -> list[CommodityBar]:
    """Convert DataFrame to CommodityBar list."""
    if df.is_empty():
        return []
    return [
        CommodityBar(
            instrument_id=row["instrument_id"],
            trade_date=row["trade_date"].isoformat(),
            open=row["open"],
            high=row["high"],
            low=row["low"],
            close=row["close"],
        )
        for row in df.to_dicts()
    ]


@router.post("/bars", response_model=APIResponse[list[CommodityBar]])
@inject
async def post_bars(
    query: CommodityQuery,
    market_service: Annotated[MarketService, FromDishka()],
) -> APIResponse[list[CommodityBar]]:
    """
    查询商品 K 线数据.

    Args:
        query: 查询参数
        market_service: MarketService 实例

    Returns:
        APIResponse 包含商品 K 线数据列表

    """
    # 合并 commodity 和 VIX 的映射
    all_mappings = {**COMMODITY_CODE_TO_INSTRUMENT_ID, **VIX_CODE_TO_INSTRUMENT_ID}

    # 获取 instrument_ids
    if query.symbols:
        instrument_ids = [
            all_mappings[symbol]
            for symbol in query.symbols
            if symbol in all_mappings
        ]
    else:
        instrument_ids = list(all_mappings.values())

    if not instrument_ids:
        return APIResponse(data=[])

    # 查询数据
    df = market_service.list_bars(
        instrument_ids=instrument_ids,
        start=query.start_date.isoformat() if query.start_date else None,
        end=query.end_date.isoformat() if query.end_date else None,
    )

    # 应用 limit
    bars = _to_commodity_bars(df)
    if query.limit:
        bars = bars[:query.limit]

    return APIResponse(data=bars)
```

**Step 4: Run type check**

Run: `pixi run -e dev type apps/port/src/ditto_port/`

**Step 5: Commit**

```bash
git add apps/port/src/ditto_port/main.py
git add apps/port/src/ditto_port/api/routes/fx.py
git add apps/port/src/ditto_port/api/routes/commodity.py
git commit -m "feat(port): implement FX/Commodity API routes with MarketService integration"
```

---

## Task 8: 运行完整验证

**Step 1: Run lint check**

Run: `pixi run -e dev lint`

**Step 2: Run type check**

Run: `pixi run -e dev type`

**Step 3: Run fast tests**

Run: `pixi run -e dev test --fast`

**Step 4: Run architecture check**

Run: `pixi run -e dev arch-check`

**Step 5: Run full check**

Run: `pixi run -e dev check`

Expected: All checks pass

**Step 6: Final commit (if any fixes needed)**

```bash
git add -A
git commit -m "fix: address remaining issues from verification"
```

---

## 验收清单

- [ ] `pixi run -e dev check` 全部通过
- [ ] `write_data('fx_daily', ...)` 成功写入数据
- [ ] `write_data('commodity_daily', ...)` 成功写入数据
- [ ] `/api/v1/fx/bars` 返回正确数据
- [ ] `/api/v1/commodity/bars` 返回正确数据
- [ ] 国债收益率异常值不再被静默写成 0.0
- [ ] FRED 未配置时返回明确的错误信息

---

## 回滚方案

如果出现问题，可以逐个 revert commits：

```bash
git log --oneline -10  # 查看最近的 commits
git revert HEAD~N      # revert 特定 commit
```
