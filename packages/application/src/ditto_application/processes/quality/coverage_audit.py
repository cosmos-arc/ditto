"""
价格与身份覆盖审计服务（#624 / 父规格 #621 P2）.

编排 data 层纯审计函数（``ditto_data.quality.coverage_audit``）：从
MarketService/MetadataService 取物理帧（日线/状态/复权因子/名册/日历），
对给定窗口产出逐证券交易日缺口归因报告。物理覆盖核验语义与 PIT 消费
查询的边界见纯函数模块 docstring。

入口：``ops audit-price-coverage``（CLI）；无例行调度，按需复跑刷新证据。
"""

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import polars as pl
from ditto_data.quality.coverage_audit import (
    CalendarAudit,
    SessionCoverageAudit,
    audit_session_coverage,
    audit_trading_calendar,
)
from ditto_data.services.market_service import MarketService
from ditto_data.services.metadata_service import MetadataService
from ditto_data.storage.metadata.instrument import SecurityQuery

__all__ = [
    "PriceCoverageAuditReport",
    "PriceCoverageAuditRequest",
    "PriceCoverageAuditService",
]

_ASSET_CLASSES = frozenset({"stock", "etf"})
_ONE_DAY = timedelta(days=1)

# 空窗读取可能返回无列空帧；带 schema 空帧让纯函数走「状态集存在但窗口内无行」路径。
_STATUS_KEYS_SCHEMA = {
    "instrument_id": pl.Int64,
    "trade_date": pl.Date,
    "is_suspended": pl.Boolean,
}


@dataclass(frozen=True)
class PriceCoverageAuditRequest:
    """
    审计请求：窗口 + 资产类.

    start_date/end_date 为 YYYY-MM-DD；窗口按交易日历裁剪。
    """

    start_date: str
    end_date: str
    asset_class: str = "stock"
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

    @property
    def passed(self) -> bool:
        """日历与会话审计同时通过."""
        return self.calendar.passed and self.session.passed

    def to_dict(self) -> dict[str, Any]:
        """CLI/JSON 可序列化形状."""
        return {
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

    def __init__(self, *, market: MarketService, metadata: MetadataService) -> None:
        self._market = market
        self._metadata = metadata

    def run(self, request: PriceCoverageAuditRequest) -> PriceCoverageAuditReport:
        """执行审计：读物理帧 → 纯函数归因 → 报告."""
        if request.asset_class not in _ASSET_CLASSES:
            raise ValueError(
                f"未知资产类 {request.asset_class!r}: 允许 {sorted(_ASSET_CLASSES)}"
            )
        window_start = date.fromisoformat(request.start_date)
        window_end = date.fromisoformat(request.end_date)
        if window_end < window_start:
            raise ValueError("end_date 不得早于 start_date")

        trading_days = [
            date.fromisoformat(day)
            for day in self._metadata.calendar.list_trading_days(
                request.start_date, request.end_date
            )
        ]
        calendar_audit = audit_trading_calendar(
            trading_days, window_start=window_start, window_end=window_end
        )

        roster = self._metadata.instrument.find_securities(
            SecurityQuery(asset_class=request.asset_class, is_active=None)
        )
        if request.asset_class == "stock":
            bars = self._market.get_stock_bars(request.start_date, request.end_date)
            status = self._market.get_stock_status(request.start_date, request.end_date)
            adj_factors: pl.DataFrame | None = self._market.get_adj_factors(
                request.start_date, request.end_date
            )
            # 状态期起点 = 窗口内状态数据最早会话；窗口完全早于状态期
            # （如仅审计 2014~2015）时，era 取窗口外首日，让全部缺失落到
            # pre_status_era 证据边界——股票状态数据集存在，不得误标
            # no_status_dataset（那是 ETF 无数据集的语义）。
            status_frame: pl.DataFrame | None = (
                status if status.height else pl.DataFrame(schema=_STATUS_KEYS_SCHEMA)
            )
            era_value = status["trade_date"].min() if status.height else None
            status_available_from = (
                era_value if isinstance(era_value, date) else window_end + _ONE_DAY
            )
        else:
            bars = self._market.get_etf_bars(request.start_date, request.end_date)
            # ETF 无状态数据集（market/etf/status 未注册摄取）：缺口归因
            # 诚实落在 no_status_dataset 证据边界，不冒充停牌可判。
            status_frame = None
            status_available_from = None
            adj_factors = self._market.get_fund_adj(
                request.start_date, request.end_date
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
        )


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
