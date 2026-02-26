"""
list_date 推断服务。

作为 basic 数据摄取后的独立补偿流程，
针对 list_date 为 NULL 的证券，从 2010 年起查询历史行情数据推断上市日期。

API 返回限制：
- ETF: 2000 条/次
- Index: 8000 条/次
- 申万指数: 4000 条/次
- Stock: 6000 条/次
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import TYPE_CHECKING, Literal

import polars as pl
from ditto_infra.foundation import logger, traced

if TYPE_CHECKING:
    from ditto_datahub.services.metadata_service import MetadataService
    from ditto_datahub.sources.base import DataSource

# list_date 推断的最早起始日期
EARLIEST_LIST_DATE_INFERENCE = date(2010, 1, 1)

# API 返回限制（每种类型的最大记录数）
API_LIMITS: dict[str, int] = {
    "stock": 6000,
    "etf": 2000,
    "index": 8000,
    "sw_index": 4000,  # 申万指数
}

# 估算的年均交易日数
TRADING_DAYS_PER_YEAR = 250


class ListDateInferenceService:
    """
    list_date 推断服务。

    作为 basic 数据摄取后的独立补偿流程，
    针对 list_date 为 NULL 的证券，从 2010 年起查询历史行情数据推断上市日期。
    """

    def __init__(
        self,
        metadata_service: MetadataService,
        source: DataSource,
        source_name: str = "tushare",
    ) -> None:
        """
        初始化 ListDateInferenceService。

        Args:
            metadata_service: MetadataService 实例
            source: 数据源实例
            source_name: 数据源名称

        """
        self._metadata_service = metadata_service
        self._source = source
        self._source_name = source_name

    @traced("list_date_inference.infer_for_asset_class")
    def infer_for_asset_class(
        self,
        asset_class: Literal["stock", "etf", "index"],
    ) -> int:
        """
        对指定资产类型的所有 list_date 为 NULL 的证券推断上市日期。

        Args:
            asset_class: 资产类型

        Returns:
            成功推断的证券数量

        """
        logger.info(
            "Starting list_date inference",
            event="list_date_inference_start",
            asset_class=asset_class,
        )

        # 查找 list_date 为 NULL 的证券
        instruments = self._metadata_service.find_instruments_without_list_date(
            asset_class=asset_class
        )

        if instruments.is_empty():
            logger.info(
                "No instruments without list_date found",
                event="list_date_inference_empty",
                asset_class=asset_class,
            )
            return 0

        # 获取 source_ticker 和 instrument_id 的映射
        source_tickers = instruments["source_ticker"].to_list()
        instrument_ids = instruments["instrument_id"].to_list()

        logger.info(
            f"Found {len(source_tickers)} instruments without list_date",
            event="list_date_inference_found",
            asset_class=asset_class,
            count=len(source_tickers),
        )

        success_count = 0

        for source_ticker, instrument_id in zip(
            source_tickers, instrument_ids, strict=True
        ):
            try:
                inferred_date = self._infer_list_date_for_instrument(
                    source_ticker=source_ticker,
                    asset_class=asset_class,
                )
                if inferred_date is not None:
                    self._metadata_service.update_list_date(
                        instrument_id, inferred_date
                    )
                    success_count += 1
                    logger.debug(
                        "Updated list_date",
                        event="list_date_updated",
                        instrument_id=instrument_id,
                        source_ticker=source_ticker,
                        list_date=str(inferred_date),
                    )
            except Exception as e:
                logger.warning(
                    f"Failed to infer list_date for {source_ticker}",
                    event="list_date_inference_failed",
                    source_ticker=source_ticker,
                    error=str(e),
                )

        logger.info(
            "Completed list_date inference",
            event="list_date_inference_complete",
            asset_class=asset_class,
            total=len(source_tickers),
            success=success_count,
        )

        return success_count

    def _infer_list_date_for_instrument(
        self,
        source_ticker: str,
        asset_class: str,
    ) -> date | None:
        """
        为单个证券推断 list_date。

        从 2010 年起分批查询历史数据，找到最早有数据的日期。

        Args:
            source_ticker: 源代码
            asset_class: 资产类型

        Returns:
            推断的上市日期，如果无法推断则返回 None

        """
        api_limit = API_LIMITS.get(asset_class, 6000)
        years_per_batch = api_limit // TRADING_DAYS_PER_YEAR

        # 从当前日期往回查询，直到找到数据或到达 2010 年
        end_date = date.today()
        earliest_date: date | None = None

        while end_date >= EARLIEST_LIST_DATE_INFERENCE:
            # 计算批次起始日期
            start_date = max(
                EARLIEST_LIST_DATE_INFERENCE,
                end_date - timedelta(days=years_per_batch * 365),
            )

            try:
                df = self._fetch_daily_data(
                    source_ticker=source_ticker,
                    asset_class=asset_class,
                    start_date=start_date,
                    end_date=end_date,
                )

                if not df.is_empty() and "trade_date" in df.columns:
                    # 先过滤出 >= 2010 年的数据，再找最早的日期
                    filtered_df = df.filter(
                        pl.col("trade_date") >= EARLIEST_LIST_DATE_INFERENCE
                    )

                    if not filtered_df.is_empty():
                        batch_earliest = filtered_df.select(
                            pl.col("trade_date").min()
                        ).item()

                        if batch_earliest is not None:
                            # 转换为 date 类型
                            if isinstance(batch_earliest, str):
                                batch_earliest = date.fromisoformat(batch_earliest)
                            elif hasattr(batch_earliest, "date"):
                                batch_earliest = batch_earliest.date()

                            if earliest_date is None or batch_earliest < earliest_date:
                                earliest_date = batch_earliest

                # 如果数据量小于限制，说明已经到达最早的数据
                if len(df) < api_limit:
                    break

            except Exception as e:
                msg = (
                    f"No data found for {source_ticker} "
                    f"in range {start_date} to {end_date}"
                )
                logger.debug(
                    msg,
                    event="list_date_inference_no_data",
                    source_ticker=source_ticker,
                    start_date=str(start_date),
                    end_date=str(end_date),
                    error=str(e),
                )

            # 移动到下一个批次
            end_date = start_date - timedelta(days=1)

        return earliest_date

    def _fetch_daily_data(
        self,
        source_ticker: str,
        asset_class: str,
        start_date: date,
        end_date: date,
    ) -> pl.DataFrame:
        """
        获取日线数据。

        Args:
            source_ticker: 源代码
            asset_class: 资产类型
            start_date: 起始日期
            end_date: 结束日期

        Returns:
            日线数据 DataFrame

        """
        start_str = start_date.isoformat()
        end_str = end_date.isoformat()

        if asset_class == "stock":
            return self._source.fetch_stock_daily(
                source_ticker=source_ticker,
                start_date=start_str,
                end_date=end_str,
            )
        elif asset_class == "etf":
            return self._source.fetch_etf_daily(
                source_ticker=source_ticker,
                start_date=start_str,
                end_date=end_str,
            )
        elif asset_class == "index":
            return self._source.fetch_index_daily(
                source_ticker=source_ticker,
                start_date=start_str,
                end_date=end_str,
            )
        else:
            raise ValueError(f"Unsupported asset_class: {asset_class}")
