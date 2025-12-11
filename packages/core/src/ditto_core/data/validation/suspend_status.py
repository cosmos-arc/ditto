"""停牌状态处理模块."""

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any


@dataclass
class SuspendInfo:
    """停牌信息."""

    symbol: str
    is_suspended: bool
    suspend_start_date: date | None = None
    suspend_days: int = 0
    reason: str = "normal"
    is_abnormal_price: bool = False
    last_trading_date: date | None = None
    expected_resume_date: date | None = None
    total_suspend_days: int = 0  # 总停牌天数


class SuspendStatusDetector:
    """停牌状态检测器."""

    def __init__(self) -> None:
        """初始化检测器."""
        # 存储停牌历史记录
        self._suspend_history: dict[str, list[dict[str, Any]]] = {}

    def detect_suspend_status(
        self,
        symbol: str,
        trading_dates: list[date],
        price_data: list[dict[str, Any]],
        detection_date: date,
        consecutive_days: int = 3,
    ) -> SuspendInfo:
        """
        检测停牌状态.

        Args:
            symbol: 股票代码
            trading_dates: 交易日期列表(已过滤交易日)
            price_data: 价格数据
            detection_date: 检测日期
            consecutive_days: 连续停牌天数阈值

        """
        if not trading_dates or not price_data:
            return SuspendInfo(symbol=symbol, is_suspended=False, reason="no_data")

        # 创建价格数据字典
        price_dict = {item["date"]: item for item in price_data}

        # 查找最后有交易的日期
        last_trading_date = None
        suspend_days = 0
        is_suspended = False
        reason = "normal"
        suspend_start_date = None

        # 从前往后遍历, 记录最后交易日期和连续无数据段
        last_trading_date = None
        max_suspend_days = 0
        max_suspend_start = None
        current_suspend_days = 0
        current_suspend_start = None

        for date in trading_dates:
            if date > detection_date:
                continue

            price_info = price_dict.get(date)
            if price_info:
                # 检查是否有异常价格(跌停超过20%)
                if "close" in price_info:
                    # 找前一个有价格的日期
                    prev_date = None
                    for d in trading_dates[: trading_dates.index(date)]:
                        if price_dict.get(d) and "close" in price_dict.get(d):
                            prev_date = d
                            break

                    if prev_date:
                        prev_info = price_dict.get(prev_date)
                        if prev_info and prev_info["close"] > 0:
                            price_change = (
                                price_info["close"] - prev_info["close"]
                            ) / prev_info["close"]
                            if price_change <= -0.20:  # 跌停超过20%
                                return SuspendInfo(
                                    symbol=symbol,
                                    is_suspended=False,
                                    reason="abnormal_price_change",
                                    is_abnormal_price=True,
                                    last_trading_date=date,
                                )

                # 检查成交量为0
                if price_info.get("volume", 0) == 0:
                    # 成交量为0也算停牌
                    if current_suspend_days == 0:
                        current_suspend_start = date
                    current_suspend_days += 1
                else:
                    # 有交易数据, 记录最后交易日期
                    last_trading_date = date
                    # 结束当前停牌段
                    if current_suspend_days > max_suspend_days:
                        max_suspend_days = current_suspend_days
                        max_suspend_start = current_suspend_start
                    current_suspend_days = 0
                    current_suspend_start = None
            else:
                # 无交易数据
                if current_suspend_days == 0:
                    current_suspend_start = date
                current_suspend_days += 1

        # 检查最后一段停牌
        if current_suspend_days > max_suspend_days:
            max_suspend_days = current_suspend_days
            max_suspend_start = current_suspend_start

        # 判断是否达到连续停牌阈值
        if max_suspend_days >= consecutive_days:
            is_suspended = True
            reason = (
                "zero_volume"
                if any(
                    d.get("volume", 0) == 0
                    for d in price_data
                    if max_suspend_start and d["date"] >= max_suspend_start
                )
                else "no_trading_data"
            )
            suspend_days = max_suspend_days
            suspend_start_date = max_suspend_start
        # 检查是否有交易恢复的情况(曾经停牌但最后恢复了)
        elif (
            max_suspend_days > 0
            and max_suspend_days < consecutive_days
            and last_trading_date
        ):
            # 有部分停牌但未达到阈值, 且最后有交易
            is_suspended = False
            suspend_start_date = None
            suspend_days = 0
            reason = "trading_resumed"
        else:
            is_suspended = False
            suspend_start_date = None
            suspend_days = 0
            reason = "normal"

        # 如果最后一天仍在停牌
        if is_suspended and suspend_start_date:
            expected_resume = detection_date + timedelta(days=1)
        else:
            expected_resume = None

        # 计算总停牌天数
        total_suspend_days = self._calculate_total_suspend_days(symbol, suspend_days)

        return SuspendInfo(
            symbol=symbol,
            is_suspended=is_suspended,
            suspend_start_date=suspend_start_date,
            suspend_days=suspend_days,
            reason=reason,
            is_abnormal_price=False,
            last_trading_date=last_trading_date,
            expected_resume_date=expected_resume,
            total_suspend_days=total_suspend_days,
        )

    def batch_detect(
        self,
        symbols_data: dict[str, list[dict[str, Any]]],
        trading_dates: list[date],
        detection_date: date,
    ) -> dict[str, SuspendInfo]:
        """批量检测停牌状态."""
        results = {}

        for symbol, price_data in symbols_data.items():
            suspend_info = self.detect_suspend_status(
                symbol=symbol,
                trading_dates=trading_dates,
                price_data=price_data,
                detection_date=detection_date,
            )
            results[symbol] = suspend_info

            # 更新停牌历史
            self._update_suspend_history(symbol, suspend_info)

        return results

    def get_suspend_history(self, symbol: str) -> list[dict[str, Any]]:
        """获取停牌历史."""
        return self._suspend_history.get(symbol, [])

    def _is_abnormal_price(self, price_info: dict[str, Any]) -> bool:
        """判断是否为异常价格."""
        # 这里可以实现更复杂的异常价格检测逻辑
        # 例如: 涨跌幅超过20%、价格突变等
        return False  # 暂时简单实现

    def _calculate_total_suspend_days(self, symbol: str, current_days: int) -> int:
        """计算总停牌天数."""
        history = self.get_suspend_history(symbol)
        total = current_days

        for record in history:
            if record.get("end_date") is None:  # 仍在停牌
                total += record.get("suspend_days", 0)
            else:
                start = record.get("start_date")
                end = record.get("end_date")
                if start and end:
                    total += (end - start).days + 1

        return total

    def _update_suspend_history(self, symbol: str, suspend_info: SuspendInfo) -> None:
        """更新停牌历史记录."""
        if symbol not in self._suspend_history:
            self._suspend_history[symbol] = []

        # 检查是否需要更新现有记录
        if suspend_info.is_suspended:
            # 检查是否有正在进行的停牌
            ongoing = None
            for i, record in enumerate(self._suspend_history[symbol]):
                if record.get("end_date") is None:
                    ongoing = i
                    break

            if ongoing is not None:
                # 更新现有记录
                self._suspend_history[symbol][ongoing].update(
                    {
                        "suspend_days": suspend_info.suspend_days,
                    }
                )
            else:
                # 新增停牌记录
                self._suspend_history[symbol].append(
                    {
                        "start_date": suspend_info.suspend_start_date,
                        "end_date": None,
                        "suspend_days": suspend_info.suspend_days,
                        "reason": suspend_info.reason,
                    }
                )
        else:
            # 检查是否需要结束停牌
            for record in self._suspend_history[symbol]:
                if record.get("end_date") is None:
                    record["end_date"] = suspend_info.last_trading_date
                    break
