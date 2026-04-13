"""
ComparisonQueryFacade — 回测 vs 实际对比查询门面 + 纯计算函数.

提供 ComparisonMetrics 数据类和 compute_comparison_from_raw 纯函数，
从原始指标值计算回测与实际交易表现的差异指标。
"""

from __future__ import annotations

import logging
import math
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from ditto_kernel.math import pearson_correlation

from ditto_app.execution_dto import ManualExecutionFill
from ditto_app.query._artifact_utils import compute_total_return
from ditto_app.query.backtest import BacktestQueryFacade
from ditto_app.query.market import MarketQueryFacade
from ditto_app.query.portfolio_actual import PortfolioActualQueryFacade

logger = logging.getLogger(__name__)

__all__ = ["ComparisonMetrics", "ComparisonQueryFacade", "compute_comparison_from_raw"]

_TRADING_DAYS_PER_YEAR = 252
_MIN_PAIRED_POINTS = 2
_MIN_POINTS_FOR_TRACKING_ERROR = 3


@dataclass(frozen=True)
class ComparisonMetrics:
    """
    回测 vs 实际对比指标.

    Attributes:
        backtest_return: 回测总收益率 (%)
        actual_return: 实际总收益率 (%)
        return_diff: 收益率偏差 (actual - backtest) (%)
        return_diff_bps: 基点偏差
        backtest_sharpe: 回测 Sharpe
        actual_sharpe: 实际 Sharpe
        backtest_total_cost: 回测总成本
        actual_total_cost: 实际总成本
        cost_drag_bps: 成本拖累 (基点)
        nav_correlation: NAV 序列 Pearson 相关系数
        max_nav_diff_bps: 最大 NAV 偏差 (基点)
        avg_daily_tracking_error_bps: 日均跟踪误差 (基点)

    """

    backtest_return: float
    actual_return: float | None  # 实验性: 无真实 NAV 时为 None
    return_diff: float | None
    return_diff_bps: float | None
    backtest_sharpe: float
    actual_sharpe: float
    backtest_total_cost: float
    actual_total_cost: float
    cost_drag_bps: float
    nav_correlation: float
    max_nav_diff_bps: float
    avg_daily_tracking_error_bps: float


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
        market_facade: MarketQueryFacade | None = None,
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
# 纯计算函数
# ------------------------------------------------------------------


def compute_comparison_from_raw(
    backtest_return: float,
    backtest_sharpe: float,
    backtest_total_cost: float,
    backtest_nav_series: list[tuple[str, float]],
    actual_fills: list[ManualExecutionFill],
    actual_navs: list[tuple[str, float]],
    initial_cash: float = 1_000_000.0,
) -> ComparisonMetrics:
    """
    从原始指标计算回测 vs 实际对比.

    Args:
        backtest_return: 回测年化收益率 (%).
        backtest_sharpe: 回测 Sharpe 比率.
        backtest_total_cost: 回测总手续费.
        backtest_nav_series: 回测 NAV 序列 [(date, nav), ...].
        actual_fills: 实际成交记录列表.
        actual_navs: 实际 NAV 序列 [(date, nav), ...].
        initial_cash: 初始资金（用于基点计算）.

    Returns:
        ComparisonMetrics 实例.

    """
    actual_return = _compute_total_return(actual_navs)
    actual_sharpe = _compute_sharpe_from_navs(actual_navs)
    actual_total_cost = sum(f.fee for f in actual_fills)

    return_diff: float | None = (
        actual_return - backtest_return if actual_return is not None else None
    )
    return_diff_bps: float | None = (
        return_diff * 100.0 if return_diff is not None else None
    )

    cost_drag_bps = (
        (actual_total_cost - backtest_total_cost) / initial_cash * 10_000.0
        if initial_cash > 0
        else 0.0
    )

    bt_navs = tuple(backtest_nav_series)
    nav_correlation = _compute_nav_correlation(bt_navs, actual_navs)
    max_nav_diff_bps = _compute_max_nav_diff_bps(bt_navs, actual_navs, initial_cash)
    avg_daily_tracking_error_bps = _compute_tracking_error_bps(bt_navs, actual_navs)

    return ComparisonMetrics(
        backtest_return=backtest_return,
        actual_return=actual_return,
        return_diff=return_diff,
        return_diff_bps=return_diff_bps,
        backtest_sharpe=backtest_sharpe,
        actual_sharpe=actual_sharpe,
        backtest_total_cost=backtest_total_cost,
        actual_total_cost=actual_total_cost,
        cost_drag_bps=cost_drag_bps,
        nav_correlation=nav_correlation,
        max_nav_diff_bps=max_nav_diff_bps,
        avg_daily_tracking_error_bps=avg_daily_tracking_error_bps,
    )


# ------------------------------------------------------------------
# 内部辅助
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
    return _safe_float(report, "initial_cash", 1_000_000.0)


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
    price_query: MarketQueryFacade | None = None,
) -> list[tuple[str, float]]:
    """
    从成交记录构建实际 NAV 序列.

    当 price_query 为 None 时，回退到简化占位逻辑（仅扣除费用）。
    当 price_query 可用时，逐日重建现金/持仓台账并按收盘价计算 NAV。

    Args:
        fills: 成交记录列表.
        initial_cash: 初始资金.
        price_query: 行情查询门面（可选）.

    Returns:
        按日期排序的 [(date_str, nav), ...] 序列.

    """
    if not fills:
        return []

    # 回退: 无行情数据源时使用简化逻辑
    if price_query is None:
        by_date: dict[str, float] = {}
        for f in fills:
            by_date.setdefault(f.trade_date, initial_cash)
            by_date[f.trade_date] -= f.fee
        return sorted(by_date.items())

    # 完整 NAV 重建
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

    return nav_series


def _compute_total_return(navs: list[tuple[str, float]]) -> float | None:
    """从 NAV 序列计算总收益率 (%). 无足够数据时返回 None."""
    if len(navs) < _MIN_PAIRED_POINTS:
        return None
    initial = navs[0][1]
    final = navs[-1][1]
    if initial == 0:
        return None
    return compute_total_return(initial_cash=initial, final_nav=final) * 100.0


def _compute_sharpe_from_navs(navs: list[tuple[str, float]]) -> float:
    """从 NAV 序列计算 Sharpe 比率 (假设无风险利率为 0)."""
    if len(navs) < _MIN_PAIRED_POINTS:
        return 0.0
    nav_values = [v for _, v in navs]
    daily_returns = _daily_returns(nav_values)

    n = len(daily_returns)
    if n < _MIN_PAIRED_POINTS:
        return 0.0

    mean_ret = sum(daily_returns) / n
    variance = sum((r - mean_ret) ** 2 for r in daily_returns) / (n - 1)
    if variance == 0:
        return 0.0

    ann_vol = math.sqrt(variance) * math.sqrt(_TRADING_DAYS_PER_YEAR)
    ann_ret = mean_ret * _TRADING_DAYS_PER_YEAR
    return ann_ret / ann_vol if ann_vol > 0 else 0.0


def _align_nav_series(
    bt_navs: tuple[tuple[str, float], ...],
    actual_navs: list[tuple[str, float]],
    min_points: int = _MIN_PAIRED_POINTS,
) -> tuple[list[float], list[float]]:
    """
    对齐两条 NAV 序列到共同日期，返回 (bt_values, actual_values).

    Returns:
        空列表对齐时 (空, 空)；不足 min_points 时 (空, 空).

    """
    if not bt_navs or not actual_navs:
        return [], []

    bt_dict = dict(bt_navs)
    actual_dict = dict(actual_navs)
    common_dates = sorted(set(bt_dict.keys()) & set(actual_dict.keys()))

    if len(common_dates) < min_points:
        return [], []

    return (
        [bt_dict[d] for d in common_dates],
        [actual_dict[d] for d in common_dates],
    )


def _compute_nav_correlation(
    bt_navs: tuple[tuple[str, float], ...],
    actual_navs: list[tuple[str, float]],
) -> float:
    """计算两条 NAV 序列的 Pearson 相关系数."""
    bt_values, actual_values = _align_nav_series(bt_navs, actual_navs)
    if not bt_values:
        return 0.0
    return pearson_correlation(bt_values, actual_values)


def _compute_max_nav_diff_bps(
    bt_navs: tuple[tuple[str, float], ...],
    actual_navs: list[tuple[str, float]],
    initial_cash: float,
) -> float:
    """计算最大 NAV 偏差 (基点)."""
    if initial_cash <= 0:
        return 0.0

    bt_values, actual_values = _align_nav_series(
        bt_navs,
        actual_navs,
        min_points=1,
    )
    if not bt_values:
        return 0.0

    max_diff_bps = 0.0
    for bt_v, actual_v in zip(bt_values, actual_values, strict=True):
        diff = abs(bt_v - actual_v)
        bps = diff / initial_cash * 10_000.0
        max_diff_bps = max(max_diff_bps, bps)

    return max_diff_bps


def _compute_tracking_error_bps(
    bt_navs: tuple[tuple[str, float], ...],
    actual_navs: list[tuple[str, float]],
) -> float:
    """计算日均跟踪误差 (基点)."""
    bt_values, actual_values = _align_nav_series(
        bt_navs,
        actual_navs,
        min_points=_MIN_POINTS_FOR_TRACKING_ERROR,
    )
    if not bt_values:
        return 0.0

    bt_returns = _daily_returns(bt_values)
    actual_returns = _daily_returns(actual_values)

    if not bt_returns or not actual_returns:
        return 0.0

    min_len = min(len(bt_returns), len(actual_returns))
    if min_len < _MIN_PAIRED_POINTS:
        return 0.0

    excess = [bt_returns[i] - actual_returns[i] for i in range(min_len)]

    mean_excess = sum(excess) / min_len
    te_var = sum((e - mean_excess) ** 2 for e in excess) / (min_len - 1)
    if te_var <= 0:
        return 0.0

    # 日均超额收益标准差 → 基点 (CFA Institute 标准)
    return math.sqrt(te_var) * 10_000.0


def _daily_returns(navs: list[float]) -> list[float]:
    """将 NAV 序列转为日收益率序列 (小数)."""
    result: list[float] = []
    for i in range(1, len(navs)):
        if navs[i - 1] != 0:
            result.append(navs[i] / navs[i - 1] - 1)
        else:
            result.append(0.0)
    return result
