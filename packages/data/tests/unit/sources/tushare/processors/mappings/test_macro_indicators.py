"""Tushare macro indicator tests."""

from ditto_data.sources.tushare.processors.mappings.macro import (
    get_tushare_macro_indicator,
)


class TestTushareRateIndicators:
    """Tushare 利率指标测试."""

    def test_shibor_indicators_exist(self) -> None:
        """测试 Shibor 指标存在."""
        # 全期限 Shibor
        assert get_tushare_macro_indicator("CN_SHIBOR_ON") is not None
        assert get_tushare_macro_indicator("CN_SHIBOR_1W") is not None
        assert get_tushare_macro_indicator("CN_SHIBOR_2W") is not None
        assert get_tushare_macro_indicator("CN_SHIBOR_1M") is not None
        assert get_tushare_macro_indicator("CN_SHIBOR_3M") is not None
        assert get_tushare_macro_indicator("CN_SHIBOR_6M") is not None
        assert get_tushare_macro_indicator("CN_SHIBOR_9M") is not None
        assert get_tushare_macro_indicator("CN_SHIBOR_1Y") is not None

    def test_lpr_indicators_exist(self) -> None:
        """测试 LPR 指标存在."""
        assert get_tushare_macro_indicator("CN_LPR_1Y") is not None
        assert get_tushare_macro_indicator("CN_LPR_5Y") is not None

    def test_libor_hibor_indicators_exist(self) -> None:
        """测试 Libor/Hibor 指标存在."""
        assert get_tushare_macro_indicator("CN_LIBOR_USD") is not None
        assert get_tushare_macro_indicator("CN_HIBOR_ON") is not None

    def test_indicator_attributes(self) -> None:
        """测试指标属性正确."""
        shibor_on = get_tushare_macro_indicator("CN_SHIBOR_ON")
        assert shibor_on is not None
        assert shibor_on.api_name == "shibor"
        assert shibor_on.field == "on"
        assert shibor_on.category == "interest_rate"
        assert shibor_on.frequency == "daily"

        lpr_1y = get_tushare_macro_indicator("CN_LPR_1Y")
        assert lpr_1y is not None
        assert lpr_1y.api_name == "shibor_lpr"
        assert lpr_1y.field == "lpr_1y"
        assert lpr_1y.frequency == "monthly"
