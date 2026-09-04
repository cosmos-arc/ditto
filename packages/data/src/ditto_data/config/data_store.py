"""数据存储配置 - 统一管理所有存储路径和引擎配置。"""

from __future__ import annotations

from pathlib import Path
from typing import final

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# 路径组：纯计算对象，按子域分组路径推导
# ---------------------------------------------------------------------------


class _MarketPaths:
    """市场数据路径组."""

    __slots__ = ("_root",)

    def __init__(self, root: Path) -> None:
        self._root = root

    @property
    def stock_bars(self) -> Path:
        """股票日线行情路径."""
        return self._root / "market" / "stock" / "bars" / "daily"

    @property
    def etf_bars(self) -> Path:
        """ETF 日线行情路径."""
        return self._root / "market" / "etf" / "bars" / "daily"

    @property
    def index_bars(self) -> Path:
        """指数日线行情路径."""
        return self._root / "market" / "index" / "bars" / "daily"

    @property
    def global_index_bars(self) -> Path:
        """全球指数日线行情路径."""
        return self._root / "market" / "index" / "global_bars"

    @property
    def stock_status(self) -> Path:
        """股票状态路径."""
        return self._root / "market" / "stock" / "status"

    @property
    def etf_status(self) -> Path:
        """ETF 状态路径."""
        return self._root / "market" / "etf" / "status"

    @property
    def stock_adj(self) -> Path:
        """股票复权因子路径."""
        return self._root / "market" / "stock" / "adj"

    @property
    def etf_adj(self) -> Path:
        """ETF 复权因子路径."""
        return self._root / "market" / "etf" / "adj"

    @property
    def etf_nav(self) -> Path:
        """ETF 净值路径."""
        return self._root / "market" / "etf" / "nav"

    def directories(self) -> list[str]:
        """该子域下的所有相对目录."""
        return [
            "market/stock/bars/daily",
            "market/etf/bars/daily",
            "market/index/bars/daily",
            "market/index/global_bars",
            "market/stock/status",
            "market/etf/status",
            "market/stock/adj",
            "market/etf/adj",
            "market/etf/nav",
        ]


class _CapitalPaths:
    """资金流路径组."""

    __slots__ = ("_root",)

    def __init__(self, root: Path) -> None:
        self._root = root

    @property
    def flow(self) -> Path:
        """资金流路径."""
        return self._root / "capital" / "flow"

    @property
    def margin(self) -> Path:
        """融资融券路径."""
        return self._root / "capital" / "margin"

    @property
    def top_board(self) -> Path:
        """龙虎榜路径."""
        return self._root / "capital" / "top_board"

    @property
    def limit_board(self) -> Path:
        """涨跌停路径."""
        return self._root / "capital" / "limit_board"

    @property
    def chip(self) -> Path:
        """筹码分布路径."""
        return self._root / "capital" / "chip"

    def directories(self) -> list[str]:
        """该子域下的所有相对目录."""
        return [
            "capital/flow",
            "capital/margin",
            "capital/top_board",
            "capital/limit_board",
            "capital/chip",
        ]


class _FundamentalPaths:
    """基本面路径组."""

    __slots__ = ("_root",)

    def __init__(self, root: Path) -> None:
        self._root = root

    @property
    def financial(self) -> Path:
        """财务数据路径."""
        return self._root / "fundamental" / "financial"

    @property
    def indicator(self) -> Path:
        """财务指标路径."""
        return self._root / "fundamental" / "indicator"

    @property
    def forecast(self) -> Path:
        """业绩预告路径."""
        return self._root / "fundamental" / "forecast"

    @property
    def holding(self) -> Path:
        """持股数据路径."""
        return self._root / "fundamental" / "holding"

    def directories(self) -> list[str]:
        """该子域下的所有相对目录."""
        return [
            "fundamental/financial",
            "fundamental/indicator",
            "fundamental/forecast",
            "fundamental/holding",
        ]


class _MacroPaths:
    """宏观路径组."""

    __slots__ = ("_root",)

    def __init__(self, root: Path) -> None:
        self._root = root

    @property
    def indicators(self) -> Path:
        """宏观指标路径."""
        return self._root / "macro" / "indicators"

    def directories(self) -> list[str]:
        """该子域下的所有相对目录."""
        return ["macro/indicators"]


class _UtilityPaths:
    """通用路径组（日志、备份、临时、数据库等）."""

    __slots__ = ("_logs_override", "_root")

    def __init__(self, root: Path, logs_override: Path | None = None) -> None:
        self._root = root
        self._logs_override = logs_override

    @property
    def logs(self) -> Path:
        """日志存储路径（支持覆盖）."""
        return self._logs_override or self._root / "logs"

    @property
    def backups(self) -> Path:
        """备份存储路径."""
        return self._root / "backups"

    @property
    def temp(self) -> Path:
        """临时文件存储路径."""
        return self._root / "temp"

    @property
    def db(self) -> Path:
        """数据库存储路径."""
        return self._root / "db"

    @property
    def provider_payloads(self) -> Path:
        """不可变 provider 响应归档路径."""
        return self._root / "provider_payloads"

    def directories(self) -> list[str]:
        """该子域下的所有相对目录."""
        return ["logs", "backups", "temp", "db", "provider_payloads"]


@final
class PathGroups:
    """
    路径组聚合 — 按子域分组访问数据路径.

    用法::

        settings = DataStoreSettings(data_root=Path("/data"))
        settings.paths.market.stock_bars   # /data/market/stock/bars/daily
        settings.paths.capital.flow        # /data/capital/flow
    """

    __slots__ = ("_capital", "_fundamental", "_macro", "_market", "_utility")

    def __init__(self, root: Path, logs_override: Path | None = None) -> None:
        self._market = _MarketPaths(root)
        self._capital = _CapitalPaths(root)
        self._fundamental = _FundamentalPaths(root)
        self._macro = _MacroPaths(root)
        self._utility = _UtilityPaths(root, logs_override)

    @property
    def market(self) -> _MarketPaths:
        """市场数据路径组."""
        return self._market

    @property
    def capital(self) -> _CapitalPaths:
        """资金流路径组."""
        return self._capital

    @property
    def fundamental(self) -> _FundamentalPaths:
        """基本面路径组."""
        return self._fundamental

    @property
    def macro(self) -> _MacroPaths:
        """宏观路径组."""
        return self._macro

    @property
    def utility(self) -> _UtilityPaths:
        """通用路径组."""
        return self._utility

    def all_directories(self) -> list[str]:
        """聚合所有子域的相对目录（含 metadata / locks 等非路径组条目）."""
        dirs: list[str] = []
        dirs.extend(self._market.directories())
        dirs.extend(self._capital.directories())
        dirs.extend(self._fundamental.directories())
        dirs.extend(self._macro.directories())
        dirs.extend(self._utility.directories())
        dirs.append("metadata")
        dirs.append("locks")
        return dirs


# ---------------------------------------------------------------------------
# SQL 引擎配置
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# 数据存储配置主类
# ---------------------------------------------------------------------------


class DataStoreSettings(BaseModel):
    """
    数据存储配置 - 统一配置入口。

    替代原有的 DataRootConfig 和 DatabaseSettings，
    提供所有数据存储相关的配置和路径派生。

    路径可通过两种方式访问：
    1. 顶层 property（向后兼容）：``settings.market_stock_bars_path``
    2. 嵌套路径组（推荐）：``settings.paths.market.stock_bars``

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

    # ========== 嵌套路径组（推荐入口）==========

    @property
    def paths(self) -> PathGroups:
        """按子域分组的路径集合."""
        return PathGroups(self.data_root, self.logs_path_override)

    # ========== 解析后的数据库路径（唯一真源）==========

    @property
    def resolved_sqlite_path(self) -> Path:
        """解析后的 SQLite 路径（唯一真源）。"""
        return self.sqlite_path or self.data_root / "metadata" / "metadata.sqlite"

    @property
    def resolved_duckdb_path(self) -> Path:
        """解析后的 DuckDB 路径。"""
        return self.duckdb_path or self.data_root / "db" / "ditto.duckdb"

    # ========== 路径访问说明 ==========

    def all_directories(self) -> list[str]:
        """
        返回所有数据目录的相对路径列表（相对于 data_root）。

        作为 Data 层目录结构的唯一真源，供 Infra DataRootInitProvider 使用。
        """
        return self.paths.all_directories()


__all__ = ["DataStoreSettings", "PathGroups", "SqlEngineConfig"]
