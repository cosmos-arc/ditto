"""Tushare source base class."""

from __future__ import annotations

from ditto_foundation import logger

from ditto_datahub.config import DataSourceSettings
from ditto_datahub.sources.tushare.client import TushareClient


class BaseTushareAdapter:
    """
    Tushare adapter base class.

    Provides shared client initialization for all specialized Tushare adapters.

    Attributes:
        _client: Tushare API client.

    """

    def __init__(
        self,
        token: str | None = None,
        settings: DataSourceSettings | None = None,
        *,
        _client: TushareClient | None = None,
    ) -> None:
        """
        Initialize Tushare adapter.

        Args:
            token: API token. Reads from keyring or ~/.ditto/secrets.toml if None.
            settings: 数据源配置（包含 URL/timeout 等参数）.
            _client: 已存在的 client（用于依赖注入）.

        """
        if _client is not None:
            self._client = _client
        else:
            self._client = TushareClient(token=token, settings=settings)
        logger.debug(
            f"{self.__class__.__name__} initialized",
            event="tushare_adapter_init",
        )
