"""Database adapter protocol using typing.Protocol."""

from typing import Any, Protocol


class Connection(Protocol):
    """Database connection protocol."""

    def execute(self, query: str, params: Any = None) -> Any:
        """Execute a query."""
        ...

    def close(self) -> None:
        """Close connection."""
        ...


class Result(Protocol):
    """Query result protocol."""

    def fetchall(self) -> list[Any]:
        """Fetch all results."""
        ...

    def fetchone(self) -> Any:
        """Fetch one result."""
        ...


class DatabaseAdapter(Protocol):
    """Database adapter protocol for type hinting."""

    @property
    def connection(self) -> Connection:
        """Get database connection."""
        ...

    def execute(self, query: str, params: Any = None) -> Result:
        """Execute a query."""
        ...

    def close(self) -> None:
        """Close database connection."""
        ...
