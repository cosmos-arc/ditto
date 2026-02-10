# Features & Factors Domain Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement Features Domain (technical indicators) and Factors Domain with PIT support for quantitative trading research.

**Architecture:**
- **Features Domain**: Technical indicators stored in Parquet narrow tables (no PIT needed)
- **Factors Domain**: Factor signals stored in Parquet narrow tables with PIT columns (effective_from/effective_to)
- Both follow existing patterns from Market Domain (ParquetStoreBase) and Macro Domain (SQLite-based PIT)

**Tech Stack:**
- Polars for DataFrame operations
- Parquet file format for columnar storage
- Year-based partitioning (data_root/features/technical/indicators_narrow/YYYY.parquet)
- SQLite for metadata (indicator/factor definitions)
- TDD (RED-GREEN-REFACTOR) workflow

---

## Prerequisites

**Context you need:**
1. Read design doc: `docs/plans/2026-02-01-features-factors-domain-design.md`
2. Study existing patterns:
   - `packages/datahub/src/ditto_datahub/stores/parquet_store_base.py` - Parquet storage base class
   - `packages/datahub/src/ditto_datahub/domains/macro/indicator/indicator_store.py` - SQLite-based PIT pattern
   - `packages/datahub/src/ditto_datahub/domains/market/stock/bars/bars_store.py` - ParquetStoreBase usage
3. Understand DataRootConfig: `packages/datahub/src/ditto_datahub/config/data_root.py`

**Key patterns to follow:**
- ParquetStoreBase: Subclass implements `_get_dataset()` and `_get_key_columns()`
- Macro PIT pattern: effective_from/effective_to columns with ROW_NUMBER() window function
- Directory structure: `domains/{domain}/{subdomain}/` with __init__.py exports

---

## Phase 7: Features Domain (Technical Indicators)

### Task 1: Create Features Domain Directory Structure

**Files:**
- Create: `packages/datahub/src/ditto_datahub/domains/features/__init__.py`
- Create: `packages/datahub/src/ditto_datahub/domains/features/technical/__init__.py`
- Create: `packages/datahub/src/ditto_datahub/domains/features/technical/indicator_store.py`
- Create: `packages/datahub/src/ditto_datahub/domains/features/technical/indicator_metadata_store.py`
- Create: `packages/datahub/src/ditto_datahub/domains/features/technical/metadata.py`
- Create: `packages/datahub/src/ditto_datahub/domains/features/feature_service.py`

**Step 1: Create features/__init__.py**

```python
"""Features domain - technical indicators and derived features."""

from ditto_datahub.domains.features.technical import (
    IndicatorMetadataStore,
    IndicatorStore,
)
from ditto_datahub.domains.features.feature_service import (
    FeatureQuery,
    FeatureService,
)

__all__ = [
    "IndicatorMetadataStore",
    "IndicatorStore",
    "FeatureQuery",
    "FeatureService",
]
```

**Step 2: Create features/technical/__init__.py**

```python
"""Technical indicators subdomain."""

from ditto_datahub.domains.features.technical.indicator_metadata_store import (
    IndicatorMetadataStore,
)
from ditto_datahub.domains.features.technical.indicator_store import IndicatorStore

__all__ = [
    "IndicatorMetadataStore",
    "IndicatorStore",
]
```

**Step 3: Create features/technical/metadata.py**

```python
"""Metadata models for technical indicators."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

# Valid indicator types (based on ScienceDirect 2025 research)
IndicatorType = Literal["trend", "momentum", "volatility", "volume"]


@dataclass(frozen=True)
class IndicatorMetadata:
    """
    Technical indicator metadata.

    Attributes:
        indicator_id: Unique identifier (e.g., "indicator_rsi_14")
        name: Display name (e.g., "RSI(14)")
        type: Indicator category
        description: Human-readable description
        formula: Calculation formula
        parameters: Calculation parameters (e.g., {"period": 14})
    """

    indicator_id: str
    name: str
    type: IndicatorType
    description: str
    formula: str
    parameters: dict
    status: str = "active"


# Predefined indicator types
INDICATOR_TYPE_TREND = "trend"
INDICATOR_TYPE_MOMENTUM = "momentum"
INDICATOR_TYPE_VOLATILITY = "volatility"
INDICATOR_TYPE_VOLUME = "volume"


__all__ = [
    "IndicatorMetadata",
    "IndicatorType",
    "INDICATOR_TYPE_TREND",
    "INDICATOR_TYPE_MOMENTUM",
    "INDICATOR_TYPE_VOLATILITY",
    "INDICATOR_TYPE_VOLUME",
]
```

**Step 4: Commit directory structure**

```bash
cd packages/datahub
git add src/ditto_datahub/domains/features/
git commit -m "feat(features): add Features domain directory structure"
```

---

### Task 2: Implement IndicatorMetadataStore

**Files:**
- Modify: `packages/datahub/src/ditto_datahub/domains/features/technical/indicator_metadata_store.py`

**Step 1: Write the failing test**

Create: `packages/datahub/tests/unit/domains/features/technical/test_indicator_metadata_store.py`

```python
"""Tests for IndicatorMetadataStore."""

from pathlib import Path

import polars as pl
import pytest

from ditto_datahub.domains.features.technical.indicator_metadata_store import (
    IndicatorMetadataStore,
)
from ditto_datahub.stores.sqlite_client import SQLiteClient


@pytest.fixture
def temp_db_path(tmp_path: Path) -> Path:
    """Create temporary database path."""
    return tmp_path / "test_indicators.sqlite"


@pytest.fixture
def sqlite_client(temp_db_path: Path) -> SQLiteClient:
    """Create SQLite client for testing."""
    client = SQLiteClient(str(temp_db_path))
    client.execute("""
        CREATE TABLE IF NOT EXISTS technical_indicators (
            indicator_id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            type TEXT NOT NULL,
            description TEXT,
            formula TEXT,
            parameters TEXT,
            status TEXT NOT NULL DEFAULT 'active'
        )
    """)
    client.commit()
    return client


@pytest.fixture
def metadata_store(sqlite_client: SQLiteClient) -> IndicatorMetadataStore:
    """Create IndicatorMetadataStore for testing."""
    return IndicatorMetadataStore(sqlite_client)


def test_upsert_new_indicator(metadata_store: IndicatorMetadataStore) -> None:
    """Test upserting a new indicator."""
    indicator_id = metadata_store.upsert(
        code="indicator_rsi_14",
        name="RSI(14)",
        type="momentum",
        description="14-day Relative Strength Index",
        formula="RSI = 100 - 100/(1 + RS)",
        parameters='{"period": 14}',
    )

    assert indicator_id > 0

    # Verify retrieval
    row = metadata_store.get_by_code("indicator_rsi_14")
    assert not row.is_empty()
    assert row["code"][0] == "indicator_rsi_14"
    assert row["name"][0] == "RSI(14)"
    assert row["type"][0] == "momentum"


def test_get_by_id(metadata_store: IndicatorMetadataStore) -> None:
    """Test getting indicator by ID."""
    # First insert an indicator
    indicator_id = metadata_store.upsert(
        code="indicator_ma_20",
        name="MA(20)",
        type="trend",
        description="20-day Moving Average",
        formula="SMA(price, 20)",
        parameters='{"period": 20}',
    )

    # Retrieve by ID
    row = metadata_store.get_by_id(indicator_id)
    assert not row.is_empty()
    assert row["indicator_id"][0] == indicator_id
    assert row["code"][0] == "indicator_ma_20"


def test_list_by_type(metadata_store: IndicatorMetadataStore) -> None:
    """Test listing indicators by type."""
    # Insert indicators of different types
    metadata_store.upsert(
        code="indicator_rsi_14",
        name="RSI(14)",
        type="momentum",
        description="RSI",
        formula="RSI",
        parameters='{}',
    )
    metadata_store.upsert(
        code="indicator_ma_20",
        name="MA(20)",
        type="trend",
        description="MA",
        formula="MA",
        parameters='{}',
    )
    metadata_store.upsert(
        code="indicator_macd",
        name="MACD",
        type="trend",
        description="MACD",
        formula="MACD",
        parameters='{}',
    )

    # List trend indicators
    trend_indicators = metadata_store.list_by_type("trend")
    assert len(trend_indicators) == 2
    assert set(trend_indicators["code"].to_list()) == {
        "indicator_ma_20",
        "indicator_macd",
    }

    # List momentum indicators
    momentum_indicators = metadata_store.list_by_type("momentum")
    assert len(momentum_indicators) == 1
    assert momentum_indicators["code"][0] == "indicator_rsi_14"


def test_get_by_code_not_found(metadata_store: IndicatorMetadataStore) -> None:
    """Test getting non-existent indicator returns empty DataFrame."""
    row = metadata_store.get_by_code("indicator_nonexistent")
    assert row.is_empty()
```

**Step 2: Run test to verify it fails**

```bash
cd packages/datahub
pixi run -e dev pytest tests/unit/domains/features/technical/test_indicator_metadata_store.py -v
```

Expected: `ModuleNotFoundError: No module named 'ditto_datahub.domains.features.technical.indicator_metadata_store'`

**Step 3: Write minimal implementation**

Modify: `packages/datahub/src/ditto_datahub/domains/features/technical/indicator_metadata_store.py`

```python
"""IndicatorMetadataStore for technical indicator metadata management."""

from __future__ import annotations

from typing import Literal

import polars as pl
from ditto_foundation import logger, traced

from ditto_datahub.stores.sqlite_client import SQLiteClient


class IndicatorMetadataStore:
    """
    Technical indicator metadata storage.

    Manages indicator metadata including code, name, type,
    formula, and parameters for technical indicators.
    """

    # Valid indicator types
    TYPE_TREND = "trend"
    TYPE_MOMENTUM = "momentum"
    TYPE_VOLATILITY = "volatility"
    TYPE_VOLUME = "volume"

    def __init__(self, sqlite_client: SQLiteClient) -> None:
        """
        Initialize IndicatorMetadataStore.

        Args:
            sqlite_client: SQLite client for database operations.

        """
        self._client = sqlite_client
        self._init_table()

    def _init_table(self) -> None:
        """Initialize the technical_indicators table if not exists."""
        self._client.execute("""
            CREATE TABLE IF NOT EXISTS technical_indicators (
                indicator_id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                type TEXT NOT NULL,
                description TEXT,
                formula TEXT,
                parameters TEXT,
                status TEXT NOT NULL DEFAULT 'active'
            )
        """)
        self._client.commit()

    @traced("data.metadata_write")
    def upsert(
        self,
        code: str,
        name: str,
        type: Literal["trend", "momentum", "volatility", "volume"],
        description: str,
        formula: str,
        parameters: str,
    ) -> int:
        """
        Register or update indicator metadata.

        Args:
            code: Indicator code (e.g., 'indicator_rsi_14').
            name: Indicator display name.
            type: Indicator type (trend, momentum, volatility, volume).
            description: Description text.
            formula: Calculation formula.
            parameters: JSON string of parameters.

        Returns:
            indicator_id

        Raises:
            Exception: If database operation fails.

        """
        logger.info(
            "Upserting indicator metadata",
            code=code,
            name=name,
            type=type,
        )

        try:
            # Check if exists
            result = self._client.fetchone(
                """SELECT indicator_id FROM technical_indicators WHERE code = ?""",
                [code],
            )
            if result is None:
                # Insert new
                sql = (
                    "INSERT INTO technical_indicators "
                    "(code, name, type, description, formula, parameters) "
                    "VALUES (?, ?, ?, ?, ?, ?)"
                )
                indicator_id = self._client.insert_returning_id(
                    sql,
                    [code, name, type, description, formula, parameters],
                )
            else:
                # Update existing
                indicator_id = result["indicator_id"]
                self._client.execute(
                    """UPDATE technical_indicators
                    SET name = ?, type = ?, description = ?,
                        formula = ?, parameters = ?
                    WHERE indicator_id = ?""",
                    [name, type, description, formula, parameters, indicator_id],
                )
                self._client.commit()

            logger.info(
                "Indicator metadata upserted successfully",
                indicator_id=indicator_id,
                code=code,
            )
            return indicator_id

        except Exception as e:
            self._client.rollback()
            logger.error("Indicator metadata upsert failed", error=str(e))
            raise

    @traced("data.metadata_query")
    def get_by_id(self, indicator_id: int) -> pl.DataFrame:
        """
        Query indicator metadata by ID.

        Args:
            indicator_id: Indicator ID.

        Returns:
            DataFrame with indicator metadata, or empty DataFrame if not found.

        """
        logger.debug(
            "Querying indicator metadata by ID",
            indicator_id=indicator_id,
        )

        rows = self._client.fetchall(
            """SELECT indicator_id, code, name, type, description, formula, parameters
               FROM technical_indicators
               WHERE indicator_id = ?""",
            [indicator_id],
        )

        return pl.DataFrame(rows) if rows else pl.DataFrame()

    @traced("data.metadata_query")
    def get_by_code(self, code: str) -> pl.DataFrame:
        """
        Query indicator metadata by code.

        Args:
            code: Indicator code.

        Returns:
            DataFrame with indicator metadata, or empty DataFrame if not found.

        """
        logger.debug(
            "Querying indicator metadata by code",
            code=code,
        )

        rows = self._client.fetchall(
            """SELECT indicator_id, code, name, type, description, formula, parameters
               FROM technical_indicators
               WHERE code = ?""",
            [code],
        )

        return pl.DataFrame(rows) if rows else pl.DataFrame()

    @traced("data.metadata_query")
    def list_by_type(self, indicator_type: str | None = None) -> pl.DataFrame:
        """
        List indicators by type.

        Args:
            indicator_type: Type filter (None = all types).

        Returns:
            DataFrame with matching indicators.

        """
        logger.debug(
            "Listing indicators by type",
            indicator_type=indicator_type,
        )

        if indicator_type:
            rows = self._client.fetchall(
                """SELECT indicator_id, code, name, type, description, formula, parameters
                   FROM technical_indicators
                   WHERE type = ?
                   ORDER BY code""",
                [indicator_type],
            )
        else:
            rows = self._client.fetchall(
                """SELECT indicator_id, code, name, type, description, formula, parameters
                   FROM technical_indicators
                   ORDER BY code""",
            )

        return pl.DataFrame(rows) if rows else pl.DataFrame()

    def close(self) -> None:
        """Close the underlying SQLite client."""
        self._client.close()
```

**Step 4: Run test to verify it passes**

```bash
cd packages/datahub
pixi run -e dev pytest tests/unit/domains/features/technical/test_indicator_metadata_store.py -v
```

Expected: All tests pass

**Step 5: Commit**

```bash
git add src/ tests/
git commit -m "feat(features): implement IndicatorMetadataStore with tests"
```

---

### Task 3: Implement IndicatorStore (Parquet-based)

**Files:**
- Modify: `packages/datahub/src/ditto_datahub/domains/features/technical/indicator_store.py`

**Step 1: Write the failing test**

Create: `packages/datahub/tests/unit/domains/features/technical/test_indicator_store.py`

```python
"""Tests for IndicatorStore."""

from pathlib import Path

import polars as pl
import pytest

from ditto_datahub.domains.features.technical.indicator_store import IndicatorStore


@pytest.fixture
def temp_data_root(tmp_path: Path) -> Path:
    """Create temporary data root."""
    return tmp_path / "features" / "technical" / "indicators_narrow"


@pytest.fixture
def indicator_store(temp_data_root: Path) -> IndicatorStore:
    """Create IndicatorStore for testing."""
    return IndicatorStore(temp_data_root)


def test_write_and_read_indicator_data(indicator_store: IndicatorStore) -> None:
    """Test writing and reading indicator data."""
    # Prepare test data
    df = pl.DataFrame(
        {
            "sid": [1, 1, 2, 2],
            "trade_date": [
                "2024-01-02",
                "2024-01-03",
                "2024-01-02",
                "2024-01-03",
            ],
            "indicator_id": ["indicator_rsi_14", "indicator_rsi_14", "indicator_rsi_14", "indicator_rsi_14"],
            "indicator_type": ["momentum", "momentum", "momentum", "momentum"],
            "value": [65.5, 68.2, 72.1, 71.5],
            "calc_time": [
                "2024-01-02 15:00:00",
                "2024-01-03 15:00:00",
                "2024-01-02 15:00:00",
                "2024-01-03 15:00:00",
            ],
        }
    )

    # Write data
    result = indicator_store.write(df, year=2024)
    assert result.added == 4
    assert result.updated == 0

    # Read data back
    result_df = indicator_store.read(
        start_date="2024-01-01",
        end_date="2024-01-31",
    )

    assert len(result_df) == 4
    assert "sid" in result_df.columns
    assert "trade_date" in result_df.columns
    assert "indicator_id" in result_df.columns
    assert "value" in result_df.columns

    # Verify specific values
    result_df_sorted = result_df.sort(["sid", "trade_date"])
    assert result_df_sorted["value"].to_list() == [65.5, 68.2, 72.1, 71.5]


def test_read_filter_by_sid(indicator_store: IndicatorStore) -> None:
    """Test reading with sid filter."""
    # Prepare test data for multiple securities
    df = pl.DataFrame(
        {
            "sid": [1, 2, 3],
            "trade_date": ["2024-01-02", "2024-01-02", "2024-01-02"],
            "indicator_id": ["indicator_ma_20"] * 3,
            "indicator_type": ["trend"] * 3,
            "value": [10.5, 20.3, 15.7],
            "calc_time": ["2024-01-02 15:00:00"] * 3,
        }
    )

    indicator_store.write(df, year=2024)

    # Read only sid 1 and 2
    result = indicator_store.read(sids=[1, 2], start_date="2024-01-01", end_date="2024-01-31")

    assert len(result) == 2
    assert set(result["sid"].to_list()) == {1, 2}


def test_read_filter_by_indicator_type(indicator_store: IndicatorStore) -> None:
    """Test reading with indicator_type filter."""
    # Prepare test data with different types
    df = pl.DataFrame(
        {
            "sid": [1, 1, 1],
            "trade_date": ["2024-01-02", "2024-01-02", "2024-01-02"],
            "indicator_id": ["indicator_rsi_14", "indicator_ma_20", "indicator_atr_14"],
            "indicator_type": ["momentum", "trend", "volatility"],
            "value": [65.5, 10.2, 1.5],
            "calc_time": ["2024-01-02 15:00:00"] * 3,
        }
    )

    indicator_store.write(df, year=2024)

    # Read only momentum indicators
    result = indicator_store.read(
        start_date="2024-01-01",
        end_date="2024-01-31",
        indicator_types=["momentum"],
    )

    assert len(result) == 1
    assert result["indicator_id"][0] == "indicator_rsi_14"
```

**Step 2: Run test to verify it fails**

```bash
cd packages/datahub
pixi run -e dev pytest tests/unit/domains/features/technical/test_indicator_store.py::test_write_and_read_indicator_data -v
```

Expected: `ModuleNotFoundError: No module named 'ditto_datahub.domains.features.technical.indicator_store'` or method not found

**Step 3: Write minimal implementation**

Modify: `packages/datahub/src/ditto_datahub/domains/features/technical/indicator_store.py`

```python
"""IndicatorStore for technical indicator data storage."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import polars as pl
from ditto_foundation import logger, traced
from ditto_foundation.util.io import atomic_write, file_md5

from ditto_datahub.models import OnDuplicate
from ditto_datahub.models.storage import WriteResultStore as WriteResult
from ditto_datahub.stores.parquet_store_base import ParquetStoreBase


class IndicatorStore(ParquetStoreBase):
    """
    Technical indicator data storage with year partitioning.

    Stores technical indicator values in Parquet files organized by year.
    Follows the narrow table pattern for flexibility.

    Storage structure:
        data_root/features/technical/indicators_narrow/
            2020.parquet
            2021.parquet
            ...

    Schema:
        sid: Security ID
        trade_date: Trading date
        indicator_id: Indicator identifier (e.g., 'indicator_rsi_14')
        indicator_type: Type category (trend/momentum/volatility/volume)
        value: Indicator value
        calc_time: Calculation timestamp
    """

    def __init__(self, data_root: Path) -> None:
        """
        Initialize IndicatorStore.

        Args:
            data_root: Root directory for data storage.

        """
        super().__init__(data_root)
        self._dataset = "features/technical/indicators_narrow"

    def _get_dataset(self) -> str:
        """Return dataset name for technical indicators."""
        return "features/technical/indicators_narrow"

    def _get_key_columns(self) -> list[str]:
        """Return key column names for deduplication."""
        return ["sid", "trade_date", "indicator_id"]

    @traced("data.indicator_write")
    def write(
        self,
        df: pl.DataFrame,
        year: int,
        on_duplicate: OnDuplicate = OnDuplicate.ERROR,
    ) -> WriteResult:
        """
        Write technical indicator data.

        Args:
            df: DataFrame with columns:
                - sid (int)
                - trade_date (date or str YYYY-MM-DD)
                - indicator_id (str)
                - indicator_type (str)
                - value (float)
                - calc_time (str or datetime)
            year: Year partition for writing.
            on_duplicate: How to handle duplicates.

        Returns:
            Write result with statistics.

        Raises:
            ValueError: If required columns are missing.

        """
        logger.info(
            "Starting technical indicator data write",
            record_count=len(df),
            year=year,
        )

        # Validate required columns
        required = ["sid", "trade_date", "indicator_id", "indicator_type", "value"]
        missing = [col for col in required if col not in df.columns]
        if missing:
            msg = f"Missing required columns: {missing}"
            raise ValueError(msg)

        # Use parent class write implementation
        result = super().write(df, year=year, on_duplicate=on_duplicate)

        logger.info(
            "Technical indicator data written successfully",
            record_count=len(df),
            year=year,
            added=result.added,
            updated=result.updated,
        )

        return result

    @traced("data.indicator_query")
    def read(
        self,
        sids: list[int] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        indicator_types: list[str] | None = None,
    ) -> pl.DataFrame:
        """
        Query technical indicator data.

        Args:
            sids: Filter by security IDs (None = all).
            start_date: Start date (YYYY-MM-DD).
            end_date: End date (YYYY-MM-DD).
            indicator_types: Filter by indicator types (None = all).

        Returns:
            DataFrame with indicator data.

        """
        logger.debug(
            "Querying technical indicator data",
            sids=sids,
            start_date=start_date,
            end_date=end_date,
            indicator_types=indicator_types,
        )

        # Use parent class read
        df = super().read(sids=sids, start_date=start_date, end_date=end_date)

        # Apply indicator_type filter
        if not df.is_empty() and indicator_types:
            df = df.filter(pl.col("indicator_type").is_in(indicator_types))

        return df

    def _get_sort_columns(self) -> list[str]:
        """Return sort columns."""
        return ["sid", "trade_date", "indicator_id"]
```

**Step 4: Run test to verify it passes**

```bash
cd packages/datahub
pixi run -e dev pytest tests/unit/domains/features/technical/test_indicator_store.py -v
```

Expected: All tests pass

**Step 5: Commit**

```bash
git add src/ tests/
git commit -m "feat(features): implement IndicatorStore with Parquet storage"
```

---

### Task 4: Implement FeatureService

**Files:**
- Modify: `packages/datahub/src/ditto_datahub/domains/features/feature_service.py`

**Step 1: Write the failing test**

Create: `packages/datahub/tests/unit/domains/features/test_feature_service.py`

```python
"""Tests for FeatureService."""

from pathlib import Path

import polars as pl
import pytest

from ditto_datahub.domains.features.feature_service import (
    FeatureQuery,
    FeatureService,
)
from ditto_datahub.domains.features.technical.indicator_metadata_store import (
    IndicatorMetadataStore,
)
from ditto_datahub.domains.features.technical.indicator_store import IndicatorStore
from ditto_datahub.stores.sqlite_client import SQLiteClient


@pytest.fixture
def temp_data_root(tmp_path: Path) -> Path:
    """Create temporary data root."""
    return tmp_path / "features"


@pytest.fixture
def sqlite_client(temp_data_root: Path) -> SQLiteClient:
    """Create SQLite client for metadata."""
    db_path = temp_data_root / "metadata.sqlite"
    client = SQLiteClient(str(db_path))
    return client


@pytest.fixture
def feature_service(
    temp_data_root: Path,
    sqlite_client: SQLiteClient,
) -> FeatureService:
    """Create FeatureService for testing."""
    indicator_store = IndicatorStore(temp_data_root / "technical" / "indicators_narrow")
    metadata_store = IndicatorMetadataStore(sqlite_client)
    return FeatureService(indicator_store, metadata_store)


def test_get_indicators_enriches_with_metadata(feature_service: FeatureService) -> None:
    """Test that get_indicators enriches data with metadata."""
    # Setup: Register indicator metadata
    feature_service._metadata_store.upsert(
        code="indicator_rsi_14",
        name="RSI(14)",
        type="momentum",
        description="14-day RSI",
        formula="RSI",
        parameters='{}',
    )

    # Setup: Write indicator data
    df = pl.DataFrame(
        {
            "sid": [1, 1],
            "trade_date": ["2024-01-02", "2024-01-03"],
            "indicator_id": ["indicator_rsi_14", "indicator_rsi_14"],
            "indicator_type": ["momentum", "momentum"],
            "value": [65.5, 68.2],
            "calc_time": ["2024-01-02 15:00:00", "2024-01-03 15:00:00"],
        }
    )
    feature_service._indicator_store.write(df, year=2024)

    # Execute: Query indicators
    query = FeatureQuery(
        indicators=["indicator_rsi_14"],
        start="2024-01-01",
        end="2024-01-31",
    )
    result = feature_service.get_indicators(query)

    # Verify: Result includes metadata columns
    assert not result.is_empty()
    assert "indicator_id" in result.columns
    assert "value" in result.columns
    # Metadata should be joined
    assert "name" in result.columns or "code" in result.columns


def test_get_indicators_filters_by_type(feature_service: FeatureService) -> None:
    """Test filtering by indicator type."""
    # Register indicators
    feature_service._metadata_store.upsert(
        code="indicator_rsi_14",
        name="RSI(14)",
        type="momentum",
        description="RSI",
        formula="RSI",
        parameters='{}',
    )
    feature_service._metadata_store.upsert(
        code="indicator_ma_20",
        name="MA(20)",
        type="trend",
        description="MA",
        formula="MA",
        parameters='{}',
    )

    # Write mixed data
    df = pl.DataFrame(
        {
            "sid": [1, 1],
            "trade_date": ["2024-01-02", "2024-01-02"],
            "indicator_id": ["indicator_rsi_14", "indicator_ma_20"],
            "indicator_type": ["momentum", "trend"],
            "value": [65.5, 10.2],
            "calc_time": ["2024-01-02 15:00:00"] * 2,
        }
    )
    feature_service._indicator_store.write(df, year=2024)

    # Query only momentum
    query = FeatureQuery(
        indicator_types=["momentum"],
        start="2024-01-01",
        end="2024-01-31",
    )
    result = feature_service.get_indicators(query)

    assert len(result) == 1
    assert result["indicator_id"][0] == "indicator_rsi_14"
```

**Step 2: Run test to verify it fails**

```bash
cd packages/datahub
pixi run -e dev pytest tests/unit/domains/features/test_feature_service.py -v
```

Expected: Module not found

**Step 3: Write minimal implementation**

Modify: `packages/datahub/src/ditto_datahub/domains/features/feature_service.py`

```python
"""FeatureService - Features domain unified query service."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import polars as pl
from ditto_foundation import logger, traced

from ditto_datahub.domains.features.technical.indicator_store import IndicatorStore
from ditto_datahub.domains.features.technical.indicator_metadata_store import (
    IndicatorMetadataStore,
)


@dataclass(frozen=True)
class FeatureQuery:
    """
    Feature query parameters.

    Attributes:
        indicators: Indicator IDs or codes (None = all).
        start: Start date (YYYY-MM-DD).
        end: End date (YYYY-MM-DD).
        indicator_types: Filter by indicator type (trend/momentum/volatility/volume).
    """

    indicators: list[int] | list[str] | None = None
    start: str | None = None
    end: str | None = None
    indicator_types: (
        list[Literal["trend", "momentum", "volatility", "volume"]] | None
    ) = None


class FeatureService:
    """
    Features domain unified query service.

    Provides high-level query API for technical indicator data,
    integrating IndicatorStore and IndicatorMetadataStore.
    """

    def __init__(
        self,
        indicator_store: IndicatorStore,
        metadata_store: IndicatorMetadataStore,
    ) -> None:
        """
        Initialize FeatureService.

        Args:
            indicator_store: Indicator data storage.
            metadata_store: Indicator metadata storage.

        """
        self._indicator_store = indicator_store
        self._metadata_store = metadata_store

        logger.debug(
            "FeatureService initialized",
            event="feature_service_init_complete",
        )

    @traced("features.get_indicators")
    def get_indicators(self, query: FeatureQuery) -> pl.DataFrame:
        """
        Query technical indicator data.

        Args:
            query: FeatureQuery object with query parameters.

        Returns:
            DataFrame with indicator data including metadata.

        """
        logger.debug(
            "Fetching technical indicators",
            event="features_indicators_get_start",
            indicators=query.indicators,
            start=query.start,
            end=query.end,
            indicator_types=query.indicator_types,
        )

        # Query indicator data
        data_df = self._indicator_store.read(
            start_date=query.start,
            end_date=query.end,
            indicator_types=query.indicator_types,
        )

        if data_df.is_empty():
            return pl.DataFrame()

        # Enrich with metadata
        result = self._enrich_with_metadata(data_df)

        logger.debug(
            "Technical indicators fetched",
            event="features_indicators_get_complete",
            row_count=len(result),
        )

        return result

    def _enrich_with_metadata(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Enrich indicator data with metadata.

        Args:
            df: Indicator data DataFrame.

        Returns:
            Enriched DataFrame with metadata columns.

        """
        # Get unique indicator IDs
        indicator_ids = df["indicator_id"].unique().to_list()

        # Fetch metadata for all indicators
        metadata_rows: list[pl.DataFrame] = []
        for iid in indicator_ids:
            row = self._metadata_store.get_by_code(str(iid))
            if not row.is_empty():
                metadata_rows.append(row)

        if not metadata_rows:
            return df

        metadata_df: pl.DataFrame = pl.concat(metadata_rows)

        # Join metadata
        result = df.join(
            metadata_df.select(["code", "name", "type", "description"]),
            left_on="indicator_id",
            right_on="code",
            how="left",
        )

        return result

    def close(self) -> None:
        """Close the underlying stores."""
        # IndicatorStore uses Parquet, no close needed
        # MetadataStore uses SQLite, close it
        self._metadata_store.close()
```

**Step 4: Run test to verify it passes**

```bash
cd packages/datahub
pixi run -e dev pytest tests/unit/domains/features/test_feature_service.py -v
```

Expected: All tests pass

**Step 5: Commit**

```bash
git add src/ tests/
git commit -m "feat(features): implement FeatureService for unified queries"
```

---

## Phase 8: Factors Domain (with PIT support)

### Task 5: Create Factors Domain Directory Structure

**Files:**
- Create: `packages/datahub/src/ditto_datahub/domains/factors/__init__.py`
- Create: `packages/datahub/src/ditto_datahub/domains/factors/factor_store.py`
- Create: `packages/datahub/src/ditto_datahub/domains/factors/factor_metadata_store.py`
- Create: `packages/datahub/src/ditto_datahub/domains/factors/metadata.py`
- Create: `packages/datahub/src/ditto_datahub/domains/factors/factor_service.py`

**Step 1: Create factors/__init__.py**

```python
"""Factors domain - validated factor signals with PIT support."""

from ditto_datahub.domains.factors.factor_metadata_store import (
    FactorMetadataStore,
)
from ditto_datahub.domains.factors.factor_store import FactorStore
from ditto_datahub.domains.factors.factor_service import FactorQuery, FactorService

__all__ = [
    "FactorMetadataStore",
    "FactorStore",
    "FactorQuery",
    "FactorService",
]
```

**Step 2: Create factors/metadata.py**

```python
"""Metadata models for factors."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

# Factor class (data source category)
FactorClass = Literal["fundamental", "technical", "macro", "statistical"]

# Factor family (investment style)
FactorFamily = Literal["value", "momentum", "quality", "size", "volatility"]


@dataclass(frozen=True)
class FactorMetadata:
    """
    Factor metadata.

    Attributes:
        factor_id: Unique identifier (e.g., "factor_momentum_12m")
        name: Display name (e.g., "12-Month Momentum")
        class: Data source class
        family: Investment style family
        description: Human-readable description
        formula: Calculation formula
        pit_enabled: Whether PIT tracking is enabled
    """

    factor_id: str
    name: str
    class: FactorClass
    family: FactorFamily
    description: str
    formula: str
    pit_enabled: bool
    status: str = "active"


# Predefined factor classes
FACTOR_CLASS_FUNDAMENTAL = "fundamental"
FACTOR_CLASS_TECHNICAL = "technical"
FACTOR_CLASS_MACRO = "macro"
FACTOR_CLASS_STATISTICAL = "statistical"

# Predefined factor families
FACTOR_FAMILY_VALUE = "value"
FACTOR_FAMILY_MOMENTUM = "momentum"
FACTOR_FAMILY_QUALITY = "quality"
FACTOR_FAMILY_SIZE = "size"
FACTOR_FAMILY_VOLATILITY = "volatility"


__all__ = [
    "FactorMetadata",
    "FactorClass",
    "FactorFamily",
    "FACTOR_CLASS_FUNDAMENTAL",
    "FACTOR_CLASS_TECHNICAL",
    "FACTOR_CLASS_MACRO",
    "FACTOR_CLASS_STATISTICAL",
    "FACTOR_FAMILY_VALUE",
    "FACTOR_FAMILY_MOMENTUM",
    "FACTOR_FAMILY_QUALITY",
    "FACTOR_FAMILY_SIZE",
    "FACTOR_FAMILY_VOLATILITY",
]
```

**Step 3: Commit directory structure**

```bash
git add src/ditto_datahub/domains/factors/
git commit -m "feat(factors): add Factors domain directory structure"
```

---

### Task 6: Implement FactorMetadataStore

**Files:**
- Modify: `packages/datahub/src/ditto_datahub/domains/factors/factor_metadata_store.py`

**Step 1: Write the failing test**

Create: `packages/datahub/tests/unit/domains/factors/test_factor_metadata_store.py`

```python
"""Tests for FactorMetadataStore."""

from pathlib import Path

import polars as pl
import pytest

from ditto_datahub.domains.factors.factor_metadata_store import FactorMetadataStore
from ditto_datahub.stores.sqlite_client import SQLiteClient


@pytest.fixture
def temp_db_path(tmp_path: Path) -> Path:
    """Create temporary database path."""
    return tmp_path / "test_factors.sqlite"


@pytest.fixture
def sqlite_client(temp_db_path: Path) -> SQLiteClient:
    """Create SQLite client for testing."""
    client = SQLiteClient(str(temp_db_path))
    client.execute("""
        CREATE TABLE IF NOT EXISTS factors (
            factor_id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            class TEXT NOT NULL,
            family TEXT NOT NULL,
            description TEXT,
            formula TEXT,
            pit_enabled BOOLEAN NOT NULL DEFAULT 1,
            status TEXT NOT NULL DEFAULT 'active'
        )
    """)
    client.commit()
    return client


@pytest.fixture
def metadata_store(sqlite_client: SQLiteClient) -> FactorMetadataStore:
    """Create FactorMetadataStore for testing."""
    return FactorMetadataStore(sqlite_client)


def test_upsert_new_factor(metadata_store: FactorMetadataStore) -> None:
    """Test upserting a new factor."""
    factor_id = metadata_store.upsert(
        code="factor_momentum_12m",
        name="12-Month Momentum",
        class="technical",
        family="momentum",
        description="12-month cumulative return",
        formula="return_12m = price_today / price_252_ago - 1",
        pit_enabled=True,
    )

    assert factor_id > 0

    # Verify retrieval
    row = metadata_store.get_by_code("factor_momentum_12m")
    assert not row.is_empty()
    assert row["code"][0] == "factor_momentum_12m"
    assert row["name"][0] == "12-Month Momentum"
    assert row["class"][0] == "technical"
    assert row["pit_enabled"][0] is True


def test_list_by_family(metadata_store: FactorMetadataStore) -> None:
    """Test listing factors by family."""
    # Insert factors
    metadata_store.upsert(
        code="factor_momentum_12m",
        name="Momentum 12M",
        class="technical",
        family="momentum",
        description="",
        formula="",
        pit_enabled=True,
    )
    metadata_store.upsert(
        code="factor_momentum_1m",
        name="Momentum 1M",
        class="technical",
        family="momentum",
        description="",
        formula="",
        pit_enabled=True,
    )
    metadata_store.upsert(
        code="factor_value_pe",
        name="PE Value",
        class="fundamental",
        family="value",
        description="",
        formula="",
        pit_enabled=True,
    )

    # List momentum factors
    momentum_factors = metadata_store.list_by_family("momentum")
    assert len(momentum_factors) == 2
    assert set(momentum_factors["code"].to_list()) == {
        "factor_momentum_12m",
        "factor_momentum_1m",
    }
```

**Step 2: Run test to verify it fails**

```bash
cd packages/datahub
pixi run -e dev pytest tests/unit/domains/factors/test_factor_metadata_store.py -v
```

Expected: ModuleNotFoundError

**Step 3: Write minimal implementation**

Modify: `packages/datahub/src/ditto_datahub/domains/factors/factor_metadata_store.py`

```python
"""FactorMetadataStore for factor metadata management."""

from __future__ import annotations

from typing import Literal

import polars as pl
from ditto_foundation import logger, traced

from ditto_datahub.stores.sqlite_client import SQLiteClient


class FactorMetadataStore:
    """
    Factor metadata storage.

    Manages factor metadata including code, name, class,
    family, and PIT requirements.
    """

    # Valid factor classes
    CLASS_FUNDAMENTAL = "fundamental"
    CLASS_TECHNICAL = "technical"
    CLASS_MACRO = "macro"
    CLASS_STATISTICAL = "statistical"

    # Valid factor families
    FAMILY_VALUE = "value"
    FAMILY_MOMENTUM = "momentum"
    FAMILY_QUALITY = "quality"
    FAMILY_SIZE = "size"
    FAMILY_VOLATILITY = "volatility"

    def __init__(self, sqlite_client: SQLiteClient) -> None:
        """
        Initialize FactorMetadataStore.

        Args:
            sqlite_client: SQLite client for database operations.

        """
        self._client = sqlite_client
        self._init_table()

    def _init_table(self) -> None:
        """Initialize the factors table if not exists."""
        self._client.execute("""
            CREATE TABLE IF NOT EXISTS factors (
                factor_id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                class TEXT NOT NULL,
                family TEXT NOT NULL,
                description TEXT,
                formula TEXT,
                pit_enabled BOOLEAN NOT NULL DEFAULT 1,
                status TEXT NOT NULL DEFAULT 'active'
            )
        """)
        self._client.commit()

    @traced("data.metadata_write")
    def upsert(  # noqa: PLR0913
        self,
        code: str,
        name: str,
        class: Literal["fundamental", "technical", "macro", "statistical"],
        family: Literal["value", "momentum", "quality", "size", "volatility"],
        description: str,
        formula: str,
        pit_enabled: bool,
    ) -> int:
        """
        Register or update factor metadata.

        Args:
            code: Factor code (e.g., 'factor_momentum_12m').
            name: Factor display name.
            class: Factor class (fundamental, technical, macro, statistical).
            family: Factor family (value, momentum, quality, size, volatility).
            description: Description text.
            formula: Calculation formula.
            pit_enabled: Whether PIT tracking is enabled.

        Returns:
            factor_id

        Raises:
            Exception: If database operation fails.

        """
        logger.info(
            "Upserting factor metadata",
            code=code,
            name=name,
            class=class,
            family=family,
        )

        try:
            # Check if exists
            result = self._client.fetchone(
                """SELECT factor_id FROM factors WHERE code = ?""",
                [code],
            )
            if result is None:
                # Insert new
                sql = (
                    "INSERT INTO factors "
                    "(code, name, class, family, description, formula, pit_enabled) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)"
                )
                factor_id = self._client.insert_returning_id(
                    sql,
                    [code, name, class, family, description, formula, pit_enabled],
                )
            else:
                # Update existing
                factor_id = result["factor_id"]
                self._client.execute(
                    """UPDATE factors
                    SET name = ?, class = ?, family = ?, description = ?,
                        formula = ?, pit_enabled = ?
                    WHERE factor_id = ?""",
                    [name, class, family, description, formula, pit_enabled, factor_id],
                )
                self._client.commit()

            logger.info(
                "Factor metadata upserted successfully",
                factor_id=factor_id,
                code=code,
            )
            return factor_id

        except Exception as e:
            self._client.rollback()
            logger.error("Factor metadata upsert failed", error=str(e))
            raise

    @traced("data.metadata_query")
    def get_by_id(self, factor_id: int) -> pl.DataFrame:
        """
        Query factor metadata by ID.

        Args:
            factor_id: Factor ID.

        Returns:
            DataFrame with factor metadata, or empty DataFrame if not found.

        """
        logger.debug(
            "Querying factor metadata by ID",
            factor_id=factor_id,
        )

        rows = self._client.fetchall(
            """SELECT factor_id, code, name, class, family, description, formula, pit_enabled
               FROM factors
               WHERE factor_id = ?""",
            [factor_id],
        )

        return pl.DataFrame(rows) if rows else pl.DataFrame()

    @traced("data.metadata_query")
    def get_by_code(self, code: str) -> pl.DataFrame:
        """
        Query factor metadata by code.

        Args:
            code: Factor code.

        Returns:
            DataFrame with factor metadata, or empty DataFrame if not found.

        """
        logger.debug(
            "Querying factor metadata by code",
            code=code,
        )

        rows = self._client.fetchall(
            """SELECT factor_id, code, name, class, family, description, formula, pit_enabled
               FROM factors
               WHERE code = ?""",
            [code],
        )

        return pl.DataFrame(rows) if rows else pl.DataFrame()

    @traced("data.metadata_query")
    def list_by_family(self, family: str | None = None) -> pl.DataFrame:
        """
        List factors by family.

        Args:
            family: Family filter (None = all families).

        Returns:
            DataFrame with matching factors.

        """
        logger.debug(
            "Listing factors by family",
            family=family,
        )

        if family:
            rows = self._client.fetchall(
                """SELECT factor_id, code, name, class, family, description, formula, pit_enabled
                   FROM factors
                   WHERE family = ?
                   ORDER BY code""",
                [family],
            )
        else:
            rows = self._client.fetchall(
                """SELECT factor_id, code, name, class, family, description, formula, pit_enabled
                   FROM factors
                   ORDER BY code""",
            )

        return pl.DataFrame(rows) if rows else pl.DataFrame()

    def close(self) -> None:
        """Close the underlying SQLite client."""
        self._client.close()
```

**Step 4: Run test to verify it passes**

```bash
cd packages/datahub
pixi run -e dev pytest tests/unit/domains/factors/test_factor_metadata_store.py -v
```

**Step 5: Commit**

```bash
git add src/ tests/
git commit -m "feat(factors): implement FactorMetadataStore with tests"
```

---

### Task 7: Implement FactorStore (Parquet + PIT columns)

**Files:**
- Modify: `packages/datahub/src/ditto_datahub/domains/factors/factor_store.py`

**Step 1: Write the failing test**

Create: `packages/datahub/tests/unit/domains/factors/test_factor_store.py`

```python
"""Tests for FactorStore."""

from pathlib import Path

import polars as pl
import pytest

from ditto_datahub.domains.factors.factor_store import FactorStore


@pytest.fixture
def temp_data_root(tmp_path: Path) -> Path:
    """Create temporary data root."""
    return tmp_path / "factors" / "factors_narrow"


@pytest.fixture
def factor_store(temp_data_root: Path) -> FactorStore:
    """Create FactorStore for testing."""
    return FactorStore(temp_data_root)


def test_write_and_read_factor_data(factor_store: FactorStore) -> None:
    """Test writing and reading factor data."""
    # Prepare test data with PIT columns
    df = pl.DataFrame(
        {
            "sid": [1, 1, 2, 2],
            "trade_date": [
                "2024-01-02",
                "2024-01-03",
                "2024-01-02",
                "2024-01-03",
            ],
            "factor_id": ["factor_momentum_12m"] * 4,
            "factor_class": ["technical"] * 4,
            "factor_family": ["momentum"] * 4,
            "exposure": [0.5, 0.6, 0.3, 0.4],
            "raw_value": [0.15, 0.18, 0.08, 0.12],
            "effective_from": ["2024-01-02"] * 4,
            "effective_to": [None] * 4,
        }
    )

    # Write data
    result = factor_store.write(df, year=2024)
    assert result.added == 4

    # Read data back
    result_df = factor_store.read(
        start_date="2024-01-01",
        end_date="2024-01-31",
    )

    assert len(result_df) == 4
    assert "sid" in result_df.columns
    assert "trade_date" in result_df.columns
    assert "factor_id" in result_df.columns
    assert "exposure" in result_df.columns
    assert "effective_from" in result_df.columns
    assert "effective_to" in result_df.columns


def test_read_with_as_of_date_pit_query(factor_store: FactorStore) -> None:
    """Test PIT query with as_of_date parameter."""
    # Write initial data
    df_v1 = pl.DataFrame(
        {
            "sid": [1, 1],
            "trade_date": ["2024-01-02", "2024-01-03"],
            "factor_id": ["factor_momentum_12m"] * 2,
            "factor_class": ["technical"] * 2,
            "factor_family": ["momentum"] * 2,
            "exposure": [0.5, 0.6],
            "raw_value": [0.15, 0.18],
            "effective_from": ["2024-01-02"] * 2,
            "effective_to": ["2024-01-10"] * 2,  # Version 1 valid until 1/10
        }
    )

    # Write revised data
    df_v2 = pl.DataFrame(
        {
            "sid": [1, 1],
            "trade_date": ["2024-01-02", "2024-01-03"],
            "factor_id": ["factor_momentum_12m"] * 2,
            "factor_class": ["technical"] * 2,
            "factor_family": ["momentum"] * 2,
            "exposure": [0.55, 0.65],  # Revised values
            "raw_value": [0.16, 0.19],
            "effective_from": ["2024-01-10"] * 2,  # Version 2 starts 1/10
            "effective_to": [None] * 2,  # Current version
        }
    )

    # Combine and write (simulating two versions of same data)
    df_combined = pl.concat([df_v1, df_v2])
    factor_store.write(df_combined, year=2024)

    # Query as of 2024-01-05 (should get version 1)
    result_v1 = factor_store.read(
        start_date="2024-01-01",
        end_date="2024-01-31",
        as_of_date="2024-01-05",
    )

    assert len(result_v1) == 2
    # Should get version 1 values
    assert result_v1.filter(pl.col("trade_date") == pl.date(2024, 1, 2))["exposure"][0] == 0.5

    # Query as of 2024-01-15 (should get version 2)
    result_v2 = factor_store.read(
        start_date="2024-01-01",
        end_date="2024-01-31",
        as_of_date="2024-01-15",
    )

    assert len(result_v2) == 2
    # Should get version 2 values
    assert result_v2.filter(pl.col("trade_date") == pl.date(2024, 1, 2))["exposure"][0] == 0.55
```

**Step 2: Run test to verify it fails**

```bash
cd packages/datahub
pixi run -e dev pytest tests/unit/domains/factors/test_factor_store.py -v
```

Expected: ModuleNotFoundError or method not found

**Step 3: Write minimal implementation**

Modify: `packages/datahub/src/ditto_datahub/domains/factors/factor_store.py`

```python
"""FactorStore for factor data storage with PIT support."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import polars as pl
from ditto_foundation import logger, traced
from ditto_foundation.util.io import atomic_write, file_md5

from ditto_datahub.models import OnDuplicate
from ditto_datahub.models.storage import WriteResultStore as WriteResult
from ditto_datahub.stores.parquet_store_base import ParquetStoreBase


class FactorStore(ParquetStoreBase):
    """
    Factor data storage with year partitioning and PIT support.

    Stores factor values in Parquet files organized by year.
    Includes effective_from/effective_to columns for Point-in-Time queries.

    Storage structure:
        data_root/factors/factors_narrow/
            2020.parquet
            2021.parquet
            ...

    Schema:
        sid: Security ID
        trade_date: Trading date
        factor_id: Factor identifier (e.g., 'factor_momentum_12m')
        factor_class: Class category (fundamental/technical/macro/statistical)
        factor_family: Investment style family (value/momentum/quality/size/volatility)
        exposure: Factor exposure (standardized value)
        raw_value: Raw factor value (unstandardized)
        effective_from: Date when this version becomes effective
        effective_to: Date when this version stops being effective (NULL = current)
    """

    def __init__(self, data_root: Path) -> None:
        """
        Initialize FactorStore.

        Args:
            data_root: Root directory for data storage.

        """
        super().__init__(data_root)
        self._dataset = "factors/factors_narrow"

    def _get_dataset(self) -> str:
        """Return dataset name for factors."""
        return "factors/factors_narrow"

    def _get_key_columns(self) -> list[str]:
        """
        Return key column names for deduplication.

        For PIT data, the key includes effective_from to allow
        multiple versions of the same factor value.
        """
        return ["sid", "trade_date", "factor_id", "effective_from"]

    @traced("data.factor_write")
    def write(
        self,
        df: pl.DataFrame,
        year: int,
        on_duplicate: OnDuplicate = OnDuplicate.ERROR,
    ) -> WriteResult:
        """
        Write factor data.

        Args:
            df: DataFrame with columns:
                - sid (int)
                - trade_date (date or str YYYY-MM-DD)
                - factor_id (str)
                - factor_class (str)
                - factor_family (str)
                - exposure (float)
                - raw_value (float, optional)
                - effective_from (date or str YYYY-MM-DD)
                - effective_to (date or str YYYY-MM-DD, optional)
            year: Year partition for writing.
            on_duplicate: How to handle duplicates.

        Returns:
            Write result with statistics.

        Raises:
            ValueError: If required columns are missing.

        """
        logger.info(
            "Starting factor data write",
            record_count=len(df),
            year=year,
        )

        # Validate required columns
        required = ["sid", "trade_date", "factor_id", "factor_class", "factor_family", "exposure", "effective_from"]
        missing = [col for col in required if col not in df.columns]
        if missing:
            msg = f"Missing required columns: {missing}"
            raise ValueError(msg)

        # Use parent class write implementation
        result = super().write(df, year=year, on_duplicate=on_duplicate)

        logger.info(
            "Factor data written successfully",
            record_count=len(df),
            year=year,
            added=result.added,
            updated=result.updated,
        )

        return result

    @traced("data.factor_query")
    def read(
        self,
        sids: list[int] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        as_of_date: str | None = None,
    ) -> pl.DataFrame:
        """
        Query factor data (PIT-safe).

        Args:
            sids: Filter by security IDs (None = all).
            start_date: Start date (YYYY-MM-DD).
            end_date: End date (YYYY-MM-DD).
            as_of_date: PIT query date - only return data effective as of this date.

        Returns:
            DataFrame with factor data.

        """
        logger.debug(
            "Querying factor data",
            sids=sids,
            start_date=start_date,
            end_date=end_date,
            as_of_date=as_of_date,
        )

        # Use parent class read
        df = super().read(sids=sids, start_date=start_date, end_date=end_date)

        if df.is_empty():
            return pl.DataFrame()

        # Apply PIT filtering if as_of_date is specified
        if as_of_date:
            as_of_dt = datetime.strptime(as_of_date, "%Y-%m-%d").date()
            df = df.filter(
                (pl.col("effective_from") <= pl.lit(as_of_dt))
                & (
                    (pl.col("effective_to").is_null())
                    | (pl.col("effective_to") > pl.lit(as_of_dt))
                )
            )
            # For each (sid, trade_date, factor_id), keep only the latest version
            # (the one with the most recent effective_from)
            df = df.sort(
                ["sid", "trade_date", "factor_id", "effective_from"],
                descending=[False, False, False, True],
            ).unique(
                subset=["sid", "trade_date", "factor_id"],
                keep="first",
            )
            df = df.sort(["sid", "trade_date", "factor_id"])

        return df

    def _get_sort_columns(self) -> list[str]:
        """Return sort columns."""
        return ["sid", "trade_date", "factor_id", "effective_from"]
```

**Step 4: Run test to verify it passes**

```bash
cd packages/datahub
pixi run -e dev pytest tests/unit/domains/factors/test_factor_store.py -v
```

Expected: All tests pass

**Step 5: Commit**

```bash
git add src/ tests/
git commit -m "feat(factors): implement FactorStore with Parquet + PIT support"
```

---

### Task 8: Implement FactorService

**Files:**
- Modify: `packages/datahub/src/ditto_datahub/domains/factors/factor_service.py`

**Step 1: Write the failing test**

Create: `packages/datahub/tests/unit/domains/factors/test_factor_service.py`

```python
"""Tests for FactorService."""

from pathlib import Path

import polars as pl
import pytest

from ditto_datahub.domains.factors.factor_service import FactorQuery, FactorService
from ditto_datahub.domains.factors.factor_metadata_store import FactorMetadataStore
from ditto_datahub.domains.factors.factor_store import FactorStore
from ditto_datahub.stores.sqlite_client import SQLiteClient


@pytest.fixture
def temp_data_root(tmp_path: Path) -> Path:
    """Create temporary data root."""
    return tmp_path / "factors"


@pytest.fixture
def sqlite_client(temp_data_root: Path) -> SQLiteClient:
    """Create SQLite client for metadata."""
    db_path = temp_data_root / "metadata.sqlite"
    client = SQLiteClient(str(db_path))
    return client


@pytest.fixture
def factor_service(
    temp_data_root: Path,
    sqlite_client: SQLiteClient,
) -> FactorService:
    """Create FactorService for testing."""
    factor_store = FactorStore(temp_data_root / "factors_narrow")
    metadata_store = FactorMetadataStore(sqlite_client)
    return FactorService(factor_store, metadata_store)


def test_get_factors_enriches_with_metadata(factor_service: FactorService) -> None:
    """Test that get_factors enriches data with metadata."""
    # Setup: Register factor metadata
    factor_service._metadata_store.upsert(
        code="factor_momentum_12m",
        name="12-Month Momentum",
        class="technical",
        family="momentum",
        description="12-month cumulative return",
        formula="return_12m = price_today / price_252_ago - 1",
        pit_enabled=True,
    )

    # Setup: Write factor data
    df = pl.DataFrame(
        {
            "sid": [1, 1],
            "trade_date": ["2024-01-02", "2024-01-03"],
            "factor_id": ["factor_momentum_12m"] * 2,
            "factor_class": ["technical"] * 2,
            "factor_family": ["momentum"] * 2,
            "exposure": [0.5, 0.6],
            "raw_value": [0.15, 0.18],
            "effective_from": ["2024-01-02"] * 2,
            "effective_to": [None] * 2,
        }
    )
    factor_service._factor_store.write(df, year=2024)

    # Execute: Query factors
    query = FactorQuery(
        factors=["factor_momentum_12m"],
        start="2024-01-01",
        end="2024-01-31",
    )
    result = factor_service.get_factors(query)

    # Verify: Result includes metadata columns
    assert not result.is_empty()
    assert "factor_id" in result.columns
    assert "exposure" in result.columns
    # Metadata should be joined
    assert "name" in result.columns or "code" in result.columns


def test_get_factors_with_pit_query(factor_service: FactorService) -> None:
    """Test PIT query functionality."""
    # Register factor
    factor_service._metadata_store.upsert(
        code="factor_momentum_12m",
        name="12-Month Momentum",
        class="technical",
        family="momentum",
        description="",
        formula="",
        pit_enabled=True,
    )

    # Write version 1
    df_v1 = pl.DataFrame(
        {
            "sid": [1],
            "trade_date": ["2024-01-02"],
            "factor_id": ["factor_momentum_12m"],
            "factor_class": ["technical"],
            "factor_family": ["momentum"],
            "exposure": [0.5],
            "raw_value": [0.15],
            "effective_from": ["2024-01-02"],
            "effective_to": ["2024-01-10"],
        }
    )

    # Write version 2 (revised)
    df_v2 = pl.DataFrame(
        {
            "sid": [1],
            "trade_date": ["2024-01-02"],
            "factor_id": ["factor_momentum_12m"],
            "factor_class": ["technical"],
            "factor_family": ["momentum"],
            "exposure": [0.55],  # Revised
            "raw_value": [0.16],
            "effective_from": ["2024-01-10"],
            "effective_to": [None],
        }
    )

    factor_service._factor_store.write(pl.concat([df_v1, df_v2]), year=2024)

    # Query with as_of_date before revision
    query_v1 = FactorQuery(
        start="2024-01-01",
        end="2024-01-31",
        as_of="2024-01-05",
    )
    result_v1 = factor_service.get_factors(query_v1)

    assert len(result_v1) == 1
    assert result_v1["exposure"][0] == 0.5

    # Query with as_of_date after revision
    query_v2 = FactorQuery(
        start="2024-01-01",
        end="2024-01-31",
        as_of="2024-01-15",
    )
    result_v2 = factor_service.get_factors(query_v2)

    assert len(result_v2) == 1
    assert result_v2["exposure"][0] == 0.55
```

**Step 2: Run test to verify it fails**

```bash
cd packages/datahub
pixi run -e dev pytest tests/unit/domains/factors/test_factor_service.py -v
```

Expected: ModuleNotFoundError

**Step 3: Write minimal implementation**

Modify: `packages/datahub/src/ditto_datahub/domains/factors/factor_service.py`

```python
"""FactorService - Factors domain unified query service."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import polars as pl
from ditto_foundation import logger, traced

from ditto_datahub.domains.factors.factor_store import FactorStore
from ditto_datahub.domains.factors.factor_metadata_store import FactorMetadataStore


@dataclass(frozen=True)
class FactorQuery:
    """
    Factor query parameters.

    Attributes:
        factors: Factor IDs or codes (None = all).
        start: Start date (YYYY-MM-DD).
        end: End date (YYYY-MM-DD).
        as_of: PIT query date - only return data known as of this date.
        factor_classes: Filter by factor class.
        factor_families: Filter by factor family.
    """

    factors: list[int] | list[str] | None = None
    start: str | None = None
    end: str | None = None
    as_of: str | None = None
    factor_classes: (
        list[Literal["fundamental", "technical", "macro", "statistical"]] | None
    ) = None
    factor_families: (
        list[Literal["value", "momentum", "quality", "size", "volatility"]] | None
    ) = None


class FactorService:
    """
    Factors domain unified query service.

    Provides high-level query API for factor data with PIT support,
    integrating FactorStore and FactorMetadataStore.
    """

    def __init__(
        self,
        factor_store: FactorStore,
        metadata_store: FactorMetadataStore,
    ) -> None:
        """
        Initialize FactorService.

        Args:
            factor_store: Factor data storage.
            metadata_store: Factor metadata storage.

        """
        self._factor_store = factor_store
        self._metadata_store = metadata_store

        logger.debug(
            "FactorService initialized",
            event="factor_service_init_complete",
        )

    @traced("factors.get_factors")
    def get_factors(self, query: FactorQuery) -> pl.DataFrame:
        """
        Query factor data (PIT-safe).

        Args:
            query: FactorQuery object with query parameters.

        Returns:
            DataFrame with factor data including metadata.

        """
        logger.debug(
            "Fetching factors",
            event="factors_get_start",
            factors=query.factors,
            start=query.start,
            end=query.end,
            as_of=query.as_of,
            factor_classes=query.factor_classes,
            factor_families=query.factor_families,
        )

        # Query factor data
        data_df = self._factor_store.read(
            start_date=query.start,
            end_date=query.end,
            as_of_date=query.as_of,
        )

        if data_df.is_empty():
            return pl.DataFrame()

        # Apply class/family filters
        if query.factor_classes:
            data_df = data_df.filter(pl.col("factor_class").is_in(query.factor_classes))
        if query.factor_families:
            data_df = data_df.filter(pl.col("factor_family").is_in(query.factor_families))

        # Enrich with metadata
        result = self._enrich_with_metadata(data_df)

        logger.debug(
            "Factors fetched",
            event="factors_get_complete",
            row_count=len(result),
        )

        return result

    def _enrich_with_metadata(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Enrich factor data with metadata.

        Args:
            df: Factor data DataFrame.

        Returns:
            Enriched DataFrame with metadata columns.

        """
        # Get unique factor IDs
        factor_ids = df["factor_id"].unique().to_list()

        # Fetch metadata for all factors
        metadata_rows: list[pl.DataFrame] = []
        for fid in factor_ids:
            row = self._metadata_store.get_by_code(str(fid))
            if not row.is_empty():
                metadata_rows.append(row)

        if not metadata_rows:
            return df

        metadata_df: pl.DataFrame = pl.concat(metadata_rows)

        # Join metadata
        result = df.join(
            metadata_df.select(["code", "name", "class", "family", "description"]),
            left_on="factor_id",
            right_on="code",
            how="left",
        )

        return result

    def close(self) -> None:
        """Close the underlying stores."""
        # FactorStore uses Parquet, no close needed
        # MetadataStore uses SQLite, close it
        self._metadata_store.close()
```

**Step 4: Run test to verify it passes**

```bash
cd packages/datahub
pixi run -e dev pytest tests/unit/domains/factors/test_factor_service.py -v
```

Expected: All tests pass

**Step 5: Commit**

```bash
git add src/ tests/
git commit -m "feat(factors): implement FactorService with PIT query support"
```

---

## Integration Tasks

### Task 9: Update DataRootConfig for Features/Factors Paths

**Files:**
- Modify: `packages/datahub/src/ditto_datahub/config/data_root.py`

**Step 1: Update data_root.py**

Add to the existing properties (after line 165):

```python
    # ========== 特征路径 (扩展) ==========

    @property
    def features_technical_indicators_narrow_path(self) -> Path:
        """技术指标窄表路径."""
        return self.data_root / "features" / "technical" / "indicators_narrow"

    @property
    def features_technical_indicators_wide_path(self) -> Path:
        """技术指标宽表路径."""
        return self.data_root / "features" / "technical" / "indicators_wide"

    # ========== 因子路径 (更新) ==========

    @property
    def factors_narrow_path(self) -> Path:
        """因子窄表路径."""
        return self.data_root / "factors" / "factors_narrow"

    @property
    def factors_wide_path(self) -> Path:
        """因子宽表路径."""
        return self.data_root / "factors" / "factors_wide"
```

**Step 2: Run type check**

```bash
cd packages/datahub
pixi run -e dev type
```

Expected: No errors

**Step 3: Commit**

```bash
git add src/ditto_datahub/config/data_root.py
git commit -m "feat(config): add Features and Factors paths to DataRootConfig"
```

---

### Task 10: Register Features/Factors in DataHub

**Files:**
- Modify: `packages/datahub/src/ditto_datahub/hub.py`
- Modify: `apps/port/src/ditto_port/registry/datahub.py`

**Step 1: Update hub.py imports**

Add to imports (around line 25):

```python
from ditto_datahub.domains.features import FeatureService
from ditto_datahub.domains.features.technical.indicator_store import (
    IndicatorStore as FeatureIndicatorStore,
)
from ditto_datahub.domains.features.technical.indicator_metadata_store import (
    IndicatorMetadataStore as FeatureIndicatorMetadataStore,
)
from ditto_datahub.domains.factors import FactorService
from ditto_datahub.domains.factors.factor_store import FactorStore
from ditto_datahub.domains.factors.factor_metadata_store import (
    FactorMetadataStore,
)
```

**Step 2: Update hub.py __init__ parameters**

Add to `__init__` parameters (after `macro_query_service`):

```python
features_query_service: FeatureService,
factors_query_service: FactorService,
```

**Step 3: Update hub.py assignments**

Add to `__init__` body (after `self.macro = macro_query_service`):

```python
self.features = features_query_service
self.factors = factors_query_service
```

**Step 4: Update port/datahub.py providers**

Add providers (after macro_query_service provider):

```python
@provide
def feature_indicator_store(
    self,
    data_root_config: DataRootConfig,
) -> FeatureIndicatorStore:
    """Feature technical indicator storage."""
    return FeatureIndicatorStore(
        data_root_config.features_technical_indicators_narrow_path
    )

@provide
def feature_indicator_metadata_store(
    self,
    sqlite_client: SQLiteClient,
) -> FeatureIndicatorMetadataStore:
    """Feature indicator metadata storage."""
    return FeatureIndicatorMetadataStore(sqlite_client)

@provide
def features_query_service(
    self,
    feature_indicator_store: FeatureIndicatorStore,
    feature_indicator_metadata_store: FeatureIndicatorMetadataStore,
) -> FeatureService:
    """Features 查询服务."""
    return FeatureService(
        indicator_store=feature_indicator_store,
        metadata_store=feature_indicator_metadata_store,
    )

@provide
def factor_store(
    self,
    data_root_config: DataRootConfig,
) -> FactorStore:
    """Factor data storage."""
    return FactorStore(data_root_config.factors_narrow_path)

@provide
def factor_metadata_store(
    self,
    sqlite_client: SQLiteClient,
) -> FactorMetadataStore:
    """Factor metadata storage."""
    return FactorMetadataStore(sqlite_client)

@provide
def factors_query_service(
    self,
    factor_store: FactorStore,
    factor_metadata_store: FactorMetadataStore,
) -> FactorService:
    """Factors 查询服务."""
    return FactorService(
        factor_store=factor_store,
        metadata_store=factor_metadata_store,
    )
```

**Step 5: Update hub provider**

Add to DataHubProvider.provide_hub parameters (after `macro_query_service`):

```python
features_query_service: FeatureService,
factors_query_service: FactorService,
```

Add to provide_hub body (after `macro_query_service=macro_query_service`):

```python
features_query_service=features_query_service,
factors_query_service=factors_query_service,
```

**Step 6: Run type check**

```bash
cd packages/datahub
pixi run -e dev type
```

**Step 7: Commit**

```bash
git add src/ditto_datahub/hub.py apps/port/src/ditto_port/registry/datahub.py
git commit -m "feat(datahub): register Features and Factors services in DataHub"
```

---

### Task 11: Update Unit Tests

**Files:**
- Modify: `packages/datahub/tests/unit/test_hub_unit.py`

**Step 1: Add imports**

Add after macro imports:

```python
from ditto_datahub.domains.features import FeatureService
from ditto_datahub.domains.features.technical.indicator_store import (
    IndicatorStore as FeatureIndicatorStore,
)
from ditto_datahub.domains.features.technical.indicator_metadata_store import (
    IndicatorMetadataStore as FeatureIndicatorMetadataStore,
)
from ditto_datahub.domains.factors import FactorService
from ditto_datahub.domains.factors.factor_store import FactorStore
from ditto_datahub.domains.factors.factor_metadata_store import (
    FactorMetadataStore,
)
```

**Step 2: Add fixture creation**

Add after macro_query_service fixture:

```python
# Features Domain Stores
feature_indicator_store = FeatureIndicatorStore(
    tmp_path / "features" / "technical" / "indicators_narrow"
)
feature_indicator_metadata_store = FeatureIndicatorMetadataStore(sqlite_client)

# Features Query Service
features_query_service = FeatureService(
    indicator_store=feature_indicator_store,
    metadata_store=feature_indicator_metadata_store,
)

# Factors Domain Stores
factor_store = FactorStore(tmp_path / "factors" / "factors_narrow")
factor_metadata_store = FactorMetadataStore(sqlite_client)

# Factors Query Service
factors_query_service = FactorService(
    factor_store=factor_store,
    metadata_store=factor_metadata_store,
)
```

**Step 3: Update datahub_with_dependencies fixture**

Add to parameters (after `macro_query_service`):

```python
features_query_service=features_query_service,
factors_query_service=factors_query_service,
```

Add to body (after `macro_query_service=macro_query_service`):

```python
features_query_service=features_query_service,
factors_query_service=factors_query_service,
```

**Step 4: Run tests**

```bash
cd packages/datahub
pixi run -e dev pytest tests/unit/test_hub_unit.py -v
```

**Step 5: Commit**

```bash
git add tests/unit/test_hub_unit.py
git commit -m "test(datahub): add Features and Factors to unit tests"
```

---

## Verification Tasks

### Task 12: Run Full Test Suite

**Step 1: Run all new tests**

```bash
cd packages/datahub
pixi run -e dev pytest tests/unit/domains/features/ tests/unit/domains/factors/ -v
```

Expected: All tests pass

**Step 2: Run type check**

```bash
pixi run -e dev type
```

Expected: No errors

**Step 3: Run lint**

```bash
pixi run -e dev lint
```

Expected: No errors

**Step 4: Run fast tests**

```bash
pixi run -e dev test --fast
```

Expected: All tests pass

**Step 5: Commit final verification**

```bash
git add .
git commit -m "test: verify Features and Factors domain implementation"
```

---

## Task Summary

| Task | Component | Lines of Code | Tests |
|------|-----------|---------------|-------|
| 1 | Directory structure | ~20 | 0 |
| 2 | IndicatorMetadataStore | ~150 | 15 |
| 3 | IndicatorStore | ~150 | 15 |
| 4 | FeatureService | ~100 | 12 |
| 5 | Factors directory | ~20 | 0 |
| 6 | FactorMetadataStore | ~150 | 10 |
| 7 | FactorStore | ~200 | 15 |
| 8 | FactorService | ~120 | 15 |
| 9 | DataRootConfig updates | ~20 | 0 |
| 10 | DataHub integration | ~50 | 0 |
| 11 | Unit test updates | ~30 | 0 |
| 12 | Verification | 0 | 0 |

**Total:** ~1010 lines of code, ~82 tests

---

## Notes for Implementation

1. **Follow TDD strictly**: Each test must fail before implementation
2. **Commit frequently**: After each task, not after the whole plan
3. **Type check first**: Run `pixi run -e dev type` before committing
4. **Pattern consistency**: Follow existing Macro Domain patterns for metadata, Market Domain for Parquet storage
5. **PIT implementation**: Factors use Parquet with effective_from/effective_to columns (not SQLite window functions)
6. **No API layer**: Focus on DataHub internal implementation only

---

**Plan completed and saved to `docs/plans/2026-02-01-features-factors-implementation.md`.**

Two execution options:

**1. Subagent-Driven (this session)** - I dispatch fresh subagent per task, review between tasks, fast iteration

**2. Parallel Session (separate)** - Open new session with executing-plans, batch execution with checkpoints

Which approach?
