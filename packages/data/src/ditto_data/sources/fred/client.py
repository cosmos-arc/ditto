"""FRED API client with retry and PIT support."""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from typing import Any, cast

import httpx
import polars as pl
from polars import exceptions as pl_exceptions
from tenacity import (
    RetryCallState,
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from ditto_data.sources.base import (
    SourceAuthenticationError,
    SourceConfigurationError,
    SourceFetchError,
    SourceRateLimitError,
)
from ditto_data.sources.throttle import MinIntervalThrottle

FRED_API_BASE_URL = "https://api.stlouisfed.org/fred"
HTTP_UNAUTHORIZED = 401
_HTTP_TOO_MANY_REQUESTS = 429

# 官方限速 120 req/min（≈2 req/s），超限先收到 429、持续违反可致 key 封禁
# （https://fred.stlouisfed.org/docs/api/fred/errors.html）。全量日更 ≈51
# 序列突发，默认 0.5s 节流把请求压在限速内；429 仍触发时走专用退避
# （10s 起指数，存在 Retry-After 则优先遵从，上限 120s），与瞬态错误的
# 2-10s 通用退避分离（#516）。
_FRED_DEFAULT_MIN_REQUEST_INTERVAL = 0.5
_TRANSIENT_SERVER_ERRORS = frozenset({500, 502, 503, 504})
_RATE_LIMIT_BACKOFF_BASE_SECONDS = 10.0
_RATE_LIMIT_RETRY_AFTER_CAP_SECONDS = 120.0

_REDACTED_QUERY_VALUE = "%3Credacted%3E"
_SENSITIVE_QUERY_PARAMETER = re.compile(r"(?i)([?&]api_key=)[^&\s\"]+")


class _FREDHTTPLogFilter(logging.Filter):
    """Remove FRED credentials from HTTPX's rendered request URL."""

    def filter(self, record: logging.LogRecord) -> bool:
        """Redact query credentials before any logger handler sees the record."""
        if isinstance(record.args, tuple):
            record.args = tuple(_redact_log_argument(value) for value in record.args)
        elif isinstance(record.args, Mapping):
            record.args = {
                key: _redact_log_argument(value) for key, value in record.args.items()
            }
        return True


def _redact_log_argument(value: object) -> object:
    rendered = str(value)
    if not _SENSITIVE_QUERY_PARAMETER.search(rendered):
        return value
    return _SENSITIVE_QUERY_PARAMETER.sub(
        rf"\1{_REDACTED_QUERY_VALUE}",
        rendered,
    )


def _install_http_log_filter() -> None:
    httpx_logger = logging.getLogger("httpx")
    if not any(isinstance(value, _FREDHTTPLogFilter) for value in httpx_logger.filters):
        httpx_logger.addFilter(_FREDHTTPLogFilter())


class _PermanentFetchError(SourceFetchError):
    """确定性失败（非限流 4xx、200 但响应体非法）——重试无意义，立即抛出."""


def _is_retryable(exc: BaseException) -> bool:
    return isinstance(exc, SourceFetchError | SourceRateLimitError) and not isinstance(
        exc, _PermanentFetchError
    )


_TRANSIENT_WAIT = wait_exponential(multiplier=1, min=2, max=10)


def _decode_observations(
    response: httpx.Response, series_id: str
) -> list[dict[str, Any]]:
    """200 响应体 → observations 列表；非法体（非 JSON/非文档）确定性失败."""
    body: object
    try:
        body = response.json()
    except ValueError as e:
        # 200 但非 JSON（网关/防护页等）：确定性失败，不重试不裸抛（#516）
        raise _PermanentFetchError(
            message="FRED API returned 200 with a non-JSON body",
            source="fred",
            details={"dataset": series_id, "original_error": str(e)},
        ) from e
    observations = (
        cast("dict[str, Any]", body).get("observations")
        if isinstance(body, dict)
        else None
    )
    if not isinstance(observations, list):
        raise _PermanentFetchError(
            message="FRED API response body is not an observations document",
            source="fred",
            details={"dataset": series_id},
        )
    malformed = [
        type(element).__name__
        for element in cast("list[object]", observations)
        if not isinstance(element, dict)
    ]
    if malformed:
        # 标量/混合元素（如 [1,2,3]）会让下游 polars 构造裸抛（#516 评审）
        raise _PermanentFetchError(
            message=(
                f"FRED API observations contain non-object elements: {malformed[:5]}"
            ),
            source="fred",
            details={"dataset": series_id},
        )
    return cast("list[dict[str, Any]]", observations)


def _rate_limit_aware_wait(retry_state: RetryCallState) -> float:
    """429 专用退避（优先 Retry-After）；其余可重试错误沿用指数退避 2-10s."""
    outcome = retry_state.outcome
    error = outcome.exception() if outcome is not None else None
    if isinstance(error, SourceRateLimitError):
        retry_after = error.details.get("retry_after_seconds")
        if (
            isinstance(retry_after, int | float)
            and 0 < retry_after <= _RATE_LIMIT_RETRY_AFTER_CAP_SECONDS
        ):
            return float(retry_after)
        return _RATE_LIMIT_BACKOFF_BASE_SECONDS * 2 ** max(
            0, retry_state.attempt_number - 1
        )
    return _TRANSIENT_WAIT(retry_state)


class FredClient:
    """
    FRED API client.

    Features:
    - API key authentication from parameter or environment variable
    - Client-side throttling to the official 2 req/s limit (#516)
    - Retry with exponential backoff (Tenacity); 429 gets dedicated
      longer backoff honoring Retry-After, deterministic 4xx fails fast
    - PIT (Point-in-Time) query support via realtime_start/realtime_end
    - Returns polars DataFrame

    Attributes:
        _api_key: FRED API key.
        _client: HTTPX client instance.
        _throttle: 请求起点间隔节流器（官方 2 req/s，0 禁用）.

    """

    def __init__(
        self,
        api_key: str | None = None,
        *,
        min_request_interval: float | None = None,
    ) -> None:
        """
        Initialize FRED client.

        Args:
            api_key: FRED API Key（由 DataSourceSettings.fred_api_key 注入）.
            min_request_interval: 相邻请求起点最小间隔（秒）；None 取模块
                默认 0.5（官方 2 req/s），0 显式禁用（测试用）.

        Raises:
            SourceConfigurationError: If API key not configured.

        """
        # 唯一配置入口（#433）：DITTO_CONFIG_ROOT 配置经 backend config loader
        # 汇入 DataSourceSettings 注入；数据层不读环境变量，避免第二入口。
        self._api_key = api_key
        if not self._api_key:
            raise SourceConfigurationError(
                message=(
                    "FRED API Key not configured. "
                    "Set FRED_API_KEY in the DITTO_CONFIG_ROOT data_source "
                    "config (or keyring); it is injected via "
                    "DataSourceSettings.fred_api_key."
                ),
                env_var="FRED_API_KEY",
            )
        self._throttle = MinIntervalThrottle(
            _FRED_DEFAULT_MIN_REQUEST_INTERVAL
            if min_request_interval is None
            else min_request_interval
        )

        _install_http_log_filter()
        self._client = httpx.Client(
            base_url=FRED_API_BASE_URL,
            timeout=30.0,
        )

    @staticmethod
    def _rate_limit_error(http_error: httpx.HTTPStatusError) -> SourceRateLimitError:
        """429 → SourceRateLimitError，携带 Retry-After（存在且为秒数时）."""
        error = SourceRateLimitError(
            message="FRED API rate limit exceeded (429)",
            source="fred",
            limit=2,
            window=1,
        )
        retry_after = http_error.response.headers.get("Retry-After", "")
        if retry_after.isdigit():
            error.details["retry_after_seconds"] = int(retry_after)
        return error

    def close(self) -> None:
        """Close HTTP client and release resources."""
        if hasattr(self, "_client"):
            self._client.close()

    def __enter__(self) -> FredClient:
        """Context manager entry."""
        return self

    def __exit__(self, *args: object) -> None:
        """Context manager exit."""
        self.close()

    @retry(
        stop=stop_after_attempt(3),
        wait=_rate_limit_aware_wait,
        retry=retry_if_exception(_is_retryable),
    )
    def get_series_observations(
        self,
        series_id: str,
        observation_start: str,
        observation_end: str,
        *,
        realtime_start: str | None = None,
        realtime_end: str | None = None,
    ) -> pl.DataFrame:
        """
        Fetch series observations from FRED API.

        Args:
            series_id: FRED series ID (e.g., "UNRATE", "GDP").
            observation_start: Start date (YYYY-MM-DD).
            observation_end: End date (YYYY-MM-DD).
            realtime_start: PIT parameter - only return data known by this date.
            realtime_end: PIT parameter - only return data known by this date.

        Returns:
            DataFrame with columns: date, value, realtime_start, realtime_end

        Raises:
            SourceAuthenticationError: If API key is invalid.
            SourceFetchError: If request fails after retries.

        """
        params: dict[str, Any] = {
            "series_id": series_id,
            "api_key": self._api_key,
            "observation_start": observation_start,
            "observation_end": observation_end,
            "file_type": "json",
        }

        # PIT parameters (for ALFRED mode)
        if realtime_start:
            params["realtime_start"] = realtime_start
        if realtime_end:
            params["realtime_end"] = realtime_end

        try:
            self._throttle.wait()
            response = self._client.get("/series/observations", params=params)
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            if status == HTTP_UNAUTHORIZED:
                raise SourceAuthenticationError(
                    message="FRED API authentication failed. Check your API key.",
                    source="fred",
                ) from e
            if status == _HTTP_TOO_MANY_REQUESTS:
                raise self._rate_limit_error(e) from e
            if status not in _TRANSIENT_SERVER_ERRORS:
                # 400/404 等确定性 4xx：重试不会改变结果（#508 调研缺陷）
                raise _PermanentFetchError(
                    message=f"FRED API request failed: {status}",
                    source="fred",
                    details={"dataset": series_id, "original_error": str(e)},
                ) from e
            raise SourceFetchError(
                message=f"FRED API request failed: {status}",
                source="fred",
                details={"dataset": series_id, "original_error": str(e)},
            ) from e
        except httpx.RequestError as e:
            raise SourceFetchError(
                message="FRED API network error",
                source="fred",
                details={"dataset": series_id, "original_error": str(e)},
            ) from e

        observations = _decode_observations(response, series_id)

        if not observations:
            return pl.DataFrame(
                schema={
                    "date": pl.Date,
                    "value": pl.Float64,
                    "realtime_start": pl.Date,
                    "realtime_end": pl.Date,
                }
            )

        try:
            df = pl.DataFrame(observations)
            return df.with_columns(
                pl.col("date").str.to_date(strict=False),
                pl.col("value").cast(pl.Float64, strict=False),
                pl.col("realtime_start").str.to_date(strict=False),
                pl.col("realtime_end").str.to_date(strict=False),
            ).select("date", "value", "realtime_start", "realtime_end")
        except (pl_exceptions.PolarsError, TypeError, KeyError) as e:
            # 缺键/异构行等形态违约：包装为确定性失败，不留 polars 裸抛（#516）
            raise _PermanentFetchError(
                message="FRED API observations have a malformed element shape",
                source="fred",
                details={"dataset": series_id, "original_error": str(e)},
            ) from e
