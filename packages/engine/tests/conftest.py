"""Pytest configuration for unit tests."""

from pathlib import Path

import pytest


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """
    Auto-mark tests based on their directory location.

    - tests/unit/ -> unit
    - tests/integration/ -> integration
    Only special cases need manual markers (e.g., @pytest.mark.slow).
    """
    for item in items:
        # Get the relative path from the tests directory
        rel_path_str = str(item.fspath)  # Initialize with fallback value
        try:
            # Try to get path relative to tests directory
            tests_root = Path(__file__).parent  # this is tests/
            rel_path = item.path.relative_to(tests_root)
        except ValueError:
            rel_path = None  # Will use string matching instead

        # Mark based on directory
        path_to_check = str(rel_path) if rel_path else rel_path_str
        if "integration" in path_to_check:
            item.add_marker(pytest.mark.integration)
        elif "unit" in path_to_check:
            item.add_marker(pytest.mark.unit)
