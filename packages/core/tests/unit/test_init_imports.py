"""Test __init__ module imports."""

from unittest.mock import patch

from ditto_core.data.adapters import SQLiteAdapter
from ditto_core.data.datasources import AkShareDataSource, DataSourceFactory


def test_duckdb_import_error_handling() -> None:
    """Test that DuckDB import error is handled gracefully."""
    # Mock ImportError when importing DuckDBAdapter
    with patch.dict("sys.modules", {"duckdb": None}):
        # Force reload of the module to trigger import error
        import importlib

        from ditto_core.data import adapters

        # Reload adapters to trigger the import error path
        importlib.reload(adapters)

        # DuckDBAdapter should be None when import fails
        assert adapters.DuckDBAdapter is None

        # Other adapters should still be available
        assert adapters.SQLiteAdapter is not None


def test_datasources_import_error_handling() -> None:
    """Test that datasource import errors are handled gracefully."""
    import importlib

    # Test AkShare import error
    with patch.dict("sys.modules", {"akshare": None}):
        # Reload datasources module to trigger import error
        import ditto_core.data.datasources

        importlib.reload(ditto_core.data.datasources)

        # AkShareDataSource should be None when import fails
        assert ditto_core.data.datasources.AkShareDataSource is None

        # Other datasources should still be available
        assert ditto_core.data.datasources.DataSource is not None
        assert ditto_core.data.datasources.DataSourceFactory is not None

    # Test Tushare import error
    with patch.dict("sys.modules", {"tushare": None}):
        # Reload datasources module to trigger import error
        import ditto_core.data.datasources

        importlib.reload(ditto_core.data.datasources)

        # TushareDataSource should be None when import fails
        assert ditto_core.data.datasources.TushareDataSource is None


def test_adapters_duckdb_import_error_handling() -> None:
    """Test that adapters module handles DuckDB import error."""
    import importlib

    # Test duckdb_adapter import error
    with patch.dict("sys.modules", {"duckdb": None}):
        # Reload adapters module
        import ditto_core.data.adapters

        importlib.reload(ditto_core.data.adapters)

        # DuckDBAdapter should be None
        assert ditto_core.data.adapters.DuckDBAdapter is None

        # Other adapters should still be available
        assert ditto_core.data.adapters.DatabaseAdapter is not None
        assert ditto_core.data.adapters.SQLiteAdapter is not None


def test_normal_imports() -> None:
    """Test that normal imports work correctly."""
    from ditto_core.data.adapters import DatabaseAdapter
    from ditto_core.data.constants import DatabaseType, DataSourceType
    from ditto_core.data.datasources import (
        DataSource,
        TushareDataSource,
    )

    # Verify all imports are successful
    assert DatabaseAdapter is not None
    assert SQLiteAdapter is not None
    assert DatabaseType is not None
    assert DataSourceType is not None
    assert AkShareDataSource is not None
    assert DataSource is not None
    assert DataSourceFactory is not None
    assert TushareDataSource is not None
