"""Capital corporate actions: corporate actions, share buyback, rights issue."""

from __future__ import annotations

import polars as pl
from ditto_platform.foundation import Metrics, logger, traced

from ditto_data.sources.tushare.adapters.base import BaseTushareAdapter
from ditto_data.sources.tushare.processors.error_handler import (
    tushare_fetch_error_handler,
)
from ditto_data.sources.tushare.processors.mappings import (
    RIGHTS_ISSUE_MAPPING,
    SHARE_BUYBACK_MAPPING,
)
from ditto_data.sources.tushare.processors.transformer import TushareDataTransformer

_CORPORATE_ACTION_COLUMNS = (
    "source_ticker",
    "action_type",
    "action_date",
    "knowledge_date",
    "effective_from",
    "effective_to",
    "description",
)


def _empty_corporate_actions() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "source_ticker": pl.String,
            "action_type": pl.String,
            "action_date": pl.Date,
            "knowledge_date": pl.Date,
            "effective_from": pl.Date,
            "effective_to": pl.Date,
            "description": pl.String,
        }
    )


def _date(name: str) -> pl.Expr:
    return pl.col(name).cast(pl.String).str.to_date("%Y%m%d", strict=False)


def _normalized_repurchase(value: pl.DataFrame) -> pl.DataFrame:
    if value.is_empty():
        return _empty_corporate_actions()
    observable_date = pl.coalesce(
        _date("ann_date"),
        _date("end_date"),
        _date("exp_date"),
    )
    return value.select(
        pl.col("ts_code").cast(pl.String).alias("source_ticker"),
        pl.lit("share_repurchase").alias("action_type"),
        observable_date.alias("action_date"),
        observable_date.alias("knowledge_date"),
        pl.coalesce(
            _date("end_date"),
            _date("ann_date"),
            _date("exp_date"),
        ).alias("effective_from"),
        _date("exp_date").alias("effective_to"),
        pl.concat_str(
            pl.lit("progress="),
            pl.col("proc").cast(pl.String).fill_null("unknown"),
            pl.lit(";volume="),
            pl.col("vol").cast(pl.String).fill_null("unknown"),
            pl.lit(";amount="),
            pl.col("amount").cast(pl.String).fill_null("unknown"),
        ).alias("description"),
    )


def _normalized_share_float(value: pl.DataFrame) -> pl.DataFrame:
    if value.is_empty():
        return _empty_corporate_actions()
    observable_date = pl.coalesce(_date("ann_date"), _date("float_date"))
    return value.select(
        pl.col("ts_code").cast(pl.String).alias("source_ticker"),
        pl.lit("restricted_share_release").alias("action_type"),
        observable_date.alias("action_date"),
        observable_date.alias("knowledge_date"),
        pl.coalesce(_date("float_date"), _date("ann_date")).alias("effective_from"),
        pl.lit(None, dtype=pl.Date).alias("effective_to"),
        pl.concat_str(
            pl.lit("share_type="),
            pl.col("share_type").cast(pl.String).fill_null("unknown"),
            pl.lit(";holder="),
            pl.col("holder_name").cast(pl.String).fill_null("unknown"),
            pl.lit(";shares="),
            pl.col("float_share").cast(pl.String).fill_null("unknown"),
            pl.lit(";ratio="),
            pl.col("float_ratio").cast(pl.String).fill_null("unknown"),
        ).alias("description"),
    )


def _normalized_corporate_actions(
    repurchase: pl.DataFrame,
    share_float: pl.DataFrame,
) -> pl.DataFrame:
    normalized = pl.concat(
        (
            _normalized_repurchase(repurchase),
            _normalized_share_float(share_float),
        )
    )
    if normalized.is_empty():
        return _empty_corporate_actions()
    return normalized.sort("action_date", "source_ticker").select(
        _CORPORATE_ACTION_COLUMNS
    )


class CapitalCorporateTushareAdapter(BaseTushareAdapter):
    """
    Capital corporate actions Tushare adapter.

    提供公司行为相关数据的 Tushare API 访问，包括：
    - 公司行为
    - 限售解禁
    - 配股

    """

    @traced("source.tushare.fetch_corporate_actions")
    def fetch_corporate_actions(
        self,
        ts_code: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """
        获取公司行为数据.

        Args:
            ts_code: 股票代码 (e.g., "000001.SZ")
            start_date: 开始日期 (YYYYMMDD)
            end_date: 结束日期 (YYYYMMDD)

        Returns:
            DataFrame with columns:
            - source_ticker: 股票代码
            - action_type: 行为类型
            - action_date: 行为日期
            - knowledge_date: 知识日期
            - effective_from: 生效日期
            - effective_to: 失效日期
            - description: 描述

        Raises:
            SourceFetchError: If fetch fails.

        """
        logger.info(
            "Fetching Tushare corporate actions",
            event="tushare_corporate_actions_fetch_start",
            ts_code=ts_code,
            start_date=start_date,
            end_date=end_date,
        )

        with tushare_fetch_error_handler(
            "corporate_actions",
            "repurchase+share_float",
        ):
            common = {
                key: value
                for key, value in {
                    "ts_code": ts_code,
                    "start_date": start_date,
                    "end_date": end_date,
                }.items()
                if value
            }
            repurchase = self._client.query(
                api_name="repurchase",
                fields=("ts_code,ann_date,end_date,proc,exp_date,vol,amount"),
                **common,
            )
            share_float = self._client.query(
                api_name="share_float",
                fields=(
                    "ts_code,ann_date,float_date,float_share,float_ratio,"
                    "holder_name,share_type"
                ),
                **common,
            )
            result = _normalized_corporate_actions(repurchase, share_float)

            row_count = len(result)
            logger.info(
                "Tushare corporate actions fetched",
                event="tushare_corporate_actions_fetch_complete",
                row_count=row_count,
            )
            Metrics.data_records.add(
                row_count,
                {
                    "source": "tushare",
                    "dataset": "corporate_actions",
                    "status": "success",
                },
            )

            return result

    @traced("source.tushare.fetch_share_buyback")
    def fetch_share_buyback(
        self,
        ts_code: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """
        获取限售解禁数据.

        Args:
            ts_code: 股票代码 (e.g., "000001.SZ")
            start_date: 开始日期 (YYYYMMDD)
            end_date: 结束日期 (YYYYMMDD)

        Returns:
            DataFrame with columns:
            - source_ticker: 股票代码
            - announcement_date: 公告日期
            - effective_date: 解禁日期
            - float_shares: 解禁股数
            - float_ratio: 解禁比例

        Raises:
            SourceFetchError: If fetch fails.

        """
        logger.info(
            "Fetching Tushare share buyback data",
            event="tushare_share_buyback_fetch_start",
            ts_code=ts_code,
            start_date=start_date,
            end_date=end_date,
        )

        with tushare_fetch_error_handler("share_buyback", "share_float"):
            params: dict[str, str] = {
                "api_name": "share_float",
                "fields": "ts_code,ann_date,float_date,float_share,float_ratio",
            }

            if ts_code:
                params["ts_code"] = ts_code
            if start_date:
                params["start_date"] = start_date
            if end_date:
                params["end_date"] = end_date

            response = self._client.query(**params)

            result = TushareDataTransformer.transform(
                response, "share_buyback", SHARE_BUYBACK_MAPPING
            )

            row_count = len(result)
            logger.info(
                "Tushare share buyback data fetched",
                event="tushare_share_buyback_fetch_complete",
                row_count=row_count,
            )
            Metrics.data_records.add(
                row_count,
                {
                    "source": "tushare",
                    "dataset": "share_buyback",
                    "status": "success",
                },
            )

            return result

    @traced("source.tushare.fetch_rights_issue")
    def fetch_rights_issue(
        self,
        ts_code: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """
        获取配股数据.

        Args:
            ts_code: 股票代码 (e.g., "000001.SZ")
            start_date: 开始日期 (YYYYMMDD)
            end_date: 结束日期 (YYYYMMDD)

        Returns:
            DataFrame with columns:
            - source_ticker: 股票代码
            - rights_type: 配股类型
            - announcement_date: 公告日期
            - record_date: 股权登记日
            - ex_rights_date: 除权日
            - rights_price: 配股价
            - rights_ratio: 配股比例

        Raises:
            SourceFetchError: If fetch fails.

        """
        logger.info(
            "Fetching Tushare rights issue data",
            event="tushare_rights_issue_fetch_start",
            ts_code=ts_code,
            start_date=start_date,
            end_date=end_date,
        )

        with tushare_fetch_error_handler("rights_issue", "rights"):
            params: dict[str, str] = {
                "api_name": "rights",
                "fields": (
                    "ts_code,rights_type,ann_date,reg_date,"
                    "ex_date,rights_price,rights_ratio"
                ),
            }

            if ts_code:
                params["ts_code"] = ts_code
            if start_date:
                params["start_date"] = start_date
            if end_date:
                params["end_date"] = end_date

            response = self._client.query(**params)

            result = TushareDataTransformer.transform(
                response, "rights_issue", RIGHTS_ISSUE_MAPPING
            )

            row_count = len(result)
            logger.info(
                "Tushare rights issue data fetched",
                event="tushare_rights_issue_fetch_complete",
                row_count=row_count,
            )
            Metrics.data_records.add(
                row_count,
                {
                    "source": "tushare",
                    "dataset": "rights_issue",
                    "status": "success",
                },
            )

            return result
