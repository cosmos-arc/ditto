"""ETF 适配器实现."""

from __future__ import annotations

from datetime import date, timedelta

import polars as pl
from ditto_platform.foundation import logger, traced

from ditto_data.config import DataSourceSettings
from ditto_data.errors.network import SourceFetchError
from ditto_data.sources.tushare.adapters.base import BaseTushareAdapter
from ditto_data.sources.tushare.client import TushareClient
from ditto_data.sources.tushare.processors.error_handler import (
    tushare_fetch_error_handler,
)
from ditto_data.sources.tushare.processors.mappings import (
    ETF_BASIC_MAPPING,
    ETF_NAV_MAPPING,
    FUND_ADJ_MAPPING,
)
from ditto_data.sources.tushare.processors.transformer import TushareDataTransformer

# 日更滚动回看窗：QDII 净值公布 T+1/T+2，7 天覆盖节假日顺延（#483）
_NAV_LOOKBACK_DAYS = 7


def _yyyymmdd_range(ts_start: str, ts_end: str) -> list[str]:
    """闭区间逐日序列（YYYYMMDD）."""
    start = date(int(ts_start[:4]), int(ts_start[4:6]), int(ts_start[6:8]))
    end = date(int(ts_end[:4]), int(ts_end[4:6]), int(ts_end[6:8]))
    days: list[str] = []
    current = start
    while current <= end:
        days.append(current.strftime("%Y%m%d"))
        current += timedelta(days=1)
    return days


class ETFTushareAdapter(BaseTushareAdapter):
    """
    ETF Tushare 适配器.

    专门处理 ETF 相关数据获取，包括：
    - ETF 基本信息
    - ETF 日线数据
    - 基金复权因子
    - 基金净值

    品种边界（#513）：fund_daily/fund_adj/fund_nav 的全市场响应会混入
    LOF 等非 ETF 品种（#1891），本 adapter 统一按 etf_basic universe
    交集过滤（按日模式）并拒绝非 universe 标的（按标的模式）。
    """

    def __init__(
        self,
        token: str | None = None,
        settings: DataSourceSettings | None = None,
        *,
        _client: TushareClient | None = None,
    ) -> None:
        super().__init__(token, settings, _client=_client)
        # fund_daily 全市场拉取会混入 LOF 等非 ETF 品种（#1891），
        # 按 etf_basic 口径做 universe 交集（#513）。进程内缓存一份。
        self._etf_universe: frozenset[str] | None = None

    def _load_etf_universe(self) -> frozenset[str]:
        """
        Load (and cache) the ETF ticker universe from etf_basic.

        空清单视为源侧异常并显式失败：静默空 universe 会把 etf_daily
        的全市场拉取整体过滤为空（fail-closed）。
        """
        if self._etf_universe is None:
            basic = self.fetch_etf_basic()
            if basic.is_empty():
                raise SourceFetchError(
                    message=(
                        "etf_basic returned no rows; cannot establish the ETF "
                        "universe for fund_daily intersection (#513)"
                    ),
                    source="tushare",
                )
            self._etf_universe = frozenset(basic["source_ticker"].to_list())
        return self._etf_universe

    @traced("source.tushare.fetch_etf_basic")
    def fetch_etf_basic(self) -> pl.DataFrame:
        """
        获取 ETF 基本信息.

        Returns:
            DataFrame with columns:
            - source_ticker: Source code (e.g., "510300.SH")
            - ticker: Display ticker (e.g., "510300")
            - name: ETF name
            - exchange: Exchange code
            - list_date: Listing date

        Raises:
            SourceFetchError: If fetch fails.

        """
        logger.info(
            "Fetching Tushare ETF basic info",
            event="tushare_etf_basic_fetch_start",
        )

        with tushare_fetch_error_handler("etf_basic", "etf_basic"):
            response = self._client.query(
                api_name="etf_basic",
                fields="ts_code,csname,list_date,list_status,index_code,etf_type",
            )

            transformed = TushareDataTransformer.transform(
                response, "etf_basic", ETF_BASIC_MAPPING
            )
            if transformed.is_empty():
                return transformed
            return transformed.filter(
                pl.col("list_date").is_not_null()
                & pl.col("exchange").is_in(["SSE", "SZSE"])
            )

    @traced("source.tushare.fetch_etf_daily")
    def fetch_etf_daily(
        self,
        trade_date: str | None = None,
        source_ticker: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """
        获取 ETF 日线 OHLCV 数据.

        支持两种查询模式：
        - 按日期批量：指定 trade_date
        - 按标的+时间段：指定 source_ticker + start_date + end_date

        Args:
            trade_date: Trade date (YYYY-MM-DD). 与 source_ticker 互斥.
            source_ticker: Source code (e.g., "510300.SH").
            start_date: Start date (YYYY-MM-DD). 与 source_ticker 配合使用.
            end_date: End date (YYYY-MM-DD). 与 source_ticker 配合使用.

        Returns:
            DataFrame with columns (matching ETF_DAILY_SCHEMA):
            - source_ticker: Source code
            - trade_date: Date
            - open, high, low, close, pre_close: Float64
            - volume, amount: Float64
            - pct_change: Float64

        Raises:
            ValueError: 参数组合无效.
            SourceFetchError: If fetch fails.
            SourceTransformationError: If data transformation fails.

        """
        # 参数校验
        if trade_date and source_ticker:
            raise ValueError("trade_date 和 source_ticker 互斥, 不能同时指定")

        if not trade_date and not source_ticker:
            raise ValueError("必须指定 trade_date 或 source_ticker 之一")

        # 按日期批量查询
        if trade_date:
            return self._fetch_etf_daily_by_date(trade_date)

        # 按标的+时间段查询（此时 source_ticker 必定不为 None）
        if not source_ticker or not start_date or not end_date:
            raise ValueError("按标的查询必须指定 source_ticker、start_date 和 end_date")

        return self._fetch_etf_daily_by_ticker(source_ticker, start_date, end_date)

    def _fetch_etf_daily_by_date(self, trade_date: str) -> pl.DataFrame:
        """按日期获取 ETF 日线数据（与 etf_basic universe 交集过滤）."""
        logger.info(
            "Fetching Tushare ETF daily",
            event="tushare_etf_daily_fetch_start",
            trade_date=trade_date,
        )

        # universe 加载在 fetch 错误处理之外：清单为空属源侧配置/契约
        # 问题，应携带原始信息失败，而非被包装成泛化 fetch 错误。
        self._load_etf_universe()

        with tushare_fetch_error_handler("etf_daily", "fund_daily"):
            ts_date = trade_date.replace("-", "")
            response = self._client.query(
                api_name="fund_daily",
                ts_code="",
                trade_date=ts_date,
                fields="ts_code,trade_date,open,high,low,close,pre_close,vol,amount,pct_chg",
            )

            response = self._filter_non_etf_rows(response)
            return TushareDataTransformer.transform_daily_ohlcv(
                response,
                "etf_daily",
            )

    def _filter_non_etf_rows(self, response: pl.DataFrame) -> pl.DataFrame:
        """
        Intersect fund_daily rows with the etf_basic universe (#513).

        fund_daily 全市场拉取混入 LOF 等非 ETF 品种（#1891），不过滤会
        以 source_ticker 落入 etf_daily。被过滤行数记录 WARNING，不静默。
        """
        if response.is_empty():
            return response
        universe = self._load_etf_universe()
        kept = response.filter(pl.col("ts_code").is_in(universe))
        dropped = response.height - kept.height
        if dropped:
            dropped_codes = sorted(set(response["ts_code"].to_list()) - universe)
            logger.warning(
                "fund_daily returned non-ETF rows, dropped",
                event="tushare_etf_daily_non_etf_dropped",
                dropped_rows=dropped,
                dropped_codes=dropped_codes[:20],
                dropped_code_count=len(dropped_codes),
            )
        return kept

    def _fetch_etf_daily_by_ticker(
        self,
        source_ticker: str,
        start_date: str,
        end_date: str,
    ) -> pl.DataFrame:
        """按标的+时间段获取 ETF 日线数据（内部方法）."""
        logger.info(
            "Fetching Tushare ETF daily by ticker",
            event="tushare_etf_daily_ticker_fetch_start",
            source_ticker=source_ticker,
            start_date=start_date,
            end_date=end_date,
        )

        if source_ticker not in self._load_etf_universe():
            # 按标的模式显式拒绝非 ETF 品种（如 LOF），防止污染 etf_daily
            raise ValueError(
                f"source_ticker {source_ticker} is not in the etf_basic "
                + "universe; etf_daily only accepts ETF instruments (#513)"
            )

        with tushare_fetch_error_handler("etf_daily", "fund_daily"):
            ts_start = start_date.replace("-", "")
            ts_end = end_date.replace("-", "")
            response = self._client.query(
                api_name="fund_daily",
                ts_code=source_ticker,
                start_date=ts_start,
                end_date=ts_end,
                fields="ts_code,trade_date,open,high,low,close,pre_close,vol,amount,pct_chg",
            )

            return TushareDataTransformer.transform_daily_ohlcv(
                response,
                "etf_daily",
            )

    @traced("source.tushare.fetch_fund_adj")
    def fetch_fund_adj(
        self,
        trade_date: str | None = None,
        source_ticker: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """
        获取 ETF/基金复权因子.

        支持两种查询模式：
        - 按日期批量：指定 trade_date
        - 按标的+时间段：指定 source_ticker + start_date + end_date

        Args:
            trade_date: Trade date (YYYY-MM-DD). 与 source_ticker 互斥.
            source_ticker: Source code (e.g., "510300.SH").
            start_date: Start date (YYYY-MM-DD). 与 source_ticker 配合使用.
            end_date: End date (YYYY-MM-DD). 与 source_ticker 配合使用.

        Returns:
            DataFrame with columns:
            - source_ticker: Source code
            - trade_date: Date
            - knowledge_date: Date (PIT safety: when this data became known)
            - adj_factor: Float64

        Raises:
            ValueError: 参数组合无效.
            SourceFetchError: If fetch fails.

        """
        # 参数校验
        if trade_date and source_ticker:
            raise ValueError("trade_date 和 source_ticker 互斥, 不能同时指定")

        if not trade_date and not source_ticker:
            raise ValueError("必须指定 trade_date 或 source_ticker 之一")

        # 按日期批量查询
        if trade_date:
            return self._fetch_fund_adj_by_date(trade_date)

        # 按标的+时间段查询（此时 source_ticker 必定不为 None）
        if not source_ticker or not start_date or not end_date:
            raise ValueError("按标的查询必须指定 source_ticker、start_date 和 end_date")

        return self._fetch_fund_adj_by_ticker(source_ticker, start_date, end_date)

    def _fetch_fund_adj_by_date(self, trade_date: str) -> pl.DataFrame:
        """按日期获取 ETF/基金复权因子（与 etf_basic universe 交集过滤）."""
        logger.info(
            "Fetching Tushare fund adj factors",
            event="tushare_fund_adj_fetch_start",
            trade_date=trade_date,
        )

        self._load_etf_universe()

        with tushare_fetch_error_handler("fund_adj", "fund_adj"):
            ts_date = trade_date.replace("-", "")
            response = self._client.query(
                api_name="fund_adj",
                fields="ts_code,trade_date,adj_factor",
                trade_date=ts_date,
            )

            response = self._filter_non_etf_rows(response)
            return TushareDataTransformer.transform(
                response, "fund_adj", FUND_ADJ_MAPPING
            )

    def _fetch_fund_adj_by_ticker(
        self,
        source_ticker: str,
        start_date: str,
        end_date: str,
    ) -> pl.DataFrame:
        """按标的+时间段获取 ETF/基金复权因子（内部方法）."""
        logger.info(
            "Fetching Tushare fund adj by ticker",
            event="tushare_fund_adj_ticker_fetch_start",
            source_ticker=source_ticker,
            start_date=start_date,
            end_date=end_date,
        )

        if source_ticker not in self._load_etf_universe():
            raise ValueError(
                f"source_ticker {source_ticker} is not in the etf_basic "
                + "universe; fund_adj only accepts ETF instruments (#513)"
            )

        with tushare_fetch_error_handler("fund_adj", f"fund_adj:{source_ticker}"):
            ts_start = start_date.replace("-", "")
            ts_end = end_date.replace("-", "")
            response = self._client.query(
                api_name="fund_adj",
                ts_code=source_ticker,
                start_date=ts_start,
                end_date=ts_end,
                fields="ts_code,trade_date,adj_factor",
            )

            return TushareDataTransformer.transform(
                response, "fund_adj", FUND_ADJ_MAPPING
            )

    @traced("source.tushare.fetch_fund_nav")
    def fetch_fund_nav(
        self,
        trade_date: str | None = None,
        source_ticker: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """
        获取 ETF/基金单位净值（#483）.

        支持两种查询模式：
        - 按日期：指定 trade_date——逐日查询 nav_date ∈ [D-7, D]（该端点
          全市场仅支持 nav_date 单日参数（2026-10-05 实测），滚动逐日 +
          幂等上写接住 QDII 晚 1-2 个自然日公布的净值；ann_date 参数
          不被接受）；
        - 按标的+时间段：source_ticker + start_date/end_date（nav_date
          区间，接受范围参数）.

        Returns:
            [source_ticker, trade_date(=nav_date 估值日), knowledge_date(=ann_date
            披露日，未知保持 null), unit_nav, acc_nav].

        """
        if trade_date and source_ticker:
            raise ValueError("trade_date 和 source_ticker 互斥, 不能同时指定")
        if not trade_date and not source_ticker:
            raise ValueError("必须指定 trade_date 或 source_ticker 之一")

        if trade_date:
            target = trade_date.replace("-", "")
            lookback = (
                date.fromisoformat(trade_date) - timedelta(days=_NAV_LOOKBACK_DAYS)
            ).strftime("%Y%m%d")
            return self._fetch_fund_nav_window(None, lookback, target, trade_date)
        if not start_date or not end_date:
            raise ValueError("按标的查询必须指定 start_date 和 end_date")
        return self._fetch_fund_nav_window(
            source_ticker,
            start_date.replace("-", ""),
            end_date.replace("-", ""),
            trade_date=f"{start_date}~{end_date}",
        )

    def _fetch_fund_nav_window(
        self,
        source_ticker: str | None,
        ts_start: str,
        ts_end: str,
        trade_date: str,
    ) -> pl.DataFrame:
        """fund_nav 按 nav_date 区间取数（source_ticker 为空 = 全市场）."""
        scope = f":{source_ticker}" if source_ticker else ""
        logger.info(
            "Fetching Tushare fund NAV",
            event="tushare_fund_nav_fetch_start",
            trade_date=trade_date,
            source_ticker=source_ticker,
        )
        fields = "ts_code,ann_date,nav_date,unit_nav,acc_nav"
        if source_ticker and source_ticker not in self._load_etf_universe():
            raise ValueError(
                f"source_ticker {source_ticker} is not in the etf_basic "
                + "universe; etf_nav only accepts ETF instruments (#513)"
            )
        if not source_ticker:
            self._load_etf_universe()
        with tushare_fetch_error_handler("etf_nav", f"fund_nav{scope}"):
            if source_ticker:
                response = self._client.query(
                    api_name="fund_nav",
                    fields=fields,
                    ts_code=source_ticker,
                    start_date=ts_start,
                    end_date=ts_end,
                )
            else:
                # 全市场：端点只接受 nav_date 单日，滚动窗逐日查询后拼接
                frames = [
                    self._client.query(api_name="fund_nav", fields=fields, nav_date=day)
                    for day in _yyyymmdd_range(ts_start, ts_end)
                ]
                response = (
                    pl.concat(frames, how="vertical_relaxed")
                    if frames
                    else pl.DataFrame()
                )
                response = self._filter_non_etf_rows(response)
            # 服务端同 (ts_code, nav_date) 可返回多条不同 ann_date 的披露行
            # （2026-10-05 实测单日响应内重复）——保留最新披露行
            result = (
                TushareDataTransformer.transform(
                    response, f"etf_nav{scope}", ETF_NAV_MAPPING
                )
                .sort("knowledge_date", nulls_last=False)
                .unique(
                    subset=["source_ticker", "trade_date"],
                    keep="last",
                    maintain_order=True,
                )
            )
            if missing := result["knowledge_date"].null_count():
                logger.warning(
                    "ETF NAV disclosure unknown; display and reconciliation only",
                    event="tushare_fund_nav_unknown_disclosure",
                    row_count=result.height,
                    missing_disclosure_count=missing,
                )
            return result
