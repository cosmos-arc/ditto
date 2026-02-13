"""
FeatureService - Features domain unified service.

Features 域统一查询服务,集成技术指标数据和元数据查询.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import polars as pl
from ditto_infra.foundation import logger, traced

from ditto_datahub.stores.features.technical.technical_indicator_metadata_reader import (  # noqa: E501
    TechnicalIndicatorMetadataReader,
)
from ditto_datahub.stores.features.technical.technical_indicator_metadata_writer import (  # noqa: E501
    TechnicalIndicatorMetadataWriter,
)
from ditto_datahub.stores.features.technical.technical_indicator_reader import (
    TechnicalIndicatorReader,
)
from ditto_datahub.stores.features.technical.technical_indicator_writer import (
    TechnicalIndicatorWriter,
)


@dataclass(frozen=True)
class FeatureQuery:
    """
    Feature query parameters.

    特征查询参数.

    Attributes:
        indicators: Indicator IDs or codes (None = all).
        start: Start date (YYYY-MM-DD).
        end: End date (YYYY-MM-DD).
        indicator_types: Filter by indicator type (trend/momentum/volatility/volume).

    """

    indicators: list[int] | list[str] | None = None
    start: str | None = None
    end: str | None = None
    indicator_types: (
        list[Literal["trend", "momentum", "volatility", "volume"]] | None
    ) = None


class FeatureService:
    """
    Features domain unified service.

    Features 域统一查询服务,提供技术指标数据的高级查询 API,
    集成 TechnicalIndicatorReader/Writer 和 IndicatorMetadataReader/Writer.

    Follows CQRS pattern with separate Reader and Writer components.

    **注意**：技术指标不需要 PIT 支持，因为计算公式固定且可重现。
    与需要 PIT 的基本面特征不同，技术指标在任何时间点重新计算都会得到相同结果。
    """

    def __init__(
        self,
        indicator_reader: TechnicalIndicatorReader,
        indicator_writer: TechnicalIndicatorWriter,
        metadata_reader: TechnicalIndicatorMetadataReader,
        metadata_writer: TechnicalIndicatorMetadataWriter,
    ) -> None:
        """
        Initialize FeatureService with CQRS Readers and Writers.

        Args:
            indicator_reader: Technical indicator data reader.
            indicator_writer: Technical indicator data writer.
            metadata_reader: Indicator metadata reader.
            metadata_writer: Indicator metadata writer.

        """
        self._indicator_reader = indicator_reader
        self._indicator_writer = indicator_writer
        self._metadata_reader = metadata_reader
        self._metadata_writer = metadata_writer

        logger.debug(
            "FeatureService initialized with CQRS Readers and Writers",
            event="feature_service_init_complete",
        )

    @traced("features.find_indicators")
    def find_indicators(self, query: FeatureQuery) -> pl.DataFrame:
        """
        Find technical indicator data via unified service contract.

        查询技术指标数据（多维条件查询）.

        Args:
            query: FeatureQuery object with query parameters.

        Returns:
            DataFrame with indicator data including metadata.

        """
        logger.debug(
            "Fetching technical indicators",
            event="features_indicators_find_start",
            indicators=query.indicators,
            start=query.start,
            end=query.end,
            indicator_types=query.indicator_types,
        )

        # Query indicator data
        # Type narrowing: list[Literal[...]] is assignable to list[str]
        indicator_types_str: list[str] | None = (
            query.indicator_types
            if query.indicator_types is None
            else list(query.indicator_types)
        )
        # Convert indicators to list[str] (accepts both int and str)
        indicator_ids_str: list[str] | None = (
            None if query.indicators is None else [str(i) for i in query.indicators]
        )
        data_df = self._indicator_reader.read(
            start_date=query.start,
            end_date=query.end,
            indicator_types=indicator_types_str,
            indicator_ids=indicator_ids_str,
        )

        if data_df.is_empty():
            return pl.DataFrame()

        # Enrich with metadata
        result = self._enrich_with_metadata(data_df)

        logger.debug(
            "Technical indicators fetched",
            event="features_indicators_find_complete",
            row_count=len(result),
        )

        return result

    def list_indicators(
        self,
        start: str,
        end: str,
        indicator_types: list[Literal["trend", "momentum", "volatility", "volume"]]
        | None = None,
    ) -> pl.DataFrame:
        """
        List indicators by date range (convenience method).

        按日期范围列出技术指标（便利方法）.

        Args:
            start: Start date (YYYY-MM-DD).
            end: End date (YYYY-MM-DD).
            indicator_types: Filter by indicator type (trend/momentum/volatility/
                volume).

        Returns:
            DataFrame with indicator data including metadata.

        """
        query = FeatureQuery(
            start=start,
            end=end,
            indicator_types=indicator_types,
        )
        return self.find_indicators(query)

    def _enrich_with_metadata(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Enrich indicator data with metadata.

        使用元数据丰富指标数据.

        Args:
            df: Indicator data DataFrame.

        Returns:
            Enriched DataFrame with metadata columns.

        """
        # Get unique indicator IDs
        indicator_ids = df["indicator_id"].unique().to_list()

        # Batch fetch metadata for all indicators (优化：一次性查询所有元数据)
        codes = [str(iid) for iid in indicator_ids]
        metadata_df = self._metadata_reader.batch_get_by_codes(codes)

        if metadata_df.is_empty():
            return df

        # Join metadata
        result = df.join(
            metadata_df.select(["code", "name", "type", "description"]),
            left_on="indicator_id",
            right_on="code",
            how="left",
        )

        return result

    def close(self) -> None:
        """
        Close the underlying stores.

        Note: TechnicalIndicatorReader/Writer use Parquet, no close needed.
        The SQLite client from MetadataReader should be closed by the owner.
        """
        # Readers/Writers don't own resources, no action needed
        pass
