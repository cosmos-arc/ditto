"""
CalendarService - 交易日历子服务.

交易日历数据的查询、写入与丰富（enrichment）逻辑。
"""

from __future__ import annotations

from datetime import date
from typing import Any

import polars as pl
from ditto_infra.foundation import traced

from ditto_data.storage.metadata.calendar import CalendarReader, CalendarWriter


def compute_calendar_enrichment(days: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    计算日历丰富字段（纯函数）.

    从仅有 trade_date/is_open 的基本日历数据，
    计算 prev_trade_date, next_trade_date, week_of_year,
    month, quarter, year, is_week_end, is_month_end, is_quarter_end.

    Args:
        days: 输入格式 [{"trade_date": "2024-01-02", "is_open": True}, ...]

    Returns:
        丰富后的完整 records 列表（仅包含 is_open=True 的交易日）.

    """
    if not days:
        return []

    # 筛选交易日并按 trade_date 排序
    trading_days = sorted(
        [d for d in days if d.get("is_open", False)],
        key=lambda d: d["trade_date"],
    )

    if not trading_days:
        return []

    results: list[dict[str, Any]] = []

    for i, day in enumerate(trading_days):
        d = date.fromisoformat(day["trade_date"])
        iso = d.isocalendar()
        month = d.month
        quarter = (month - 1) // 3 + 1

        prev_td: str | None = None
        next_td: str | None = None

        if i > 0:
            prev_td = trading_days[i - 1]["trade_date"]
        if i < len(trading_days) - 1:
            next_td = trading_days[i + 1]["trade_date"]

        # 周末/月末/季末: 比较当前和下一个交易日的对应周期
        is_week_end = False
        is_month_end = False
        is_quarter_end = False

        if next_td is not None:
            next_d = date.fromisoformat(next_td)
            next_iso = next_d.isocalendar()
            next_month = next_d.month
            next_quarter = (next_month - 1) // 3 + 1

            is_week_end = (iso[0], iso[1]) != (next_iso[0], next_iso[1])
            is_month_end = month != next_month
            is_quarter_end = quarter != next_quarter

        results.append(
            {
                "trade_date": day["trade_date"],
                "is_open": True,
                "exchange": day.get("exchange", "SSE"),
                "prev_trade_date": prev_td,
                "next_trade_date": next_td,
                "week_of_year": iso[1],
                "month": month,
                "quarter": quarter,
                "year": d.year,
                "is_week_end": is_week_end,
                "is_month_end": is_month_end,
                "is_quarter_end": is_quarter_end,
                "is_half_day": False,
                "is_special": bool(day.get("is_special", False)),
            }
        )

    return results


class CalendarService:
    """交易日历子服务."""

    def __init__(
        self,
        calendar_reader: CalendarReader,
        calendar_writer: CalendarWriter,
    ) -> None:
        """
        初始化 CalendarService.

        Args:
            calendar_reader: 交易日历读取器.
            calendar_writer: 交易日历写入器.

        """
        self._calendar_reader = calendar_reader
        self._calendar_writer = calendar_writer

    @traced("metadata.calendar.list_trading_days")
    def list_trading_days(
        self,
        start: str,
        end: str,
        only_open: bool = True,
    ) -> list[str]:
        """
        查询交易日列表.

        Args:
            start: 开始日期.
            end: 结束日期.
            only_open: 是否只返回交易日.

        Returns:
            交易日列表.

        """
        return self._calendar_reader.get_range(start, end)

    @traced("metadata.calendar.list_calendar_range")
    def list_calendar_range(
        self,
        start: str,
        end: str,
        only_open: bool = True,
    ) -> pl.DataFrame:
        """
        查询日历数据（DataFrame 格式）.

        Args:
            start: 开始日期.
            end: 结束日期.
            only_open: 是否只返回交易日.

        Returns:
            日历数据 DataFrame，包含 trade_date, is_open, prev_trade_date 等列.

        """
        return self._calendar_reader.get_range_df(start, end, only_open)

    @traced("metadata.calendar.save_calendar")
    def save_calendar(self, records: list[dict[str, Any]]) -> int:
        """
        插入或更新日历记录.

        Args:
            records: 日历记录列表.

        Returns:
            插入的记录数.

        """
        self._calendar_writer.upsert(records)
        return len(records)

    @traced("metadata.calendar.is_trading_day")
    def is_trading_day(self, date: str) -> bool:
        """
        判断是否为交易日.

        Args:
            date: 日期字符串.

        Returns:
            是否为交易日.

        """
        return self._calendar_reader.is_trading_day(date)

    @traced("metadata.calendar.get_last_trading_day")
    def get_last_trading_day(self) -> str | None:
        """
        获取最后一个交易日.

        Returns:
            最后一个交易日日期字符串，如果没有数据则返回 None.

        """
        return self._calendar_reader.get_last_trading_day()

    @traced("metadata.calendar.get_first_trading_day")
    def get_first_trading_day(self) -> str | None:
        """
        获取第一个交易日.

        Returns:
            第一个交易日日期字符串，如果没有数据则返回 None.

        """
        return self._calendar_reader.get_first_trading_day()

    @traced("metadata.calendar.update_half_days")
    def update_half_days(self, half_days: list[str]) -> int:
        """
        批量更新半日交易标记.

        Args:
            half_days: 半日交易日期列表 (YYYY-MM-DD 格式).

        Returns:
            更新的记录数.

        """
        if not half_days:
            return 0
        records = [{"trade_date": d, "is_half_day": True} for d in half_days]
        return self._calendar_writer.upsert(records)

    @traced("metadata.calendar.enrich_calendar")
    def enrich_calendar(self, start: str, end: str) -> int:
        """
        丰富日历数据：计算 prev/next、周/月/季末标记.

        仅处理 prev_trade_date 为 NULL 的未丰富行。
        增量模式下额外包含 1 个已丰富边界行，确保 prev/next 计算正确。

        Args:
            start: 开始日期.
            end: 结束日期.

        Returns:
            更新的记录数.

        """
        df = self._calendar_reader.get_range_df(start, end, only_open=False)

        if df.is_empty():
            return 0

        # 筛选未丰富的行（prev_trade_date 为 null）
        unenriched = df.filter(pl.col("prev_trade_date").is_null())
        if unenriched.is_empty():
            return 0

        unenriched_dates = set(unenriched["trade_date"].to_list())

        # 增量模式：补充边界行，确保首尾 unenriched 行的 prev/next 正确
        min_unenriched = min(unenriched_dates)
        max_unenriched = max(unenriched_dates)
        boundary_rows: list[dict[str, Any]] = []
        prev_day = self._calendar_reader.offset(min_unenriched, -1)
        if prev_day is not None and prev_day not in unenriched_dates:
            boundary_rows.append({"trade_date": prev_day, "is_open": True})
        next_day = self._calendar_reader.offset(max_unenriched, 1)
        if next_day is not None and next_day not in unenriched_dates:
            boundary_rows.append({"trade_date": next_day, "is_open": True})

        # 合并边界行 + 未丰富行传入纯函数
        days = boundary_rows + unenriched.to_dicts()
        enriched = compute_calendar_enrichment(days)

        # 只保留原本未丰富的行（不覆盖已丰富的边界行）
        result = [r for r in enriched if r["trade_date"] in unenriched_dates]

        if not result:
            return 0

        self._calendar_writer.upsert(result)
        return len(result)

    @traced("metadata.calendar.auto_enrich_calendar")
    def auto_enrich_calendar(self) -> int:
        """
        自动丰富所有未处理的日历数据。

        自动确定日期范围（从第一个交易日到最后一个交易日），
        然后调用 enrich_calendar。

        Returns:
            更新的记录数。

        """
        first = self._calendar_reader.get_first_trading_day()
        last = self._calendar_reader.get_last_trading_day()
        if first is None or last is None:
            return 0
        return self.enrich_calendar(first, last)
