"""Market 子域单元测试."""

import pytest
from ditto_kernel.market import (
    CALENDAR_TO_TIMEZONE,
    GRAIN_TO_TIME_KEYS,
    CalendarId,
    GrainId,
    MacroCategory,
    MacroFrequency,
    TimeSpec,
)


class TestCalendarId:
    """CalendarId 类型别名测试."""

    def test_value(self) -> None:
        cal: CalendarId = "cn_stock"
        assert cal == "cn_stock"


class TestGrainId:
    """GrainId 类型别名测试."""

    def test_daily(self) -> None:
        grain: GrainId = "1d"
        assert grain == "1d"

    def test_minute(self) -> None:
        grain: GrainId = "1m"
        assert grain == "1m"


class TestGrainToTimeKeys:
    """GRAIN_TO_TIME_KEYS 映射测试."""

    def test_daily_keys(self) -> None:
        assert GRAIN_TO_TIME_KEYS["1d"] == ("trade_date",)

    def test_minute_keys(self) -> None:
        assert GRAIN_TO_TIME_KEYS["1m"] == ("trade_date", "bar_time")


class TestCalendarToTimezone:
    """CALENDAR_TO_TIMEZONE 映射测试."""

    def test_cn_stock_timezone(self) -> None:
        assert CALENDAR_TO_TIMEZONE["cn_stock"] == "Asia/Shanghai"


class TestMacroCategory:
    """MacroCategory 枚举测试."""

    def test_all_values(self) -> None:
        expected = {
            "economic",
            "interest_rate",
            "exchange_rate",
            "money_supply",
            "prices",
            "employment",
            "credit",
            "survey",
            "commodity",
            "vix",
            "dollar_index",
        }
        assert {e.value for e in MacroCategory} == expected


class TestMacroFrequency:
    """MacroFrequency 枚举测试."""

    def test_all_values(self) -> None:
        expected = {"daily", "monthly", "quarterly"}
        assert {e.value for e in MacroFrequency} == expected


class TestTimeSpec:
    """TimeSpec 值对象测试."""

    def test_frozen(self) -> None:
        spec = TimeSpec(event_time_key="trade_date")
        with pytest.raises(AttributeError):
            spec.event_time_key = "bar_time"

    def test_has_availability_time_true(self) -> None:
        spec = TimeSpec(
            event_time_key="trade_date", availability_time_key="publish_date"
        )
        assert spec.has_availability_time is True

    def test_has_availability_time_false(self) -> None:
        spec = TimeSpec(event_time_key="trade_date")
        assert spec.has_availability_time is False

    def test_default_no_availability(self) -> None:
        spec = TimeSpec(event_time_key="trade_date")
        assert spec.availability_time_key is None
