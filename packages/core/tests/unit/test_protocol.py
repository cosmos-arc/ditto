"""Tests for database adapter protocol."""

from typing import Any, Protocol, runtime_checkable

# Import the actual protocol classes
from ditto_core.data.adapters.protocol import (
    Connection as ConnectionProtocol,
)
from ditto_core.data.adapters.protocol import (
    DatabaseAdapter as DatabaseAdapterProtocol,
)
from ditto_core.data.adapters.protocol import (
    Result as ResultProtocol,
)


# Create runtime-checkable versions for testing
@runtime_checkable
class ITestConnection(Protocol):
    """Test Connection protocol."""

    def execute(self, query: str, params: Any = None) -> Any:
        """Execute a query."""
        ...

    def close(self) -> None:
        """Close connection."""
        ...


@runtime_checkable
class ITestResult(Protocol):
    """Test Result protocol."""

    def fetchall(self) -> list[Any]:
        """Fetch all results."""
        ...

    def fetchone(self) -> Any:
        """Fetch one result."""
        ...


@runtime_checkable
class ITestDatabaseAdapter(Protocol):
    """Test DatabaseAdapter protocol."""

    @property
    def connection(self) -> ITestConnection:
        """Get database connection."""
        ...

    def execute(self, query: str, params: Any = None) -> ITestResult:
        """Execute a query."""
        ...

    def close(self) -> None:
        """Close database connection."""
        ...


class TestConnectionImpl:
    """Test the Connection protocol."""

    def test_connection_implementation(self) -> None:
        """Test that a concrete implementation of Connection works."""

        class ConcreteConnection:
            def execute(self, query: str, params: Any = None) -> Any:
                return f"Executed: {query}"

            def close(self) -> None:
                pass

        conn = ConcreteConnection()

        # Test that it satisfies the test protocol
        assert isinstance(conn, ITestConnection)

        # Test methods
        result = conn.execute("SELECT * FROM test")
        assert result == "Executed: SELECT * FROM test"

        # Test close (should not raise)
        conn.close()


class TestResultImpl:
    """Test the Result protocol."""

    def test_result_implementation(self) -> None:
        """Test that a concrete implementation of Result works."""

        class ConcreteResult:
            def __init__(self, data: list[Any]) -> None:
                self.data = data

            def fetchall(self) -> list[Any]:
                return self.data

            def fetchone(self) -> Any:
                return self.data[0] if self.data else None

        # Test with data
        result = ConcreteResult([{"id": 1}, {"id": 2}])

        # Test that it satisfies the test protocol
        assert isinstance(result, ITestResult)

        # Test methods
        all_data = result.fetchall()
        assert all_data == [{"id": 1}, {"id": 2}]

        one_data = result.fetchone()
        assert one_data == {"id": 1}

        # Test with empty data
        empty_result = ConcreteResult([])
        assert empty_result.fetchall() == []
        assert empty_result.fetchone() is None


class TestDatabaseAdapterImpl:
    """Test the DatabaseAdapter protocol."""

    def test_database_adapter_implementation(self) -> None:
        """Test that a concrete implementation of DatabaseAdapter works."""

        class ConcreteResult:
            def __init__(self, data: list[Any] | None = None) -> None:
                self.data = data or []

            def fetchall(self) -> list[Any]:
                return self.data

            def fetchone(self) -> Any:
                return self.data[0] if self.data else None

        class ConcreteConnection:
            def __init__(self) -> None:
                self.closed = False

            def close(self) -> None:
                self.closed = True

        class ConcreteAdapter:
            def __init__(self) -> None:
                self._connection = ConcreteConnection()

            @property
            def connection(self) -> "ConcreteConnection":
                return self._connection

            def execute(self, query: str, params: Any = None) -> "ConcreteResult":
                return ConcreteResult([])

            def close(self) -> None:
                self.connection.close()

        adapter = ConcreteAdapter()

        # Test methods directly without isinstance checks
        conn = adapter.connection
        assert isinstance(conn, ConcreteConnection)
        assert not conn.closed

        result = adapter.execute("SELECT * FROM test")
        assert isinstance(result, ConcreteResult)
        assert result.fetchall() == []

        adapter.close()
        assert conn.closed  # Connection should be closed


class TestProtocolTypeHinting:
    """Test that protocols work correctly with type hints."""

    def use_connection(self, conn: ConnectionProtocol) -> Any:
        """Function that uses a Connection."""
        return conn.execute("test query")

    def use_database(self, db: DatabaseAdapterProtocol) -> ResultProtocol:
        """Function that uses a DatabaseAdapter."""
        result = db.execute("test query")
        db.close()
        return result

    def test_type_hint_compatibility(self) -> None:
        """Test that implementations work with type hinted functions."""

        class TestConnImpl:
            def execute(self, query: str, params: Any = None) -> Any:
                return {"result": "ok"}

            def close(self) -> None:
                pass

        class TestAdapterImpl:
            def __init__(self) -> None:
                self.conn = TestConnImpl()

            @property
            def connection(self) -> ConnectionProtocol:
                return self.conn

            def execute(self, query: str, params: Any = None) -> ResultProtocol:
                class TestResultImpl:
                    def fetchall(self) -> list[Any]:
                        return []

                    def fetchone(self) -> Any:
                        return None

                return TestResultImpl()

            def close(self) -> None:
                self.conn.close()

        # Test with type hinted functions
        conn = TestConnImpl()
        result = self.use_connection(conn)
        assert result == {"result": "ok"}

        adapter = TestAdapterImpl()
        db_result = self.use_database(adapter)
        assert hasattr(db_result, "fetchall")
        assert hasattr(db_result, "fetchone")
