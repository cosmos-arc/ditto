"""
ComparisonQueryFacade — 回测 vs 实际对比查询门面.

提供 ComparisonQueryFacade 门面，从回测报告和实际交易数据编排对比指标计算。
ComparisonMetrics DTO 和纯计算函数已抽取到 comparison_math.py。
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from loguru import logger

from ditto_app.config import DEFAULT_INITIAL_CASH
from ditto_app.execution_dto import ManualExecutionFill
from ditto_app.query.backtest import BacktestQueryFacade
from ditto_app.query.comparison_math import (
    ComparisonMetrics,
    compute_comparison_from_raw,
)
from ditto_app.query.market import MarketQueryFacade
from ditto_app.query.portfolio_actual import PortfolioActualQueryFacade

__all__ = ["ComparisonQueryFacade"]


class ComparisonQueryFacade:
    """
    回测 vs 实际对比查询门面.

    编排 BacktestQueryFacade 和 PortfolioActualQueryFacade，
    从回测报告提取指标，从实际持仓/成交获取数据，
    计算对比结果。
    """

    def __init__(
        self,
        backtest_facade: BacktestQueryFacade,
        actual_facade: PortfolioActualQueryFacade,
        market_facade: MarketQueryFacade,
    ) -> None:
        self._backtest = backtest_facade
        self._actual = actual_facade
        self._market = market_facade

    def get_comparison(
        self,
        strategy_id: str,
        run_id: str,
    ) -> ComparisonMetrics | None:
        """
        计算回测 vs 实际对比指标.

        Args:
            strategy_id: 策略 ID.
            run_id: 回测运行 ID.

        Returns:
            ComparisonMetrics 实例，报告不存在时返回 None.

        """
        report = self._backtest.get_report(run_id)
        if report is None:
            return None

        alpha_stats = _extract_alpha_stats(report)
        initial_cash = _extract_initial_cash(report)

        bt_navs = _extract_nav_series(
            self._backtest.get_nav_series(run_id),
        )

        fills = self._actual.get_fills(strategy_id)

        actual_navs = _build_actual_navs(fills, initial_cash, self._market)

        return compute_comparison_from_raw(
            backtest_return=alpha_stats["annualized_return"],
            backtest_sharpe=alpha_stats["sharpe_ratio"],
            backtest_total_cost=alpha_stats["total_fees"],
            backtest_nav_series=bt_navs,
            actual_fills=fills,
            actual_navs=actual_navs,
            initial_cash=initial_cash,
        )


# ------------------------------------------------------------------
# 内部辅助（紧耦合 Facade）
# ------------------------------------------------------------------


def _extract_alpha_stats(report: dict[str, Any]) -> dict[str, float]:
    """从报告 dict 提取 alpha_stats，缺失字段返回 0.0."""
    raw = report.get("alpha_stats")
    if raw is None:
        return {"annualized_return": 0.0, "sharpe_ratio": 0.0, "total_fees": 0.0}
    try:
        return {
            "annualized_return": float(raw.get("annualized_return", 0.0) or 0.0),
            "sharpe_ratio": float(raw.get("sharpe_ratio", 0.0) or 0.0),
            "total_fees": float(raw.get("total_fees", 0.0) or 0.0),
        }
    except (AttributeError, TypeError, ValueError):
        logger.warning("无法解析 alpha_stats, 返回零值: raw=%r", raw)
        return {"annualized_return": 0.0, "sharpe_ratio": 0.0, "total_fees": 0.0}


def _safe_float(data: dict[str, object], key: str, default: float = 0.0) -> float:
    """从 dict 安全提取 float 值."""
    val = data.get(key, default)
    if isinstance(val, int | float):
        return float(val)
    return default


def _extract_initial_cash(report: dict[str, Any]) -> float:
    """从报告 dict 提取 initial_cash."""
    return _safe_float(report, "initial_cash", DEFAULT_INITIAL_CASH)


def _extract_nav_series(
    nav_rows: list[dict[str, Any]],
) -> list[tuple[str, float]]:
    """从 get_nav_series 返回的行列表提取 (date, nav) 序列."""
    result: list[tuple[str, float]] = []
    for row in nav_rows:
        date_val = row.get("trade_date", "")
        nav_val = row.get("nav", 0.0)
        date = str(date_val) if isinstance(date_val, str) else ""
        nav = float(nav_val) if isinstance(nav_val, int | float) else 0.0
        if date:
            result.append((date, nav))
    return result


def _build_actual_navs(
    fills: list[ManualExecutionFill],
    initial_cash: float,
    price_query: MarketQueryFacade,
) -> list[tuple[str, float]]:
    """
    从成交记录构建实际 NAV 序列.

    逐日重建现金/持仓台账并按收盘价计算 NAV。

    Args:
        fills: 成交记录列表.
        initial_cash: 初始资金.
        price_query: 行情查询门面.

    Returns:
        按日期排序的 [(date_str, nav), ...] 序列.

    """
    if not fills:
        return []

    # 1. 收集所有成交日期和标的 ID
    all_dates: set[str] = set()
    all_instrument_ids: set[int] = set()
    fills_by_date: dict[str, list[ManualExecutionFill]] = defaultdict(list)

    for f in fills:
        all_dates.add(f.trade_date)
        all_instrument_ids.add(f.instrument_id)
        fills_by_date[f.trade_date].append(f)

    sorted_dates = sorted(all_dates)

    # 2. 查询收盘价
    bars = price_query.find_bars(
        instrument_ids=sorted(all_instrument_ids),
        start=sorted_dates[0],
        end=sorted_dates[-1],
    )

    # 构建查找表 (instrument_id, date_str) -> close_price
    close_prices: dict[tuple[int, str], float] = {}
    for row in bars.iter_rows(named=True):
        iid = row["instrument_id"]
        date_val = row["trade_date"]
        close = row["close"]
        if not iid or not date_val or not close:
            continue
        date_str = (
            date_val.isoformat() if hasattr(date_val, "isoformat") else str(date_val)
        )
        close_prices[(int(iid), date_str)] = float(close)

    # 3. 逐日构建现金/持仓台账
    cash = initial_cash
    positions: dict[int, int] = {}
    last_fill_price: dict[int, float] = {}
    nav_series: list[tuple[str, float]] = []

    for date_str in sorted_dates:
        for f in fills_by_date[date_str]:
            cost = f.fill_price * f.quantity
            if f.direction == "buy":
                cash -= cost + f.fee
                positions[f.instrument_id] = (
                    positions.get(f.instrument_id, 0) + f.quantity
                )
            else:
                cash += cost - f.fee
                positions[f.instrument_id] = (
                    positions.get(f.instrument_id, 0) - f.quantity
                )
            last_fill_price[f.instrument_id] = f.fill_price

        position_value = sum(
            qty * (close_prices.get((iid, date_str)) or last_fill_price.get(iid, 0.0))
            for iid, qty in positions.items()
            if qty
        )
        nav_series.append((date_str, cash + position_value))

    return nav_series
