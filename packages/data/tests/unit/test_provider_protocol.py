"""ditto_data.provider 单元测试（DataProvider Protocol + 查询契约）."""

import polars as pl
from ditto_data.provider import BarQuery, DataProvider, InstrumentQuery


class TestBarQuery:
    """BarQuery 值对象测试."""

    def test_creation(self) -> None:
        """应正确创建 BarQuery."""
        query = BarQuery(
            instruments=["000001.SZ", "600000.SH"],
            start="2024-01-01",
            end="2024-12-31",
            frequency="daily",
            adj="hfq",
        )
        assert query.instruments == ("000001.SZ", "600000.SH")
        assert query.start == "2024-01-01"
        assert query.end == "2024-12-31"
        assert query.frequency == "daily"
        assert query.adj == "hfq"

    def test_frozen(self) -> None:
        """BarQuery 应为不可变."""
        query = BarQuery(
            instruments=["000001.SZ"],
            start="2024-01-01",
            end="2024-12-31",
        )
        try:
            query.start = "2023-01-01"  # type: ignore[misc]
            msg = "应为 frozen"
            raise AssertionError(msg)
        except AttributeError:
            pass

    def test_defaults(self) -> None:
        """可选字段应有默认值."""
        query = BarQuery(
            instruments=["000001.SZ"],
            start="2024-01-01",
            end="2024-12-31",
        )
        assert query.frequency == "daily"
        assert query.adj == "none"

    def test_instruments_is_tuple(self) -> None:
        """instruments 应转为 tuple（不可变）."""
        query = BarQuery(
            instruments=["000001.SZ", "600000.SH"],
            start="2024-01-01",
            end="2024-12-31",
        )
        assert isinstance(query.instruments, tuple)


class TestInstrumentQuery:
    """InstrumentQuery 值对象测试."""

    def test_creation_with_all_fields(self) -> None:
        """应正确创建带所有字段的查询."""
        query = InstrumentQuery(
            asset_class="etf",
            exchange="XSHE",
            universe="hs300",
        )
        assert query.asset_class == "etf"
        assert query.exchange == "XSHE"
        assert query.universe == "hs300"

    def test_defaults_are_none(self) -> None:
        """所有字段默认为 None."""
        query = InstrumentQuery()
        assert query.asset_class is None
        assert query.exchange is None
        assert query.universe is None

    def test_frozen(self) -> None:
        """InstrumentQuery 应为不可变."""
        query = InstrumentQuery(asset_class="etf")
        try:
            query.asset_class = "stock"  # type: ignore[misc]
            msg = "应为 frozen"
            raise AssertionError(msg)
        except AttributeError:
            pass


class TestBarQueryAsof:
    """BarQuery.asof 字段测试."""

    def test_get_bars_defaults_asof_to_none(self) -> None:
        """BarQuery 未指定 asof 时应默认为 None（当前行为不变）。"""
        query = BarQuery(
            instruments=["000001.SZ"],
            start="2024-01-01",
            end="2024-12-31",
        )
        assert query.asof is None
        assert query.instruments == ("000001.SZ",)

    def test_get_bars_with_asof(self) -> None:
        """BarQuery 指定 asof 后应正确存储。"""
        query = BarQuery(
            instruments=["000001.SZ"],
            start="2024-01-01",
            end="2024-12-31",
            asof="2024-06-01",
        )
        assert query.asof == "2024-06-01"
        assert query.instruments == ("000001.SZ",)

    def test_get_bars_asof_with_other_params(self) -> None:
        """BarQuery asof 应与其他参数共存。"""
        query = BarQuery(
            instruments=["510300.SH", "000001.SZ"],
            start="2024-01-01",
            end="2024-12-31",
            frequency="weekly",
            adj="hfq",
            asof="2024-06-01",
        )
        assert query.asof == "2024-06-01"
        assert query.frequency == "weekly"
        assert query.adj == "hfq"


class TestDataProviderProtocol:
    """DataProvider Protocol 一致性测试."""

    def test_protocol_methods(self) -> None:
        """DataProvider 应定义所需方法签名."""

        class StubProvider:
            def get_bars(self, query: BarQuery) -> pl.DataFrame:
                return pl.DataFrame()

            def get_instruments(self, query: InstrumentQuery) -> pl.DataFrame:
                return pl.DataFrame()

            def get_schedule(self, start: str, end: str) -> pl.DataFrame:
                return pl.DataFrame()

            def get_factor(
                self,
                name: str,
                instruments: tuple[str, ...],
                start: str,
                end: str,
                asof: str | None = None,
            ) -> pl.DataFrame:
                return pl.DataFrame()

        provider: DataProvider = StubProvider()
        result = provider.get_bars(
            BarQuery(
                instruments=["000001.SZ"],
                start="2024-01-01",
                end="2024-12-31",
            ),
        )
        assert isinstance(result, pl.DataFrame)
