"""
MarketService 单元测试.

测试 Market 域服务的查询功能。
"""

from datetime import date
from unittest.mock import MagicMock

import polars as pl
import pytest
from ditto_data.services.deps import MarketReaders
from ditto_data.services.market_service import (
    AdjType,
    MarketBarsQuery,
    MarketService,
)


@pytest.fixture
def mock_readers() -> dict[str, MagicMock]:
    """创建 Mock Reader 实例."""
    return {
        "stock_bars": MagicMock(),
        "stock_status": MagicMock(),
        "stock_adj": MagicMock(),
        "etf_bars": MagicMock(),
        "etf_status": MagicMock(),
        "instrument": MagicMock(),
    }


@pytest.fixture
def market_service(
    mock_readers: dict[str, MagicMock],
) -> MarketService:
    """创建 MarketService 实例."""
    read_ports = MarketReaders(
        stock_bars=mock_readers["stock_bars"],
        stock_status=mock_readers["stock_status"],
        stock_adj=mock_readers["stock_adj"],
        etf_bars=mock_readers["etf_bars"],
        etf_status=mock_readers["etf_status"],
        instrument=mock_readers["instrument"],
    )

    return MarketService(
        read_ports=read_ports,
    )


class TestMarketServiceFindBars:
    """测试 find_bars() 方法."""

    def test_find_bars_stock(
        self,
        market_service: MarketService,
        mock_readers: dict[str, MagicMock],
    ) -> None:
        """测试查询股票K线数据."""
        # Arrange - 使用正确的 Stock ID 范围 (1,000,000 - 1,999,999)
        query = MarketBarsQuery(
            instrument_ids=[1_000_001, 1_000_002, 1_000_003],
            start="2024-01-01",
            end="2024-01-05",
            adj=AdjType.NONE,
        )
        mock_df = pl.DataFrame(
            {
                "instrument_id": [1_000_001, 1_000_001, 1_000_002],
                "trade_date": ["2024-01-01", "2024-01-02", "2024-01-01"],
                "open": [10.0, 11.0, 20.0],
                "close": [10.5, 11.5, 20.5],
            }
        )
        mock_readers["stock_bars"].read.return_value = mock_df
        mock_readers["instrument"].list_instrument_ids.return_value = [
            1_000_001,
            1_000_002,
            1_000_003,
        ]

        # Act
        result = market_service.find_bars(query)

        # Assert
        assert len(result) == 3
        mock_readers["stock_bars"].read.assert_called_once()

    def test_find_bars_etf(
        self,
        market_service: MarketService,
        mock_readers: dict[str, MagicMock],
    ) -> None:
        """测试查询 ETF K线数据."""
        # Arrange - 使用正确的 ETF ID 范围 (2,000,000 - 2,999,999)
        query = MarketBarsQuery(
            instrument_ids=[2_000_001, 2_000_002],
            start="2024-01-01",
            end="2024-01-05",
            asset_class="etf",
        )
        mock_df = pl.DataFrame(
            {
                "instrument_id": [2_000_001],
                "trade_date": ["2024-01-01"],
                "open": [1.0],
                "close": [1.05],
            }
        )
        mock_readers["etf_bars"].read.return_value = mock_df

        # Act
        result = market_service.find_bars(query)

        # Assert
        assert len(result) == 1
        mock_readers["etf_bars"].read.assert_called_once()


class TestMarketServiceListBars:
    """测试 list_bars() 便利方法."""

    def test_list_bars_accepts_query_object(
        self,
        market_service: MarketService,
        mock_readers: dict[str, MagicMock],
    ) -> None:
        """list_bars() accepts the same query object as find_bars()."""
        mock_df = pl.DataFrame(
            {
                "instrument_id": [1_000_001],
                "trade_date": ["2024-01-01"],
                "close": [10.5],
            }
        )
        mock_readers["stock_bars"].read.return_value = mock_df

        result = market_service.list_bars(
            MarketBarsQuery(
                instrument_ids=[1_000_001],
                start="2024-01-01",
                end="2024-01-05",
            )
        )

        assert len(result) == 1
        mock_readers["stock_bars"].read.assert_called_once()

    def test_list_bars(
        self,
        market_service: MarketService,
        mock_readers: dict[str, MagicMock],
    ) -> None:
        """测试 list_bars() 便利方法."""
        # Arrange - 使用正确的 Stock ID 范围 (1,000,000 - 1,999,999)
        mock_df = pl.DataFrame(
            {
                "instrument_id": [1_000_001, 1_000_002],
                "trade_date": ["2024-01-01", "2024-01-01"],
                "close": [10.5, 20.5],
            }
        )
        mock_readers["stock_bars"].read.return_value = mock_df

        # Act
        result = market_service.list_bars(
            instrument_ids=[1_000_001, 1_000_002],
            start="2024-01-01",
            end="2024-01-05",
        )

        # Assert
        assert len(result) == 2
        mock_readers["stock_bars"].read.assert_called_once()

    def test_list_bars_with_adj(
        self,
        market_service: MarketService,
        mock_readers: dict[str, MagicMock],
    ) -> None:
        """测试 list_bars() 带复权参数."""
        # Arrange - 使用正确的 Stock ID 范围 (1,000,000 - 1,999,999)
        bars_df = pl.DataFrame(
            {
                "instrument_id": [1_000_001, 1_000_001],
                "trade_date": ["2024-01-01", "2024-01-02"],
                "open": [10.0, 11.0],
                "high": [10.5, 11.5],
                "low": [9.5, 10.5],
                "close": [10.0, 11.0],
                "volume": [1000, 1100],
                "amount": [10000, 11000],
            }
        )
        adj_df = pl.DataFrame(
            {
                "instrument_id": [1_000_001, 1_000_001],
                "trade_date": ["2024-01-01", "2024-01-02"],
                "adj_factor": [1.2, 1.2],
            }
        )
        mock_readers["stock_bars"].read.return_value = bars_df
        mock_readers["stock_adj"].read.return_value = adj_df

        # Act
        result = market_service.list_bars(
            instrument_ids=[1_000_001],
            start="2024-01-01",
            end="2024-01-05",
            adj=AdjType.QFQ,
        )

        # Assert
        assert len(result) == 2


class TestMarketServiceGetConstituents:
    """测试 get_constituents() 方法."""

    def test_get_constituents_not_implemented(
        self, market_service: MarketService
    ) -> None:
        """测试未配置 IndexConstituentReader 时抛出异常."""
        # Act & Assert
        with pytest.raises(
            NotImplementedError, match="IndexConstituentReader not configured"
        ):
            market_service.get_constituents(1)


class TestApplyAdjustmentPitAsof:
    """apply_adjustment 的 PIT as-of 语义回归（#538 CI 恢复阻塞项）."""

    @staticmethod
    def _readers(adj_df: pl.DataFrame) -> MarketReaders:
        stock_adj = MagicMock()
        stock_adj.read.return_value = adj_df
        return MarketReaders(
            stock_bars=MagicMock(),
            stock_status=MagicMock(),
            stock_adj=stock_adj,
            etf_bars=MagicMock(),
            etf_status=MagicMock(),
            instrument=MagicMock(),
        )

    @staticmethod
    def _bars() -> pl.DataFrame:
        return pl.DataFrame(
            {
                "instrument_id": [1_000_001, 1_000_001, 1_000_002, 1_000_002],
                "trade_date": [
                    date(2024, 6, 2),
                    date(2024, 6, 10),
                    date(2024, 6, 2),
                    date(2024, 6, 10),
                ],
                "open": [10.0, 12.0, 20.0, 22.0],
                "high": [10.5, 12.5, 20.5, 22.5],
                "low": [9.5, 11.5, 19.5, 21.5],
                "close": [10.0, 12.0, 20.0, 22.0],
                "volume": [1000, 1100, 2000, 2100],
                "amount": [10000, 11000, 20000, 21000],
            }
        )

    @staticmethod
    def _factors(with_knowledge: bool) -> pl.DataFrame:
        data: dict[str, list[object]] = {
            "instrument_id": [1_000_001, 1_000_002] * 5,
            "trade_date": [date(2024, 6, d) for d in (2, 4, 6, 8, 10) for _ in (0, 1)],
            "adj_factor": [1.0, 1.0, 1.0, 1.0, 2.0, 1.0, 2.0, 1.0, 2.0, 1.0],
        }
        if with_knowledge:
            # 因子发布滞后：6/6 起生效的 2.0 在 6/7 才可知。
            data["knowledge_date"] = [
                date(2024, 6, d) for d in (2, 4, 6, 6, 7, 7, 8, 8, 10, 10)
            ]
        return pl.DataFrame(data)

    def test_asof_backfills_post_asof_rows_with_last_known_factor(self) -> None:
        """窗口越过 asof 的行用截至 asof 已知的最近因子，不因精确 join miss 失败."""
        from ditto_data.services.market_adjustment import apply_adjustment

        result = apply_adjustment(
            self._bars(),
            AdjType.QFQ,
            [1_000_001, 1_000_002],
            date(2024, 6, 2),
            date(2024, 6, 10),
            date(2024, 6, 5),
            self._readers(self._factors(with_knowledge=True)),
        )
        # asof=6/5：已知因子均为 1.0 → 价格不变；6/6 起的 2.0 不可见。
        assert result["close"].to_list() == [10.0, 12.0, 20.0, 22.0]

    def test_asof_and_non_asof_queries_share_row_order(self) -> None:
        """同一查询 asof 与非 asof 返回一致行序（limit 语义不因分支漂移）."""
        from ditto_data.services.market_adjustment import apply_adjustment

        bars = self._bars()
        plain = apply_adjustment(
            bars,
            AdjType.QFQ,
            [1_000_001, 1_000_002],
            date(2024, 6, 1),
            date(2024, 6, 10),
            None,
            self._readers(self._factors(with_knowledge=True)),
        )
        asof = apply_adjustment(
            bars,
            AdjType.QFQ,
            [1_000_001, 1_000_002],
            date(2024, 6, 1),
            date(2024, 6, 10),
            date(2024, 6, 10),
            self._readers(self._factors(with_knowledge=True)),
        )
        assert plain["instrument_id"].to_list() == bars["instrument_id"].to_list()
        assert asof["instrument_id"].to_list() == bars["instrument_id"].to_list()
        assert asof["trade_date"].to_list() == bars["trade_date"].to_list()

    def test_revision_tie_break_takes_latest_known_factor(self) -> None:
        """同 trade_date 多条修订时，join 取 knowledge_date 最大者（晚知者胜）."""
        from ditto_data.services.market_adjustment import apply_adjustment

        revisions = pl.DataFrame(
            {
                "instrument_id": [1_000_001, 1_000_001, 1_000_002],
                "trade_date": [date(2024, 6, 2)] * 3,
                "knowledge_date": [
                    date(2024, 6, 2),
                    date(2024, 6, 3),
                    date(2024, 6, 2),
                ],
                "adj_factor": [1.0, 3.0, 1.0],
            }
        )
        result = apply_adjustment(
            self._bars(),
            AdjType.HFQ,
            [1_000_001, 1_000_002],
            date(2024, 6, 1),
            date(2024, 6, 10),
            date(2024, 6, 10),
            self._readers(revisions),
        )
        # 1_000_001 的两行都拿到 3.0（最大 knowledge_date 的修订，
        # 6/10 行回填同因子）；1_000_002 为 1.0。
        assert result["close"].to_list() == [30.0, 36.0, 20.0, 22.0]
