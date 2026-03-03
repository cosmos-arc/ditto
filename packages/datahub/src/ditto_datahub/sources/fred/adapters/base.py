"""FRED adapter base class."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ditto_datahub.sources.fred.client import FredClient

if TYPE_CHECKING:
    pass


class BaseFredAdapter:
    """
    Base class for FRED data adapters.

    Provides shared client management and context manager protocol.
    Subclasses should implement specific data fetching methods.

    Attributes:
        _client: FredClient instance for API calls.

    """

    def __init__(self, api_key: str | None = None) -> None:
        """
        Initialize FRED adapter.

        Args:
            api_key: FRED API key. If None, reads from FRED_API_KEY env var.

        """
        self._client = FredClient(api_key=api_key)

    def close(self) -> None:
        """Close underlying HTTP client."""
        self._client.close()

    def __enter__(self) -> BaseFredAdapter:
        """Context manager entry."""
        return self

    def __exit__(self, *args: object) -> None:
        """Context manager exit."""
        self.close()


__all__ = ["BaseFredAdapter"]
