# packages/data/tests/unit/sources/fred/test_indicators.py

"""Tests for FRED indicator definitions."""


def test_rate_indicators_exist() -> None:
    """测试美国利率指标定义存在."""
    from ditto_data.sources.fred.indicators import get_fred_indicator

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
    """测试大宗商品指标定义存在；死序列已清理（#432）."""
    from ditto_data.sources.fred.indicators import get_fred_indicator

    # 能源
    assert get_fred_indicator("COMMOD_WTI") is not None
    assert get_fred_indicator("COMMOD_BRENT") is not None

    # 死序列不注册（核查依据见 indicators.py 文件头）：
    # - GOLDAMGBD228NLBM/SLVPRUSD：FRED 2022-01 官方公告移除 IBA/LBMA 数据
    # - 金银参考改由 Tushare fx_daily FXCM bid 承担（不同基准，身份分离）
    assert get_fred_indicator("COMMOD_GOLD") is None
    assert get_fred_indicator("COMMOD_SILVER") is None


def test_vix_indicators_exist() -> None:
    """测试 VIX 指标定义存在；VIX9D 已隔离（#432）."""
    from ditto_data.sources.fred.indicators import get_fred_indicator

    assert get_fred_indicator("VIX_30D") is not None
    # VIX9D 序列页访问失败 + 前轮 404，隔离出默认批次
    assert get_fred_indicator("VIX_9D") is None


def test_level_series_codes_do_not_promise_yoy() -> None:
    """注册拉取 level/index 序列的代码不得承诺同比（#432）."""
    from ditto_data.sources.fred.indicators import FRED_INDICATORS

    for code in (
        "US_CPI_INDEX",
        "US_CORE_CPI_INDEX",
        "US_PCE_INDEX",
        "US_CORE_PCE_INDEX",
        "US_M2",
    ):
        assert code in FRED_INDICATORS
        assert "YOY" not in code
    # 旧误名代码已移除
    for removed in ("US_CPI_YOY", "US_PCE_YOY", "US_M2_YOY"):
        assert removed not in FRED_INDICATORS


def test_revisable_series_need_pit() -> None:
    """UNRATE/M2 会发布修订，need_pit 不得为 False（#432）."""
    from ditto_data.sources.fred.indicators import get_fred_indicator

    assert get_fred_indicator("US_UNRATE").need_pit is True
    assert get_fred_indicator("US_M2").need_pit is True


def test_dollar_index_indicators_exist() -> None:
    """测试美元指数指标定义存在."""
    from ditto_data.sources.fred.indicators import get_fred_indicator

    indicator = get_fred_indicator("US_DOLLAR_INDEX_BROAD")
    assert indicator is not None
    assert indicator.series_id == "DTWEXBGS"
    assert indicator.category == "dollar_index"
    assert indicator.frequency == "daily"
    assert indicator.need_pit is False


def test_models_mirror_matches_registry() -> None:
    """镜像 ⊇ 注册表，且多余项恰为已退役 FRED 代码（供 application 层使用）."""
    from ditto_data.models import FRED_INDICATOR_CODES
    from ditto_data.sources.fred.indicators import FRED_INDICATORS

    retired = {
        "US_CPI_YOY",
        "US_CPI_CORE_YOY",
        "US_PCE_YOY",
        "US_PCE_CORE_YOY",
        "US_M2_YOY",
    }
    assert frozenset(FRED_INDICATORS) <= FRED_INDICATOR_CODES
    assert FRED_INDICATOR_CODES - frozenset(FRED_INDICATORS) == retired
    # 退役代码不在注册表（防止新旧并存）
    assert not (retired & frozenset(FRED_INDICATORS))
