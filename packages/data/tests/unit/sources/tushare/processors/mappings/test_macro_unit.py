"""Tests for Tushare macro indicator metadata."""

from __future__ import annotations

from ditto_data.sources.tushare.processors.mappings.macro import (
    TUSHARE_MACRO_INDICATORS,
    TushareMacroIndicator,
    get_tushare_macro_indicator,
    list_tushare_macro_indicators,
)


class TestTushareMacroIndicatorMetadata:
    """Tests for Tushare macro indicator metadata."""

    def test_indicator_registry_contains_expected_indicators(self) -> None:
        """Registry contains all expected indicators."""
        expected_codes = [
            "CN_GDP_YOY",
            "CN_CPI_YOY",
            "CN_PPI_YOY",
            "CN_PMI_MFG",
            "CN_M2_YOY",
            "CN_M1_YOY",
            "CN_M0_YOY",
            "CN_CREDIT_TS",
        ]
        for code in expected_codes:
            assert code in TUSHARE_MACRO_INDICATORS, f"Missing indicator: {code}"

    def test_gdp_indicator_has_correct_metadata(self) -> None:
        """GDP indicator has correct metadata."""
        gdp = TUSHARE_MACRO_INDICATORS["CN_GDP_YOY"]
        assert gdp.api_name == "cn_gdp"
        assert gdp.code == "CN_GDP_YOY"
        assert gdp.field == "gdp_yoy"
        assert gdp.category == "economic"
        assert gdp.frequency == "quarterly"
        assert gdp.need_pit is True
        assert gdp.release_lag_days == 15

    def test_cpi_indicator_has_correct_metadata(self) -> None:
        """CPI indicator has correct metadata."""
        cpi = TUSHARE_MACRO_INDICATORS["CN_CPI_YOY"]
        assert cpi.api_name == "cn_cpi"
        assert cpi.field == "cpi_yoy"
        assert cpi.category == "prices"
        assert cpi.frequency == "monthly"

    def test_money_supply_indicators_share_same_api(self) -> None:
        """M0, M1, M2 indicators share the same API."""
        m0 = TUSHARE_MACRO_INDICATORS["CN_M0_YOY"]
        m1 = TUSHARE_MACRO_INDICATORS["CN_M1_YOY"]
        m2 = TUSHARE_MACRO_INDICATORS["CN_M2_YOY"]

        assert m0.api_name == "cn_m"
        assert m1.api_name == "cn_m"
        assert m2.api_name == "cn_m"

        assert m0.field == "m0_yoy"
        assert m1.field == "m1_yoy"
        assert m2.field == "m2_yoy"

    def test_shibor_indicator_has_no_release_lag(self) -> None:
        """Shibor indicator has no release lag (daily data)."""
        shibor = TUSHARE_MACRO_INDICATORS["CN_CREDIT_TS"]
        assert shibor.frequency == "daily"
        assert shibor.release_lag_days == 0
        assert shibor.need_pit is False

    def test_get_tushare_macro_indicator_returns_indicator(self) -> None:
        """get_tushare_macro_indicator returns indicator when found."""
        result = get_tushare_macro_indicator("CN_GDP_YOY")
        assert result is not None
        assert isinstance(result, TushareMacroIndicator)
        assert result.code == "CN_GDP_YOY"

    def test_get_tushare_macro_indicator_returns_none_for_unknown(self) -> None:
        """get_tushare_macro_indicator returns None for unknown code."""
        result = get_tushare_macro_indicator("UNKNOWN_CODE")
        assert result is None

    def test_list_tushare_macro_indicators_returns_all(self) -> None:
        """list_tushare_macro_indicators returns all indicators without filter."""
        result = list_tushare_macro_indicators()
        # 8 个原有指标 + 12 个新增利率指标 = 20
        assert len(result) == 20

    def test_list_tushare_macro_indicators_filters_by_api_name(self) -> None:
        """list_tushare_macro_indicators filters by API name."""
        result = list_tushare_macro_indicators(api_name="cn_m")
        assert len(result) == 3
        for indicator in result:
            assert indicator.api_name == "cn_m"

    def test_list_tushare_macro_indicators_filters_by_category(self) -> None:
        """list_tushare_macro_indicators filters by category."""
        result = list_tushare_macro_indicators(category="prices")
        assert len(result) == 2
        for indicator in result:
            assert indicator.category == "prices"

    def test_list_tushare_macro_indicators_filters_by_frequency(self) -> None:
        """list_tushare_macro_indicators filters by frequency."""
        result = list_tushare_macro_indicators(frequency="monthly")
        # CPI, PPI, PMI, M0, M1, M2 是月度 (6) + LPR_1Y, LPR_5Y (2) = 8
        assert len(result) == 8
        for indicator in result:
            assert indicator.frequency == "monthly"

    def test_list_tushare_macro_indicators_combines_filters(self) -> None:
        """list_tushare_macro_indicators combines multiple filters."""
        result = list_tushare_macro_indicators(
            api_name="cn_cpi",
            category="prices",
        )
        assert len(result) == 1
        assert result[0].code == "CN_CPI_YOY"

    def test_indicator_is_frozen_dataclass(self) -> None:
        """TushareMacroIndicator is immutable (frozen)."""
        indicator = TUSHARE_MACRO_INDICATORS["CN_GDP_YOY"]
        # Frozen dataclasses raise AttributeError on assignment
        try:
            indicator.code = "NEW_CODE"  # type: ignore[misc]
            raise AssertionError("Expected frozen dataclass to prevent assignment")
        except AttributeError:
            pass  # Expected

    def test_all_indicators_have_release_lag_days(self) -> None:
        """All indicators have release_lag_days defined."""
        for code, indicator in TUSHARE_MACRO_INDICATORS.items():
            assert hasattr(indicator, "release_lag_days"), (
                f"{code} missing release_lag_days"
            )
            assert isinstance(indicator.release_lag_days, int), (
                f"{code} release_lag_days not int"
            )
