"""
fuyao（同花顺开源金融数据 API）HTTP 客户端.

Base URL https://fuyao.aicubes.cn，鉴权头 X-api-key，统一响应信封
ApiResponse：``{code, message, request_id, data}``，业务失败 code != 0
（2001 无效 key、2003 无权限、4001 限流）。时间字段为毫秒 Unix 时间戳，
交易日按 Asia/Shanghai 解释。
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone
from typing import Any, BinaryIO

import httpx
import orjson
from ditto_platform.foundation import logger

from ditto_data.sources.base import SourceConfigurationError, SourceFetchError

# fuyao 文档约定：交易日毫秒戳按 Asia/Shanghai 零点解释
_BEIJING = timezone(timedelta(hours=8))


def ms_to_date(ms: int) -> date:
    """毫秒时间戳（Asia/Shanghai）→ 日期."""
    return datetime.fromtimestamp(ms / 1000, tz=_BEIJING).date()


def date_to_ms(d: date) -> int:
    """日期 → 北京时区零点毫秒时间戳."""
    return int(datetime(d.year, d.month, d.day, tzinfo=_BEIJING).timestamp() * 1000)


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


class FuyaoClient:
    """fuyao REST 客户端 — 信封校验 fail-closed，业务错误即抛 SourceFetchError."""

    def __init__(
        self,
        *,
        base_url: str = "https://fuyao.aicubes.cn",
        api_key: str = "",
        timeout: float = 30.0,
    ) -> None:
        if not api_key:
            raise SourceConfigurationError(
                message="fuyao api key not configured (fuyao_api_key)",
            )
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=timeout,
            headers={"X-api-key": api_key},
        )

    def get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """GET 并校验信封，返回 data 字段；code != 0 一律 fail-closed 抛错."""
        response = self._client.get(path, params=params)
        response.raise_for_status()
        envelope = orjson.loads(response.content)
        code = envelope.get("code")
        if code != 0:
            raise SourceFetchError(
                source="fuyao",
                message=(
                    f"fuyao {path} business error: code={code} "
                    f"message={envelope.get('message')}"
                ),
            )
        data = envelope.get("data")
        if data is None:
            raise SourceFetchError(
                source="fuyao",
                message=f"fuyao {path} returned no data payload",
            )
        logger.debug(
            "Fuyao request success",
            event="fuyao_http_success",
            path=path,
            checked_at=_utc_now_iso(),
        )
        return data

    def download(self, path: str, dest: BinaryIO) -> None:
        """流式下载（预签名 URL 由 get 先获取）到 dest 文件对象."""
        with self._client.stream("GET", path) as response:
            response.raise_for_status()
            for chunk in response.iter_bytes():
                dest.write(chunk)

    def close(self) -> None:
        """释放底层 HTTP 连接."""
        if hasattr(self, "_client"):
            self._client.close()

    def __enter__(self) -> FuyaoClient:
        """支持 with 语句."""
        return self

    def __exit__(self, *args: object) -> None:
        """退出上下文时关闭连接."""
        self.close()
