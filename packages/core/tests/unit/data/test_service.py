"""测试 DataService 相关功能."""

import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import ditto_core.data.service as service_module
import pytest
from ditto_core.data.adapters.duckdb_adapter import DuckDBAdapter
from ditto_core.data.adapters.sqlite_adapter import SQLiteAdapter
from ditto_core.data.service import DataService


class TestDuckDBAdapter:
    """DuckDB 适配器测试."""

    def setup_method(self) -> None:
        """每个测试前执行."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test.duckdb"

    def teardown_method(self) -> None:
        """每个测试后执行."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_create_adapter_with_path(self) -> None:
        """测试使用路径创建适配器."""
        adapter = DuckDBAdapter(db_path=str(self.db_path))

        assert str(adapter.db_path) == str(self.db_path)
        # Removed: adapter.connection is not None when created

    def test_connection_creation(self) -> None:
        """测试连接创建."""
        adapter = DuckDBAdapter(db_path=str(self.db_path))

        assert adapter.connection is not None
        assert adapter.connection.execute("SELECT 1").fetchone()[0] == 1

    def test_initialize_schema(self) -> None:
        """测试数据库 schema 初始化."""
        adapter = DuckDBAdapter(db_path=str(self.db_path))

        # 验证表是否创建成功
        tables = adapter.connection.execute("SHOW TABLES").fetchall()

        table_names = [table[0] for table in tables]
        expected_tables = [
            "etf_info",
            "daily_price",
            "adjustment_factors",
            "trading_calendar",
        ]

        for table in expected_tables:
            assert table in table_names


class TestSQLiteAdapter:
    """SQLite 适配器测试."""

    def setup_method(self) -> None:
        """每个测试前执行."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test.sqlite"

    def teardown_method(self) -> None:
        """每个测试后执行."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_create_adapter_with_path(self) -> None:
        """测试使用路径创建适配器."""
        adapter = SQLiteAdapter(db_path=str(self.db_path))

        assert str(adapter.db_path) == str(self.db_path)
        # Removed: adapter.connection is not None when created

    def test_connection_creation(self) -> None:
        """测试连接创建."""
        adapter = SQLiteAdapter(db_path=str(self.db_path))

        assert adapter.connection is not None
        assert adapter.connection.execute("SELECT 1").fetchone()[0] == 1

    def test_initialize_schema(self) -> None:
        """测试数据库 schema 初始化."""
        adapter = SQLiteAdapter(db_path=str(self.db_path))

        # 验证表是否创建成功
        tables = adapter.connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()

        table_names = [table[0] for table in tables]
        expected_tables = [
            "trades",
            "orders",
            "positions",
            "portfolio_snapshots",
            "strategy_configs",
            "execution_logs",
        ]

        for table in expected_tables:
            assert table in table_names


class TestDataService:
    """数据服务测试."""

    def setup_method(self) -> None:
        """每个测试前执行."""
        self.temp_dir = tempfile.mkdtemp()
        self.duckdb_path = Path(self.temp_dir) / "test.duckdb"
        self.sqlite_path = Path(self.temp_dir) / "test.sqlite"

    def teardown_method(self) -> None:
        """每个测试后执行."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_initialization(self) -> None:
        """Test DataService initialization."""
        service = DataService(
            duckdb_path=str(self.duckdb_path),
            sqlite_path=str(self.sqlite_path),
        )

        # Verify paths are stored correctly
        assert service.duckdb_path == str(self.duckdb_path)
        assert service.sqlite_path == str(self.sqlite_path)

        # Verify adapters are initially None
        assert service._duckdb is None
        assert service._sqlite is None

    def test_initialization_with_path_objects(self) -> None:
        """Test DataService initialization with Path objects."""
        service = DataService(
            duckdb_path=self.duckdb_path,
            sqlite_path=self.sqlite_path,
        )

        # DataService stores paths as-is (doesn't convert to string)
        assert service.duckdb_path == self.duckdb_path
        assert service.sqlite_path == self.sqlite_path

    def test_service_initialization(self) -> None:
        """测试服务初始化."""
        service = DataService(
            duckdb_path=str(self.duckdb_path), sqlite_path=str(self.sqlite_path)
        )

        assert service.duckdb_path == str(self.duckdb_path)
        assert service.sqlite_path == str(self.sqlite_path)
        # 适配器实例已创建但未连接
        assert service.duckdb_adapter is not None
        assert service.sqlite_adapter is not None
        # 连接已自动创建
        assert service.duckdb_adapter.connection is not None
        assert service.sqlite_adapter.connection is not None

    @patch("ditto_core.data.service.DuckDBAdapter")
    def test_get_duckdb_lazy_loading(self, mock_duckdb_class: MagicMock) -> None:
        """Test get_duckdb method creates adapter on first call."""
        mock_adapter = MagicMock(spec=DuckDBAdapter)
        mock_duckdb_class.return_value = mock_adapter

        service = DataService(
            duckdb_path=str(self.duckdb_path),
            sqlite_path=str(self.sqlite_path),
        )

        # First call should create adapter
        result = service.get_duckdb()

        # Verify adapter was created with correct path
        mock_duckdb_class.assert_called_once_with(str(self.duckdb_path))
        assert result == mock_adapter

        # Second call should return same instance
        result2 = service.get_duckdb()
        assert result2 is result
        assert mock_duckdb_class.call_count == 1

    @patch("ditto_core.data.service.SQLiteAdapter")
    def test_get_sqlite_lazy_loading(self, mock_sqlite_class: MagicMock) -> None:
        """Test get_sqlite method creates adapter on first call."""
        mock_adapter = MagicMock(spec=SQLiteAdapter)
        mock_sqlite_class.return_value = mock_adapter

        service = DataService(
            duckdb_path=str(self.duckdb_path),
            sqlite_path=str(self.sqlite_path),
        )

        # First call should create adapter
        result = service.get_sqlite()

        # Verify adapter was created with correct path
        mock_sqlite_class.assert_called_once_with(str(self.sqlite_path))
        assert result == mock_adapter

        # Second call should return same instance
        result2 = service.get_sqlite()
        assert result2 is result
        assert mock_sqlite_class.call_count == 1

    @patch("ditto_core.data.service.DuckDBAdapter")
    def test_duckdb_adapter_property(self, mock_duckdb_class: MagicMock) -> None:
        """Test duckdb_adapter property lazy loading."""
        mock_adapter = MagicMock(spec=DuckDBAdapter)
        mock_duckdb_class.return_value = mock_adapter

        service = DataService(
            duckdb_path=str(self.duckdb_path),
            sqlite_path=str(self.sqlite_path),
        )

        # First access should create adapter
        result = service.duckdb_adapter

        # Verify adapter was created with correct path
        mock_duckdb_class.assert_called_once_with(str(self.duckdb_path))
        assert result == mock_adapter

        # Second access should return same instance
        result2 = service.duckdb_adapter
        assert result2 is result
        assert mock_duckdb_class.call_count == 1

    @patch("ditto_core.data.service.SQLiteAdapter")
    def test_sqlite_adapter_property(self, mock_sqlite_class: MagicMock) -> None:
        """Test sqlite_adapter property lazy loading."""
        mock_adapter = MagicMock(spec=SQLiteAdapter)
        mock_sqlite_class.return_value = mock_adapter

        service = DataService(
            duckdb_path=str(self.duckdb_path),
            sqlite_path=str(self.sqlite_path),
        )

        # First access should create adapter
        result = service.sqlite_adapter

        # Verify adapter was created with correct path
        mock_sqlite_class.assert_called_once_with(str(self.sqlite_path))
        assert result == mock_adapter

        # Second access should return same instance
        result2 = service.sqlite_adapter
        assert result2 is result
        assert mock_sqlite_class.call_count == 1

    @patch("ditto_core.data.service.SQLiteAdapter")
    @patch("ditto_core.data.service.DuckDBAdapter")
    def test_initialize(
        self, mock_duckdb_class: MagicMock, mock_sqlite_class: MagicMock
    ) -> None:
        """Test initialize method creates both adapters."""
        mock_duckdb = MagicMock(spec=DuckDBAdapter)
        mock_sqlite = MagicMock(spec=SQLiteAdapter)
        mock_duckdb_class.return_value = mock_duckdb
        mock_sqlite_class.return_value = mock_sqlite

        service = DataService(
            duckdb_path=str(self.duckdb_path),
            sqlite_path=str(self.sqlite_path),
        )

        # Initialize should create both adapters
        service.initialize()

        # Verify both adapters were created
        mock_duckdb_class.assert_called_once_with(str(self.duckdb_path))
        mock_sqlite_class.assert_called_once_with(str(self.sqlite_path))

        # Verify adapters are stored
        assert service._duckdb is mock_duckdb
        assert service._sqlite is mock_sqlite

    @patch("ditto_core.data.service.SQLiteAdapter")
    @patch("ditto_core.data.service.DuckDBAdapter")
    def test_close_with_adapters_initialized(
        self, mock_duckdb_class: MagicMock, mock_sqlite_class: MagicMock
    ) -> None:
        """Test close method closes initialized adapters."""
        mock_duckdb = MagicMock(spec=DuckDBAdapter)
        mock_sqlite = MagicMock(spec=SQLiteAdapter)
        mock_duckdb_class.return_value = mock_duckdb
        mock_sqlite_class.return_value = mock_sqlite

        service = DataService(
            duckdb_path=str(self.duckdb_path),
            sqlite_path=str(self.sqlite_path),
        )

        # Initialize adapters
        service.get_duckdb()
        service.get_sqlite()

        # Close should call close on both adapters
        service.close()

        mock_duckdb.close.assert_called_once()
        mock_sqlite.close.assert_called_once()

    @patch("ditto_core.data.service.SQLiteAdapter")
    @patch("ditto_core.data.service.DuckDBAdapter")
    def test_close_with_no_adapters_initialized(
        self, mock_duckdb_class: MagicMock, mock_sqlite_class: MagicMock
    ) -> None:
        """Test close method does nothing when no adapters initialized."""
        service = DataService(
            duckdb_path=str(self.duckdb_path),
            sqlite_path=str(self.sqlite_path),
        )

        # Close should not fail when adapters are not initialized
        service.close()

        # Verify no adapters were created
        mock_duckdb_class.assert_not_called()
        mock_sqlite_class.assert_not_called()

    @patch("ditto_core.data.service.SQLiteAdapter")
    @patch("ditto_core.data.service.DuckDBAdapter")
    def test_close_with_partial_adapters(
        self, mock_duckdb_class: MagicMock, mock_sqlite_class: MagicMock
    ) -> None:
        """Test close method works when only one adapter is initialized."""
        mock_duckdb = MagicMock(spec=DuckDBAdapter)
        mock_duckdb_class.return_value = mock_duckdb

        service = DataService(
            duckdb_path=str(self.duckdb_path),
            sqlite_path=str(self.sqlite_path),
        )

        # Initialize only DuckDB adapter
        service.get_duckdb()

        # Close should only call close on initialized adapter
        service.close()

        mock_duckdb.close.assert_called_once()
        # SQLite adapter should not be created
        mock_sqlite_class.assert_not_called()

    @patch("ditto_core.data.service.SQLiteAdapter")
    @patch("ditto_core.data.service.DuckDBAdapter")
    def test_context_manager(
        self, mock_duckdb_class: MagicMock, mock_sqlite_class: MagicMock
    ) -> None:
        """Test context manager functionality."""
        mock_duckdb = MagicMock(spec=DuckDBAdapter)
        mock_sqlite = MagicMock(spec=SQLiteAdapter)
        mock_duckdb_class.return_value = mock_duckdb
        mock_sqlite_class.return_value = mock_sqlite

        service = DataService(
            duckdb_path=str(self.duckdb_path),
            sqlite_path=str(self.sqlite_path),
        )

        # Use as context manager
        with service as s:
            # Verify it's the same instance
            assert s is service

            # Verify initialize was called
            mock_duckdb_class.assert_called_once_with(str(self.duckdb_path))
            mock_sqlite_class.assert_called_once_with(str(self.sqlite_path))

        # Verify close was called after exiting context
        mock_duckdb.close.assert_called_once()
        mock_sqlite.close.assert_called_once()

    @patch("ditto_core.data.service.SQLiteAdapter")
    @patch("ditto_core.data.service.DuckDBAdapter")
    def test_context_manager_with_exception(
        self, mock_duckdb_class: MagicMock, mock_sqlite_class: MagicMock
    ) -> None:
        """Test context manager closes adapters even when exception occurs."""
        mock_duckdb = MagicMock(spec=DuckDBAdapter)
        mock_sqlite = MagicMock(spec=SQLiteAdapter)
        mock_duckdb_class.return_value = mock_duckdb
        mock_sqlite_class.return_value = mock_sqlite

        service = DataService(
            duckdb_path=str(self.duckdb_path),
            sqlite_path=str(self.sqlite_path),
        )

        # Use context manager with exception
        with pytest.raises(ValueError, match="Test exception"), service:
            raise ValueError("Test exception")

        # Verify close was still called despite exception
        mock_duckdb.close.assert_called_once()
        mock_sqlite.close.assert_called_once()

    def test_duckdb_adapter_not_available(self) -> None:
        """Test behavior when DuckDBAdapter is not available."""
        # Simulate DuckDB not being available by setting it to None in the module
        original_duckdb = service_module.DuckDBAdapter

        try:
            # Set DuckDBAdapter to None
            service_module.DuckDBAdapter = None

            service = DataService(
                duckdb_path=str(self.duckdb_path),
                sqlite_path=str(self.sqlite_path),
            )

            # Should raise TypeError when trying to get DuckDB adapter
            # because DuckDBAdapter is None
            with pytest.raises(TypeError, match="'NoneType' object is not callable"):
                _ = service.get_duckdb()
        finally:
            # Restore original value
            service_module.DuckDBAdapter = original_duckdb

    @patch("ditto_core.data.service.DuckDBAdapter")
    def test_adapter_sharing_between_methods_and_properties(
        self, mock_duckdb_class: MagicMock
    ) -> None:
        """Test that methods and properties share the same adapter instance."""
        mock_adapter = MagicMock(spec=DuckDBAdapter)
        mock_duckdb_class.return_value = mock_adapter

        service = DataService(
            duckdb_path=str(self.duckdb_path),
            sqlite_path=str(self.sqlite_path),
        )

        # Get adapter through method
        method_result = service.get_duckdb()

        # Get adapter through property
        property_result = service.duckdb_adapter

        # Should be the same instance
        assert method_result is property_result
        assert mock_duckdb_class.call_count == 1

    @patch("ditto_core.data.service.SQLiteAdapter")
    @patch("ditto_core.data.service.DuckDBAdapter")
    def test_multiple_initialize_calls(
        self, mock_duckdb_class: MagicMock, mock_sqlite_class: MagicMock
    ) -> None:
        """Test that multiple initialize calls don't create duplicate adapters."""
        mock_duckdb = MagicMock(spec=DuckDBAdapter)
        mock_sqlite = MagicMock(spec=SQLiteAdapter)
        mock_duckdb_class.return_value = mock_duckdb
        mock_sqlite_class.return_value = mock_sqlite

        service = DataService(
            duckdb_path=str(self.duckdb_path),
            sqlite_path=str(self.sqlite_path),
        )

        # Call initialize multiple times
        service.initialize()
        service.initialize()
        service.initialize()

        # Should only create adapters once
        mock_duckdb_class.assert_called_once_with(str(self.duckdb_path))
        mock_sqlite_class.assert_called_once_with(str(self.sqlite_path))

    def test_lazy_connection(self) -> None:
        """测试懒加载连接."""
        service = DataService(
            duckdb_path=str(self.duckdb_path), sqlite_path=str(self.sqlite_path)
        )

        # 调用方法时才创建连接
        duckdb_adapter = service.get_duckdb()
        sqlite_adapter = service.get_sqlite()

        assert duckdb_adapter is not None
        assert sqlite_adapter is not None
        assert duckdb_adapter.connection is not None
        assert sqlite_adapter.connection is not None

        # 验证数据库文件已创建
        assert self.duckdb_path.exists()
        assert self.sqlite_path.exists()
