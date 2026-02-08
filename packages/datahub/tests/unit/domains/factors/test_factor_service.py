"""Tests for FactorService."""

from pathlib import Path

import polars as pl
import pytest
from ditto_datahub.domains.factors.factor_metadata_store import FactorMetadataStore
from ditto_datahub.domains.factors.factor_service import FactorQuery, FactorService
from ditto_datahub.domains.factors.factor_store import FactorStore
from ditto_datahub.stores.sqlite_client import SQLiteClient
from ditto_foundation import SQLitePool


@pytest.fixture
def temp_data_root(tmp_path: Path) -> Path:
    """Create temporary data root."""
    return tmp_path / "factors"


@pytest.fixture
def sqlite_client(temp_data_root: Path) -> SQLiteClient:
    """Create SQLite client for metadata."""
    db_path = temp_data_root / "metadata.sqlite"
    # Ensure parent directory exists
    db_path.parent.mkdir(parents=True, exist_ok=True)
    pool = SQLitePool(str(db_path))
    return SQLiteClient(pool)


@pytest.fixture
def factor_service(
    temp_data_root: Path,
    sqlite_client: SQLiteClient,
) -> FactorService:
    """Create FactorService for testing."""
    factor_store = FactorStore(temp_data_root)
    metadata_store = FactorMetadataStore(sqlite_client)
    return FactorService(factor_store, metadata_store)


def test_get_factors_enriches_with_metadata(factor_service: FactorService) -> None:
    """Test that get_factors enriches data with metadata."""
    # Setup: Register factor metadata
    factor_service._metadata_store.upsert(
        code="factor_momentum_12m",
        name="12-Month Momentum",
        factor_class="technical",
        family="momentum",
        description="12-month cumulative return",
        formula="return_12m = price_today / price_252_ago - 1",
        pit_enabled=True,
    )

    # Setup: Write factor data
    df = pl.DataFrame(
        {
            "instrument_id": [1, 1],
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
    result = factor_service.query(query)

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
        factor_class="technical",
        family="momentum",
        description="",
        formula="",
        pit_enabled=True,
    )

    # Write version 1
    df_v1 = pl.DataFrame(
        {
            "instrument_id": [1],
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
            "instrument_id": [1],
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
    result_v1 = factor_service.query(query_v1)

    assert len(result_v1) == 1
    assert result_v1["exposure"][0] == 0.5

    # Query with as_of_date after revision
    query_v2 = FactorQuery(
        start="2024-01-01",
        end="2024-01-31",
        as_of="2024-01-15",
    )
    result_v2 = factor_service.query(query_v2)

    assert len(result_v2) == 1
    assert result_v2["exposure"][0] == 0.55


def test_get_factors_with_class_filter(factor_service: FactorService) -> None:
    """Test filtering by factor class."""
    # Register factors from different classes
    factor_service._metadata_store.upsert(
        code="factor_momentum_12m",
        name="12-Month Momentum",
        factor_class="technical",
        family="momentum",
        description="",
        formula="",
        pit_enabled=True,
    )
    factor_service._metadata_store.upsert(
        code="factor_value_pe",
        name="PE Value",
        factor_class="fundamental",
        family="value",
        description="",
        formula="",
        pit_enabled=True,
    )

    # Write mixed data
    df = pl.DataFrame(
        {
            "instrument_id": [1, 1, 2, 2],
            "trade_date": ["2024-01-02"] * 4,
            "factor_id": [
                "factor_momentum_12m",
                "factor_value_pe",
                "factor_momentum_12m",
                "factor_value_pe",
            ],
            "factor_class": ["technical", "fundamental", "technical", "fundamental"],
            "factor_family": ["momentum", "value", "momentum", "value"],
            "exposure": [0.5, 0.3, 0.4, 0.2],
            "raw_value": [0.15, 0.08, 0.12, 0.05],
            "effective_from": ["2024-01-02"] * 4,
            "effective_to": [None] * 4,
        }
    )
    factor_service._factor_store.write(df, year=2024)

    # Query for technical class only
    query = FactorQuery(
        start="2024-01-01",
        end="2024-01-31",
        factor_classes=["technical"],
    )
    result = factor_service.query(query)

    assert len(result) == 2
    assert result["factor_class"].to_list() == ["technical", "technical"]


def test_get_factors_with_family_filter(factor_service: FactorService) -> None:
    """Test filtering by factor family."""
    # Register factors from different families
    factor_service._metadata_store.upsert(
        code="factor_momentum_12m",
        name="Momentum 12M",
        factor_class="technical",
        family="momentum",
        description="",
        formula="",
        pit_enabled=True,
    )
    factor_service._metadata_store.upsert(
        code="factor_value_pe",
        name="PE Value",
        factor_class="fundamental",
        family="value",
        description="",
        formula="",
        pit_enabled=True,
    )

    # Write mixed data
    df = pl.DataFrame(
        {
            "instrument_id": [1, 1, 2, 2],
            "trade_date": ["2024-01-02"] * 4,
            "factor_id": [
                "factor_momentum_12m",
                "factor_value_pe",
                "factor_momentum_12m",
                "factor_value_pe",
            ],
            "factor_class": ["technical", "fundamental", "technical", "fundamental"],
            "factor_family": ["momentum", "value", "momentum", "value"],
            "exposure": [0.5, 0.3, 0.4, 0.2],
            "raw_value": [0.15, 0.08, 0.12, 0.05],
            "effective_from": ["2024-01-02"] * 4,
            "effective_to": [None] * 4,
        }
    )
    factor_service._factor_store.write(df, year=2024)

    # Query for momentum family only
    query = FactorQuery(
        start="2024-01-01",
        end="2024-01-31",
        factor_families=["momentum"],
    )
    result = factor_service.query(query)

    assert len(result) == 2
    assert result["factor_family"].to_list() == ["momentum", "momentum"]


def test_get_factors_empty_store(factor_service: FactorService) -> None:
    """Test querying when no data exists."""
    query = FactorQuery(
        start="2024-01-01",
        end="2024-01-31",
    )
    result = factor_service.query(query)

    assert result.is_empty()


def test_get_factors_no_metadata(factor_service: FactorService) -> None:
    """Test behavior when metadata is missing."""
    # Write factor data without registering metadata
    df = pl.DataFrame(
        {
            "instrument_id": [1],
            "trade_date": ["2024-01-02"],
            "factor_id": ["factor_momentum_12m"],
            "factor_class": ["technical"],
            "factor_family": ["momentum"],
            "exposure": [0.5],
            "raw_value": [0.15],
            "effective_from": ["2024-01-02"],
            "effective_to": [None],
        }
    )
    factor_service._factor_store.write(df, year=2024)

    # Query should still return data, but without enrichment
    query = FactorQuery(
        start="2024-01-01",
        end="2024-01-31",
    )
    result = factor_service.query(query)

    assert not result.is_empty()
    # Data columns should be present
    assert "instrument_id" in result.columns
    assert "factor_id" in result.columns
    assert "exposure" in result.columns


def test_close_service(factor_service: FactorService) -> None:
    """Test closing the service."""
    # Should not raise any exception
    factor_service.close()
