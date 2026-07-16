"""Strategy-owned daily ingestion scope tests."""

import pytest
from ditto_application.config.ingestion_scope import resolve_ingestion_scope
from ditto_application.exceptions import AppConfigurationError
from ditto_data.models import Dataset


def test_resolves_only_required_dataset_dependency_closure() -> None:
    """A stock-selection EOD must not expand to unrelated registry datasets."""
    scope = resolve_ingestion_scope(
        ("stock_daily", "adj_factor", "balance_sheet", "income_statement")
    )

    assert scope.t0_datasets == (Dataset.STOCK_BASIC,)
    assert scope.t1_levels == (
        (
            Dataset.STOCK_DAILY,
            Dataset.BALANCE_SHEET,
            Dataset.INCOME_STATEMENT,
        ),
        (Dataset.ADJ_FACTOR,),
    )
    assert scope.datasets == (
        Dataset.STOCK_BASIC,
        Dataset.STOCK_DAILY,
        Dataset.BALANCE_SHEET,
        Dataset.INCOME_STATEMENT,
        Dataset.ADJ_FACTOR,
    )


def test_unknown_required_dataset_fails_closed() -> None:
    with pytest.raises(
        AppConfigurationError,
        match="unknown_market_feed",
    ):
        resolve_ingestion_scope(("stock_daily", "unknown_market_feed"))


def test_empty_required_dataset_scope_fails_closed() -> None:
    with pytest.raises(AppConfigurationError, match="at least one"):
        resolve_ingestion_scope(())
