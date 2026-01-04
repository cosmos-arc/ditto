"""Tushare API client with rate limiting and retry."""

from __future__ import annotations

import os
import tomllib
from pathlib import Path

import httpx
import polars as pl
from ditto_foundation import logger
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from ditto_datahub.sources.base import (
    SourceConfigurationError,
    SourceFetchError,
    SourceRateLimitError,
)
from ditto_datahub.sources.tushare.http_utils import (
    map_http_error,
    response_to_dataframe,
    validate_tushare_response,
)
from ditto_datahub.sources.tushare.rate_limiter import (
    TushareAPIGroup,
    TushareRateLimitConfig,
    TushareRateLimiter,
)


def _get_tushare_token(token: str | None = None) -> str:
    """
    Get Tushare token with graceful fallback.

    Priority order:
    1. Provided token parameter
    2. keyring (recommended)
    3. ~/.ditto/secrets.toml (fallback)
    4. TUSHARE_TOKEN env var (legacy)

    Args:
        token: Explicitly provided token.

    Returns:
        str: The Tushare API token.

    Raises:
        SourceConfigurationError: If token not found in any source.

    """
    # 1. Explicit parameter
    if token:
        logger.debug(
            "Token loaded from parameter",
            event="token_loaded",
            source="parameter",
        )
        return token

    # 2. Try keyring (recommended)
    try:
        import keyring

        if keyring_token := keyring.get_password("ditto", "tushare"):
            # keyring.get_password returns str | None
            assert isinstance(keyring_token, str)
            logger.debug(
                "Token loaded from keyring",
                event="token_loaded",
                source="keyring",
            )
            return keyring_token
    except Exception:
        # keyring may not be available or configured, silently continue
        pass

    # 3. Try ~/.ditto/secrets.toml (fallback)
    config_file = Path.home() / ".ditto" / "secrets.toml"
    if config_file.exists():
        try:
            config = tomllib.loads(config_file.read_text())
            if config_token := config.get("tushare", {}).get("token"):
                assert isinstance(config_token, str)
                logger.debug(
                    "Token loaded from secrets.toml",
                    event="token_loaded",
                    source="secrets.toml",
                )
                return config_token
        except Exception:
            pass

    # 4. Try TUSHARE_TOKEN env var (legacy)
    if env_token := os.getenv("TUSHARE_TOKEN"):
        assert env_token is not None
        logger.debug(
            "Token loaded from env var",
            event="token_loaded",
            source="env_var",
        )
        return env_token

    # No token found
    raise SourceConfigurationError(
        message=(
            "Tushare token not configured. "
            "Use keyring: keyring.set_password('ditto', 'tushare', 'YOUR_TOKEN') "
            "or create ~/.ditto/secrets.toml with [tushare] token = 'YOUR_TOKEN'"
        )
    )


class TushareClient:
    """
    Tushare Pro API client.

    Features:
    - Token authentication from keyring/secrets.toml/env
    - Multi-level rate limiting using limits library
    - Retry with exponential backoff (Tenacity)
    - Error handling and logging

    Attributes:
        _token: Tushare API token.
        _limiter: Rate limiter instance.

    """

    def __init__(
        self,
        token: str | None = None,
        rate_config: TushareRateLimitConfig | None = None,
    ) -> None:
        """
        Initialize Tushare client.

        Args:
            token: API token (auto-detected if None).
            rate_config: 限流配置(默认免费账户).

        Raises:
            SourceConfigurationError: If token not found.

        """
        # Get token with fallback chain
        self._token = _get_tushare_token(token)

        # 配置限流器(默认免费账户)
        config = rate_config or TushareRateLimitConfig.free()
        self._limiter = TushareRateLimiter(config)

        # Initialize HTTP client
        self._client = httpx.Client(
            base_url="http://api.tushare.pro",
            timeout=30.0,
            headers={"Content-Type": "application/json"},
        )

        logger.debug(
            "TushareClient initialized with HTTP client",
            event="tushare_client_init",
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

    def __del__(self) -> None:
        """清理 HTTP 客户端."""
        if hasattr(self, "_client"):
            self._client.close()
