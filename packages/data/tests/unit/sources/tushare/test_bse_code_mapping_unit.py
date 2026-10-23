"""#592 bse_mapping 适配器单元测试."""

from unittest.mock import MagicMock

import polars as pl
import pytest
from ditto_data.sources.tushare.adapters.stock import StockTushareAdapter


@pytest.mark.unit
class TestFetchBseCodeMapping:
    def test_returns_selected_columns(self) -> None:
        client = MagicMock()
        client.query.return_value = pl.DataFrame(
            {
                "name": ["星昊医药"],
                "o_code": ["430017.BJ"],
                "n_code": ["920017.BJ"],
                "list_date": ["20230531"],
                # 源端多余列必须被裁掉
                "extra": ["x"],
            }
        )
        adapter = StockTushareAdapter(_client=client)

        frame = adapter.fetch_bse_code_mapping()

        assert frame.columns == ["name", "o_code", "n_code", "list_date"]
        assert frame.height == 1
        client.query.assert_called_once_with(
            api_name="bse_mapping", fields="name,o_code,n_code,list_date"
        )

    def test_empty_response_returns_typed_empty_frame(self) -> None:
        client = MagicMock()
        client.query.return_value = pl.DataFrame()
        adapter = StockTushareAdapter(_client=client)

        frame = adapter.fetch_bse_code_mapping()

        assert frame.height == 0
        assert frame.columns == ["name", "o_code", "n_code", "list_date"]
