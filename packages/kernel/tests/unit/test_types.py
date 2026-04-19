"""ditto_kernel.types 单元测试."""

from __future__ import annotations

import pytest
from ditto_kernel.instrument import InstrumentIngestParams


class TestInstrumentIngestParamsDefaults:
    """InstrumentIngestParams 默认值测试."""

    def test_all_none_and_empty(self) -> None:
        """无参数构造时所有字段应为 None 或空字符串."""
        params = InstrumentIngestParams()
        assert params.instrument_id is None
        assert params.standard_ticker is None
        assert params.ticker is None
        assert params.start_date == ""
        assert params.end_date == ""


class TestInstrumentIngestParamsWithIdentifier:
    """InstrumentIngestParams 标识符字段测试."""

    def test_instrument_id(self) -> None:
        """instrument_id 正确赋值."""
        params = InstrumentIngestParams(instrument_id=1_000_001)
        assert params.instrument_id == 1_000_001

    def test_standard_ticker(self) -> None:
        """standard_ticker 正确赋值."""
        params = InstrumentIngestParams(standard_ticker="000001.XSHE")
        assert params.standard_ticker == "000001.XSHE"

    def test_ticker(self) -> None:
        """ticker 正确赋值."""
        params = InstrumentIngestParams(ticker="000001")
        assert params.ticker == "000001"

    def test_multiple_identifiers(self) -> None:
        """可同时设置多个标识符."""
        params = InstrumentIngestParams(
            instrument_id=1,
            standard_ticker="000001.XSHE",
            ticker="000001",
        )
        assert params.instrument_id == 1
        assert params.standard_ticker == "000001.XSHE"
        assert params.ticker == "000001"


class TestInstrumentIngestParamsTimeRange:
    """InstrumentIngestParams 时间范围字段测试."""

    def test_date_range(self) -> None:
        """start_date 和 end_date 正确赋值."""
        params = InstrumentIngestParams(start_date="2025-01-01", end_date="2025-12-31")
        assert params.start_date == "2025-01-01"
        assert params.end_date == "2025-12-31"

    def test_only_start_date(self) -> None:
        """仅设置 start_date."""
        params = InstrumentIngestParams(start_date="2025-06-01")
        assert params.start_date == "2025-06-01"
        assert params.end_date == ""


class TestInstrumentIngestParamsFrozen:
    """InstrumentIngestParams 不可变性测试."""

    def test_frozen(self) -> None:
        """frozen dataclass 不可变."""
        params = InstrumentIngestParams(instrument_id=1)
        with pytest.raises(AttributeError):
            params.instrument_id = 2  # type: ignore[misc]

    def test_frozen_ticker(self) -> None:
        """ticker 字段也不可变."""
        params = InstrumentIngestParams(ticker="000001")
        with pytest.raises(AttributeError):
            params.ticker = "changed"  # type: ignore[misc]

    def test_frozen_start_date(self) -> None:
        """start_date 字段也不可变."""
        params = InstrumentIngestParams()
        with pytest.raises(AttributeError):
            params.start_date = "2025-01-01"  # type: ignore[misc]


class TestInstrumentIngestParamsEquality:
    """InstrumentIngestParams 相等性测试."""

    def test_equal(self) -> None:
        """相同字段值的两个实例应相等."""
        a = InstrumentIngestParams(instrument_id=1, start_date="2025-01-01")
        b = InstrumentIngestParams(instrument_id=1, start_date="2025-01-01")
        assert a == b

    def test_equal_both_default(self) -> None:
        """两个默认构造实例应相等."""
        assert InstrumentIngestParams() == InstrumentIngestParams()

    def test_not_equal_instrument_id(self) -> None:
        """instrument_id 不同应不等."""
        a = InstrumentIngestParams(instrument_id=1)
        b = InstrumentIngestParams(instrument_id=2)
        assert a != b

    def test_not_equal_identifier_type(self) -> None:
        """标识符类型不同应不等."""
        a = InstrumentIngestParams(instrument_id=1)
        b = InstrumentIngestParams(standard_ticker="000001.XSHE")
        assert a != b

    def test_not_equal_date_range(self) -> None:
        """日期范围不同应不等."""
        a = InstrumentIngestParams(start_date="2025-01-01")
        b = InstrumentIngestParams(start_date="2025-06-01")
        assert a != b
