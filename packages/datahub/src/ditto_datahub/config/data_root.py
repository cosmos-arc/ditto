"""DataRoot 配置 - 统一的数据根路径配置."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class DataRootConfig(BaseModel):
    """
    数据根路径配置。

    由应用层显式注入，不在此读取环境变量或配置文件。
    所有路径基于 data_root 派生。
    """

    model_config = ConfigDict(extra="ignore")

    data_root: Path = Field(
        default=Path("data"),
        description="数据根目录",
    )
    """数据根目录。由应用层显式注入。"""
    # ========== 市场数据路径 ==========

    @property
    def market_stock_bars_path(self) -> Path:
        """股票日线行情路径."""
        return self.data_root / "market" / "stock" / "bars" / "daily"

    @property
    def market_etf_bars_path(self) -> Path:
        """ETF 日线行情路径."""
        return self.data_root / "market" / "etf" / "bars" / "daily"

    @property
    def market_index_bars_path(self) -> Path:
        """指数日线行情路径."""
        return self.data_root / "market" / "index" / "bars" / "daily"

    @property
    def market_stock_status_path(self) -> Path:
        """股票状态路径."""
        return self.data_root / "market" / "stock" / "status"

    @property
    def market_etf_status_path(self) -> Path:
        """ETF 状态路径."""
        return self.data_root / "market" / "etf" / "status"

    @property
    def market_stock_adj_path(self) -> Path:
        """股票复权因子路径."""
        return self.data_root / "market" / "stock" / "adj"

    @property
    def market_etf_adj_path(self) -> Path:
        """ETF 复权因子路径."""
        return self.data_root / "market" / "etf" / "adj"

    @property
    def market_etf_nav_path(self) -> Path:
        """ETF 净值路径."""
        return self.data_root / "market" / "etf" / "nav"

    # ========== 元数据路径 ==========

    @property
    def metadata_db_path(self) -> Path:
        """元数据库路径."""
        return self.data_root / "metadata" / "metadata.sqlite"

    # ========== 资金流路径 ==========

    @property
    def capital_flow_path(self) -> Path:
        """资金流路径."""
        return self.data_root / "capital" / "flow"

    @property
    def capital_margin_path(self) -> Path:
        """融资融券路径."""
        return self.data_root / "capital" / "margin"

    @property
    def capital_top_board_path(self) -> Path:
        """龙虎榜路径."""
        return self.data_root / "capital" / "top_board"

    @property
    def capital_limit_board_path(self) -> Path:
        """涨跌停路径."""
        return self.data_root / "capital" / "limit_board"

    @property
    def capital_chip_path(self) -> Path:
        """筹码分布路径."""
        return self.data_root / "capital" / "chip"

    # ========== 基本面路径 ==========

    @property
    def fundamental_financial_path(self) -> Path:
        """财务数据路径."""
        return self.data_root / "fundamental" / "financial"

    @property
    def fundamental_indicator_path(self) -> Path:
        """财务指标路径."""
        return self.data_root / "fundamental" / "indicator"

    @property
    def fundamental_forecast_path(self) -> Path:
        """业绩预告路径."""
        return self.data_root / "fundamental" / "forecast"

    @property
    def fundamental_holding_path(self) -> Path:
        """持股数据路径."""
        return self.data_root / "fundamental" / "holding"

    # ========== 特征路径 ==========

    @property
    def features_technical_price_path(self) -> Path:
        """技术特征（价格）路径."""
        return self.data_root / "features" / "technical" / "price"

    # ========== 特征路径 (扩展) ==========

    @property
    def features_technical_indicators_narrow_path(self) -> Path:
        """技术指标窄表路径."""
        return self.data_root / "features" / "technical" / "indicators_narrow"

    @property
    def features_technical_indicators_wide_path(self) -> Path:
        """技术指标宽表路径."""
        return self.data_root / "features" / "technical" / "indicators_wide"

    # ========== 因子路径 (更新) ==========

    @property
    def factors_narrow_style_path(self) -> Path:
        """窄风格因子路径."""
        return self.data_root / "factors" / "narrow" / "style"

    @property
    def factors_wide_style_path(self) -> Path:
        """宽风格因子路径."""
        return self.data_root / "factors" / "wide" / "style"

    @property
    def factors_narrow_path(self) -> Path:
        """因子窄表路径."""
        return self.data_root / "factors" / "factors_narrow"

    @property
    def factors_wide_path(self) -> Path:
        """因子宽表路径."""
        return self.data_root / "factors" / "factors_wide"

    # ========== 宏观路径 ==========

    @property
    def macro_indicators_path(self) -> Path:
        """宏观指标路径."""
        return self.data_root / "macro" / "indicators"

    # ========== 通用路径 ==========

    @property
    def logs_path(self) -> Path:
        """日志存储路径."""
        return self.data_root / "logs"

    @property
    def backups_path(self) -> Path:
        """备份存储路径."""
        return self.data_root / "backups"

    @property
    def temp_path(self) -> Path:
        """临时文件存储路径."""
        return self.data_root / "temp"

    @property
    def db_path(self) -> Path:
        """数据库存储路径."""
        return self.data_root / "db"


__all__ = ["DataRootConfig"]
