"""DataRootConfig 单元测试."""

from __future__ import annotations

import tempfile
from pathlib import Path


class TestDataRootConfig:
    """DataRootConfig 测试类."""

    def test_data_root_config_generates_all_paths(self):
        """测试 DataRootConfig 能够生成所有必要的路径."""
        from ditto_datahub.config import DataRootConfig

        with tempfile.TemporaryDirectory() as temp_dir:
            # 使用临时目录作为 DATAROOT
            config = DataRootConfig(data_root=Path(temp_dir))

            # 验证主路径
            assert config.data_root == Path(temp_dir)

            # 验证市场数据路径
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

            # 验证元数据路径
            expected_path = Path(temp_dir) / "metadata" / "metadata.sqlite"
            assert config.metadata_db_path == expected_path

            # 验证资金流路径
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

            # 验证基本面路径
            expected_path = Path(temp_dir) / "fundamental" / "financial"
            assert config.fundamental_financial_path == expected_path

            expected_path = Path(temp_dir) / "fundamental" / "indicator"
            assert config.fundamental_indicator_path == expected_path

            expected_path = Path(temp_dir) / "fundamental" / "forecast"
            assert config.fundamental_forecast_path == expected_path

            expected_path = Path(temp_dir) / "fundamental" / "holding"
            assert config.fundamental_holding_path == expected_path

            # 验证特征路径
            expected_path = Path(temp_dir) / "features" / "technical" / "price"
            assert config.features_technical_price_path == expected_path

            # 验证因子路径
            expected_path = Path(temp_dir) / "factors" / "narrow" / "style"
            assert config.factors_narrow_style_path == expected_path

            expected_path = Path(temp_dir) / "factors" / "wide" / "style"
            assert config.factors_wide_style_path == expected_path

            # 验证宏观路径
            expected_path = Path(temp_dir) / "macro" / "indicators"
            assert config.macro_indicators_path == expected_path

    def test_data_root_config_from_env(self, monkeypatch):
        """测试从环境变量加载配置."""
        from ditto_datahub.config import DataRootConfig

        with tempfile.TemporaryDirectory() as temp_dir:
            # 设置环境变量（Pydantic Settings 会将 DATA_ROOT -> data_root）
            monkeypatch.setenv("DATA_ROOT", temp_dir)

            # 不传参数，从环境变量读取
            config = DataRootConfig()
            assert config.data_root == Path(temp_dir)

    def test_all_paths_are_absolute(self):
        """测试所有路径都是绝对路径."""
        from ditto_datahub.config import DataRootConfig

        with tempfile.TemporaryDirectory() as temp_dir:
            config = DataRootConfig(data_root=Path(temp_dir))

            # 验证所有路径都是绝对路径
            assert config.data_root.is_absolute()
            assert config.market_stock_bars_path.is_absolute()
            assert config.market_etf_bars_path.is_absolute()
            assert config.metadata_db_path.is_absolute()
            assert config.capital_flow_path.is_absolute()

    def test_extra_ignore(self, monkeypatch):
        """测试 extra='ignore' 忽略额外字段."""
        from ditto_datahub.config import DataRootConfig

        with tempfile.TemporaryDirectory() as temp_dir:
            monkeypatch.setenv("UNKNOWN_FIELD", "some_value")
            # 不应该抛出错误
            config = DataRootConfig(data_root=Path(temp_dir))
            assert config is not None
