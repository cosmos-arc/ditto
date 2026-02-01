"""MacroService - Macro domain unified query service."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import polars as pl
from ditto_foundation import logger, traced

from ditto_datahub.domains.macro.indicator.indicator_store import IndicatorStore
from ditto_datahub.domains.macro.indicator.metadata_store import IndicatorMetadataStore


@dataclass(frozen=True)
class MacroQuery:
    """
    Macro indicator query parameters.

    Attributes:
        indicators: Indicator IDs or codes (None = all).
        start: Start date (YYYY-MM-DD).
        end: End date (YYYY-MM-DD).
        asof: PIT query date - only return data known as of this date.
        category: Filter by category.
        frequency: Filter by frequency.

    """

    indicators: list[int] | list[str] | None = None
    start: str | None = None
    end: str | None = None
    asof: str | None = None
    category: (
        Literal["economic", "interest_rate", "exchange_rate", "money_supply"] | None
    ) = None
    frequency: Literal["daily", "monthly", "quarterly"] | None = None


class MacroService:
    """
    Macro domain unified query service.

    Provides high-level query API for macro indicator data,
    integrating IndicatorStore and IndicatorMetadataStore.
    """

    def __init__(
        self,
        indicator_store: IndicatorStore,
        metadata_store: IndicatorMetadataStore,
    ) -> None:
        """
        Initialize MacroService.

        Args:
            indicator_store: Indicator data storage.
            metadata_store: Indicator metadata storage.

        """
        self._indicator_store = indicator_store
        self._metadata_store = metadata_store

        logger.debug(
            "MacroService initialized",
            event="macro_service_init_complete",
        )

    @traced("macro.get_indicators")
    def get_indicators(self, query: MacroQuery) -> pl.DataFrame:
        """
        Query macro indicator data.

        Args:
            query: MacroQuery object with query parameters.

        Returns:
            DataFrame with indicator data including metadata.

        """
        logger.debug(
            "Fetching macro indicators",
            event="macro_indicators_get_start",
            indicators=query.indicators,
            start=query.start,
            end=query.end,
            asof=query.asof,
            category=query.category,
            frequency=query.frequency,
        )

        # Step 1: Resolve indicator IDs from codes
        indicator_ids = self._resolve_indicator_ids(
            query.indicators, query.category, query.frequency
        )

        if not indicator_ids:
            return pl.DataFrame()

        # Step 2: Query indicator data
        data_df = self._indicator_store.get(
            indicator_ids=indicator_ids,
            start_date=query.start,
            end_date=query.end,
            as_of_date=query.asof,
        )

        if data_df.is_empty():
            return pl.DataFrame()

        # Step 3: Enrich with metadata
        result = self._enrich_with_metadata(data_df)

        logger.debug(
            "Macro indicators fetched",
            event="macro_indicators_get_complete",
            row_count=len(result),
        )

        return result

    def _resolve_indicator_ids(
        self,
        indicators: list[int] | list[str] | None,
        category: str | None = None,
        frequency: str | None = None,
    ) -> list[int]:
        """
        Resolve indicator IDs from codes or filter by metadata.

        Args:
            indicators: List of indicator IDs or codes.
            category: Filter by category.
            frequency: Filter by frequency.

        Returns:
            List of indicator IDs.

        """
        # If indicators is None, get all indicators (filtered by category/frequency)
        if indicators is None:
            metadata = self._metadata_store.list_by_category(category)
            if frequency:
                metadata = metadata.filter(pl.col("frequency") == frequency)
            return metadata["indicator_id"].to_list()

        # If indicators is a list of codes, resolve to IDs
        if indicators and isinstance(indicators[0], str):
            codes = list(set(indicators))  # Deduplicate
            ids: list[int] = []
            for code in codes:
                # Ensure code is string type
                row = self._metadata_store.get_by_code(str(code))
                if not row.is_empty():
                    ids.append(int(row["indicator_id"][0]))
            return ids

        # If indicators is already a list of IDs, apply category/frequency filters
        # Cast to list[int] since we know it's not str at this point
        ids = [int(iid) for iid in set(indicators)]  # Deduplicate and ensure int
        if category or frequency:
            # Get all metadata and filter
            all_metadata = self._metadata_store.list_by_category(category)
            if frequency:
                all_metadata = all_metadata.filter(pl.col("frequency") == frequency)
            valid_ids = set(all_metadata["indicator_id"].to_list())
            return [iid for iid in ids if iid in valid_ids]

        return ids

    def _enrich_with_metadata(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Enrich indicator data with metadata.

        Args:
            df: Indicator data DataFrame.

        Returns:
            Enriched DataFrame with metadata columns.

        """
        # Get unique indicator IDs
        indicator_ids = df["indicator_id"].unique().to_list()

        # Fetch metadata for all indicators
        metadata_rows: list[pl.DataFrame] = []
        for iid in indicator_ids:
            row = self._metadata_store.get_by_id(iid)
            if not row.is_empty():
                metadata_rows.append(row)

        if not metadata_rows:
            return df

        metadata_df: pl.DataFrame = pl.concat(metadata_rows)

        # Join metadata
        result = df.join(
            metadata_df.select(
                ["indicator_id", "code", "name", "category", "frequency", "unit"]
            ),
            on="indicator_id",
            how="left",
        )

        return result

    def close(self) -> None:
        """Close the underlying stores."""
        self._indicator_store.close()
        self._metadata_store.close()
