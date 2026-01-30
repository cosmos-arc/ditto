"""FundamentalStore for fundamental data with PIT support."""

from __future__ import annotations

from ditto_datahub.stores.sqlite_client import SQLiteClient


class FundamentalStore:
    """
    Fundamental domain data storage with PIT support.

    Core functionality:
    - Financial statements (balance sheet, income statement, cash flow)
    - Corporate actions (dividend, corporate actions)
    - Performance forecast (forecast, express)

    All PIT-enabled datasets support querying data as of a specific date.
    """

    def __init__(
        self,
        sqlite_client: SQLiteClient,
    ) -> None:
        """
        Initialize FundamentalStore.

        Args:
            sqlite_client: SQLite client for database operations.

        """
        self._client = sqlite_client

    def close(self) -> None:
        """Close the underlying SQLite client."""
        self._client.close()
