"""Tests for Stock adapter."""

from datetime import date
from unittest.mock import MagicMock

import polars as pl
import pytest


@pytest.mark.unit
class TestStockAdapterFetchByTicker:
    """测试 StockAdapter 按股票查询功能."""

    def test_fetch_stock_daily_by_ticker_uses_ts_code(self) -> None:
        """按股票查询应使用 ts_code 参数."""
        from ditto_data.sources.tushare.adapters.stock import StockTushareAdapter

        mock_client = MagicMock()
        mock_client.query.return_value = pl.DataFrame(
            {
                "ts_code": ["000001.SZ"],
                "trade_date": ["20240115"],
                "open": [10.0],
                "high": [11.0],
                "low": [9.5],
                "close": [10.5],
                "pre_close": [10.0],
                "vol": [1000000],
                "amount": [10500000],
                "pct_chg": [5.0],
            }
        )

        adapter = StockTushareAdapter(_client=mock_client)

        # 按股票+时间段查询
        result = adapter.fetch_stock_daily(
            source_ticker="000001.SZ",
            start_date="2024-01-01",
            end_date="2024-01-31",
        )

        # 验证调用了正确的 API
        mock_client.query.assert_called_once()
        call_kwargs = mock_client.query.call_args.kwargs
        assert call_kwargs["api_name"] == "daily"
        assert call_kwargs["ts_code"] == "000001.SZ"
        assert call_kwargs["start_date"] == "20240101"
        assert call_kwargs["end_date"] == "20240131"
        assert isinstance(result, pl.DataFrame)

    def test_fetch_stock_daily_by_ticker_returns_dataframe(self) -> None:
        """按股票查询应返回 DataFrame."""
        from ditto_data.sources.tushare.adapters.stock import StockTushareAdapter

        mock_client = MagicMock()
        mock_client.query.return_value = pl.DataFrame(
            {
                "ts_code": ["000001.SZ", "000001.SZ"],
                "trade_date": ["20240115", "20240116"],
                "open": [10.0, 10.5],
                "high": [11.0, 11.5],
                "low": [9.5, 10.0],
                "close": [10.5, 11.0],
                "pre_close": [10.0, 10.5],
                "vol": [1000000, 1200000],
                "amount": [10500000, 13200000],
                "pct_chg": [5.0, 4.76],
            }
        )

        adapter = StockTushareAdapter(_client=mock_client)
        result = adapter.fetch_stock_daily(
            source_ticker="000001.SZ",
            start_date="2024-01-15",
            end_date="2024-01-16",
        )

        assert isinstance(result, pl.DataFrame)
        assert len(result) == 2

    def test_fetch_stock_daily_by_ticker_empty_result(self) -> None:
        """按股票查询无数据时应返回空 DataFrame."""
        from ditto_data.sources.tushare.adapters.stock import StockTushareAdapter

        mock_client = MagicMock()
        mock_client.query.return_value = pl.DataFrame()

        adapter = StockTushareAdapter(_client=mock_client)
        result = adapter.fetch_stock_daily(
            source_ticker="999999.SZ",
            start_date="2024-01-01",
            end_date="2024-01-31",
        )

        assert isinstance(result, pl.DataFrame)
        assert result.is_empty()


@pytest.mark.unit
class TestStockAdapterFetchMutualExclusiveParams:
    """测试 StockAdapter 参数互斥校验."""

    def test_fetch_stock_daily_mutual_exclusive_params(self) -> None:
        """trade_date 和 source_ticker 互斥."""
        from ditto_data.sources.tushare.adapters.stock import StockTushareAdapter

        mock_client = MagicMock()
        adapter = StockTushareAdapter(_client=mock_client)

        with pytest.raises(ValueError, match="互斥"):
            adapter.fetch_stock_daily(
                trade_date="2024-01-15",
                source_ticker="000001.SZ",
            )

    def test_fetch_stock_daily_requires_at_least_one_param(self) -> None:
        """必须指定 trade_date 或 source_ticker 之一."""
        from ditto_data.sources.tushare.adapters.stock import StockTushareAdapter

        mock_client = MagicMock()
        adapter = StockTushareAdapter(_client=mock_client)

        with pytest.raises(ValueError, match="必须指定"):
            adapter.fetch_stock_daily()

    def test_fetch_stock_daily_by_ticker_requires_date_range(self) -> None:
        """按股票查询必须指定 start_date 和 end_date."""
        from ditto_data.sources.tushare.adapters.stock import StockTushareAdapter

        mock_client = MagicMock()
        adapter = StockTushareAdapter(_client=mock_client)

        with pytest.raises(ValueError, match="必须指定"):
            adapter.fetch_stock_daily(
                source_ticker="000001.SZ",
                start_date="",
                end_date="",
            )


@pytest.mark.unit
class TestStockAdapterNameHistory:
    """测试 fetch_name_history 区间链与 (ts_code,start_date) 唯一性断言."""

    @staticmethod
    def _response(rows: dict[str, list[str | None]]) -> pl.DataFrame:
        # 真实 client 返回全 String 帧；显式 dtype 避免全 None 列被推断为 Null
        return pl.DataFrame(
            {
                "ts_code": pl.Series(rows["ts_code"], dtype=pl.String),
                "name": pl.Series(rows["name"], dtype=pl.String),
                "start_date": pl.Series(rows["start_date"], dtype=pl.String),
                "end_date": pl.Series(rows.get("end_date"), dtype=pl.String),
                "change_reason": pl.Series(rows.get("change_reason"), dtype=pl.String),
                "ann_date": pl.Series(rows.get("ann_date"), dtype=pl.String),
            }
        )

    def test_unique_rows_build_interval_chain(self) -> None:
        """唯一键输入应产出正确 old_name 区间链（相邻更早区间的名称）."""
        from ditto_data.sources.tushare.adapters.stock import StockTushareAdapter

        mock_client = MagicMock()
        mock_client.query.return_value = self._response(
            {
                "ts_code": ["000001.SZ", "000001.SZ", "000002.SZ"],
                "name": ["深发展", "平安银行", "万科A"],
                "start_date": ["20100101", "20120801", "19930101"],
                "end_date": ["20120731", None, None],
                "change_reason": [None, None, None],
                "ann_date": [None, None, None],
            }
        )
        adapter = StockTushareAdapter(_client=mock_client)

        result = adapter.fetch_name_history()

        assert result.height == 3
        chain = result.filter(pl.col("source_ticker") == "000001.SZ").sort(
            "changed_date"
        )
        assert chain["old_name"].to_list() == [None, "深发展"]
        assert chain["new_name"].to_list() == ["深发展", "平安银行"]
        # 其他标的的记录不串链（over("ts_code") 分组）
        assert result.filter(pl.col("source_ticker") == "000002.SZ")[
            "old_name"
        ].to_list() == [None]

    def test_duplicate_start_date_fails_closed(self) -> None:
        """同 (ts_code,start_date) 双记录（#1932 实测形态）应 fail closed."""
        from ditto_data.sources.base import SourceFetchError
        from ditto_data.sources.tushare.adapters.stock import StockTushareAdapter

        mock_client = MagicMock()
        mock_client.query.return_value = self._response(
            {
                "ts_code": ["000001.SZ", "000001.SZ"],
                "name": ["平安银行", "平安银行股份有限公司"],
                "start_date": ["20120801", "20120801"],
                "end_date": [None, None],
                "change_reason": [None, None],
                "ann_date": ["20120801", "20120801"],
            }
        )
        adapter = StockTushareAdapter(_client=mock_client)

        with pytest.raises(SourceFetchError, match=r"duplicate.*start_date"):
            adapter.fetch_name_history()

    def test_empty_response_returns_empty_frame(self) -> None:
        """空响应契约保持：返回带 schema 的空帧."""
        from ditto_data.sources.tushare.adapters.stock import StockTushareAdapter

        mock_client = MagicMock()
        mock_client.query.return_value = pl.DataFrame()
        adapter = StockTushareAdapter(_client=mock_client)

        result = adapter.fetch_name_history()

        assert result.is_empty()
        assert "changed_date" in result.columns


class TestStockAdapterFetchLimitKnowledgeDate:
    """#517：stk_limit 接线——mapping 输出带 kd=T+1."""

    def test_fetch_stock_limit_schema_and_knowledge_date(self) -> None:
        from ditto_data.sources.tushare.adapters.stock import StockTushareAdapter

        client = MagicMock()
        client.query.return_value = pl.DataFrame(
            {
                "ts_code": ["000001.SZ"],
                "trade_date": ["20240102"],
                "up_limit": [11.1],
                "down_limit": [9.1],
            }
        )
        adapter = StockTushareAdapter(_client=client)

        frame = adapter.fetch_stock_limit("2024-01-02")

        client.query.assert_called_once_with(
            api_name="stk_limit",
            trade_date="20240102",
            fields="ts_code,trade_date,up_limit,down_limit",
        )
        assert frame.schema == {
            "source_ticker": pl.String,
            "trade_date": pl.Date,
            "knowledge_date": pl.Date,
            "up_limit": pl.Float64,
            "down_limit": pl.Float64,
        }
        row = frame.row(0, named=True)
        assert row["trade_date"] == date(2024, 1, 2)
        assert row["knowledge_date"] == date(2024, 1, 3)


@pytest.mark.unit
class TestLimitListAdapter:
    """#519 limit_list_d：事件型映射（limit→limit_type，元单位透传）."""

    def test_fetch_limit_list_mapping(self) -> None:
        from ditto_data.sources.tushare.adapters.stock import StockTushareAdapter

        client = MagicMock()
        client.query.return_value = pl.DataFrame(
            {
                "trade_date": ["20260930"],
                "ts_code": ["000011.SZ"],
                "industry": ["房地产开发"],
                "name": ["深物业A"],
                "close": [12.24],
                "pct_chg": [9.97],
                "amount": [971267920.0],
                "limit_amount": [None],
                "float_mv": [6444060646.32],
                "total_mv": [7294784037.12],
                "turnover_ratio": [17.07],
                "fd_amount": [40166967.0],
                "first_time": ["93145"],
                "last_time": ["131124"],
                "open_times": [2],
                "up_stat": ["3/3"],
                "limit_times": [3.0],
                "limit": ["U"],
            }
        )
        adapter = StockTushareAdapter(_client=client)

        frame = adapter.fetch_limit_list(trade_date="2026-09-30")

        assert client.query.call_args.kwargs["api_name"] == "limit_list_d"
        row = frame.row(0, named=True)
        assert row["limit_type"] == "U"
        assert row["pct_change"] == pytest.approx(9.97)
        assert row["open_times"] == 2
        assert row["first_time"] == "93145"
        assert row["knowledge_date"] == date(2026, 10, 1)
