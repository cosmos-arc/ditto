"""FactorService - Factors domain unified query service."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import polars as pl
from ditto_infra.foundation import logger, traced

from ditto_datahub.stores.factors.factor_metadata_reader import FactorMetadataReader
from ditto_datahub.stores.factors.factor_metadata_writer import FactorMetadataWriter
from ditto_datahub.stores.factors.factor_reader import FactorReader
from ditto_datahub.stores.factors.factor_writer import FactorWriter


@dataclass(frozen=True)
class FactorQuery:
    """
    Factor query parameters.

    Attributes:
        factors: Factor IDs or codes (None = all).
        start: Start date (YYYY-MM-DD).
        end: End date (YYYY-MM-DD).
        as_of: PIT query date - only return data known as of this date.
        factor_classes: Filter by factor class.
        factor_families: Filter by factor family.

    """

    factors: list[int] | list[str] | None = None
    start: str | None = None
    end: str | None = None
    as_of: str | None = None
    factor_classes: (
        list[Literal["fundamental", "technical", "macro", "statistical"]] | None
    ) = None
    factor_families: (
        list[Literal["value", "momentum", "quality", "size", "volatility"]] | None
    ) = None


class FactorService:
    """
    Factors domain unified query service.

    Provides high-level query API for factor data with PIT support,
    integrating FactorReader/FactorWriter and FactorMetadataReader/FactorMetadataWriter.

    Follows CQRS pattern with separate Reader and Writer components.
    """

    def __init__(
        self,
        factor_reader: FactorReader,
        factor_writer: FactorWriter,
        metadata_reader: FactorMetadataReader,
        metadata_writer: FactorMetadataWriter,
    ) -> None:
        """
        Initialize FactorService with CQRS Readers and Writers.

        Args:
            factor_reader: Factor data reader.
            factor_writer: Factor data writer.
            metadata_reader: Factor metadata reader.
            metadata_writer: Factor metadata writer.

        """
        self._factor_reader = factor_reader
        self._factor_writer = factor_writer
        self._metadata_reader = metadata_reader
        self._metadata_writer = metadata_writer

        logger.debug(
            "FactorService initialized with CQRS Readers and Writers",
            event="factor_service_init_complete",
        )

    @traced("factors.find")
    def find_factors(self, query: FactorQuery) -> pl.DataFrame:
        """
        Find factor data via unified service contract (PIT-safe).

        Args:
            query: FactorQuery object with query parameters.

        Returns:
            DataFrame with factor data including metadata.

        """
        logger.debug(
            "Fetching factors",
            event="factors_get_start",
            factors=query.factors,
            start=query.start,
            end=query.end,
            as_of=query.as_of,
            factor_classes=query.factor_classes,
            factor_families=query.factor_families,
        )

        # Query factor data
        # Convert factors to list[str] (accepts both int and str)
        factor_ids_str: list[str] | None = (
            None if query.factors is None else [str(f) for f in query.factors]
        )
        data_df = self._factor_reader.read(
            start_date=query.start,
            end_date=query.end,
            as_of_date=query.as_of,
            factor_ids=factor_ids_str,
        )

        if data_df.is_empty():
            return pl.DataFrame()

        # Apply class/family filters
        if query.factor_classes:
            data_df = data_df.filter(pl.col("factor_class").is_in(query.factor_classes))
        if query.factor_families:
            data_df = data_df.filter(
                pl.col("factor_family").is_in(query.factor_families)
            )

        # Enrich with metadata
        result = self._enrich_with_metadata(data_df)

        logger.debug(
            "Factors fetched",
            event="factors_get_complete",
            row_count=len(result),
        )

        return result

    @traced("factors.list")
    def list_factors(
        self,
        start: str,
        end: str,
        factor_ids: list[str] | None = None,
    ) -> pl.DataFrame:
        """
        List factors by date range (convenience method).

        Convenience wrapper around find_factors() for common use cases.

        Args:
            start: Start date (YYYY-MM-DD).
            end: End date (YYYY-MM-DD).
            factor_ids: Factor IDs to filter (None = all factors).

        Returns:
            DataFrame with factor data including metadata.

        Examples:
            >>> service.list_factors("2024-01-01", "2024-01-31")
            >>> service.list_factors(
            ...     "2024-01-01", "2024-01-31", ["factor_momentum_12m"]
            ... )

        """
        query = FactorQuery(
            start=start,
            end=end,
            factors=factor_ids,
        )
        return self.find_factors(query)

    def _enrich_with_metadata(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Enrich factor data with metadata.

        Args:
            df: Factor data DataFrame.

        Returns:
            Enriched DataFrame with metadata columns.

        """
        # Get unique factor IDs (Note: factor_id in Parquet is a string code
        # like "factor_momentum_12m", not an integer ID. It corresponds to
        # the 'code' column in SQLite metadata store)
        factor_ids = df["factor_id"].unique().to_list()

        # Batch fetch metadata for all factors (优化：一次性查询所有元数据)
        metadata_df = self._metadata_reader.batch_get_by_codes(factor_ids)

        if metadata_df.is_empty():
            return df

        # Join metadata
        result = df.join(
            metadata_df.select(["code", "name", "class", "family", "description"]),
            left_on="factor_id",
            right_on="code",
            how="left",
        )

        return result

    def close(self) -> None:
        """
        Close the underlying stores.

        Note: FactorReader/FactorWriter use Parquet, no close needed.
        The SQLite client from MetadataReader should be closed by the owner.
        """
        # Readers/Writers don't own resources, no action needed
        pass
