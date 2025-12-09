"""
Abstract base class for database adapters.

This module provides both ABC and Protocol definitions for flexibility.
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from .protocol import DatabaseAdapter as DatabaseAdapterProtocol


class DatabaseAdapter(ABC, DatabaseAdapterProtocol):
    """Abstract base class for all database adapters."""

    def __init__(self, db_path: str | Path) -> None:
        """
        Initialize database adapter with path.

        Args:
            db_path: Path to the database file

        """
        self.db_path = Path(db_path)
        self._initialize_database()

    @abstractmethod
    def _initialize_database(self) -> None:
        """Initialize database with required schema."""
        pass

    @abstractmethod
    def _create_schema(self, conn: Any) -> None:
        """
        Create database schema tables.

        Args:
            conn: Database connection object

        """
        pass

    @abstractmethod
    def close(self) -> None:
        """Close database connection."""
        pass

    @property
    @abstractmethod
    def connection(self) -> Any:
        """Get database connection, creating if necessary."""
        pass

    @abstractmethod
    def execute(self, query: str, params: Any = None) -> Any:
        """Execute a query on the database."""
        pass
