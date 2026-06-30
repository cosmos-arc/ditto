"""Tests for metadata identity resolver context objects."""

from unittest.mock import MagicMock

import pytest
from ditto_data.services.metadata._identity import (
    IdentityResolutionRequest,
    IdentityResolverContext,
    resolve_source_ticker,
)
from ditto_data.sources.exchange_transformers import ExchangeTransformers
from ditto_data.sources.tushare.transformer import TushareExchangeTransformer


@pytest.mark.unit
def test_resolve_source_ticker_accepts_context_objects() -> None:
    """Internal resolver should group dependencies and query input explicitly."""
    instrument_reader = MagicMock()
    instrument_reader.get_source_ticker.return_value = "000001.SZ"

    result = resolve_source_ticker(
        IdentityResolverContext(
            instrument_reader=instrument_reader,
            exchange_transformers=ExchangeTransformers(
                tushare=TushareExchangeTransformer(),
                tdx=MagicMock(),
            ),
        ),
        IdentityResolutionRequest(
            instrument_id=1000001,
            ticker="000001",
            standard_ticker="000001.XSHE",
            asset_class="stock",
            source="tushare",
            asof="2024-01-01",
        ),
    )

    assert result == "000001.SZ"
    instrument_reader.get_source_ticker.assert_called_once_with(
        1000001,
        "tushare",
        "2024-01-01",
    )
