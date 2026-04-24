"""数据存储配置 - 统一管理所有存储路径和引擎配置。"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class SqlEngineConfig(BaseModel):
    """
    SQL 引擎性能配置。

    Attributes:
        enable_plan_cache: 启用查询计划缓存。
        plan_cache_size: 缓存大小。
        slow_query_threshold: 慢查询阈值(秒)。

    """

    model_config = ConfigDict(extra="ignore")

    enable_plan_cache: bool = Field(default=True, description="启用查询计划缓存")
    plan_cache_size: int = Field(default=1000, ge=100, description="缓存大小")
    slow_query_threshold: float = Field(
        default=1.0,
        ge=0.1,
        description="慢查询阈值(秒)",
    )


class DataStoreSettings(BaseModel):
    """
    数据存储配置 - 统一配置入口。

    替代原有的 DataRootConfig 和 DatabaseSettings，
    提供所有数据存储相关的配置和路径派生。

    Attributes:
        data_root: 数据根目录。
        sqlite_path: SQLite 路径覆盖（可选）。
        duckdb_path: DuckDB 路径覆盖（可选）。
        sql_engine: SQL 引擎配置。

    """

    model_config = ConfigDict(extra="ignore")

    # ========== 根配置 ==========
    data_root: Path = Field(default=Path("data"), description="数据根目录")

    # ========== 数据库路径（可选覆盖）==========
    sqlite_path: Path | None = Field(default=None, description="SQLite 路径覆盖")
    duckdb_path: Path | None = Field(default=None, description="DuckDB 路径覆盖")

    # ========== 其他路径覆盖 (Docker 部署用) ==========
    logs_path_override: Path | None = Field(
        default=None, description="日志路径覆盖 (Docker 部署用)"
    )

    # ========== 引擎配置 ==========
    sql_engine: SqlEngineConfig = Field(
        default_factory=SqlEngineConfig,
        description="SQL 引擎配置",
    )

    # ========== 解析后的数据库路径（唯一真源）==========

    @property
    def resolved_sqlite_path(self) -> Path:
        """解析后的 SQLite 路径（唯一真源）。"""
        return self.sqlite_path or self.data_root / "metadata" / "metadata.sqlite"

    @property
    def resolved_duckdb_path(self) -> Path:
        """解析后的 DuckDB 路径。"""
        return self.duckdb_path or self.data_root / "db" / "ditto.duckdb"

    # ========== 元数据路径 ==========

    @property
    def metadata_db_path(self) -> Path:
        """元数据库路径（兼容别名）。"""
        return self.resolved_sqlite_path

    # ========== 市场数据路径 ==========

    @property
    def market_stock_bars_path(self) -> Path:
        """股票日线行情路径。"""
        return self.data_root / "market" / "stock" / "bars" / "daily"

    @property
    def market_etf_bars_path(self) -> Path:
        """ETF 日线行情路径。"""
        return self.data_root / "market" / "etf" / "bars" / "daily"

    @property
    def market_index_bars_path(self) -> Path:
        """指数日线行情路径。"""
        return self.data_root / "market" / "index" / "bars" / "daily"

    @property
    def market_stock_status_path(self) -> Path:
        """股票状态路径。"""
        return self.data_root / "market" / "stock" / "status"

    @property
    def market_etf_status_path(self) -> Path:
        """ETF 状态路径。"""
        return self.data_root / "market" / "etf" / "status"

    @property
    def market_stock_adj_path(self) -> Path:
        """股票复权因子路径。"""
        return self.data_root / "market" / "stock" / "adj"

    @property
    def market_etf_adj_path(self) -> Path:
        """ETF 复权因子路径。"""
        return self.data_root / "market" / "etf" / "adj"

    @property
    def market_etf_nav_path(self) -> Path:
        """ETF 净值路径。"""
        return self.data_root / "market" / "etf" / "nav"

    # ========== 资金流路径 ==========

    @property
    def capital_flow_path(self) -> Path:
        """资金流路径。"""
        return self.data_root / "capital" / "flow"

    @property
    def capital_margin_path(self) -> Path:
        """融资融券路径。"""
        return self.data_root / "capital" / "margin"

    @property
    def capital_top_board_path(self) -> Path:
        """龙虎榜路径。"""
        return self.data_root / "capital" / "top_board"

    @property
    def capital_limit_board_path(self) -> Path:
        """涨跌停路径。"""
        return self.data_root / "capital" / "limit_board"

    @property
    def capital_chip_path(self) -> Path:
        """筹码分布路径。"""
        return self.data_root / "capital" / "chip"

    # ========== 基本面路径 ==========

    @property
    def fundamental_financial_path(self) -> Path:
        """财务数据路径。"""
        return self.data_root / "fundamental" / "financial"

    @property
    def fundamental_indicator_path(self) -> Path:
        """财务指标路径。"""
        return self.data_root / "fundamental" / "indicator"

    @property
    def fundamental_forecast_path(self) -> Path:
        """业绩预告路径。"""
        return self.data_root / "fundamental" / "forecast"

    @property
    def fundamental_holding_path(self) -> Path:
        """持股数据路径。"""
        return self.data_root / "fundamental" / "holding"

    # ========== 宏观路径 ==========

    @property
    def macro_indicators_path(self) -> Path:
        """宏观指标路径。"""
        return self.data_root / "macro" / "indicators"

    # ========== 特征路径 ==========

    @property
    def features_technical_price_path(self) -> Path:
        """技术特征（价格）路径。"""
        return self.data_root / "features" / "technical" / "price"

    @property
    def features_technical_indicators_narrow_path(self) -> Path:
        """技术指标窄表路径。"""
        return self.data_root / "features" / "technical" / "indicators_narrow"

    @property
    def features_technical_indicators_wide_path(self) -> Path:
        """技术指标宽表路径。"""
        return self.data_root / "features" / "technical" / "indicators_wide"

    # ========== 因子路径 ==========

    @property
    def factors_narrow_style_path(self) -> Path:
        """窄风格因子路径。"""
        return self.data_root / "factors" / "narrow" / "style"

    @property
    def factors_wide_style_path(self) -> Path:
        """宽风格因子路径。"""
        return self.data_root / "factors" / "wide" / "style"

    @property
    def factors_narrow_path(self) -> Path:
        """因子窄表路径。"""
        return self.data_root / "factors" / "factors_narrow"

    @property
    def factors_wide_path(self) -> Path:
        """因子宽表路径。"""
        return self.data_root / "factors" / "factors_wide"

    # ========== 通用路径 ==========

    @property
    def logs_path(self) -> Path:
        """日志存储路径（支持覆盖）。"""
        return self.logs_path_override or self.data_root / "logs"

    @property
    def backups_path(self) -> Path:
        """备份存储路径。"""
        return self.data_root / "backups"

    @property
    def temp_path(self) -> Path:
        """临时文件存储路径。"""
        return self.data_root / "temp"

    @property
    def db_path(self) -> Path:
        """数据库存储路径。"""
        return self.data_root / "db"

    def all_directories(self) -> list[str]:
        """
        返回所有数据目录的相对路径列表（相对于 data_root）。

        作为 Data 层目录结构的唯一真源，供 Infra DataRootInitProvider 使用。
        """
        return [
            "market/stock/bars/daily",
            "market/etf/bars/daily",
            "market/index/bars/daily",
            "market/stock/status",
            "market/etf/status",
            "market/stock/adj",
            "market/etf/adj",
            "market/etf/nav",
            "metadata",
            "capital/flow",
            "capital/margin",
            "capital/top_board",
            "capital/limit_board",
            "capital/chip",
            "fundamental/financial",
            "fundamental/indicator",
            "fundamental/forecast",
            "fundamental/holding",
            "features/technical/price",
            "features/technical/indicators_narrow",
            "features/technical/indicators_wide",
            "factors/narrow/style",
            "factors/wide/style",
            "factors/factors_narrow",
            "factors/factors_wide",
            "macro/indicators",
            "logs",
            "backups",
            "temp",
            "db",
            "locks",
        ]


__all__ = ["DataStoreSettings", "SqlEngineConfig"]
