"""Tushare API client with rate limiting and retry."""

from __future__ import annotations

import httpx
import polars as pl
from ditto_foundation import logger
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from ditto_datahub.config import DataSourceSettings
from ditto_datahub.sources.base import (
    SourceConfigurationError,
    SourceFetchError,
)
from ditto_datahub.sources.tushare.utils.http_utils import (
    map_http_error,
    response_to_dataframe,
    validate_tushare_response,
)
from ditto_datahub.sources.tushare.utils.rate_limiter import (
    TushareAPIGroup,
    TushareRateLimitConfig,
    TushareRateLimiter,
)


def _get_tushare_token(token: str | None) -> str:
    """Resolve Tushare token from explicit input/settings."""
    if token:
        logger.debug(
            "Token loaded from parameter",
            event="token_loaded",
            source="parameter",
        )
        return token

    raise SourceConfigurationError(
        message=(
            "Tushare token not configured. Provide token via settings or parameter."
        )
    )


class TushareClient:
    """
    Tushare Pro API client.

    Features:
    - Token authentication from settings or explicit parameter
    - Multi-level rate limiting using limits library
    - Retry with exponential backoff (Tenacity)
    - Error handling and logging
    - Configurable via DataSourceSettings

    Attributes:
        _token: Tushare API token.
        _limiter: Rate limiter instance.
        _settings: Data source configuration.

    """

    def __init__(
        self,
        settings: DataSourceSettings,
        token: str | None = None,
        rate_config: TushareRateLimitConfig | None = None,
    ) -> None:
        """
        Initialize Tushare client.

        Args:
            settings: 数据源配置，包含 URL/timeout 等参数.
            token: API token（可选，优先于 settings 中的 token）。
            rate_config: 限流配置(默认免费账户).

        Raises:
            SourceConfigurationError: If token not found.

        """
        # 存储 settings
        self._settings = settings

        # Get token with fallback chain
        # 优先使用 settings 中的 token（如果设置）
        token_to_use = token or self._settings.tushare_token or None
        self._token = _get_tushare_token(token_to_use if token_to_use else None)

        # 配置限流器(默认免费账户)
        config = rate_config or TushareRateLimitConfig.free()
        self._limiter = TushareRateLimiter(config)

        # Initialize HTTP client with settings
        self._client = httpx.Client(
            base_url=self._settings.http_base_url,
            timeout=self._settings.http_timeout,
            headers={"Content-Type": "application/json"},
        )

        logger.debug(
            "TushareClient initialized",
            event="tushare_client_init",
            base_url=self._settings.http_base_url,
            timeout=self._settings.http_timeout,
            rate_config=config,
        )

    def _get_api_group(self, api_name: str) -> TushareAPIGroup:
        """根据 API 名称返回分组."""
        if api_name in ["daily", "weekly", "monthly"]:
            return TushareAPIGroup.DAILY
        elif api_name.startswith("f_") or api_name.startswith("adj"):
            return TushareAPIGroup.DERIVED
        elif api_name in ["trade_cal", "pro_bar", "stock_basic"]:
            return TushareAPIGroup.BASIC
        else:
            return TushareAPIGroup.SPECIAL

    def _query(
        self,
        api_name: str,
        fields: str,
        **params: str | int,
    ) -> dict[str, object]:
        """
        执行 HTTP 查询并返回原始 JSON。

        Args:
            api_name: API 名称
            fields: 逗号分隔的字段名
            **params: API 参数

        Returns:
            Tushare API 响应的 data 字段

        Raises:
            SourceAuthenticationError: 认证失败
            SourceRateLimitError: 限流
            SourceFetchError: 其他错误

        """
        # 确定分组并进行限流检查
        group = self._get_api_group(api_name)
        self._limiter.wait_if_needed(group)

        try:
            logger.debug(
                "Tushare HTTP request",
                event="tushare_http_request",
                api_name=api_name,
            )

            # 构建请求体
            request_body = {
                "api_name": api_name,
                "token": self._token,
                "params": params,
                "fields": fields,
            }

            # 发送 HTTP POST 请求
            response = self._client.post("/", json=request_body)

            # 检查 HTTP 状态码 (会针对 4xx/5xx 抛出 HTTPStatusError)
            response.raise_for_status()

            # 解析 JSON
            response_json = response.json()

            # 验证响应并返回 data 字段
            data = validate_tushare_response(response_json)

            logger.debug(
                "Tushare HTTP request success",
                event="tushare_http_success",
                api_name=api_name,
            )

            return data

        except httpx.HTTPStatusError as e:
            # HTTP 状态码错误,映射到相应异常
            map_http_error(e, api_name)

        except (httpx.NetworkError, httpx.TimeoutException) as e:
            # 网络错误和超时,映射到 SourceFetchError
            map_http_error(e, api_name)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(SourceFetchError),
    )
    def query(
        self,
        api_name: str,
        fields: str,
        **params: str | int,
    ) -> pl.DataFrame:
        """
        Query Tushare API with rate limiting and retry.

        Args:
            api_name: API name (e.g., "trade_cal", "daily").
            fields: Comma-separated field names.
            **params: API parameters.

        Returns:
            polars DataFrame

        Raises:
            SourceRateLimitError: If rate limit exceeded after retries.
            SourceAuthenticationError: If authentication fails.
            SourceFetchError: If query fails after retries.

        """
        # 调用内部 _query 方法获取原始数据
        data = self._query(api_name, fields, **params)

        # 转换为 polars DataFrame
        return response_to_dataframe(data)

    def close(self) -> None:
        """
        显式关闭 HTTP 客户端.

        释放网络资源，推荐在 with 语句中使用或手动调用。
        """
        if hasattr(self, "_client"):
            self._client.close()

    def __enter__(self) -> TushareClient:
        """支持上下文管理器协议（with 语句）。"""
        return self

    def __exit__(self, *args: object) -> None:
        """退出上下文时关闭 HTTP 客户端."""
        self.close()

    def __del__(self) -> None:
        """清理 HTTP 客户端."""
        if hasattr(self, "_client"):
            self._client.close()
