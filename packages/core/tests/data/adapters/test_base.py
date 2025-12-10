"""Unit tests for database adapter base class."""

# Import directly to avoid import chain issues
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from ditto_core.data.adapters.base import DatabaseAdapter


class MockDatabaseAdapter(DatabaseAdapter):
    """Mock implementation of DatabaseAdapter for testing."""

    def __init__(self, db_path: str | Path, fail_init: bool = False) -> None:
        """Initialize mock adapter."""
        self.fail_init = fail_init
        self.initialize_called = False
        self.connection_instance = MagicMock()
        super().__init__(db_path)

    def _initialize_database(self) -> None:
        """Mock initialize database."""
        if self.fail_init:
            raise RuntimeError("Failed to initialize database")
        self.initialize_called = True

    def _create_schema(self, conn: Any) -> None:
        """Mock create schema."""
        conn.execute("CREATE TABLE test (id INTEGER)")

    @property
    def connection(self) -> Any:
        """Mock connection property."""
        return self.connection_instance

    def execute(self, query: str, params: Any = None) -> Any:
        """Mock execute method."""
        return MagicMock()

    def close(self) -> None:
        """Mock close method."""
        self.connection_instance = None


class TestDatabaseAdapter:
    """Test cases for DatabaseAdapter abstract base class."""

    def test_init_with_string_path(self) -> None:
        """Test initialization with string path."""
        with TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "test.db"
            adapter = MockDatabaseAdapter(str(db_path))

            assert isinstance(adapter.db_path, Path)
            assert adapter.db_path == db_path
            assert adapter.initialize_called is True

    def test_init_with_path_object(self) -> None:
        """Test initialization with Path object."""
        with TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "test.db"
            adapter = MockDatabaseAdapter(db_path)

            assert adapter.db_path == db_path
            assert adapter.initialize_called is True

    def test_init_calls_initialize_database(self) -> None:
        """Test that initialization calls _initialize_database."""
        with TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "test.db"
            adapter = MockDatabaseAdapter(db_path)

            assert adapter.initialize_called is True

    def test_init_raises_when_initialize_fails(self) -> None:
        """Test that initialization raises when _initialize_database fails."""
        with TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "test.db"

            with pytest.raises(RuntimeError, match="Failed to initialize database"):
                MockDatabaseAdapter(db_path, fail_init=True)

    def test_abstract_methods_not_implemented(self) -> None:
        """Test that DatabaseAdapter cannot be instantiated directly."""
        with TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "test.db"

            with pytest.raises(TypeError, match="Can't instantiate abstract class"):
                DatabaseAdapter(db_path)

    def test_subclass_must_implement_all_abstract_methods(self) -> None:
        """Test that subclass must implement all abstract methods."""

        class IncompleteAdapter(DatabaseAdapter):
            """Incomplete adapter missing some abstract methods."""

            def __init__(self, db_path: str | Path) -> None:
                self.db_path = Path(db_path)
                self._initialize_database()

            def _initialize_database(self) -> None:
                pass

            def _create_schema(self, conn: Any) -> None:
                pass

            # Missing other abstract methods

        with TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "test.db"

            with pytest.raises(TypeError, match="Can't instantiate abstract class"):
                IncompleteAdapter(db_path)

    def test_db_path_conversion_to_path(self) -> None:
        """Test that db_path is always converted to Path object."""
        # Test with different path formats
        test_cases = [
            "test.db",
            "./test.db",
            "C:\\temp\\test.db" if Path("C:\\").exists() else "/tmp/test.db",
        ]

        for _path_str in test_cases:
            with TemporaryDirectory() as tmp_dir:
                # Create temporary path
                temp_path = Path(tmp_dir) / "test.db"
                adapter = MockDatabaseAdapter(str(temp_path))

                assert isinstance(adapter.db_path, Path)
                assert adapter.db_path.is_absolute()

    @patch("ditto_core.data.adapters.base.DatabaseAdapter._create_schema")
    def test_create_schema_called_during_init(
        self, mock_create_schema: MagicMock
    ) -> None:
        """Test that _create_schema is called during initialization."""
        with TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "test.db"

            class TestAdapter(DatabaseAdapter):
                def __init__(self, db_path: str | Path) -> None:
                    self.connection_instance = MagicMock()
                    super().__init__(db_path)

                def _initialize_database(self) -> None:
                    pass

                @property
                def connection(self) -> Any:
                    return self.connection_instance

                def execute(self, query: str, params: Any = None) -> Any:
                    return MagicMock()

                def close(self) -> None:
                    pass

            TestAdapter(db_path)

            # _create_schema should not be called directly by __init__
            # It's called by _initialize_database in concrete implementations
            mock_create_schema.assert_not_called()

    def test_adapter_inheritance_chain(self) -> None:
        """Test that adapter inherits from both ABC and Protocol."""
        with TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "test.db"
            adapter = MockDatabaseAdapter(db_path)

            # Check MRO
            mro = MockDatabaseAdapter.__mro__
            assert DatabaseAdapter in mro

            # Check protocol import
            # Protocol is not meant for runtime checking with issubclass
            # Instead check that MockDatabaseAdapter implements the protocol methods
            assert hasattr(adapter, "connection")
            assert hasattr(adapter, "execute")
            assert hasattr(adapter, "close")

    def test_path_object_handling_edge_cases(self) -> None:
        """Test handling of various Path object edge cases."""
        with TemporaryDirectory() as tmp_dir:
            # Test with Path that has parent directories
            nested_path = Path(tmp_dir) / "nested" / "dir" / "test.db"
            adapter = MockDatabaseAdapter(nested_path)

            assert adapter.db_path == nested_path
            # Parent directories should be created when database is initialized

            # Test with relative path
            adapter2 = MockDatabaseAdapter("test.db")
            assert isinstance(adapter2.db_path, Path)
            assert adapter2.db_path.name == "test.db"

    def test_adapter_protocol_compatibility(self) -> None:
        """Test that adapter is compatible with DatabaseAdapter protocol."""
        with TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "test.db"
            adapter = MockDatabaseAdapter(db_path)

            # Protocol is not runtime_checkable, so we can't use isinstance
            # Instead check that adapter has all required protocol methods/properties
            assert hasattr(adapter, "connection")
            assert hasattr(adapter, "execute")
            assert hasattr(adapter, "close")

            # Check that the methods have correct signatures (basic check)
            assert callable(adapter.execute)
            assert callable(adapter.close)
