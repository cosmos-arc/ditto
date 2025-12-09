"""Global pytest configuration for Ditto trading system."""

import sys
from pathlib import Path
from typing import Any

# Add src directories to Python path for editable imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "packages" / "core" / "src"))
sys.path.insert(0, str(project_root / "packages" / "foundation" / "src"))
sys.path.insert(0, str(project_root / "apps" / "server" / "src"))


def pytest_configure(config: Any) -> None:
    """Configure pytest with custom markers."""
    config.addinivalue_line("markers", "unit: Mark test as a unit test")
    config.addinivalue_line("markers", "integration: Mark test as an integration test")
    config.addinivalue_line("markers", "e2e: Mark test as an end-to-end test")
    config.addinivalue_line("markers", "slow: Mark test as slow running")
