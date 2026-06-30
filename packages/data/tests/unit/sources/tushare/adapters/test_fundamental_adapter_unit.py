"""Tests for FundamentalTushareAdapter."""

from __future__ import annotations

from datetime import date
from typing import Any
from unittest.mock import MagicMock

import polars as pl
import pytest
import pytest_mock
from ditto_data.sources.tushare.adapters import fundamental as fundamental_adapter
from ditto_data.sources.tushare.adapters.fundamental import FundamentalTushareAdapter
from ditto_data.sources.tushare.processors.column_mapping import ColumnMapping

_NOOP_MAPPING = ColumnMapping(
    rename={},
    date_columns={},
    float_columns=[],
)


def _adapter_with_client() -> tuple[FundamentalTushareAdapter, MagicMock]:
    client = MagicMock()
    return FundamentalTushareAdapter(_client=client), client


def _transformed_frame() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "source_ticker": ["000001.SZ"],
            "knowledge_date": [date(2024, 5, 7)],
        }
    )


def _patch_transform(
    mocker: pytest_mock.MockFixture,
    frame: pl.DataFrame | None = None,
) -> MagicMock:
    return mocker.patch.object(
        fundamental_adapter.TushareDataTransformer,
        "transform",
        return_value=frame if frame is not None else _transformed_frame(),
    )


@pytest.mark.unit
class TestFundamentalAdapterFetchFinancial:
    """Shared financial fetch helper behavior."""

    def test_fetch_financial_filters_empty_params_and_adds_pit_columns(
        self,
        mocker: pytest_mock.MockFixture,
    ) -> None:
        """Financial helper filters empty API params and adds PIT columns."""
        adapter, client = _adapter_with_client()
        transform = _patch_transform(mocker)
        client.query.return_value = pl.DataFrame({"raw": ["value"]})

        result = adapter._fetch_financial(
            dataset="sample",
            api_name="sample_api",
            fields="a,b",
            mapping=_NOOP_MAPPING,
            log_name="sample",
            extra_params={
                "ts_code": "000001.SZ",
                "period": None,
                "ann_date": "",
            },
        )

        client.query.assert_called_once_with(
            api_name="sample_api",
            fields="a,b",
            ts_code="000001.SZ",
        )
        transform.assert_called_once_with(
            client.query.return_value,
            "sample",
            _NOOP_MAPPING,
        )
        assert result["effective_from"].to_list() == [date(2024, 5, 7)]
        assert result["effective_to"].null_count() == 1

    def test_fetch_financial_can_omit_extra_params_and_pit_columns(
        self,
        mocker: pytest_mock.MockFixture,
    ) -> None:
        """Financial helper supports bare API calls without PIT decoration."""
        adapter, client = _adapter_with_client()
        _patch_transform(mocker)
        client.query.return_value = pl.DataFrame({"raw": ["value"]})

        result = adapter._fetch_financial(
            dataset="sample",
            api_name="sample_api",
            fields="a,b",
            mapping=_NOOP_MAPPING,
            log_name="sample",
            extra_params=None,
            add_pit=False,
        )

        client.query.assert_called_once_with(api_name="sample_api", fields="a,b")
        assert "effective_from" not in result.columns
        assert "effective_to" not in result.columns


@pytest.mark.unit
class TestFundamentalAdapterFinancialMethods:
    """Financial public methods pass the correct API metadata."""

    @pytest.mark.parametrize(
        ("method_name", "expected"),
        [
            (
                "fetch_balance_sheet",
                {
                    "dataset": "balance_sheet",
                    "api_name": "balancesheet",
                    "log_name": "balance sheet",
                    "extra_params": {
                        "ts_code": "000001.SZ",
                        "start_date": "20240101",
                        "end_date": "20241231",
                    },
                },
            ),
            (
                "fetch_income_statement",
                {
                    "dataset": "income_statement",
                    "api_name": "income",
                    "log_name": "income statement",
                    "extra_params": {
                        "ts_code": "000001.SZ",
                        "start_date": "20240101",
                        "end_date": "20241231",
                    },
                },
            ),
            (
                "fetch_cash_flow",
                {
                    "dataset": "cash_flow",
                    "api_name": "cashflow",
                    "log_name": "cash flow",
                    "extra_params": {
                        "ts_code": "000001.SZ",
                        "start_date": "20240101",
                        "end_date": "20241231",
                    },
                },
            ),
        ],
    )
    def test_standard_financial_methods_delegate_to_shared_helper(
        self,
        mocker: pytest_mock.MockFixture,
        method_name: str,
        expected: dict[str, Any],
    ) -> None:
        """Standard financial methods forward their Tushare API metadata."""
        adapter, _ = _adapter_with_client()
        fetch_financial = mocker.patch.object(
            adapter,
            "_fetch_financial",
            return_value=_transformed_frame(),
        )

        result = getattr(adapter, method_name)(
            ts_code="000001.SZ",
            start_date="20240101",
            end_date="20241231",
        )

        assert result["source_ticker"].item() == "000001.SZ"
        fetch_financial.assert_called_once()
        call_kwargs = fetch_financial.call_args.kwargs
        for key, value in expected.items():
            assert call_kwargs[key] == value
        assert "fields" in call_kwargs
        assert "mapping" in call_kwargs

    @pytest.mark.parametrize(
        ("method_name", "expected"),
        [
            (
                "fetch_balance_sheet_vip",
                {
                    "dataset": "balance_sheet_vip",
                    "api_name": "balancesheet_vip",
                    "log_name": "balance sheet (VIP)",
                },
            ),
            (
                "fetch_income_statement_vip",
                {
                    "dataset": "income_statement_vip",
                    "api_name": "income_vip",
                    "log_name": "income statement (VIP)",
                },
            ),
            (
                "fetch_cash_flow_vip",
                {
                    "dataset": "cash_flow_vip",
                    "api_name": "cashflow_vip",
                    "log_name": "cash flow (VIP)",
                },
            ),
        ],
    )
    def test_vip_financial_methods_delegate_to_shared_helper(
        self,
        mocker: pytest_mock.MockFixture,
        method_name: str,
        expected: dict[str, str],
    ) -> None:
        """VIP financial methods forward period/announcement filters."""
        adapter, _ = _adapter_with_client()
        fetch_financial = mocker.patch.object(
            adapter,
            "_fetch_financial",
            return_value=_transformed_frame(),
        )

        result = getattr(adapter, method_name)(
            period="20240331",
            ann_date="20240430",
            start_date="20240401",
            end_date="20240430",
        )

        assert result["source_ticker"].item() == "000001.SZ"
        fetch_financial.assert_called_once()
        call_kwargs = fetch_financial.call_args.kwargs
        for key, value in expected.items():
            assert call_kwargs[key] == value
        assert call_kwargs["extra_params"] == {
            "period": "20240331",
            "ann_date": "20240430",
            "start_date": "20240401",
            "end_date": "20240430",
        }
        assert "fields" in call_kwargs
        assert "mapping" in call_kwargs


@pytest.mark.unit
class TestFundamentalAdapterDividendAndActions:
    """Dividend and corporate-action adapter parameter behavior."""

    def test_fetch_dividend_includes_all_optional_params_and_pit_columns(
        self,
        mocker: pytest_mock.MockFixture,
    ) -> None:
        """Dividend fetch forwards all filters and adds PIT columns."""
        adapter, client = _adapter_with_client()
        _patch_transform(mocker)
        client.query.return_value = pl.DataFrame({"raw": ["value"]})

        result = adapter.fetch_dividend(
            ts_code="000001.SZ",
            ex_date="20240506",
            start_date="20240501",
            end_date="20240531",
        )

        client.query.assert_called_once()
        call_kwargs = client.query.call_args.kwargs
        assert call_kwargs == {
            "api_name": "dividend",
            "fields": "ts_code,ex_date,cash_div,record_date,ann_date,div_proc",
            "ts_code": "000001.SZ",
            "ex_date": "20240506",
            "start_date": "20240501",
            "end_date": "20240531",
        }
        assert result["effective_from"].to_list() == [date(2024, 5, 7)]
        assert result["effective_to"].null_count() == 1

    def test_fetch_dividend_omits_empty_optional_params(
        self,
        mocker: pytest_mock.MockFixture,
    ) -> None:
        """Dividend fetch skips falsy optional filters."""
        adapter, client = _adapter_with_client()
        _patch_transform(mocker)
        client.query.return_value = pl.DataFrame({"raw": ["value"]})

        adapter.fetch_dividend()

        client.query.assert_called_once_with(
            api_name="dividend",
            fields="ts_code,ex_date,cash_div,record_date,ann_date,div_proc",
        )

    def test_fetch_corporate_actions_includes_all_optional_params(
        self,
        mocker: pytest_mock.MockFixture,
    ) -> None:
        """Corporate-action fetch forwards all filters."""
        adapter, client = _adapter_with_client()
        frame = pl.DataFrame({"source_ticker": ["000001.SZ"]})
        transform = _patch_transform(mocker, frame)
        client.query.return_value = pl.DataFrame({"raw": ["value"]})

        result = adapter.fetch_corporate_actions(
            ts_code="000001.SZ",
            start_date="20240501",
            end_date="20240531",
        )

        client.query.assert_called_once_with(
            api_name="ba",
            fields="ts_code,ann_date,act_date,ba_type,name",
            ts_code="000001.SZ",
            start_date="20240501",
            end_date="20240531",
        )
        transform.assert_called_once_with(
            client.query.return_value,
            "corporate_actions",
            fundamental_adapter.CORPORATE_ACTIONS_MAPPING,
        )
        assert result["source_ticker"].item() == "000001.SZ"

    def test_fetch_corporate_actions_omits_empty_optional_params(
        self,
        mocker: pytest_mock.MockFixture,
    ) -> None:
        """Corporate-action fetch skips falsy optional filters."""
        adapter, client = _adapter_with_client()
        _patch_transform(mocker, pl.DataFrame({"source_ticker": ["000001.SZ"]}))
        client.query.return_value = pl.DataFrame({"raw": ["value"]})

        adapter.fetch_corporate_actions()

        client.query.assert_called_once_with(
            api_name="ba",
            fields="ts_code,ann_date,act_date,ba_type,name",
        )
