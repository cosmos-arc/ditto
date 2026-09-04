"""Tests for MacroTushareAdapter."""

from __future__ import annotations

from unittest.mock import MagicMock

import polars as pl
import pytest
from ditto_data.sources.schemas.macro_schemas import MACRO_INDICATOR_SOURCE_SCHEMA


@pytest.mark.unit
class TestMacroTushareAdapterFetchIndicators:
    """Tests for MacroTushareAdapter.fetch_indicators method."""

    def test_fetch_indicators_returns_correct_schema(self) -> None:
        """Return DataFrame with MACRO_INDICATOR_SOURCE_SCHEMA columns."""
        from ditto_data.sources.tushare.adapters.macro import MacroTushareAdapter

        mock_client = MagicMock()
        mock_client.query.return_value = pl.DataFrame(
            {
                "month": ["202401"],
                "nt_yoy": [0.7],
            }
        )

        adapter = MacroTushareAdapter(_client=mock_client)
        result = adapter.fetch_indicators(
            codes=["CN_CPI_YOY"],
            start_date="2024-01-01",
            end_date="2024-01-31",
        )

        expected_columns = set(MACRO_INDICATOR_SOURCE_SCHEMA.schema.keys())
        assert set(result.columns) == expected_columns

    def test_shibor_range_uses_one_bounded_provider_request(self) -> None:
        from ditto_data.sources.tushare.adapters.macro import MacroTushareAdapter

        mock_client = MagicMock()
        mock_client.query.return_value = pl.DataFrame(
            {"date": ["20240102"], "on": [1.5]}
        )
        adapter = MacroTushareAdapter(_client=mock_client)

        result = adapter.fetch_macro_indicators_range(
            "2024-01-01",
            "2024-12-31",
        )

        assert result.height == 1
        mock_client.query.assert_called_once_with(
            api_name="shibor",
            fields="date,on",
            start_date="20240101",
            end_date="20241231",
        )

    def test_fetch_indicators_uses_correct_api_and_field(self) -> None:
        """Uses correct API name and field from metadata."""
        from ditto_data.sources.tushare.adapters.macro import MacroTushareAdapter

        mock_client = MagicMock()
        mock_client.query.return_value = pl.DataFrame(
            {
                "quarter": ["2024Q1"],
                "gdp_yoy": [5.3],
            }
        )

        adapter = MacroTushareAdapter(_client=mock_client)
        adapter.fetch_indicators(
            codes=["CN_GDP_YOY"],
            start_date="2024-01-01",
            end_date="2024-03-31",
        )

        mock_client.query.assert_called_once()
        call_kwargs = mock_client.query.call_args.kwargs
        assert call_kwargs["api_name"] == "cn_gdp"
        # fields should include the required field
        assert "gdp_yoy" in call_kwargs["fields"]

    def test_pmi_uses_uppercase_provider_date_and_value_fields(self) -> None:
        """Normalize the actual cn_pmi provider schema."""
        from datetime import date

        from ditto_data.sources.tushare.adapters.macro import MacroTushareAdapter

        mock_client = MagicMock()
        mock_client.query.return_value = pl.DataFrame(
            {"MONTH": ["202401"], "PMI010000": [49.2]}
        )

        result = MacroTushareAdapter(_client=mock_client).fetch_indicators(
            codes=["CN_PMI_MFG"],
            start_date="2024-01-01",
            end_date="2024-01-31",
            observed_on=date(2026, 9, 1),
        )

        assert result.height == 1
        assert result["date"][0] == date(2024, 1, 1)
        assert result["value"][0] == 49.2
        assert "MONTH" in mock_client.query.call_args.kwargs["fields"]
        assert "PMI010000" in mock_client.query.call_args.kwargs["fields"]

    def test_provider_full_history_response_is_bounded_locally(self) -> None:
        """China macro APIs ignore generic start/end parameters."""
        from datetime import date

        from ditto_data.sources.tushare.adapters.macro import MacroTushareAdapter

        mock_client = MagicMock()
        mock_client.query.return_value = pl.DataFrame(
            {"month": ["202312", "202401", "202402"], "nt_yoy": [0.1, 0.2, 0.3]}
        )

        result = MacroTushareAdapter(_client=mock_client).fetch_indicators(
            codes=["CN_CPI_YOY"],
            start_date="2024-01-01",
            end_date="2024-01-31",
            observed_on=date(2026, 9, 1),
        )

        assert result.get_column("date").to_list() == [date(2024, 1, 1)]

    def test_fetch_indicators_unknown_code_skipped(self) -> None:
        """Unknown indicator codes are skipped."""
        from ditto_data.sources.tushare.adapters.macro import MacroTushareAdapter

        mock_client = MagicMock()
        adapter = MacroTushareAdapter(_client=mock_client)

        result = adapter.fetch_indicators(
            codes=["UNKNOWN_CODE"],
            start_date="2024-01-01",
            end_date="2024-01-31",
        )

        # No API call made
        mock_client.query.assert_not_called()
        # Returns empty DataFrame with correct schema
        assert result.height == 0
        assert set(result.columns) == set(MACRO_INDICATOR_SOURCE_SCHEMA.schema.keys())

    def test_fetch_indicators_empty_response(self) -> None:
        """Empty response returns empty DataFrame with correct schema."""
        from ditto_data.sources.tushare.adapters.macro import MacroTushareAdapter

        mock_client = MagicMock()
        mock_client.query.return_value = pl.DataFrame(
            {
                "month": [],
                "nt_yoy": [],
            }
        )

        adapter = MacroTushareAdapter(_client=mock_client)
        result = adapter.fetch_indicators(
            codes=["CN_CPI_YOY"],
            start_date="2024-01-01",
            end_date="2024-01-31",
        )

        assert result.height == 0
        assert set(result.columns) == set(MACRO_INDICATOR_SOURCE_SCHEMA.schema.keys())

    def test_historical_macro_bootstrap_is_visible_only_from_retrieval_date(
        self,
    ) -> None:
        """A provider lag estimate must never masquerade as publication truth."""
        from datetime import date

        from ditto_data.sources.tushare.adapters.macro import MacroTushareAdapter

        mock_client = MagicMock()
        mock_client.query.return_value = pl.DataFrame(
            {
                "month": ["202401"],
                "nt_yoy": [0.7],
            }
        )

        adapter = MacroTushareAdapter(_client=mock_client)
        result = adapter.fetch_indicators(
            codes=["CN_CPI_YOY"],
            start_date="2024-01-01",
            end_date="2024-01-31",
            observed_on=date(2026, 9, 1),
        )

        assert result.height == 1
        assert result["date"][0] == date(2024, 1, 1)
        assert result["knowledge_date"][0] == date(2026, 9, 1)

    def test_historical_daily_macro_also_uses_retrieval_date(self) -> None:
        """Historical SHIBOR fetches cannot claim same-day provider visibility."""
        from datetime import date

        from ditto_data.sources.tushare.adapters.macro import MacroTushareAdapter

        mock_client = MagicMock()
        mock_client.query.return_value = pl.DataFrame(
            {
                "date": ["20240115"],
                "on": [1.75],
            }
        )

        adapter = MacroTushareAdapter(_client=mock_client)
        result = adapter.fetch_indicators(
            codes=["CN_CREDIT_TS"],
            start_date="2024-01-15",
            end_date="2024-01-15",
            observed_on=date(2026, 9, 1),
        )

        assert result.height == 1
        assert result["date"][0] == date(2024, 1, 15)
        assert result["knowledge_date"][0] == date(2026, 9, 1)

    def test_fetch_multiple_indicators_from_same_api(self) -> None:
        """M0, M1, M2 from same cn_m API use single call."""
        from ditto_data.sources.tushare.adapters.macro import MacroTushareAdapter

        mock_client = MagicMock()
        mock_client.query.return_value = pl.DataFrame(
            {
                "month": ["202401"],
                "m0_yoy": [5.0],
                "m1_yoy": [3.0],
                "m2_yoy": [8.0],
            }
        )

        adapter = MacroTushareAdapter(_client=mock_client)
        result = adapter.fetch_indicators(
            codes=["CN_M0_YOY", "CN_M1_YOY", "CN_M2_YOY"],
            start_date="2024-01-01",
            end_date="2024-01-31",
        )

        # Should call cn_m API once (not 3 times)
        mock_client.query.assert_called_once()
        # Should return 3 rows (one per indicator)
        assert result.height == 3

    def test_fetch_multiple_indicators_from_different_apis(self) -> None:
        """Indicators from different APIs make multiple calls."""
        from ditto_data.sources.tushare.adapters.macro import MacroTushareAdapter

        call_count = 0

        def mock_query(**kwargs):  # type: ignore[no-untyped-def]
            nonlocal call_count
            call_count += 1
            api_name = kwargs.get("api_name")
            if api_name == "cn_cpi":
                return pl.DataFrame({"month": ["202401"], "nt_yoy": [0.7]})
            elif api_name == "cn_ppi":
                return pl.DataFrame({"month": ["202401"], "ppi_yoy": [-2.5]})
            return pl.DataFrame()

        mock_client = MagicMock()
        mock_client.query.side_effect = mock_query

        adapter = MacroTushareAdapter(_client=mock_client)
        result = adapter.fetch_indicators(
            codes=["CN_CPI_YOY", "CN_PPI_YOY"],
            start_date="2024-01-01",
            end_date="2024-01-31",
        )

        # Should make 2 API calls
        assert call_count == 2
        assert result.height == 2

    def test_fetch_indicators_includes_metadata_columns(self) -> None:
        """Result includes all metadata columns."""
        from ditto_data.sources.tushare.adapters.macro import MacroTushareAdapter

        mock_client = MagicMock()
        mock_client.query.return_value = pl.DataFrame(
            {
                "month": ["202401"],
                "nt_yoy": [0.7],
            }
        )

        adapter = MacroTushareAdapter(_client=mock_client)
        result = adapter.fetch_indicators(
            codes=["CN_CPI_YOY"],
            start_date="2024-01-01",
            end_date="2024-01-31",
        )

        assert result["indicator_code"][0] == "CN_CPI_YOY"
        assert result["indicator_name"][0] == "CPI同比"
        assert result["category"][0] == "prices"
        assert result["frequency"][0] == "monthly"
        assert result["source"][0] == "tushare"
        assert result["need_pit"][0] is True

    def test_fetch_indicators_parses_monthly_date(self) -> None:
        """Monthly date string (YYYYMM) is parsed correctly."""
        from datetime import date

        from ditto_data.sources.tushare.adapters.macro import MacroTushareAdapter

        mock_client = MagicMock()
        mock_client.query.return_value = pl.DataFrame(
            {
                "month": ["202401"],
                "nt_yoy": [0.7],
            }
        )

        adapter = MacroTushareAdapter(_client=mock_client)
        result = adapter.fetch_indicators(
            codes=["CN_CPI_YOY"],
            start_date="2024-01-01",
            end_date="2024-01-31",
        )

        assert result["date"][0] == date(2024, 1, 1)

    def test_fetch_indicators_parses_quarterly_date(self) -> None:
        """Quarterly date string (YYYYQq) is parsed correctly."""
        from datetime import date

        from ditto_data.sources.tushare.adapters.macro import MacroTushareAdapter

        mock_client = MagicMock()
        mock_client.query.return_value = pl.DataFrame(
            {
                "quarter": ["2024Q1"],
                "gdp_yoy": [5.3],
            }
        )

        adapter = MacroTushareAdapter(_client=mock_client)
        result = adapter.fetch_indicators(
            codes=["CN_GDP_YOY"],
            start_date="2024-01-01",
            end_date="2024-03-31",
        )

        # 2024Q1 -> 2024-01-01
        assert result["date"][0] == date(2024, 1, 1)

    def test_fetch_indicators_parses_daily_date(self) -> None:
        """Daily date string (YYYYMMDD) is parsed correctly."""
        from datetime import date

        from ditto_data.sources.tushare.adapters.macro import MacroTushareAdapter

        mock_client = MagicMock()
        mock_client.query.return_value = pl.DataFrame(
            {
                "date": ["20240115"],
                "on": [1.75],
            }
        )

        adapter = MacroTushareAdapter(_client=mock_client)
        result = adapter.fetch_indicators(
            codes=["CN_CREDIT_TS"],
            start_date="2024-01-15",
            end_date="2024-01-15",
        )

        assert result["date"][0] == date(2024, 1, 15)
