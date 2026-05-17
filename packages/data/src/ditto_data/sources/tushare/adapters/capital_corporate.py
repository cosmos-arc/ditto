"""Capital corporate actions: corporate actions, share buyback, rights issue."""

from __future__ import annotations

import polars as pl
from ditto_platform.foundation import Metrics, logger, traced

from ditto_data.sources.tushare.client import TushareClient
from ditto_data.sources.tushare.processors.error_handler import (
    tushare_fetch_error_handler,
)
from ditto_data.sources.tushare.processors.mappings import (
    CORPORATE_ACTIONS_MAPPING,
    RIGHTS_ISSUE_MAPPING,
    SHARE_BUYBACK_MAPPING,
)
from ditto_data.sources.tushare.processors.transformer import TushareDataTransformer


@traced("source.tushare.fetch_corporate_actions")
def fetch_corporate_actions(
    client: TushareClient,
    ts_code: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> pl.DataFrame:
    """
    获取公司行为数据.

    Args:
        client: Tushare API client.
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

    with tushare_fetch_error_handler("corporate_actions", "ba"):
        params: dict[str, str] = {
            "api_name": "ba",
            "fields": "ts_code,ann_date,act_date,ba_type,name",
        }

        if ts_code:
            params["ts_code"] = ts_code
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date

        response = client.query(**params)

        result = TushareDataTransformer.transform(
            response, "corporate_actions", CORPORATE_ACTIONS_MAPPING
        )

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
    client: TushareClient,
    ts_code: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> pl.DataFrame:
    """
    获取限售解禁数据.

    Args:
        client: Tushare API client.
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

        response = client.query(**params)

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
    client: TushareClient,
    ts_code: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> pl.DataFrame:
    """
    获取配股数据.

    Args:
        client: Tushare API client.
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

        response = client.query(**params)

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
