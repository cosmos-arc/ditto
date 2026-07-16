"""EOD strategy request boundary safety tests."""

import pytest
from ditto_application.eod_request import eod_request_from_strategy_spec
from ditto_strategy.models import StrategySpecRecord


def _record(required_datasets: object) -> StrategySpecRecord:
    return StrategySpecRecord(
        strategy_id="stock-selection",
        name="Stock Selection",
        version=1,
        status="published",
        spec_json={
            "template": "stock_selection",
            "universe": "csi_a_share",
            "asset_class": "stock",
            "required_datasets": required_datasets,
        },
    )


def test_explicit_empty_required_datasets_uses_template_minimum() -> None:
    """An explicit empty list must not bypass the stock data gate."""
    with pytest.warns(UserWarning, match="missing required_datasets"):
        request = eod_request_from_strategy_spec(_record([]))

    assert request.required_datasets == (
        "stock_daily",
        "adj_factor",
        "balance_sheet",
        "income_statement",
    )


def test_explicit_dependencies_cannot_remove_template_minimum() -> None:
    """A partial declaration must retain every dependency owned by the template."""
    request = eod_request_from_strategy_spec(_record(["stock_daily"]))

    assert request.required_datasets == (
        "stock_daily",
        "adj_factor",
        "balance_sheet",
        "income_statement",
    )


def test_unknown_required_dataset_fails_closed() -> None:
    request = eod_request_from_strategy_spec(
        _record(["stock_daily", "unknown_market_feed"])
    )

    assert request.required_datasets == ("__invalid_strategy_spec__",)
