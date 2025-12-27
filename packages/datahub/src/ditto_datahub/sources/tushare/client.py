"""Tushare API client with rate limiting and retry."""

from __future__ import annotations

import os
import time
import tomllib
from pathlib import Path
from threading import Lock
from typing import Any

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
    - Token authentication from TUSHARE_TOKEN env var
    - Rate limiting (200 requests/minute default)
    - Retry with exponential backoff (Tenacity)
    - Error handling and logging

    Attributes:
        _token: Tushare API token.
        _rate_limit: Max requests per time window.
        _window_seconds: Time window in seconds.
        _max_retries: Max retry attempts.
        _retry_backoff: Backoff multiplier.

    """

    def __init__(
        self,
        token: str | None = None,
        rate_limit: int = 200,
        window_seconds: int = 60,
        max_retries: int = 3,
        retry_backoff: float = 1.5,
    ) -> None:
        """
        Initialize Tushare client.

        Args:
            token: API token (auto-detected from keyring/secrets.toml/env if None).
            rate_limit: Max requests per window.
            window_seconds: Time window for rate limit.
            max_retries: Max retry attempts.
            retry_backoff: Exponential backoff multiplier.

        Raises:
            SourceConfigurationError: If token not found.

        """
        # Get token with fallback chain
        self._token = _get_tushare_token(token)

        # Configuration
        self._rate_limit = rate_limit
        self._window_seconds = window_seconds
        self._max_retries = max_retries
        self._retry_backoff = retry_backoff

        # Rate limiting state
        self._request_count = 0
        self._window_start = time.time()
        self._lock = Lock()

        # Initialize Tushare API
        self._api = pro_api(token=self._token)

        logger.debug(
            "TushareClient initialized",
            event="tushare_client_init",
            rate_limit=rate_limit,
            window_seconds=window_seconds,
        )

    def _check_rate_limit(self) -> None:
        """Block if rate limit exceeded (thread-safe)."""
        with self._lock:
            now = time.time()
            elapsed = now - self._window_start

            # Reset if window expired
            if elapsed >= self._window_seconds:
                self._request_count = 0
                self._window_start = now
                elapsed = 0

            # Wait if limit exceeded
            if self._request_count >= self._rate_limit:
                wait_time = self._window_seconds - elapsed
                logger.debug(
                    "Rate limit reached, waiting",
                    event="rate_limit_wait",
                    wait_seconds=wait_time,
                )
                time.sleep(wait_time)
                self._request_count = 0
                self._window_start = time.time()

            self._request_count += 1

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
        # Enforce rate limiting
        self._check_rate_limit()

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
