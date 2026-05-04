"""Source query facade — 封装 SourceService + MetadataService."""

from __future__ import annotations

import polars as pl
from ditto_data.models import Dataset
from ditto_data.services.metadata_service import MetadataService
from ditto_data.services.source_service import SourceService
from ditto_data.sources.fred.fred_source import FredSource
from ditto_data.sources.tushare.tushare_source import TushareSource

__all__ = ["SourceQueryFacade"]

SUPPORTED_SOURCE_DATASETS: frozenset[str] = frozenset({"stock_daily"})


class SourceQueryFacade:
    """
    Source 数据查询 facade.

    封装 SourceService 和 MetadataService 的联合操作，
    隐藏 Dataset 枚举和内部服务依赖。
    """

    def __init__(
        self,
        source_service: SourceService,
        metadata_service: MetadataService,
    ) -> None:
        self._source = source_service
        self._metadata = metadata_service

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
            raise ValueError(msg) from None
        return ds.asset_class

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

    def get_source(self, name: str) -> TushareSource | FredSource:
        """
        获取数据源实例.

        Args:
            name: 数据源名称（如 "tushare"）

        Returns:
            TushareSource 或 FredSource 实例

        """
        return self._source.get_source(name)

    @property
    def tushare(self) -> TushareSource:
        """获取 Tushare 数据源."""
        return self._source.tushare

    def fetch_source_data(
        self,
        *,
        source: str,
        dataset: str,
        source_ticker: str,
        start_date: str,
        end_date: str,
    ) -> pl.DataFrame:
        """
        Fetch route-visible source data through the application facade.

        Apps routes should not import source protocols or concrete data sources.
        This method keeps the route boundary on application-facing primitives.
        """
        if source != "tushare":
            raise ValueError(f"不支持的数据源: {source}")

        if dataset == "stock_daily":
            return self.tushare.fetch_stock_daily(
                source_ticker=source_ticker,
                start_date=start_date,
                end_date=end_date,
            )

        supported = ", ".join(sorted(SUPPORTED_SOURCE_DATASETS))
        raise ValueError(
            f"数据集 {dataset} 暂不支持 Source API 查询, 支持: {supported}"
        )
