"""Pytest configuration for Execution tests."""

from collections.abc import Generator
from pathlib import Path

import pytest
from ditto_execution.storage.sqlite_client import SQLiteClient
from ditto_platform.foundation import SQLitePool, init
from ditto_platform.foundation.config.environment import Environment
from ditto_platform.foundation.observability.config import ObservabilityConfig


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Auto-mark tests based on their directory location."""
    for item in items:
        try:
            rel_path = item.path.relative_to(Path(__file__).parent)
            if "integration" in str(rel_path):
                item.add_marker(pytest.mark.integration)
                item.add_marker(pytest.mark.serial)
            elif "unit" in str(rel_path):
                item.add_marker(pytest.mark.unit)
        except ValueError:
            pass


@pytest.fixture(autouse=True)
def init_observability() -> None:
    """Initialize observability in testing mode for all tests."""
    config = ObservabilityConfig(
        environment=Environment.TESTING,
        pytest_running=True,
        assertions_enabled=False,
        verbose_logging=False,
        tracing_enabled=False,
        metrics_enabled=False,
    )
    init(config, force=True)


@pytest.fixture
def sqlite_pool() -> Generator[SQLitePool, None, None]:
    """Create an in-memory SQLite pool for testing."""
    pool = SQLitePool(":memory:")
    yield pool
    pool.close()


@pytest.fixture
def sqlite_client(sqlite_pool: SQLitePool) -> SQLiteClient:
    """Create SQLite client for testing."""
    return SQLiteClient(sqlite_pool)
