"""MacroService - Macro domain unified query service."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, ClassVar

import polars as pl
from ditto_infra.foundation import logger, traced

from ditto_data.models.macro import IndicatorMetadataSpec, MacroCategory, MacroFrequency
from ditto_data.storage.macro.indicator.indicator_reader import IndicatorReader
from ditto_data.storage.macro.indicator.indicator_writer import IndicatorWriter
from ditto_data.storage.macro.indicator.metadata_reader import (
    IndicatorMetadataReader,
)
from ditto_data.storage.macro.indicator.metadata_writer import (
    IndicatorMetadataWriter,
)


@dataclass(frozen=True)
class _MacroWriteResult:
    """Internal write result for Macro domain service."""

    records_written: int


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
    category: MacroCategory | None = None
    frequency: MacroFrequency | None = None


class MacroService:
    """
    Macro domain unified query service.

    Provides high-level query API for macro indicator data,
    integrating IndicatorReader/Writer and IndicatorMetadataReader/Writer.

    Follows CQRS pattern with separate Reader and Writer components.
    """

    _WRITE_REQUIRED_COLUMNS: ClassVar[set[str]] = {
        "indicator_code",
        "indicator_name",
        "category",
        "frequency",
        "need_pit",
        "date",
        "value",
    }

    def __init__(
        self,
        indicator_reader: IndicatorReader,
        indicator_writer: IndicatorWriter,
        metadata_reader: IndicatorMetadataReader,
        metadata_writer: IndicatorMetadataWriter,
    ) -> None:
        """
        Initialize MacroService with CQRS Readers and Writers.

        Args:
            indicator_reader: Indicator data reader.
            indicator_writer: Indicator data writer.
            metadata_reader: Indicator metadata reader.
            metadata_writer: Indicator metadata writer.

        """
        self._indicator_reader = indicator_reader
        self._indicator_writer = indicator_writer
        self._metadata_reader = metadata_reader
        self._metadata_writer = metadata_writer

        logger.debug(
            "MacroService initialized with CQRS Readers and Writers",
            event="macro_service_init_complete",
        )

    @traced("macro.save")
    def save_indicators(self, df: pl.DataFrame) -> _MacroWriteResult:
        """Save macro indicator records via unified service contract."""
        missing = self._WRITE_REQUIRED_COLUMNS - set(df.columns)
        if missing:
            msg = f"macro_indicators 写入缺少必要列: {sorted(missing)}"
            raise ValueError(msg)

        if df.is_empty():
            return _MacroWriteResult(records_written=0)

        indicator_mapping = self._upsert_indicator_metadata(df)
        write_df = self._prepare_indicator_records(df, indicator_mapping)
        records_written = self._indicator_writer.write(write_df)

        return _MacroWriteResult(
            records_written=records_written,
        )

    @traced("macro.find")
    def find_indicators(self, query: MacroQuery) -> pl.DataFrame:
        """
        Find macro indicator data via unified service contract.

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
        data_df = self._indicator_reader.get(
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

    def list_indicators(
        self,
        start: str,
        end: str,
        category: MacroCategory | None = None,
    ) -> pl.DataFrame:
        """
        List indicators by date range (convenience method).

        Args:
            start: Start date (YYYY-MM-DD).
            end: End date (YYYY-MM-DD).
            category: Filter by category.

        Returns:
            DataFrame with indicator data including metadata.

        """
        query = MacroQuery(
            start=start,
            end=end,
            category=category,
        )
        return self.find_indicators(query)

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
            metadata = self._metadata_reader.list_by_category(category)
            if frequency:
                metadata = metadata.filter(pl.col("frequency") == frequency)
            return metadata["indicator_id"].to_list()

        # If indicators is a list of codes, resolve to IDs
        if indicators and isinstance(indicators[0], str):
            codes = list(set(indicators))  # Deduplicate
            ids: list[int] = []
            for code in codes:
                # Ensure code is string type
                row = self._metadata_reader.get_by_code(str(code))
                if not row.is_empty():
                    ids.append(int(row["indicator_id"][0]))
            return ids

        # If indicators is already a list of IDs, apply category/frequency filters
        # Cast to list[int] since we know it's not str at this point
        ids = [int(iid) for iid in set(indicators)]  # Deduplicate and ensure int
        if category or frequency:
            # Get all metadata and filter
            all_metadata = self._metadata_reader.list_by_category(category)
            if frequency:
                all_metadata = all_metadata.filter(pl.col("frequency") == frequency)
            valid_ids = set(all_metadata["indicator_id"].to_list())
            return [iid for iid in ids if iid in valid_ids]

        return ids

    def _upsert_indicator_metadata(self, df: pl.DataFrame) -> dict[str, int]:
        metadata_by_code: dict[str, dict[str, Any]] = {}
        for row in df.to_dicts():
            code = str(row["indicator_code"])
            if code not in metadata_by_code:
                metadata_by_code[code] = row

        mapping: dict[str, int] = {}
        for code, row in metadata_by_code.items():
            mapping[code] = self._metadata_writer.upsert(
                IndicatorMetadataSpec(
                    code=code,
                    name=str(row["indicator_name"]),
                    category=MacroCategory(str(row["category"])),
                    frequency=MacroFrequency(str(row["frequency"])),
                    need_pit=bool(row["need_pit"]),
                    source=self._as_optional_text(row.get("source")),
                    unit=self._as_optional_text(row.get("unit")),
                    description=self._as_optional_text(row.get("description")),
                )
            )
        return mapping

    def _prepare_indicator_records(
        self, df: pl.DataFrame, mapping: dict[str, int]
    ) -> pl.DataFrame:
        records: list[dict[str, Any]] = []
        for row in df.to_dicts():
            code = str(row["indicator_code"])
            indicator_id = mapping.get(code)
            if indicator_id is None:
                msg = f"未找到指标代码映射: {code}"
                raise ValueError(msg)
            records.append(
                {
                    "indicator_id": indicator_id,
                    "date": row["date"],
                    "value": row["value"],
                    "knowledge_date": row.get("knowledge_date"),
                }
            )

        write_df = pl.DataFrame(records)
        if "knowledge_date" not in write_df.columns:
            write_df = write_df.with_columns(
                pl.lit(None, dtype=pl.Date).alias("knowledge_date")
            )

        return write_df.with_columns(
            pl.col("indicator_id").cast(pl.Int64),
            pl.col("date").cast(pl.Date),
            pl.col("value").cast(pl.Float64),
            pl.col("knowledge_date").cast(pl.Date),
        )

    @staticmethod
    def _as_optional_text(value: object) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            return value
        if isinstance(value, date):
            return value.isoformat()
        return str(value)

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

        # Batch fetch metadata for all indicators (优化：一次性查询所有元数据)
        metadata_df = pl.DataFrame()
        for iid in indicator_ids:
            row = self._metadata_reader.get_by_id(iid)
            if not row.is_empty():
                if metadata_df.is_empty():
                    metadata_df = row
                else:
                    metadata_df = pl.concat([metadata_df, row])

        if metadata_df.is_empty():
            return df

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
        """
        Close the underlying stores.

        Note: Readers/Writers share SQLite client which should be closed by the owner.
        """
        # Readers/Writers don't own resources, no action needed
        pass
