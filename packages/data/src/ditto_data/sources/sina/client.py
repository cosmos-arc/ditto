"""
新浪外盘期货 HTTP client — JSONP 端点，匿名无 key（#436）.

免费公开、无 SLA：最小超时 + 有限重试；源故障抛 SourceFetchError，
由复合源合同显式报错（不得静默跳过）。
"""

from __future__ import annotations

import httpx
import orjson
from ditto_platform.foundation import logger
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from ditto_data.sources.base import SourceFetchError

_PATH = (
    "/futures/api/jsonp.php/var%20_S=/GlobalFuturesService.getGlobalFuturesDailyKLine"
)


class SinaClient:
    """新浪 GlobalFuturesService.getGlobalFuturesDailyKLine 客户端."""

    def __init__(self, base_url: str, timeout: float = 15.0) -> None:
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=timeout,
            headers={"Content-Type": "application/json"},
        )

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=1, max=5),
        retry=retry_if_exception_type(SourceFetchError),
        reraise=True,
    )
    def get_global_futures_daily_kline(self, symbol: str) -> list[dict[str, str]]:
        """
        取回一个品种的日线全量当前视图（端点无窗口参数）.

        Returns:
            原始行列表（字段值为字符串）。

        Raises:
            SourceFetchError: HTTP 失败或 JSONP 解析失败。

        """
        try:
            response = self._client.get(
                _PATH, params={"symbol": symbol, "source": "web"}
            )
            response.raise_for_status()
            payload = response.text
            start = payload.index("(")
            end = payload.rindex(")")
            if start >= end:
                msg = f"sina JSONP payload has no parenthesized body: {symbol}"
                raise SourceFetchError(message=msg, source="sina")
            rows = orjson.loads(payload[start + 1 : end])
        except SourceFetchError:
            raise
        except Exception as exc:
            raise SourceFetchError(
                message=f"sina foreign futures fetch failed for {symbol}: {exc}",
                source="sina",
                cause=exc,
            ) from exc
        logger.debug(
            "Sina foreign futures fetched",
            event="sina_foreign_futures_fetch",
            symbol=symbol,
            rows=len(rows),
        )
        return rows

    def close(self) -> None:
        """释放 HTTP 连接资源."""
        self._client.close()
