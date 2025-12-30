"""Tushare API client with rate limiting and retry."""

from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any

# NOTE: Tushare API returns pandas DataFrame natively.
# We import pandas here for API compatibility, then convert to polars in source.py.
import pandas as pd
from ditto_foundation import logger
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)
from tushare import pro_api

from ditto_datahub.sources.base import (
    SourceAuthenticationError,
    SourceConfigurationError,
    SourceFetchError,
    SourceRateLimitError,
)
from ditto_datahub.sources.tushare.rate_limiter import (
    TushareAPIGroup,
    TushareRateLimitConfig,
    TushareRateLimiter,
)


class _TushareRetryableError(Exception):
    """Internal: Marker for retryable Tushare errors."""

    pass


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
            rate_config: 限流配置（默认免费账户）.

        Raises:
            SourceConfigurationError: If token not found.

        """
        # Get token with fallback chain
        self._token = _get_tushare_token(token)

        # 配置限流器（默认免费账户）
        config = rate_config or TushareRateLimitConfig.free()
        self._limiter = TushareRateLimiter(config)

        # Initialize Tushare API
        self._api = pro_api(token=self._token)

        logger.debug(
            "TushareClient initialized with limits library",
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

    def _is_retryable_error(self, error: Exception) -> bool:
        """Check if error is retryable."""
        error_msg = str(error)

        # Authentication errors - not retryable
        if any(keyword in error_msg for keyword in ["权限", "认证"]):
            return False

        # Rate limit errors - retryable
        if any(keyword in error_msg for keyword in ["每分钟", "流量"]):
            return True

        # Network errors - retryable
        return isinstance(error, TimeoutError | ConnectionError)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(_TushareRetryableError),
    )
    def query(
        self,
        api_name: str,
        fields: str | None = None,
        **params: Any,
    ) -> pd.DataFrame:
        """
        Query Tushare API with rate limiting and retry.

        NOTE: Returns pandas DataFrame because Tushare API returns it natively.
        The result will be converted to polars DataFrame in source.py.

        Args:
            api_name: API name (e.g., "trade_cal", "daily").
            fields: Comma-separated field names.
            **params: API parameters.

        Returns:
            API response data.

        Raises:
            SourceRateLimitError: If rate limit exceeded after retries.
            SourceAuthenticationError: If authentication fails.
            SourceFetchError: If query fails after retries.

        """
        # 确定分组并进行限流检查
        group = self._get_api_group(api_name)
        self._limiter.wait_if_needed(group)

        try:
            logger.debug(
                "Tushare API query",
                event="tushare_query_start",
                api_name=api_name,
            )

            response = self._api.query(
                api_name=api_name,
                fields=fields,
                **params,
            )

            logger.debug(
                "Tushare API query success",
                event="tushare_query_success",
                api_name=api_name,
            )

            return response

        except Exception as e:
            error_msg = str(e)

            # Check for specific error types
            if self._is_retryable_error(e):
                logger.warning(
                    "Tushare retryable error, will retry",
                    event="tushare_retry",
                    error=error_msg,
                )
                raise _TushareRetryableError() from e

            # Authentication errors
            if any(keyword in error_msg for keyword in ["权限", "认证"]):
                logger.error(
                    "Tushare authentication failed",
                    event="tushare_auth_error",
                    error=error_msg,
                )
                raise SourceAuthenticationError(
                    message="Tushare authentication failed",
                    source="tushare",
                ) from e

            # Other errors
            raise SourceFetchError(
                message="Tushare query failed",
                source="tushare",
                dataset=api_name,
                original_error=error_msg,
            ) from e
