"""交易日历适配器."""

from __future__ import annotations

import polars as pl
from ditto_foundation import logger, traced

from ditto_datahub.sources.tushare.adapters.base import BaseTushareAdapter
from ditto_datahub.sources.tushare.processors.error_handler import (
    tushare_fetch_error_handler,
)
from ditto_datahub.sources.tushare.processors.transformer import (
    CALENDAR_MAPPING,
    TushareDataTransformer,
)


class CalendarTushareAdapter(BaseTushareAdapter):
    """
    交易日历适配器.

    专门用于从 Tushare 获取交易日历数据.

    Attributes:
        _client: Tushare API client.

    """

    @traced("source.tushare.fetch_calendar")
    def fetch_calendar(
        self,
        start_date: str,
        end_date: str,
    ) -> pl.DataFrame:
        """
        获取交易日历.

        Args:
            start_date: 开始日期 (YYYY-MM-DD).
            end_date: 结束日期 (YYYY-MM-DD).

        Returns:
            包含以下列的 DataFrame:
            - trade_date: 日期
            - is_open: 是否开市 (Boolean)

        Raises:
            SourceFetchError: 获取失败.

        """
        logger.info(
            "Fetching Tushare calendar",
            event="tushare_calendar_fetch_start",
            start_date=start_date,
            end_date=end_date,
        )

        with tushare_fetch_error_handler("calendar", "trade_cal"):
            response = self._client.query(
                api_name="trade_cal",
                exchange="SSE",
                start_date=start_date.replace("-", ""),
                end_date=end_date.replace("-", ""),
                fields="cal_date,is_open",
            )

            return TushareDataTransformer.transform(
                response, "calendar", CALENDAR_MAPPING
            )
