"""DataRootConfig 单元测试."""

from __future__ import annotations

import tempfile
from pathlib import Path

from ditto_datahub.config import DataRootConfig


class TestDataRootConfig:
    """DataRootConfig 单元测试类."""

    def test_data_root_config_generates_all_paths(self) -> None:
        """测试 DataRootConfig 能够生成所有必要的路径."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config = DataRootConfig.model_validate(
                {"data_root": Path(temp_dir), "unknown_field": "some_value"}
            )

            assert config.data_root == Path(temp_dir)

            expected_path = Path(temp_dir) / "market" / "stock" / "bars" / "daily"
            assert config.market_stock_bars_path == expected_path

            expected_path = Path(temp_dir) / "market" / "etf" / "bars" / "daily"
            assert config.market_etf_bars_path == expected_path

            expected_path = Path(temp_dir) / "market" / "index" / "bars" / "daily"
            assert config.market_index_bars_path == expected_path

            expected_path = Path(temp_dir) / "market" / "stock" / "status"
            assert config.market_stock_status_path == expected_path

            expected_path = Path(temp_dir) / "market" / "etf" / "status"
            assert config.market_etf_status_path == expected_path

            expected_path = Path(temp_dir) / "market" / "stock" / "adj"
            assert config.market_stock_adj_path == expected_path

            expected_path = Path(temp_dir) / "market" / "etf" / "adj"
            assert config.market_etf_adj_path == expected_path

            expected_path = Path(temp_dir) / "market" / "etf" / "nav"
            assert config.market_etf_nav_path == expected_path

            expected_path = Path(temp_dir) / "metadata" / "metadata.sqlite"
            assert config.metadata_db_path == expected_path

            expected_path = Path(temp_dir) / "capital" / "flow"
            assert config.capital_flow_path == expected_path

            expected_path = Path(temp_dir) / "capital" / "margin"
            assert config.capital_margin_path == expected_path

            expected_path = Path(temp_dir) / "capital" / "top_board"
            assert config.capital_top_board_path == expected_path

            expected_path = Path(temp_dir) / "capital" / "limit_board"
            assert config.capital_limit_board_path == expected_path

            expected_path = Path(temp_dir) / "capital" / "chip"
            assert config.capital_chip_path == expected_path

            expected_path = Path(temp_dir) / "fundamental" / "financial"
            assert config.fundamental_financial_path == expected_path

            expected_path = Path(temp_dir) / "fundamental" / "indicator"
            assert config.fundamental_indicator_path == expected_path

            expected_path = Path(temp_dir) / "fundamental" / "forecast"
            assert config.fundamental_forecast_path == expected_path

            expected_path = Path(temp_dir) / "fundamental" / "holding"
            assert config.fundamental_holding_path == expected_path

            expected_path = Path(temp_dir) / "features" / "technical" / "price"
            assert config.features_technical_price_path == expected_path

            expected_path = Path(temp_dir) / "factors" / "narrow" / "style"
            assert config.factors_narrow_style_path == expected_path

            expected_path = Path(temp_dir) / "factors" / "wide" / "style"
            assert config.factors_wide_style_path == expected_path

            expected_path = Path(temp_dir) / "macro" / "indicators"
            assert config.macro_indicators_path == expected_path

    def test_data_root_config_default_root(self) -> None:
        """测试默认 data_root."""
        config = DataRootConfig()

        assert config.data_root == Path("data")

    def test_all_paths_are_absolute(self) -> None:
        """测试所有路径都是绝对路径."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config = DataRootConfig(data_root=Path(temp_dir))

            assert config.data_root.is_absolute()
            assert config.market_stock_bars_path.is_absolute()
            assert config.market_etf_bars_path.is_absolute()
            assert config.metadata_db_path.is_absolute()
            assert config.capital_flow_path.is_absolute()

    def test_extra_ignore(self) -> None:
        """测试 extra='ignore' 忽略额外字段."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config = DataRootConfig.model_validate(
                {"data_root": Path(temp_dir), "unknown_field": "some_value"}
            )

            assert config is not None
