"""FRED API client with retry and PIT support."""

from __future__ import annotations

import os
from typing import Any

import httpx
import polars as pl
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from ditto_datahub.sources.base import (
    SourceAuthenticationError,
    SourceConfigurationError,
    SourceFetchError,
)

FRED_API_BASE_URL = "https://api.stlouisfed.org/fred"
HTTP_UNAUTHORIZED = 401


class FredClient:
    """
    FRED API client.

    Features:
    - API key authentication from parameter or environment variable
    - Retry with exponential backoff (Tenacity)
    - PIT (Point-in-Time) query support via realtime_start/realtime_end
    - Returns polars DataFrame

    Attributes:
        _api_key: FRED API key.
        _client: HTTPX client instance.

    """

    def __init__(self, api_key: str | None = None) -> None:
        """
        Initialize FRED client.

        Args:
            api_key: FRED API Key. If None, reads from FRED_API_KEY env var.

        Raises:
            SourceConfigurationError: If API key not configured.

        """
        self._api_key = api_key or os.environ.get("FRED_API_KEY")
        if not self._api_key:
            raise SourceConfigurationError(
                message=(
                    "FRED API Key not configured. "
                    "Set FRED_API_KEY env var or pass api_key parameter."
                ),
                env_var="FRED_API_KEY",
            )

        self._client = httpx.Client(
            base_url=FRED_API_BASE_URL,
            timeout=30.0,
        )

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
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(SourceFetchError),
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
            response = self._client.get("/series/observations", params=params)
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == HTTP_UNAUTHORIZED:
                raise SourceAuthenticationError(
                    message="FRED API authentication failed. Check your API key.",
                    source="fred",
                ) from e
            raise SourceFetchError(
                message=f"FRED API request failed: {e.response.status_code}",
                source="fred",
                dataset=series_id,
                original_error=str(e),
            ) from e
        except httpx.RequestError as e:
            raise SourceFetchError(
                message="FRED API network error",
                source="fred",
                dataset=series_id,
                original_error=str(e),
            ) from e

        data = response.json()
        observations = data.get("observations", [])

        if not observations:
            return pl.DataFrame(
                schema={
                    "date": pl.Date,
                    "value": pl.Float64,
                    "realtime_start": pl.Date,
                    "realtime_end": pl.Date,
                }
            )

        df = pl.DataFrame(observations)
        return df.with_columns(
            pl.col("date").str.to_date(strict=False),
            pl.col("value").cast(pl.Float64, strict=False),
            pl.col("realtime_start").str.to_date(strict=False),
            pl.col("realtime_end").str.to_date(strict=False),
        ).select("date", "value", "realtime_start", "realtime_end")
