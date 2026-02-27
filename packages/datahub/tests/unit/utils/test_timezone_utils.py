"""Unit tests for timezone utilities."""

from datetime import date

from ditto_datahub.utils.timezone_utils import (
    MARKET_TIMEZONE_MAP,
    convert_to_utc_midnight,
    get_fred_query_date,
)


class TestMarketTimezoneMap:
    """测试市场时区映射."""

    def test_contains_key_markets(self) -> None:
        """测试包含关键市场."""
        assert "SSE" in MARKET_TIMEZONE_MAP
        assert "NYSE" in MARKET_TIMEZONE_MAP
        assert "FRED" in MARKET_TIMEZONE_MAP
        assert "FX" in MARKET_TIMEZONE_MAP

    def test_shanghai_timezone(self) -> None:
        """测试上海时区."""
        assert MARKET_TIMEZONE_MAP["SSE"] == "Asia/Shanghai"

    def test_new_york_timezone(self) -> None:
        """测试纽约时区."""
        assert MARKET_TIMEZONE_MAP["NYSE"] == "America/New_York"

    def test_london_timezone(self) -> None:
        """测试伦敦时区."""
        assert MARKET_TIMEZONE_MAP["LME"] == "Europe/London"


class TestConvertToUtcMidnight:
    """测试 UTC 午夜时间戳转换."""

    def test_shanghai_date(self) -> None:
        """测试上海日期转换."""
        utc_ts = convert_to_utc_midnight(date(2024, 1, 15), "SSE")
        # 上海 UTC+8，午夜 = UTC 前一日 16:00
        assert utc_ts.year == 2024
        assert utc_ts.month == 1
        assert utc_ts.day == 14  # 前一天

    def test_new_york_date_winter(self) -> None:
        """测试纽约日期转换（冬令时）."""
        # 1月15日在冬令时期间（11月-3月）
        utc_ts = convert_to_utc_midnight(date(2024, 1, 15), "NYSE")
        # 冬令时 UTC-5，午夜 = UTC 05:00
        assert utc_ts.hour == 5
        assert utc_ts.day == 15

    def test_new_york_date_summer(self) -> None:
        """测试纽约日期转换（夏令时）."""
        # 7月15日在夏令时期间（3月-11月）
        utc_ts = convert_to_utc_midnight(date(2024, 7, 15), "NYSE")
        # 夏令时 UTC-4，午夜 = UTC 04:00
        assert utc_ts.hour == 4
        assert utc_ts.day == 15

    def test_london_date_winter(self) -> None:
        """测试伦敦日期转换（冬令时）."""
        # 1月15日在冬令时期间（10月-3月）
        utc_ts = convert_to_utc_midnight(date(2024, 1, 15), "LME")
        # 冬令时 UTC+0，午夜 = UTC 00:00
        assert utc_ts.hour == 0
        assert utc_ts.day == 15

    def test_london_date_summer(self) -> None:
        """测试伦敦日期转换（夏令时）."""
        # 7月15日在夏令时期间（3月-10月）
        utc_ts = convert_to_utc_midnight(date(2024, 7, 15), "LME")
        # 夏令时 UTC+1，午夜 = UTC 前一日 23:00
        assert utc_ts.hour == 23
        assert utc_ts.day == 14  # 前一天

    def test_utc_timezone_attached(self) -> None:
        """测试返回值带有 UTC 时区信息."""
        utc_ts = convert_to_utc_midnight(date(2024, 1, 15), "SSE")
        assert utc_ts.tzinfo is not None


class TestGetFredQueryDate:
    """测试 FRED 查询日期转换."""

    def test_beijing_to_fred(self) -> None:
        """测试北京时间转 FRED 日期."""
        fred_date = get_fred_query_date("2024-01-16")
        assert fred_date == "2024-01-15"

    def test_cross_month_boundary(self) -> None:
        """测试跨月边界."""
        fred_date = get_fred_query_date("2024-02-01")
        assert fred_date == "2024-01-31"

    def test_cross_year_boundary(self) -> None:
        """测试跨年边界."""
        fred_date = get_fred_query_date("2024-01-01")
        assert fred_date == "2023-12-31"

    def test_march_1st_leap_year(self) -> None:
        """测试闰年3月1日."""
        fred_date = get_fred_query_date("2024-03-01")
        assert fred_date == "2024-02-29"  # 2024是闰年

    def test_march_1st_non_leap_year(self) -> None:
        """测试非闰年3月1日."""
        fred_date = get_fred_query_date("2023-03-01")
        assert fred_date == "2023-02-28"  # 2023不是闰年
