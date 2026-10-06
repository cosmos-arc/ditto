"""数据存储配置 - 统一管理所有存储路径配置。"""

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

    @property
    def stock_limit(self) -> Path:
        """涨跌停价格路径（#517）."""
        return self._root / "market" / "stock" / "limit"

    @property
    def limit_list(self) -> Path:
        """涨跌停/炸板名单路径（#519）."""
        return self._root / "market" / "stock" / "limit_list"

    @property
    def fund_share(self) -> Path:
        """基金份额路径（#522）."""
        return self._root / "market" / "etf" / "fund_share"

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
            "market/stock/limit",
            "market/stock/limit_list",
            "market/etf/fund_share",
        ]


class _CapitalPaths:
    """资金流路径组（#518-#523 数据集路径对齐真实接线）."""

    __slots__ = ("_root",)

    def __init__(self, root: Path) -> None:
        self._root = root

    @property
    def margin(self) -> Path:
        """融资融券路径."""
        return self._root / "capital" / "margin"

    @property
    def moneyflow(self) -> Path:
        """个股资金流向路径（#518）."""
        return self._root / "capital" / "moneyflow"

    @property
    def cyq_perf(self) -> Path:
        """每日筹码及胜率路径（#523）."""
        return self._root / "capital" / "cyq_perf"

    @property
    def top_list(self) -> Path:
        """龙虎榜个股明细路径（#519）."""
        return self._root / "capital" / "top_list"

    @property
    def top_inst(self) -> Path:
        """龙虎榜席位明细路径（#519）."""
        return self._root / "capital" / "top_inst"

    @property
    def hk_hold(self) -> Path:
        """北向持股路径（#520）."""
        return self._root / "capital" / "hk_hold"

    @property
    def hsgt_top10(self) -> Path:
        """沪深港通十大成交股路径（#520）."""
        return self._root / "capital" / "hsgt_top10"

    def directories(self) -> list[str]:
        """该子域下的所有相对目录."""
        return [
            "capital/margin",
            "capital/moneyflow",
            "capital/cyq_perf",
            "capital/top_list",
            "capital/top_inst",
            "capital/hk_hold",
            "capital/hsgt_top10",
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
    def fina_indicator(self) -> Path:
        """官方口径财务指标路径（#521）."""
        return self._root / "fundamental" / "fina_indicator"

    @property
    def fund_portfolio(self) -> Path:
        """基金季度持仓路径（#522）."""
        return self._root / "fundamental" / "fund_portfolio"

    def directories(self) -> list[str]:
        """该子域下的所有相对目录."""
        return [
            "fundamental/financial",
            "fundamental/fina_indicator",
            "fundamental/fund_portfolio",
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
    def provider_payloads(self) -> Path:
        """不可变 provider 响应归档路径."""
        return self._root / "provider_payloads"

    def directories(self) -> list[str]:
        """该子域下的所有相对目录."""
        return ["logs", "backups", "temp", "provider_payloads"]


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

    """

    model_config = ConfigDict(extra="ignore")

    # ========== 根配置 ==========
    data_root: Path = Field(default=Path("data"), description="数据根目录")

    # ========== 数据库路径（可选覆盖）==========
    sqlite_path: Path | None = Field(default=None, description="SQLite 路径覆盖")

    # ========== 其他路径覆盖 (Docker 部署用) ==========
    logs_path_override: Path | None = Field(
        default=None, description="日志路径覆盖 (Docker 部署用)"
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

    # ========== 路径访问说明 ==========

    def all_directories(self) -> list[str]:
        """
        返回所有数据目录的相对路径列表（相对于 data_root）。

        作为 Data 层目录结构的唯一真源，供 Infra DataRootInitProvider 使用。
        """
        return self.paths.all_directories()


__all__ = ["DataStoreSettings", "PathGroups"]
