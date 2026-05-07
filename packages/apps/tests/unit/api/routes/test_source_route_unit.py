"""Tests for source route helper functions.

Verify the extracted helpers:
1. _infer_asset_class — dataset -> asset_class resolution with error handling
2. _resolve_source_ticker — identifier -> source ticker resolution with error handling
"""

from unittest.mock import MagicMock, patch

import pytest
from ditto_application.exceptions import AppQueryError
from ditto_apps.api.errors import APIError, BadRequestError
from ditto_apps.api.routes.source import (
    SourceDataQueryParams,
    _infer_asset_class,
    _resolve_source_ticker,
)
from ditto_kernel import AmbiguousTickerError

# ---------------------------------------------------------------------------
# _infer_asset_class
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestInferAssetClass:
    """Test _infer_asset_class helper function."""

    def test_returns_asset_class_for_known_dataset(self) -> None:
        """Known dataset returns asset class string."""
        mock_facade = MagicMock()
        mock_facade.get_dataset_asset_class.return_value = "stock"
        result = _infer_asset_class(mock_facade, "stock_daily")
        assert result == "stock"
        mock_facade.get_dataset_asset_class.assert_called_once_with("stock_daily")

    def test_raises_bad_request_for_unknown_dataset(self) -> None:
        """Unknown dataset raises BadRequestError."""
        mock_facade = MagicMock()
        mock_facade.get_dataset_asset_class.side_effect = AppQueryError(
            "不支持的数据集: unknown"
        )
        with pytest.raises(BadRequestError, match="不支持的数据集"):
            _infer_asset_class(mock_facade, "unknown")

    def test_raises_bad_request_when_asset_class_is_none(self) -> None:
        """Dataset that does not support instrument queries raises BadRequestError."""
        mock_facade = MagicMock()
        mock_facade.get_dataset_asset_class.return_value = None
        with pytest.raises(BadRequestError, match="不支持按标的查询"):
            _infer_asset_class(mock_facade, "calendar")


# ---------------------------------------------------------------------------
# _resolve_source_ticker
# ---------------------------------------------------------------------------


@pytest.fixture
def query_params() -> SourceDataQueryParams:
    """Create standard query params fixture."""
    return SourceDataQueryParams(
        ticker="000001",
        standard_ticker=None,
        instrument_id=None,
        start_date="2024-01-01",
        end_date="2024-01-31",
    )


@pytest.mark.unit
class TestResolveSourceTicker:
    """Test _resolve_source_ticker helper function."""

    def test_returns_resolved_ticker(self, query_params: SourceDataQueryParams) -> None:
        """Successfully resolves ticker."""
        mock_facade = MagicMock()
        mock_facade.resolve_source_ticker.return_value = "000001.SZ"
        result = _resolve_source_ticker(mock_facade, query_params, "stock", "tushare")
        assert result == "000001.SZ"
        mock_facade.resolve_source_ticker.assert_called_once_with(
            ticker="000001",
            standard_ticker=None,
            instrument_id=None,
            asset_class="stock",
            source="tushare",
        )

    def test_passes_standard_ticker(self) -> None:
        """Passes standard_ticker to facade."""
        params = SourceDataQueryParams(
            ticker=None,
            standard_ticker="000001.XSHE",
            instrument_id=None,
            start_date="2024-01-01",
            end_date="2024-01-31",
        )
        mock_facade = MagicMock()
        mock_facade.resolve_source_ticker.return_value = "000001.SZ"
        result = _resolve_source_ticker(mock_facade, params, "stock", "tushare")
        assert result == "000001.SZ"
        mock_facade.resolve_source_ticker.assert_called_once_with(
            ticker=None,
            standard_ticker="000001.XSHE",
            instrument_id=None,
            asset_class="stock",
            source="tushare",
        )

    def test_passes_instrument_id(self) -> None:
        """Passes instrument_id to facade."""
        params = SourceDataQueryParams(
            ticker=None,
            standard_ticker=None,
            instrument_id=1_000_001,
            start_date="2024-01-01",
            end_date="2024-01-31",
        )
        mock_facade = MagicMock()
        mock_facade.resolve_source_ticker.return_value = "000001.SZ"
        result = _resolve_source_ticker(mock_facade, params, "stock", "tushare")
        assert result == "000001.SZ"
        mock_facade.resolve_source_ticker.assert_called_once_with(
            ticker=None,
            standard_ticker=None,
            instrument_id=1_000_001,
            asset_class="stock",
            source="tushare",
        )

    def test_ambiguous_ticker_raises_bad_request(
        self, query_params: SourceDataQueryParams
    ) -> None:
        """AmbiguousTickerError from facade raises BadRequestError."""
        mock_facade = MagicMock()
        mock_facade.resolve_source_ticker.side_effect = AmbiguousTickerError(
            ticker="000001", matches=[]
        )
        with pytest.raises(BadRequestError, match="歧义"):
            _resolve_source_ticker(mock_facade, query_params, "stock", "tushare")

    def test_identifier_not_found_raises_bad_request(
        self, query_params: SourceDataQueryParams
    ) -> None:
        """IdentifierNotFoundError from facade raises BadRequestError."""
        from ditto_data.errors import IdentifierNotFoundError

        mock_facade = MagicMock()
        mock_facade.resolve_source_ticker.side_effect = IdentifierNotFoundError(
            identifier="999999",
            identifier_type="ticker",
        )
        with pytest.raises(BadRequestError, match="未找到"):
            _resolve_source_ticker(mock_facade, query_params, "stock", "tushare")

    def test_unexpected_exception_raises_api_error(
        self, query_params: SourceDataQueryParams
    ) -> None:
        """Unexpected exceptions are logged and wrapped as APIError."""
        mock_facade = MagicMock()
        mock_facade.resolve_source_ticker.side_effect = RuntimeError("boom")
        with patch("ditto_apps.api.routes.source.logger") as mock_logger:
            with pytest.raises(APIError, match="Failed to resolve ticker"):
                _resolve_source_ticker(mock_facade, query_params, "stock", "tushare")
            mock_logger.exception.assert_called_once_with(
                "Unexpected error resolving ticker"
            )
