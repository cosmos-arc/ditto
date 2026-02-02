"""Tests for FactorMetadataStore."""

from pathlib import Path

import pytest
from ditto_datahub.domains.factors.factor_metadata_store import FactorMetadataStore
from ditto_datahub.stores.sqlite_client import SQLiteClient
from ditto_foundation import SQLitePool


@pytest.fixture
def temp_db_path(tmp_path: Path) -> Path:
    """Create temporary database path."""
    return tmp_path / "test_factors.sqlite"


@pytest.fixture
def sqlite_client(temp_db_path: Path) -> SQLiteClient:
    """Create SQLite client for testing."""
    pool = SQLitePool(str(temp_db_path))
    client = SQLiteClient(pool)
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
        factor_class="technical",
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
    assert row["pit_enabled"][0] == True  # noqa: E712 - SQLite returns 1/0 as int


def test_list_by_family(metadata_store: FactorMetadataStore) -> None:
    """Test listing factors by family."""
    # Insert factors
    metadata_store.upsert(
        code="factor_momentum_12m",
        name="Momentum 12M",
        factor_class="technical",
        family="momentum",
        description="",
        formula="",
        pit_enabled=True,
    )
    metadata_store.upsert(
        code="factor_momentum_1m",
        name="Momentum 1M",
        factor_class="technical",
        family="momentum",
        description="",
        formula="",
        pit_enabled=True,
    )
    metadata_store.upsert(
        code="factor_value_pe",
        name="PE Value",
        factor_class="fundamental",
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
