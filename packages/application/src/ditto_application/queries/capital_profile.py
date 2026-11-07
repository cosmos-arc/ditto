"""
个股资金画像查询（#658 批次3 首个真实流程）.

四数据集同标的同窗口联看：moneyflow／top_list／top_inst（必需，
latest_available＝库内有效版本）＋margin_trading（可选，最新观察）。
两融迟发按「窗口尾部最近 N 个交易日内缺失」表达为待补列表
（N 与 02:00 夜修滑窗 #625 语义对齐＝5）；席位与榜单事件按 reason
独立成行，席位≠机构总仓位、榜单退出≠清仓（#658 主旅程契约）。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol

import polars as pl

__all__ = [
    "MARGIN_PENDING_WINDOW_DAYS",
    "CapitalProfileDataPort",
    "CapitalProfileQueryFacade",
    "CapitalProfileRequest",
    "CapitalProfileResult",
    "ProfileBlock",
]

# 与 repair.py LATE_PUBLISHING_REFRESH_WINDOW_DAYS（#625）对齐的迟发观察窗。
MARGIN_PENDING_WINDOW_DAYS = 5


class CapitalProfileDataPort(Protocol):
    """画像所需的逐标的窗口读取能力（CapitalQueryFacade 结构满足）."""

    def get_moneyflow(
        self,
        instrument_id: int,
        start: str,
        end: str,
        *,
        allow_experimental_data: bool = ...,
    ) -> pl.DataFrame:
        """逐标的资金流窗口读."""
        ...

    def get_top_list(
        self,
        instrument_id: int,
        start: str,
        end: str,
        *,
        allow_experimental_data: bool = ...,
    ) -> pl.DataFrame:
        """逐标的龙虎榜窗口读."""
        ...

    def get_top_inst(
        self,
        instrument_id: int,
        start: str,
        end: str,
        *,
        allow_experimental_data: bool = ...,
    ) -> pl.DataFrame:
        """逐标的席位窗口读."""
        ...

    def get_margin_trading_range(
        self,
        instrument_id: int,
        start: str,
        end: str,
        as_of_date: date | None = None,
        *,
        allow_experimental_data: bool = ...,
    ) -> pl.DataFrame:
        """逐标的两融窗口读(PIT 可选)."""
        ...


class TradingDaysPort(Protocol):
    """画像所需的交易日历读取能力（MetadataService.calendar 结构满足）."""

    def list_trading_days(self, start: str, end: str) -> list[str]:
        """升序 ISO 交易日列表."""
        ...


@dataclass(frozen=True)
class CapitalProfileRequest:
    """画像请求：标的＋窗口＋experimental 通道＋当前日."""

    instrument_id: int
    start: date
    end: date
    allow_experimental_data: bool = False
    today: date | None = None  # 待补窗上界；None=不设上界(测试用)


@dataclass(frozen=True)
class ProfileBlock:
    """单数据集画像块（coverage 由 API 层并置）."""

    rows: pl.DataFrame
    latest_trade_date: str | None = None
    pending_trade_dates: tuple[str, ...] = ()
    read_error: str | None = None


@dataclass(frozen=True)
class CapitalProfileResult:
    """画像结果（四块）."""

    instrument_id: int
    start: date
    end: date
    moneyflow: ProfileBlock
    top_list: ProfileBlock
    top_inst: ProfileBlock
    margin_trading: ProfileBlock


def _latest_trade_date(rows: pl.DataFrame) -> str | None:
    if rows.is_empty() or "trade_date" not in rows.columns:
        return None
    return str(rows["trade_date"].max())


class CapitalProfileQueryFacade:
    """编排四数据集窗口读并推导末端/待补语义."""

    def __init__(
        self,
        capital: CapitalProfileDataPort,
        calendar: TradingDaysPort,
    ) -> None:
        self._capital = capital
        self._calendar = calendar

    def get_profile(self, request: CapitalProfileRequest) -> CapitalProfileResult:
        """执行画像：窗口读四数据集＋margin 待补推导."""
        start = request.start.isoformat()
        end = request.end.isoformat()
        flag = request.allow_experimental_data
        moneyflow = self._capital.get_moneyflow(
            request.instrument_id, start, end, allow_experimental_data=flag
        )
        top_list = self._capital.get_top_list(
            request.instrument_id, start, end, allow_experimental_data=flag
        )
        top_inst = self._capital.get_top_inst(
            request.instrument_id, start, end, allow_experimental_data=flag
        )
        # margin 是可选块(story 11):读取失败时受限展示,其余三块不受影响。
        try:
            margin = self._capital.get_margin_trading_range(
                request.instrument_id,
                start,
                end,
                as_of_date=None,
                allow_experimental_data=flag,
            )
            margin_error: str | None = None
        except Exception as error:
            margin = pl.DataFrame()
            margin_error = f"{type(error).__name__}: {error}"
        return CapitalProfileResult(
            instrument_id=request.instrument_id,
            start=request.start,
            end=request.end,
            moneyflow=ProfileBlock(
                rows=moneyflow, latest_trade_date=_latest_trade_date(moneyflow)
            ),
            top_list=ProfileBlock(
                rows=top_list, latest_trade_date=_latest_trade_date(top_list)
            ),
            top_inst=ProfileBlock(
                rows=top_inst, latest_trade_date=_latest_trade_date(top_inst)
            ),
            margin_trading=ProfileBlock(
                rows=margin,
                latest_trade_date=_latest_trade_date(margin),
                pending_trade_dates=self._margin_pending_dates(
                    margin, start, end, today=request.today
                ),
                read_error=margin_error,
            ),
        )

    def _margin_pending_dates(
        self,
        rows: pl.DataFrame,
        start: str,
        end: str,
        *,
        today: date | None = None,
    ) -> tuple[str, ...]:
        """
        两融待补日＝观察窗内、晚于实际末端且不超过当前日的交易日.

        仅当窗口内有两融行才推导（无行＝非两融标的或窗口外历史，
        待补语义不适用）；观察窗＝窗口尾部 MARGIN_PENDING_WINDOW_DAYS
        个交易日（与 02:00 夜修滑窗对齐，出窗归源端补发/运维复查）。
        today 上界把未发生的会话排除在「迟发」之外（correctness F3）。
        """
        latest = _latest_trade_date(rows)
        if latest is None:
            return ()
        trading_days = self._calendar.list_trading_days(start, end)
        watch = trading_days[-MARGIN_PENDING_WINDOW_DAYS:]
        ceiling = today.isoformat() if today is not None else None
        return tuple(
            day for day in watch if day > latest and (ceiling is None or day <= ceiling)
        )
