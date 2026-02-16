"""Tests for Index adapter."""

from unittest.mock import MagicMock

import polars as pl
import pytest


@pytest.mark.unit
class TestIndexAdapter:
    """测试 IndexAdapter."""

    def test_index_adapter_has_fetch_basic(self) -> None:
        """验证 IndexAdapter 有 fetch_basic 方法."""
        from ditto_datahub.sources.tushare.adapters.index import IndexTushareAdapter

        # 创建 mock client
        mock_client = MagicMock()
        adapter = IndexTushareAdapter(_client=mock_client)
        assert hasattr(adapter, "fetch_basic")
        assert callable(adapter.fetch_basic)

    def test_index_adapter_has_fetch_daily(self) -> None:
        """验证 IndexAdapter 有 fetch_daily 方法."""
        from ditto_datahub.sources.tushare.adapters.index import IndexTushareAdapter

        # 创建 mock client
        mock_client = MagicMock()
        adapter = IndexTushareAdapter(_client=mock_client)
        assert hasattr(adapter, "fetch_daily")
        assert callable(adapter.fetch_daily)

    def test_fetch_basic_returns_dataframe(self) -> None:
        """验证 fetch_basic 返回 DataFrame."""
        from ditto_datahub.sources.tushare.adapters.index import IndexTushareAdapter

        mock_client = MagicMock()
        mock_response = pl.DataFrame(
            {
                "ts_code": ["000001.SH", "000016.SH"],
                "name": ["上证指数", "上证50"],
                "market": ["SSE", "SSE"],
                "list_date": ["19910715", "20040102"],
            }
        )
        mock_client.query.return_value = mock_response

        adapter = IndexTushareAdapter(_client=mock_client)
        result = adapter.fetch_basic()

        assert isinstance(result, pl.DataFrame)
        mock_client.query.assert_called_once()
