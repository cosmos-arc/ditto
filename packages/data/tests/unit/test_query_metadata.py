"""ditto_data.query.metadata 单元测试."""

from unittest.mock import MagicMock

import polars as pl
from ditto_data.query.metadata import MetadataQuerist


class TestMetadataQuerist:
    """MetadataQuerist 门面测试."""

    def _make_querist(self) -> tuple[MetadataQuerist, MagicMock]:
        """创建 querist + mock service."""
        service = MagicMock(
            spec=[
                "list_trading_days",
                "list_calendar_range",
                "find_securities",
                "list_instrument_ids",
            ],
        )
        return MetadataQuerist(metadata_service=service), service

    def test_list_trading_days(self) -> None:
        """应委托给 MetadataService.list_trading_days."""
        querist, service = self._make_querist()
        service.list_trading_days.return_value = ["2024-01-02", "2024-01-03"]
        result = querist.list_trading_days("2024-01-01", "2024-01-31")
        assert result == ["2024-01-02", "2024-01-03"]
        service.list_trading_days.assert_called_once_with(
            "2024-01-01",
            "2024-01-31",
            only_open=True,
        )

    def test_list_trading_days_includes_closed(self) -> None:
        """应支持 only_open=False."""
        querist, service = self._make_querist()
        service.list_trading_days.return_value = ["2024-01-01", "2024-01-02"]
        querist.list_trading_days("2024-01-01", "2024-01-31", only_open=False)
        service.list_trading_days.assert_called_once_with(
            "2024-01-01",
            "2024-01-31",
            only_open=False,
        )

    def test_find_securities(self) -> None:
        """应委托给 MetadataService.find_securities."""
        querist, service = self._make_querist()
        expected_df = pl.DataFrame({"instrument_id": [1, 2]})
        service.find_securities.return_value = expected_df
        result = querist.find_securities(asset_class="etf")
        assert result.equals(expected_df)
        service.find_securities.assert_called_once_with(
            None,
            asset_class="etf",
        )

    def test_find_securities_with_exchange(self) -> None:
        """应传递 exchange 参数."""
        querist, service = self._make_querist()
        service.find_securities.return_value = pl.DataFrame()
        querist.find_securities(asset_class="stock", exchange="XSHE")
        service.find_securities.assert_called_once_with(
            None,
            asset_class="stock",
            exchange="XSHE",
        )

    def test_list_instrument_ids(self) -> None:
        """应委托给 MetadataService.list_instrument_ids."""
        querist, service = self._make_querist()
        service.list_instrument_ids.return_value = [1, 2, 3]
        result = querist.list_instrument_ids(asset_class="etf")
        assert result == [1, 2, 3]
        service.list_instrument_ids.assert_called_once_with(asset_class="etf")
