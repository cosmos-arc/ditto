"""FRED data source implementation."""

from __future__ import annotations

import datetime

import polars as pl

from ditto_data.sources.fred.adapters.commodity import CommodityFredAdapter
from ditto_data.sources.fred.adapters.macro import MacroFredAdapter
from ditto_data.sources.fred.indicators import (
    FRED_INDICATORS,
    FredIndicator,
    list_fred_indicators,
)

# 预计算所有 FRED 指标代码
ALL_FRED_CODES: list[str] = list(FRED_INDICATORS.keys())

# 预计算 commodity/vix 代码
ALL_COMMODITY_CODES: list[str] = [
    ind.code for ind in list_fred_indicators(category="commodity")
]
ALL_VIX_CODES: list[str] = [ind.code for ind in list_fred_indicators(category="vix")]

# 日更有界回看（#432）：月度序列发布滞后约 1 个月、季度约 1 个季度，
# 观察坐标必须回看才能捕获"今天发布、观察期在过去"的值与近期修订。
# 该窗口不声称覆盖所有历史修订——年度季调/基准重算可达约 5 年，
# 更老修订需显式 range 重拉（fetch_macro_indicators_range）。
_DAILY_UPDATE_LOOKBACK_DAYS: dict[str, int] = {
    "daily": 10,
    "weekly": 90,  # 周一发布上周值（#437 GASREGW），13 周回看捕获缺周补发
    "monthly": 400,
    "quarterly": 900,
}


def _lookback_start(trade_date: str, frequency: str) -> str:
    days = _DAILY_UPDATE_LOOKBACK_DAYS.get(frequency, 400)
    start = datetime.date.fromisoformat(trade_date) - datetime.timedelta(days=days)
    return start.isoformat()


class FredSource:
    """
    FRED (Federal Reserve Economic Data) data source.

    仅提供宏观指标和商品/VIX 数据，不继承 DataSource ABC。
    消费者按需依赖 MacroFetcher Protocol 即可。

    Attributes:
        _macro: FRED 宏观数据 adapter。
        _commodity: FRED 商品数据 adapter。
        _api_key: FRED API key。

    """

    def __init__(self, api_key: str | None = None) -> None:
        """
        Initialize FRED source.

        Args:
            api_key: FRED API key（可选，优先使用环境变量）。

        """
        self._api_key = api_key
        self._macro = MacroFredAdapter(api_key=api_key)
        self._commodity = CommodityFredAdapter(api_key=api_key)

    # Macro 相关方法 - 委托给 MacroFredAdapter
    def fetch_macro_indicators(
        self,
        trade_date: str,
        codes: list[str] | None = None,
        *,
        realtime_end: str | None = None,
    ) -> pl.DataFrame:
        """
        Fetch macro indicators from FRED.

        日更按指标频率做有界回看（见 ``_DAILY_UPDATE_LOOKBACK_DAYS``），
        使"发布日在今天、观察期在过去"的值（月度滞后约 1 个月、年度
        季调重算）能被捕获；不再以 observation_start=end=当天 漏采。

        Args:
            trade_date: 交易日期 (YYYY-MM-DD)，回看窗口的右端点。
            codes: 指标代码列表 (如 ["US_CPI_INDEX", "US_GDP_QOQ"])。
                如果为 None，获取所有可用指标。
            realtime_end: 可选 ALFRED PIT 锚点 (YYYY-MM-DD). 对 need_pit
                指标启用真正 point-in-time 查询（观察窗口语义不变）.

        Returns:
            DataFrame with MACRO_INDICATOR_SOURCE_SCHEMA columns。

        Raises:
            SourceFetchError: If fetch fails。

        """
        if codes is None:
            codes = ALL_FRED_CODES

        by_frequency: dict[str, list[str]] = {}
        for code in codes:
            indicator: FredIndicator | None = FRED_INDICATORS.get(code)
            key = indicator.frequency if indicator is not None else "monthly"
            by_frequency.setdefault(key, []).append(code)

        frames: list[pl.DataFrame] = []
        for frequency, group_codes in by_frequency.items():
            start = _lookback_start(trade_date, frequency)
            if realtime_end is not None:
                frames.append(
                    self._macro.fetch_indicators(
                        codes=group_codes,
                        start_date=start,
                        end_date=trade_date,
                        realtime_end=realtime_end,
                    )
                )
            else:
                frames.append(
                    self._macro.fetch_indicators(
                        codes=group_codes,
                        start_date=start,
                        end_date=trade_date,
                    )
                )
        if not frames:  # codes 为空列表：返回 schema 一致的空帧
            return self._macro.fetch_indicators(
                codes=[], start_date=trade_date, end_date=trade_date
            )
        non_empty = [frame for frame in frames if not frame.is_empty()]
        if not non_empty:
            return frames[0]
        return pl.concat(non_empty, how="vertical_relaxed")

    def fetch_macro_indicators_range(
        self,
        codes: list[str],
        start_date: str,
        end_date: str,
        *,
        realtime_start: str | None = None,
        realtime_end: str | None = None,
    ) -> pl.DataFrame:
        """
        Fetch macro indicators for a date range from FRED.

        Args:
            codes: 指标代码列表 (如 ["US_CPI_INDEX", "US_GDP_QOY"])。
            start_date: 开始日期 (YYYY-MM-DD)。
            end_date: 结束日期 (YYYY-MM-DD)。
            realtime_start: 可选 ALFRED realtime 窗口起点 (YYYY-MM-DD).
            realtime_end: 可选 ALFRED PIT 锚点 (YYYY-MM-DD).

        Returns:
            DataFrame with MACRO_INDICATOR_SOURCE_SCHEMA columns。

        Raises:
            SourceFetchError: If fetch fails。

        """
        if realtime_end is not None:
            return self._macro.fetch_indicators(
                codes=codes,
                start_date=start_date,
                end_date=end_date,
                realtime_start=realtime_start,
                realtime_end=realtime_end,
            )
        return self._macro.fetch_indicators(
            codes=codes,
            start_date=start_date,
            end_date=end_date,
        )

    # Commodity 相关方法 - 委托给 CommodityFredAdapter
    def fetch_commodities(
        self,
        codes: list[str],
        start_date: str,
        end_date: str,
    ) -> pl.DataFrame:
        """
        Fetch commodity daily prices from FRED.

        Args:
            codes: Commodity codes (e.g., ["COMMOD_WTI", "COMMOD_GOLD"]).
            start_date: Start date (YYYY-MM-DD).
            end_date: End date (YYYY-MM-DD).

        Returns:
            DataFrame with COMMODITY_SOURCE_SCHEMA columns.

        Raises:
            SourceFetchError: If fetch fails.

        """
        return self._commodity.fetch_commodities(
            codes=codes,
            start_date=start_date,
            end_date=end_date,
        )
