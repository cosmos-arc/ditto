"""Source query facade — 封装 source 数据获取 + MetadataService."""

from __future__ import annotations

from typing import Protocol

import polars as pl
from ditto_data.catalog.metadata import dataset_asset_class
from ditto_data.catalog.promotion import DatasetMaturityPromotionReader
from ditto_data.models import Dataset
from ditto_data.services.metadata_service import MetadataService

from ditto_application.catalog_maturity import blocked_catalog_datasets
from ditto_application.exceptions import AppQueryError

__all__ = ["SourceDataPort", "SourceQueryFacade"]

SUPPORTED_SOURCE_DATASETS: frozenset[str] = frozenset({"stock_daily"})


class SourceDataPort(Protocol):
    """
    窄 Protocol：route-visible source 数据获取的 application-level port.

    消费者（SourceQueryFacade）只关心 fetch_stock_daily 这一个方法；
    具体 source adapter（TushareSource / FredSource）通过 composition root 注入。
    """

    def fetch_stock_daily(
        self,
        *,
        source_ticker: str,
        start_date: str,
        end_date: str,
    ) -> pl.DataFrame:
        """Fetch daily stock bars for a single ticker."""
        ...


class SourceQueryFacade:
    """
    Source 数据查询 facade.

    通过 SourceDataPort Protocol 获取 source 数据，通过 MetadataService 解析标识符。
    不暴露任何 concrete source 类型。
    """

    def __init__(
        self,
        source_data: SourceDataPort,
        metadata_service: MetadataService,
        maturity_promotion_reader: DatasetMaturityPromotionReader | None = None,
    ) -> None:
        self._source = source_data
        self._metadata = metadata_service
        self._maturity_promotion_reader = maturity_promotion_reader

    def get_dataset_asset_class(self, dataset: str) -> str | None:
        """
        获取数据集对应的资产类别.

        Args:
            dataset: 数据集名称（如 "stock_daily"）

        Returns:
            资产类别字符串（如 "stock"），不支持按标的查询的返回 None

        Raises:
            ValueError: 不支持的数据集

        """
        try:
            ds = Dataset(dataset)
        except ValueError:
            msg = f"不支持的数据集: {dataset}"
            raise AppQueryError(msg) from None
        return dataset_asset_class(ds.value)

    def resolve_source_ticker(
        self,
        *,
        ticker: str | None = None,
        standard_ticker: str | None = None,
        instrument_id: int | None = None,
        asset_class: str = "stock",
        source: str = "tushare",
    ) -> str:
        """
        解析标识符为 source ticker.

        Args:
            ticker: 裸代码（如 "000001"）
            standard_ticker: 标准代码（如 "000001.XSHE"）
            instrument_id: 内部 ID
            asset_class: 资产类别
            source: 数据源名称

        Returns:
            source ticker 字符串

        """
        return self._metadata.resolve_source_ticker(
            ticker=ticker,
            standard_ticker=standard_ticker,
            instrument_id=instrument_id,
            asset_class=asset_class,
            source=source,
        )

    def fetch_source_data(
        self,
        *,
        source: str,
        dataset: str,
        source_ticker: str,
        start_date: str,
        end_date: str,
        allow_experimental_data: bool = False,
    ) -> pl.DataFrame:
        """
        Fetch route-visible source data through the application facade.

        Apps routes should not import source protocols or concrete data sources.
        This method keeps the route boundary on application-facing primitives.
        """
        if source != "tushare":
            raise AppQueryError(f"不支持的数据源: {source}")
        if dataset not in SUPPORTED_SOURCE_DATASETS:
            supported = ", ".join(sorted(SUPPORTED_SOURCE_DATASETS))
            raise AppQueryError(
                f"数据集 {dataset} 暂不支持 Source API 查询, 支持: {supported}"
            )

        self._assert_source_dataset_allowed(
            dataset,
            allow_experimental_data=allow_experimental_data,
        )

        if dataset == "stock_daily":
            return self._source.fetch_stock_daily(
                source_ticker=source_ticker,
                start_date=start_date,
                end_date=end_date,
            )

        raise AssertionError("unreachable supported source dataset")

    def _assert_source_dataset_allowed(
        self,
        dataset: str,
        *,
        allow_experimental_data: bool,
    ) -> None:
        blocked = blocked_catalog_datasets(
            (dataset,),
            allow_experimental_data=allow_experimental_data,
            maturity_promotion_reader=self._maturity_promotion_reader,
        )
        if not blocked:
            return

        joined = ", ".join(blocked)
        msg = (
            "source data query requires experimental dataset or other "
            f"non-initial-focus dataset maturity: {joined}. "
            "Set allow_experimental_data=True only for explicit research use."
        )
        raise AppQueryError(msg)
