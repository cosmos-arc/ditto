"""Database adapter protocol using typing.Protocol."""

from typing import Any, Protocol

import polars as pl


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

    def fetch_df(self, sql: str, params: dict[str, Any] | None = None) -> pl.DataFrame:
        """Execute SQL query and return DataFrame."""
        ...

    def execute_many(self, sql: str, data: list[dict[str, Any]]) -> None:
        """Execute SQL query with multiple parameter sets."""
        ...

    def close(self) -> None:
        """Close database connection."""
        ...
