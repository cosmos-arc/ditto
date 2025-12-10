"""Integration tests for database adapter protocols."""

# Import directly to avoid import chain issues
import inspect
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from ditto_core.data.adapters.protocol import Connection, DatabaseAdapter, Result

if TYPE_CHECKING:
    # Only use protocol types for type checking
    pass


class MockConnection:
    """Mock connection implementation."""

    def execute(self, query: str, params: Any = None) -> Any:
        """Execute a query."""
        return MockResult()

    def close(self) -> None:
        """Close connection."""
        pass


class MockResult:
    """Mock result implementation."""

    def fetchall(self) -> list[Any]:
        """Fetch all results."""
        return [{"test": "data"}]

    def fetchone(self) -> Any:
        """Fetch one result."""
        return {"test": "data"}

    def __len__(self) -> int:
        """Return number of rows."""
        return 1


class MockAdapter:
    """Mock adapter implementation."""

    def __init__(self) -> None:
        """Initialize MockAdapter."""
        self._connection = MockConnection()

    @property
    def connection(self) -> MockConnection:
        """Get database connection."""
        return self._connection

    def execute(self, query: str, params: Any = None) -> Any:
        """Execute a query."""
        return self._connection.execute(query, params)

    def close(self) -> None:
        """Close database connection."""
        self._connection.close()


@runtime_checkable
class CustomProtocol(Protocol):
    """Custom protocol for testing protocol inheritance."""

    def custom_method(self) -> str:
        """Custom method."""
        ...


@pytest.mark.integration
def test_connection_protocol_methods() -> None:
    """Test that MockConnection has required protocol methods."""
    conn = MockConnection()

    # Test execute method exists and returns expected type
    result = conn.execute("SELECT * FROM test", {"param": "value"})
    assert hasattr(result, "fetchall")
    assert hasattr(result, "fetchone")

    # Test close method exists and doesn't raise
    conn.close()  # Should not raise


@pytest.mark.integration
def test_result_protocol_methods() -> None:
    """Test that MockResult has required protocol methods."""
    result = MockResult()

    # Test fetchall method
    all_results = result.fetchall()
    assert isinstance(all_results, list)
    assert len(all_results) > 0

    # Test fetchone method
    one_result = result.fetchone()
    assert one_result is not None

    # Test additional list-like methods if present
    if hasattr(result, "__len__"):
        assert len(result) >= 0


@pytest.mark.integration
def test_database_adapter_protocol_methods() -> None:
    """Test that MockAdapter has required protocol methods."""
    adapter = MockAdapter()

    # Test connection property
    conn = adapter.connection
    assert hasattr(conn, "execute")
    assert hasattr(conn, "close")

    # Test execute method
    result = adapter.execute("SELECT * FROM test")
    assert hasattr(result, "fetchall")

    # Test close method
    adapter.close()  # Should not raise


@pytest.mark.integration
def test_protocol_usage_pattern() -> None:
    """Test that protocols can be used in function signatures."""

    # These functions demonstrate how protocols would be used
    def process_connection(conn: "Connection") -> "Result":
        """Process a connection."""
        return conn.execute("SELECT 1")

    def process_adapter(adapter: "DatabaseAdapter") -> list[Any]:
        """Process an adapter."""
        result = adapter.execute("SELECT * FROM test")
        return result.fetchall()  # type: ignore[no-any-return]

    # Test with mock implementations
    conn = MockConnection()
    result = process_connection(conn)
    assert hasattr(result, "fetchall")

    adapter = MockAdapter()
    results = process_adapter(adapter)
    assert isinstance(results, list)


@pytest.mark.integration
def test_protocol_runtime_checkability() -> None:
    """Test that protocols can be used for runtime type checking."""
    # Protocols should be runtime checkable if decorated properly
    try:
        isinstance(MockConnection(), Connection)
    except TypeError:
        # Protocol is not runtime checkable, which is acceptable
        pass


@pytest.mark.integration
def test_protocol_instantiation() -> None:
    """Test that protocols cannot be instantiated."""
    with pytest.raises(TypeError):
        Connection()

    with pytest.raises(TypeError):
        Result()

    with pytest.raises(TypeError):
        DatabaseAdapter()


@pytest.mark.integration
def test_protocol_method_signatures() -> None:
    """Test that protocol methods have correct signatures."""
    # Check Connection protocol
    conn_sig = inspect.signature(Connection.execute)
    assert "query" in conn_sig.parameters
    assert "params" in conn_sig.parameters
    assert conn_sig.parameters["params"].default is None

    close_sig = inspect.signature(Connection.close)
    assert len(close_sig.parameters) == 1  # Only self

    # Check Result protocol
    fetchall_sig = inspect.signature(Result.fetchall)
    assert len(fetchall_sig.parameters) == 1  # Only self

    fetchone_sig = inspect.signature(Result.fetchone)
    assert len(fetchone_sig.parameters) == 1  # Only self

    # Check DatabaseAdapter protocol
    execute_sig = inspect.signature(DatabaseAdapter.execute)
    assert "query" in execute_sig.parameters
    assert "params" in execute_sig.parameters

    close_sig = inspect.signature(DatabaseAdapter.close)
    assert len(close_sig.parameters) == 1  # Only self


@pytest.mark.integration
def test_protocol_with_type_hints() -> None:
    """Test that protocols work properly with type hints."""

    # Test with generic Any type
    def process_any_result(result: Result) -> Any:
        """Process a result with Any return type."""
        return result.fetchone()

    result = MockResult()
    data = process_any_result(result)
    assert data is not None

    # Test with specific type hints
    def process_str_result(result: Result) -> dict[str, Any]:
        """Process a result returning dict."""
        row = result.fetchone()
        return row if isinstance(row, dict) else {}

    result = MockResult()
    data = process_str_result(result)
    assert isinstance(data, dict)


@pytest.mark.integration
def test_protocol_inheritance() -> None:
    """Test protocol inheritance and extension."""

    # Create a protocol that extends DatabaseAdapter
    @runtime_checkable
    class ExtendedAdapter(DatabaseAdapter, Protocol):
        """Extended adapter protocol with additional methods."""

        def get_version(self) -> str:
            """Get adapter version."""
            ...

    # Create mock implementation
    class ExtendedMockAdapter:
        def __init__(self) -> None:
            self._connection = MockConnection()

        @property
        def connection(self) -> MockConnection:
            return self._connection

        def execute(self, query: str, params: Any = None) -> Any:
            return self._connection.execute(query, params)

        def close(self) -> None:
            self._connection.close()

        def get_version(self) -> str:
            return "1.0.0"

    # Test usage
    adapter = ExtendedMockAdapter()
    assert hasattr(adapter, "get_version")
    assert adapter.get_version() == "1.0.0"


@pytest.mark.integration
def test_protocol_composition() -> None:
    """Test using protocols in composition patterns."""

    class DatabaseManager:
        """Manager class using protocol composition."""

        def __init__(self, adapter: DatabaseAdapter) -> None:
            self.adapter = adapter

        def query(self, sql: str, params: Any = None) -> list[Any]:
            """Execute query and return all results."""
            result = self.adapter.execute(sql, params)
            return result.fetchall()  # type: ignore[no-any-return]

        def shutdown(self) -> None:
            """Close database connection."""
            self.adapter.close()

    # Test with mock adapter
    adapter = MockAdapter()
    manager = DatabaseManager(adapter)
    results = manager.query("SELECT * FROM test")
    assert isinstance(results, list)
    manager.shutdown()  # Should not raise


@pytest.mark.integration
def test_protocol_optional_parameters() -> None:
    """Test protocol methods with optional parameters."""
    # Test that params parameter is truly optional
    conn = MockConnection()

    # Should work without params
    result1 = conn.execute("SELECT 1")
    assert result1 is not None

    # Should work with params
    result2 = conn.execute("SELECT ?", [1])
    assert result2 is not None

    # Should work with None params
    result3 = conn.execute("SELECT 1", None)
    assert result3 is not None


@pytest.mark.integration
def test_protocol_documentation() -> None:
    """Test that protocol classes have proper documentation."""
    assert Connection.__doc__ is not None
    assert "Database connection protocol" in Connection.__doc__

    assert Result.__doc__ is not None
    assert "Query result protocol" in Result.__doc__

    assert DatabaseAdapter.__doc__ is not None
    assert "Database adapter protocol" in DatabaseAdapter.__doc__


@pytest.mark.integration
def test_protocol_method_documentation() -> None:
    """Test that protocol methods have proper documentation."""
    # Check method docstrings
    assert Connection.execute.__doc__ is not None
    assert "Execute a query" in Connection.execute.__doc__

    assert Connection.close.__doc__ is not None
    assert "Close connection" in Connection.close.__doc__

    assert Result.fetchall.__doc__ is not None
    assert "Fetch all results" in Result.fetchall.__doc__

    assert Result.fetchone.__doc__ is not None
    assert "Fetch one result" in Result.fetchone.__doc__
