"""Pytest configuration for datahub tests."""

import pytest
from ditto_foundation import Mode, init


@pytest.fixture(autouse=True)  # type: ignore[misc]
def init_observability() -> None:
    """Initialize observability in testing mode for all tests."""
    init(mode=Mode.TESTING)
    # Cleanup is handled by reset_for_testing if needed
