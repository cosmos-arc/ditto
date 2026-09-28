"""Pytest configuration for Execution tests."""

from collections.abc import Generator

import pytest
from ditto_platform.foundation import (
    Environment,
    ObservabilityConfig,
    SQLiteClient,
    SQLitePool,
    init,
    reset_for_testing,
)


@pytest.fixture(autouse=True)
def init_observability() -> Generator[None]:
    """Initialize observability in testing mode, restored after each test.

    The teardown reset mirrors the data package: shared-process entries must
    not leak an initialized global registry into other owners' tests
    (#330 B1).
    """
    config = ObservabilityConfig(
        environment=Environment.TESTING,
        pytest_running=True,
        assertions_enabled=False,
        verbose_logging=False,
        tracing_enabled=False,
        metrics_enabled=False,
    )
    init(config, force=True)
    yield
    reset_for_testing()


@pytest.fixture
def sqlite_pool() -> Generator[SQLitePool]:
    """Create an in-memory SQLite pool for testing."""
    pool = SQLitePool(":memory:")
    yield pool
    pool.close()


@pytest.fixture
def sqlite_client(sqlite_pool: SQLitePool) -> SQLiteClient:
    """Create SQLite client for testing."""
    return SQLiteClient(sqlite_pool)
