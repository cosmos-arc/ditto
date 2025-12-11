"""涨跌停识别模块."""

from dataclasses import dataclass
from datetime import date
from typing import Any


@dataclass
class LimitStatus:
    """涨跌停状态结果."""

    symbol: str
    date: date
    is_limit_up: bool
    is_limit_down: bool
    limit_type: str  # normal, limit_up, limit_down, st_limit_up, st_limit_down, etc.
    limit_ratio: float | None = None  # 涨跌幅比例
    is_suspended: bool = False
    is_st: bool = False
    is_ipo_first_day: bool = False
    board_type: str | None = None  # main, star, gem
    close_price: float | None = None
    prev_close: float | None = None


class TradingLimitsChecker:
    """涨跌停识别器."""

    def check_limit_status(
        self,
        symbol: str,
        close: float | None,
        prev_close: float | None,
        date: date,
        is_st: bool = False,
        is_suspended: bool = False,
        is_ipo_first_day: bool = False,
        board_type: str | None = None,
    ) -> LimitStatus:
        """检查单只股票的涨跌停状态."""
        # 处理停牌
        if is_suspended or close is None:
            return LimitStatus(
                symbol=symbol,
                date=date,
                is_limit_up=False,
                is_limit_down=False,
                limit_type="suspended",
                is_suspended=True,
                is_st=is_st,
                is_ipo_first_day=is_ipo_first_day,
                board_type=board_type,
                close_price=close,
                prev_close=prev_close,
            )

        # 处理无前收盘价
        if prev_close is None:
            return LimitStatus(
                symbol=symbol,
                date=date,
                is_limit_up=False,
                is_limit_down=False,
                limit_type="no_previous_close",
                is_st=is_st,
                is_ipo_first_day=is_ipo_first_day,
                board_type=board_type,
                close_price=close,
                prev_close=prev_close,
            )

        # 计算涨跌幅
        change_ratio = (close - prev_close) / prev_close

        # 确定涨跌停阈值
        if is_st:
            limit_up_threshold = 0.05  # ST股票5%
            limit_down_threshold = -0.05
        elif board_type in ("star", "gem") or is_ipo_first_day:
            limit_up_threshold = 0.20  # 科创板、创业板、新股首日20%
            limit_down_threshold = -0.20
        else:
            limit_up_threshold = 0.10  # 普通股票10%
            limit_down_threshold = -0.10

        # 考虑价格精度(2位小数)
        precision = 0.005  # 0.5%的容差

        # 判断涨跌停
        is_limit_up = change_ratio >= (limit_up_threshold - precision)
        is_limit_down = change_ratio <= (limit_down_threshold + precision)

        # 确定涨跌停类型
        if is_limit_up and is_limit_down:
            # 特殊情况, 可能是价格异常
            limit_type = "abnormal"
        elif is_limit_up:
            if is_st:
                limit_type = "st_limit_up"
            elif board_type in ("star", "gem"):
                limit_type = "sci_tech_limit_up"
            elif is_ipo_first_day:
                limit_type = "ipo_limit_up"
            else:
                limit_type = "limit_up"
        elif is_limit_down:
            if is_st:
                limit_type = "st_limit_down"
            elif board_type in ("star", "gem"):
                limit_type = "sci_tech_limit_down"
            else:
                limit_type = "limit_down"
        else:
            limit_type = "normal"

        return LimitStatus(
            symbol=symbol,
            date=date,
            is_limit_up=is_limit_up,
            is_limit_down=is_limit_down,
            limit_type=limit_type,
            limit_ratio=change_ratio,
            is_st=is_st,
            is_ipo_first_day=is_ipo_first_day,
            board_type=board_type,
            close_price=close,
            prev_close=prev_close,
        )

    def batch_check(self, data: list[dict[str, Any]], date: date) -> list[LimitStatus]:
        """批量检查涨跌停状态."""
        results = []

        for item in data:
            result = self.check_limit_status(
                symbol=item["symbol"],
                close=item.get("close"),
                prev_close=item.get("prev_close"),
                date=date,
                is_st=item.get("is_st", False),
                is_suspended=item.get("is_suspended", False),
                is_ipo_first_day=item.get("is_ipo_first_day", False),
                board_type=item.get("board_type"),
            )
            results.append(result)

        return results
