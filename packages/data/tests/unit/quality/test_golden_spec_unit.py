"""Tests for Golden Dataset model validation."""

import pytest
from ditto_data.quality.golden import (
    AssetType,
    GoldenDatasetOptions,
    GoldenDatasetSpec,
    TickerSpec,
)
from pydantic import ValidationError


@pytest.mark.unit
class TestGoldenDatasetSpecValidation:
    """测试 GoldenDatasetSpec 验证."""

    def test_tickers_accepts_list(self) -> None:
        """接受列表类型的 tickers."""
        spec = GoldenDatasetSpec(tickers=["600519", "000001"])

        assert spec.tickers == ["000001", "600519"]

    def test_tickers_rejects_string_scalar(self) -> None:
        """拒绝字符串标量（常见 YAML 误写）."""
        with pytest.raises(ValidationError) as exc_info:
            GoldenDatasetSpec(tickers="600519")  # type: ignore[arg-type]

        error_msg = str(exc_info.value).lower()
        assert "tickers" in error_msg
        assert "list" in error_msg

    def test_tickers_rejects_int_scalar(self) -> None:
        """拒绝整数标量."""
        with pytest.raises(ValidationError) as exc_info:
            GoldenDatasetSpec(tickers=600519)  # type: ignore[arg-type]

        error_msg = str(exc_info.value).lower()
        assert "tickers" in error_msg

    def test_tickers_rejects_dict(self) -> None:
        """拒绝字典类型."""
        with pytest.raises(ValidationError) as exc_info:
            GoldenDatasetSpec(tickers={"600519": "茅台"})  # type: ignore[arg-type]

        error_msg = str(exc_info.value).lower()
        assert "tickers" in error_msg

    def test_tickers_empty_list_allowed(self) -> None:
        """允许空列表."""
        spec = GoldenDatasetSpec(tickers=[])

        assert spec.tickers == []
        assert spec.is_enabled is False

    def test_tickers_none_allowed(self) -> None:
        """允许 None 值."""
        spec = GoldenDatasetSpec(tickers=None)  # type: ignore[arg-type]

        assert spec.tickers == []

    def test_tickers_deduplicates_and_sorts(self) -> None:
        """去重并排序."""
        spec = GoldenDatasetSpec(tickers=["600519", "000001", "600519"])

        assert spec.tickers == ["000001", "600519"]

    def test_ticker_spec_formats_source_and_standard_tickers(self) -> None:
        """TickerSpec 同时支持裸代码、内部交易所和未知交易所后缀."""
        bare = TickerSpec(ticker="000001")
        sh_stock = TickerSpec(ticker="600519", exchange="XSHG")
        sw_index = TickerSpec(ticker="801010", exchange="SW")
        custom = TickerSpec(ticker="ABC", exchange="CUSTOM")

        assert bare.source_ticker == "000001"
        assert bare.standard_ticker == "000001"
        assert sh_stock.source_ticker == "600519.SH"
        assert sh_stock.standard_ticker == "600519.XSHG"
        assert sw_index.source_ticker == "801010.SI"
        assert custom.source_ticker == "ABC.CUSTOM"

    def test_tickers_parse_mapping_items_and_ignore_invalid_specs(self) -> None:
        """tickers 列表可混合字符串和对象，坏对象只进入裸 ticker 集合."""
        spec = GoldenDatasetSpec(
            tickers=[
                " 600519 ",
                " ",
                {"ticker": "510300", "name": "沪深300ETF", "asset_type": "etf"},
                {"ticker": ""},
                {"ticker": "BAD", "asset_type": "unknown"},
            ]
        )

        assert spec.tickers == ["510300", "600519", "BAD"]
        assert [ticker_spec.ticker for ticker_spec in spec.ticker_specs] == ["510300"]
        assert spec.ticker_specs[0].asset_type == AssetType.ETF

    def test_existing_ticker_specs_are_not_overwritten_by_parsed_specs(self) -> None:
        """显式 ticker_specs 优先于从 tickers 对象中解析出的 specs."""
        explicit = TickerSpec(ticker="000001", asset_type=AssetType.STOCK)

        spec = GoldenDatasetSpec(
            tickers=[{"ticker": "510300", "asset_type": "etf"}],
            ticker_specs=[explicit],
        )

        assert spec.tickers == ["510300"]
        assert spec.ticker_specs == [explicit]

    def test_disabled_options_return_empty_tickers(self) -> None:
        """禁用黄金数据集时不向调用方暴露 ticker."""
        spec = GoldenDatasetSpec(
            tickers=["600519"],
            options=GoldenDatasetOptions(enabled=False),
        )

        assert spec.is_enabled is False
        assert spec.get_tickers() == []

    def test_ticker_spec_lookup_and_asset_type_filters(self) -> None:
        """按 ticker 和资产类型读取完整 spec/source ticker."""
        spec = GoldenDatasetSpec(
            tickers=[
                {
                    "ticker": "600519",
                    "asset_type": "stock",
                    "exchange": "XSHG",
                },
                {
                    "ticker": "510300",
                    "asset_type": "etf",
                    "exchange": "XSHG",
                },
            ]
        )

        assert spec.get_ticker_spec("600519") is not None
        assert spec.get_ticker_spec("missing") is None
        assert spec.get_tickers_by_asset_type(AssetType.ETF) == ["510300"]
        assert spec.get_source_tickers() == ["600519.SH", "510300.SH"]
        assert spec.get_source_tickers(AssetType.STOCK) == ["600519.SH"]
