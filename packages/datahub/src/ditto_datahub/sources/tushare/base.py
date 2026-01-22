"""Tushare source base class."""

from __future__ import annotations

from ditto_foundation import logger

from ditto_datahub.sources.tushare.client import TushareClient


class BaseTushareSource:
    """
    Tushare source base class.

    Provides shared client initialization for all specialized Tushare sources.

    Attributes:
        _client: Tushare API client.

    """

    def __init__(self, token: str | None = None) -> None:
        """
        Initialize Tushare source.

        Args:
            token: API token. Reads from keyring or ~/.ditto/secrets.toml if None.

        """
        self._client = TushareClient(token=token)
        logger.debug(
            f"{self.__class__.__name__} initialized",
            event="tushare_source_init",
        )
