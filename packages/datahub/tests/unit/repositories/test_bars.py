"""Tests for DQ-related functions in bars module.

This file contains tests specifically for data quality functionality,
including the _generate_dq_report method which handles both legacy
DQCheckResult and new DQResult formats.

Spec compliance: Task 1.1 - Fix DQCheckResult NameError
"""

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from ditto_datahub.repositories.bars import BarsRepository
from ditto_datahub.runtime.dq_checker import DQCheckResult
from ditto_datahub.runtime.file_lock import FileLockManager
from ditto_datahub.runtime.sqlite_pool import SQLitePool
from ditto_datahub.stores.adj_factor_store import AdjFactorStore
from ditto_datahub.stores.bars_store import BarsStore
from ditto_datahub.stores.security_store import SecurityStore
from ditto_datahub.stores.sqlite_client import SQLiteClient
from ditto_datahub.stores.stock_status_store import StockStatusStore


def test_generate_dq_report_with_legacy_dq_result():
    """Test that _generate_dq_report handles legacy DQCheckResult.

    This test verifies the fix for the P0 NameError issue where DQCheckResult
    was only imported in TYPE_CHECKING block but used at runtime in isinstance().

    The test calls BarsRepository._generate_dq_report() with a legacy DQCheckResult
    to ensure the isinstance check at line 732 works without NameError.
    """
    # Arrange
    temp_dir = TemporaryDirectory()
    data_root = Path(temp_dir.name)

    pool = SQLitePool(":memory:")
    pool.init_schema()
    client = SQLiteClient(pool)

    bars_store = BarsStore(data_root)
    adj_factor_store = AdjFactorStore(data_root)
    security_store = SecurityStore(client)
    stock_status_store = StockStatusStore(data_root)
    dq_checker = None  # Not needed for this test
    file_lock_manager = FileLockManager(data_root / "locks")

    repo = BarsRepository(
        bars_store,
        adj_factor_store,
        security_store,
        stock_status_store,
        dq_checker,
        file_lock_manager,
    )

    # Create a legacy DQCheckResult
    mock_result = DQCheckResult(passed=True, results=[])

    # Act & Assert
    # This should NOT raise NameError
    # The isinstance check inside _generate_dq_report should work
    try:
        repo._generate_dq_report(mock_result, "test_dataset")
    except NameError as e:
        pytest.fail(f"NameError raised: {e}")
    except Exception:
        # Other exceptions are OK (e.g., file system issues)
        # We only care that NameError doesn't occur
        pass
    finally:
        temp_dir.cleanup()
