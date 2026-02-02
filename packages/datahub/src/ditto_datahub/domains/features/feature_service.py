"""
FeatureService - Features domain unified service.

Features 域统一查询服务,集成技术指标数据和元数据查询.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import polars as pl
from ditto_foundation import logger, traced

from ditto_datahub.domains.features.technical.indicator_metadata_store import (
    IndicatorMetadataStore,
)
from ditto_datahub.domains.features.technical.indicator_store import IndicatorStore


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
    集成 IndicatorStore 和 IndicatorMetadataStore.

    **注意**：技术指标不需要 PIT 支持，因为计算公式固定且可重现。
    与需要 PIT 的基本面特征不同，技术指标在任何时间点重新计算都会得到相同结果。
    """

    def __init__(
        self,
        indicator_store: IndicatorStore,
        metadata_store: IndicatorMetadataStore,
    ) -> None:
        """
        Initialize FeatureService.

        Args:
            indicator_store: Indicator data storage.
            metadata_store: Indicator metadata storage.

        """
        self._indicator_store = indicator_store
        self._metadata_store = metadata_store

        logger.debug(
            "FeatureService initialized",
            event="feature_service_init_complete",
        )

    @traced("features.get_indicators")
    def get_indicators(self, query: FeatureQuery) -> pl.DataFrame:
        """
        Query technical indicator data.

        查询技术指标数据.

        Args:
            query: FeatureQuery object with query parameters.

        Returns:
            DataFrame with indicator data including metadata.

        """
        logger.debug(
            "Fetching technical indicators",
            event="features_indicators_get_start",
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
        data_df = self._indicator_store.read(
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
            event="features_indicators_get_complete",
            row_count=len(result),
        )

        return result

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
        metadata_df = self._metadata_store.batch_get_by_codes(codes)

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
        """Close the underlying stores."""
        # IndicatorStore uses Parquet, no close needed
        # MetadataStore uses SQLite, close it
        self._metadata_store.close()
