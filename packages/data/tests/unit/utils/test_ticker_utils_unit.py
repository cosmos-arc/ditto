"""test_ticker_utils_unit.py - Ticker 工具函数单元测试。"""

from ditto_data.utils.ticker_utils import get_standard_ticker


class TestGetStandardTicker:
    """get_standard_ticker 函数测试."""

    def test_sse_ticker(self) -> None:
        """测试上交所代码."""
        result = get_standard_ticker("600000", "SSE")
        assert result == "600000.SSE"

    def test_szse_ticker(self) -> None:
        """测试深交所代码."""
        result = get_standard_ticker("000001", "SZSE")
        assert result == "000001.SZSE"

    def test_bse_ticker(self) -> None:
        """测试北交所代码."""
        result = get_standard_ticker("830799", "BSE")
        assert result == "830799.BSE"

    def test_etf_ticker(self) -> None:
        """测试 ETF 代码."""
        result = get_standard_ticker("510300", "SSE")
        assert result == "510300.SSE"
