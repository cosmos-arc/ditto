# packages/datahub/tests/unit/sources/fred/test_indicators.py

"""Tests for FRED indicator definitions."""


def test_rate_indicators_exist() -> None:
    """测试美国利率指标定义存在."""
    from ditto_datahub.sources.fred.indicators import get_fred_indicator

    # 美国国债收益率
    assert get_fred_indicator("US_BOND_YIELD_1Y") is not None
    assert get_fred_indicator("US_BOND_YIELD_2Y") is not None
    assert get_fred_indicator("US_BOND_YIELD_5Y") is not None
    assert get_fred_indicator("US_BOND_YIELD_10Y") is not None
    assert get_fred_indicator("US_BOND_YIELD_30Y") is not None

    # 利差
    assert get_fred_indicator("US_BOND_SPREAD_10Y2Y") is not None

    # 联邦基金利率
    assert get_fred_indicator("US_FEDFUNDS_M") is not None
    assert get_fred_indicator("US_FEDFUNDS_D") is not None


def test_commodity_indicators_exist() -> None:
    """测试大宗商品指标定义存在."""
    from ditto_datahub.sources.fred.indicators import get_fred_indicator

    # 能源
    assert get_fred_indicator("COMMOD_WTI") is not None
    assert get_fred_indicator("COMMOD_BRENT") is not None

    # 贵金属
    assert get_fred_indicator("COMMOD_GOLD") is not None
    assert get_fred_indicator("COMMOD_SILVER") is not None


def test_vix_indicators_exist() -> None:
    """测试 VIX 指标定义存在."""
    from ditto_datahub.sources.fred.indicators import get_fred_indicator

    assert get_fred_indicator("VIX_30D") is not None
    assert get_fred_indicator("VIX_9D") is not None
