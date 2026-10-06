"""
fuyao（同花顺开源金融数据 API）HTTP 客户端.

Base URL https://fuyao.aicubes.cn，鉴权头 X-api-key，统一响应信封
ApiResponse：``{code, message, request_id, data}``，业务失败 code != 0
（2001 无效 key、2003 无权限、4001 限流）。时间字段为毫秒 Unix 时间戳，
交易日按 Asia/Shanghai 解释。

限流（官方 llms.txt「调用频率与限流」）：不限累计次数，策略按服务端负载
动态调整，HTTP 429 与 code=4001 均表示触发限流，官方建议降低频率、避免
立即连续重试。宽基对账逐标的串行连发数千请求（#508）——默认 0.1s 节流，
触发限流时间隔 ×2 自适应上升（封顶 2s），并按 2s/4s/8s 退避重试至多 3 次；
重试耗尽仍以 SourceFetchError fail-closed（对账按标的隔离语义不变）.
"""

from __future__ import annotations

import time
from datetime import UTC, date, datetime, timedelta, timezone
from typing import Any, BinaryIO, cast

import httpx
import orjson
from ditto_platform.foundation import logger

from ditto_data.sources.base import SourceConfigurationError, SourceFetchError

# fuyao 文档约定：交易日毫秒戳按 Asia/Shanghai 零点解释
_BEIJING = timezone(timedelta(hours=8))

# 限流治理常量（#516）：间隔/退避均可在测试中注入或 monkeypatch
FUYAO_DEFAULT_MIN_REQUEST_INTERVAL = 0.1
_FUYAO_MAX_REQUEST_INTERVAL = 2.0
_FUYAO_RATE_LIMIT_CODE = 4001
_FUYAO_HTTP_TOO_MANY_REQUESTS = 429
_FUYAO_RATE_LIMIT_RETRIES = 3
_FUYAO_RATE_LIMIT_BACKOFF_BASE_SECONDS = 2.0


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
        min_request_interval: float | None = None,
    ) -> None:
        if not api_key:
            raise SourceConfigurationError(
                message=(
                    "fuyao api key not configured: set FUYAO_API_KEY in the "
                    "DITTO_CONFIG_ROOT data_source config (injected via "
                    "DataSourceSettings.fuyao_api_key); the data layer does "
                    "not read environment variables (#433)"
                ),
            )
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=timeout,
            headers={"X-api-key": api_key},
        )
        self._min_request_interval = (
            FUYAO_DEFAULT_MIN_REQUEST_INTERVAL
            if min_request_interval is None
            else max(0.0, min_request_interval)
        )
        self._last_request_monotonic: float | None = None

    def _throttle(self) -> None:
        """把相邻请求起点间隔压到当前最小间隔以内（限流后自适应上升）."""
        if self._min_request_interval <= 0:
            return
        now = time.monotonic()
        if self._last_request_monotonic is not None:
            remaining = self._min_request_interval - (
                now - self._last_request_monotonic
            )
            if remaining > 0:
                time.sleep(remaining)
        self._last_request_monotonic = time.monotonic()

    def _backoff_for_rate_limit(self, path: str, attempt: int, *, origin: str) -> None:
        """限流后退避（官方：避免立即连续重试），并把节流间隔翻倍封顶 2s."""
        wait_seconds = _FUYAO_RATE_LIMIT_BACKOFF_BASE_SECONDS * 2**attempt
        if self._min_request_interval > 0:
            self._min_request_interval = min(
                self._min_request_interval * 2, _FUYAO_MAX_REQUEST_INTERVAL
            )
        logger.warning(
            "Fuyao rate limit hit, backing off before retry",
            event="fuyao_rate_limit_backoff",
            path=path,
            origin=origin,
            attempt=attempt + 1,
            wait_seconds=wait_seconds,
            next_min_request_interval=self._min_request_interval,
        )
        time.sleep(wait_seconds)

    def _get_envelope(self, path: str, params: dict[str, Any] | None) -> dict[str, Any]:
        """单次到多次限流退避的 GET，返回原始信封 dict（不校验业务码）."""
        attempt = 0
        while True:
            self._throttle()
            try:
                response = self._client.get(path, params=params)
                response.raise_for_status()
            except httpx.HTTPStatusError as e:
                status = e.response.status_code
                if (
                    status == _FUYAO_HTTP_TOO_MANY_REQUESTS
                    and attempt < _FUYAO_RATE_LIMIT_RETRIES
                ):
                    self._backoff_for_rate_limit(path, attempt, origin=f"http_{status}")
                    attempt += 1
                    continue
                raise SourceFetchError(
                    source="fuyao",
                    message=(
                        f"fuyao {path} http error: {status} {e.response.text[:200]}"
                    ),
                ) from e
            try:
                envelope: object = orjson.loads(response.content)
            except ValueError as e:
                raise SourceFetchError(
                    source="fuyao",
                    message=f"fuyao {path} returned a non-JSON body",
                ) from e
            if not isinstance(envelope, dict):
                raise SourceFetchError(
                    source="fuyao",
                    message=f"fuyao {path} returned a non-object JSON envelope",
                )
            typed_envelope = cast("dict[str, Any]", envelope)
            if (
                typed_envelope.get("code") == _FUYAO_RATE_LIMIT_CODE
                and attempt < _FUYAO_RATE_LIMIT_RETRIES
            ):
                self._backoff_for_rate_limit(path, attempt, origin="code_4001")
                attempt += 1
                continue
            return typed_envelope

    def get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """GET 并校验信封，返回 data 字段；code != 0 一律 fail-closed 抛错."""
        envelope = self._get_envelope(path, params)
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
