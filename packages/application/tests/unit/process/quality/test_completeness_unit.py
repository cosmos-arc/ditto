"""Quality completeness application process tests."""

from __future__ import annotations

from unittest.mock import MagicMock

import polars as pl
import pytest
from ditto_application.exceptions import AppProcessError
from ditto_application.processes.quality.completeness import (
    QualityCompletenessService,
)
from ditto_application.processes.quality.types import QualityCompletenessRequest


@pytest.mark.unit
def test_completeness_service_compares_expected_and_actual_instruments() -> None:
    market = MagicMock()
    market.find_bars.return_value = pl.DataFrame({"instrument_id": [1001, 1003, 1003]})
    service = QualityCompletenessService(market=market)

    result = service.run(
        QualityCompletenessRequest(
            trade_date="2026-07-16",
            dataset="stock_daily",
            expected_sids=(1001, 1002),
            market_wide=True,
        )
    )

    assert result.to_dict() == {
        "trade_date": "2026-07-16",
        "dataset": "stock_daily",
        "expected_count": 2,
        "actual_count": 2,
        "missing_count": 1,
        "missing_sids": [1002],
        "extra_count": 1,
        "extra_sids": [1003],
        "is_complete": False,
    }
    market.find_bars.assert_called_once_with(
        start="2026-07-16",
        end="2026-07-16",
        market_wide=True,
        asset_class="stock",
        allow_experimental_data=True,
    )


@pytest.mark.unit
def test_completeness_service_uses_adjustment_factor_reader() -> None:
    market = MagicMock()
    market.get_adj_factors.return_value = pl.DataFrame({"instrument_id": [1001, 1002]})
    service = QualityCompletenessService(market=market)

    result = service.run(
        QualityCompletenessRequest(
            trade_date="2026-07-16",
            dataset="adj_factor",
            expected_sids=(1001, 1002),
            market_wide=True,
        )
    )

    assert result.is_complete is True
    market.get_adj_factors.assert_called_once_with(
        start="2026-07-16",
        end="2026-07-16",
        allow_experimental_data=True,
    )
    market.find_bars.assert_not_called()


@pytest.mark.unit
def test_completeness_service_rejects_dataset_without_matching_reader() -> None:
    market = MagicMock()
    market.find_bars.return_value = pl.DataFrame({"instrument_id": [1001]})
    service = QualityCompletenessService(market=market)

    with pytest.raises(AppProcessError, match="index_weight"):
        service.run(
            QualityCompletenessRequest(
                trade_date="2026-07-16",
                dataset="index_weight",
                expected_sids=(1001,),
                market_wide=True,
            )
        )

    market.find_bars.assert_not_called()
    market.get_adj_factors.assert_not_called()
