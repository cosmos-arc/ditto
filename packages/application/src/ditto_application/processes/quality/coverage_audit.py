"""
价格与身份覆盖审计服务（#624 / 父规格 #621 P2；#625 扩展资金面数据集）.

编排 data 层纯审计函数（``ditto_data.quality.coverage_audit``）：从
MarketService/MetadataService/CapitalStore 取物理帧（日线/状态/复权因子/
名册/日历/资金面数据集），对给定窗口产出逐证券交易日缺口归因报告。
物理覆盖核验语义与 PIT 消费查询的边界见纯函数模块 docstring。

dataset 语义（#625）：
- ``daily``：价格日线（#624 原语义，复权因子在场核验仅此档）；
- ``moneyflow``：个股资金流（stock 名册 × 日历，停牌归因沿用 stock_status；
  复用价格审计的会话网格，bars 换为 moneyflow 业务键）；
- ``fund_share``：ETF 场内份额（etf 名册 × 日历；ETF 无状态数据集，
  缺口诚实落 no_status_dataset 证据边界）。

入口：``ops audit-price-coverage``（daily）与 ``ops audit-capital-coverage``
（moneyflow/fund_share，CLI）；无例行调度，按需复跑刷新证据。
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from typing import Any

import polars as pl
from ditto_data.quality.coverage_audit import (
    CalendarAudit,
    SessionCoverageAudit,
    audit_session_coverage,
    audit_trading_calendar,
)
from ditto_data.services.capital_store import CapitalStore
from ditto_data.services.market_service import MarketService
from ditto_data.services.metadata_service import MetadataService

from ditto_application.exceptions import AppQueryError

__all__ = [
    "PriceCoverageAuditReport",
    "PriceCoverageAuditRequest",
    "PriceCoverageAuditService",
    "dataset_asset_class",
]

_ASSET_CLASSES = frozenset({"stock", "etf"})
# 数据集档位 → 允许的资产类（名册与状态归因口径由资产类决定）。
_DATASET_ASSET_CLASSES: Mapping[str, frozenset[str]] = {
    "daily": frozenset({"stock", "etf"}),
    "moneyflow": frozenset({"stock"}),
    "fund_share": frozenset({"etf"}),
}


def dataset_asset_class(dataset: str) -> str:
    """单资产类数据集档位的名册口径（CLI 用）；未知/多资产类档位响亮失败."""
    allowed = _DATASET_ASSET_CLASSES.get(dataset)
    if allowed is None:
        raise AppQueryError(
            f"未知数据集档位 {dataset!r}: 允许 {sorted(_DATASET_ASSET_CLASSES)}"
        )
    if len(allowed) != 1:
        raise AppQueryError(
            f"数据集档位 {dataset!r} 支持多资产类 {sorted(allowed)}: "
            "须显式指定 asset_class"
        )
    return next(iter(allowed))


# 空窗读取（窗口早于数据集起点）经 ParquetStore.read 可能返回无列空帧；
# 补齐最小 schema 让审计产出归因报告而非在 select 上崩溃。
_BAR_KEYS_SCHEMA: Mapping[str, type[pl.DataType]] = {
    "instrument_id": pl.Int64,
    "trade_date": pl.Date,
}
_MASTER_KEYS_SCHEMA: Mapping[str, type[pl.DataType]] = {
    "instrument_id": pl.Int64,
    "list_date": pl.Date,
    "delist_date": pl.Date,
}
_STATUS_KEYS_SCHEMA: Mapping[str, type[pl.DataType]] = {
    "instrument_id": pl.Int64,
    "trade_date": pl.Date,
    "is_suspended": pl.Boolean,
}


def _ensure_schema(
    frame: pl.DataFrame, schema: Mapping[str, type[pl.DataType]]
) -> pl.DataFrame:
    """缺列帧（空窗读取形态）替换为带 schema 的空帧，其余原样返回."""
    if all(column in frame.columns for column in schema):
        return frame
    return pl.DataFrame(schema=schema)


@dataclass(frozen=True)
class PriceCoverageAuditRequest:
    """
    审计请求：窗口 + 资产类 + 数据集档位.

    start_date/end_date 为 YYYY-MM-DD；窗口按交易日历裁剪。
    dataset 须与 asset_class 组合合法（见 _DATASET_ASSET_CLASSES）。
    """

    start_date: str
    end_date: str
    asset_class: str = "stock"
    dataset: str = "daily"
    detail_limit: int = 20


@dataclass(frozen=True)
class PriceCoverageAuditReport:
    """审计报告（JSON 可序列化形状由 to_dict 提供）."""

    asset_class: str
    window: tuple[str, str]
    calendar: CalendarAudit
    session: SessionCoverageAudit
    top_gap_securities: list[dict[str, Any]]
    gap_samples: list[dict[str, Any]]
    dataset: str = "daily"

    @property
    def passed(self) -> bool:
        """日历与会话审计同时通过."""
        return self.calendar.passed and self.session.passed

    def to_dict(self) -> dict[str, Any]:
        """CLI/JSON 可序列化形状."""
        return {
            "dataset": self.dataset,
            "asset_class": self.asset_class,
            "window": list(self.window),
            "passed": self.passed,
            "calendar": {
                "trading_days": self.calendar.trading_days,
                "duplicate_days": self.calendar.duplicate_days,
                "weekend_days": self.calendar.weekend_days,
                "missing_years": list(self.calendar.missing_years),
                "years_out_of_bounds": list(self.calendar.years_out_of_bounds),
                "yearly_counts": [
                    [year, count] for year, count in self.calendar.yearly_counts
                ],
                "passed": self.calendar.passed,
            },
            "session": self.session.summary(),
            "gap_counts": dict(sorted(self.session.gap_counts.items())),
            "anomaly_counts": dict(sorted(self.session.anomaly_counts.items())),
            "top_gap_securities": self.top_gap_securities,
            "gap_samples": self.gap_samples,
        }


class PriceCoverageAuditService:
    """编排物理帧并调用纯审计函数."""

    def __init__(
        self,
        *,
        market: MarketService,
        metadata: MetadataService,
        capital: CapitalStore | None = None,
    ) -> None:
        self._market = market
        self._metadata = metadata
        self._capital = capital

    def run(self, request: PriceCoverageAuditRequest) -> PriceCoverageAuditReport:
        """执行审计：读物理帧 → 纯函数归因 → 报告."""
        self._validate_request(request)
        window_start = date.fromisoformat(request.start_date)
        window_end = date.fromisoformat(request.end_date)

        trading_days = [
            date.fromisoformat(day)
            for day in self._metadata.calendar.list_trading_days(
                request.start_date, request.end_date
            )
        ]
        calendar_audit = audit_trading_calendar(
            trading_days, window_start=window_start, window_end=window_end
        )

        # kwargs 重载走 MetadataService（其职责即隐藏 SecurityQuery 等
        # storage 层内部类型；application 不得直 import ditto_data.storage）。
        roster = self._metadata.find_securities(
            asset_class=request.asset_class, is_active=None
        )
        bars, status_frame, status_available_from, adj_factors = (
            self._load_audit_frames(request)
        )

        session_audit = audit_session_coverage(
            trading_days=trading_days,
            master=roster,
            bars=bars,
            status=status_frame,
            status_available_from=status_available_from,
            adj_factors=adj_factors,
        )

        tickers = _roster_tickers(roster)
        limit = max(request.detail_limit, 0)
        return PriceCoverageAuditReport(
            asset_class=request.asset_class,
            window=(request.start_date, request.end_date),
            calendar=calendar_audit,
            session=session_audit,
            top_gap_securities=_top_gap_securities(session_audit, tickers, limit),
            gap_samples=_gap_samples(session_audit, tickers, limit),
            dataset=request.dataset,
        )

    @staticmethod
    def _validate_request(request: PriceCoverageAuditRequest) -> None:
        """资产类 × 数据集档位组合校验（fail-closed）."""
        if request.asset_class not in _ASSET_CLASSES:
            raise AppQueryError(
                f"未知资产类 {request.asset_class!r}: 允许 {sorted(_ASSET_CLASSES)}"
            )
        allowed = _DATASET_ASSET_CLASSES.get(request.dataset)
        if allowed is None:
            known = sorted(_DATASET_ASSET_CLASSES)
            raise AppQueryError(f"未知数据集档位 {request.dataset!r}: 允许 {known}")
        if request.asset_class not in allowed:
            names = sorted(allowed)
            message = (
                f"数据集 {request.dataset!r} 不支持资产类 "
                f"{request.asset_class!r}: 允许 {names}"
            )
            raise AppQueryError(message)
        if date.fromisoformat(request.end_date) < date.fromisoformat(
            request.start_date
        ):
            raise AppQueryError("end_date 不得早于 start_date")

    def _load_audit_frames(
        self, request: PriceCoverageAuditRequest
    ) -> tuple[pl.DataFrame, pl.DataFrame | None, date | None, pl.DataFrame | None]:
        """按数据集档位装配审计帧: bars/status/status 期起点/复权因子."""
        if request.dataset == "moneyflow":
            # 资金流会话网格复用价格审计口径：bars 换成 moneyflow 业务键，
            # 停牌归因沿用 stock_status（停牌日无资金流行是正常缺席）。
            if self._capital is None:
                raise AppQueryError("moneyflow 审计需要 capital 存储服务")
            bars = _ensure_schema(
                self._capital.get_moneyflows(request.start_date, request.end_date),
                _BAR_KEYS_SCHEMA,
            )
            status = _ensure_schema(
                self._market.get_stock_status(request.start_date, request.end_date),
                _STATUS_KEYS_SCHEMA,
            )
            status_range = self._market.get_stock_status_date_range()
            status_frame = status if status_range is not None else None
            return bars, status_frame, (status_range[0] if status_range else None), None

        if request.dataset == "fund_share":
            fund_share = self._market.get_fund_share(
                request.start_date, request.end_date
            )
            if fund_share is None:
                raise AppQueryError(
                    "fund_share 读取端口未装配: 无法执行场内份额覆盖审计"
                )
            # ETF 无状态数据集：缺口归因诚实落在 no_status_dataset 证据边界。
            return _ensure_schema(fund_share, _BAR_KEYS_SCHEMA), None, None, None

        if request.asset_class == "stock":
            bars = _ensure_schema(
                self._market.get_stock_bars(request.start_date, request.end_date),
                _BAR_KEYS_SCHEMA,
            )
            status = _ensure_schema(
                self._market.get_stock_status(request.start_date, request.end_date),
                _STATUS_KEYS_SCHEMA,
            )
            adj_factors = _ensure_schema(
                self._market.get_adj_factors(request.start_date, request.end_date),
                _BAR_KEYS_SCHEMA,
            )
            # 状态期起点 = 数据集物理覆盖起点（不受请求窗口约束）。窗口内
            # 状态帧最早行无法区分「数据集尚未开始」与「窗口内前导摄取
            # 空洞」——后者按状态缺失失败处理，不得借 pre_status_era 豁免。
            status_range = self._market.get_stock_status_date_range()
            status_frame = status if status_range is not None else None
            return (
                bars,
                status_frame,
                status_range[0] if status_range else None,
                adj_factors,
            )

        bars = _ensure_schema(
            self._market.get_etf_bars(request.start_date, request.end_date),
            _BAR_KEYS_SCHEMA,
        )
        # ETF 无状态数据集（market/etf/status 未注册摄取）：缺口归因
        # 诚实落在 no_status_dataset 证据边界，不冒充停牌可判。
        fund_adj = self._market.get_fund_adj(request.start_date, request.end_date)
        adj_factors = (
            _ensure_schema(fund_adj, _BAR_KEYS_SCHEMA) if fund_adj is not None else None
        )
        return bars, None, None, adj_factors


def _roster_tickers(roster: pl.DataFrame) -> dict[int, str]:
    """instrument_id → 主映射 ticker（缺失时退化为 id 字符串）."""
    if roster.is_empty() or "source_ticker" not in roster.columns:
        return {}
    pairs = roster.select("instrument_id", "source_ticker").drop_nulls()
    return {int(row[0]): str(row[1]) for row in pairs.iter_rows()}


def _top_gap_securities(
    audit: SessionCoverageAudit, tickers: dict[int, str], limit: int
) -> list[dict[str, Any]]:
    if audit.gap_detail.is_empty() or limit == 0:
        return []
    counted = (
        audit.gap_detail.group_by("instrument_id")
        .len()
        .sort(["len", "instrument_id"], descending=[True, False])
        .head(limit)
    )
    return [
        {
            "instrument_id": int(instrument_id),
            "ticker": tickers.get(int(instrument_id), str(instrument_id)),
            "gaps": int(count),
        }
        for instrument_id, count in counted.iter_rows()
    ]


def _gap_samples(
    audit: SessionCoverageAudit, tickers: dict[int, str], limit: int
) -> list[dict[str, Any]]:
    if audit.gap_detail.is_empty() or limit == 0:
        return []
    samples = audit.gap_detail.sort(["kind", "instrument_id", "trade_date"]).head(limit)
    return [
        {
            "instrument_id": int(instrument_id),
            "ticker": tickers.get(int(instrument_id), str(instrument_id)),
            "trade_date": trade_date.isoformat(),
            "kind": kind,
        }
        for instrument_id, trade_date, kind in samples.iter_rows()
    ]
