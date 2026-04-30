"""
BacktestReportSerializer 单元测试 — JSON 输出格式兼容 replay 反序列化.

覆盖：
  - period 输出为 dict {"start": ..., "end": ...}（非 list）
  - rebalance_freq 字段存在
  - nav_series 字段存在
"""

from __future__ import annotations

import orjson
from ditto_engine.backtest.statistics import (
    AggregatedTradeStatistics,
    AlphaStatistics,
    BacktestReport,
)

# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------


def _make_report(
    *,
    run_id: str = "test-run-001",
    period: tuple[str, str] = ("2026-01-01", "2026-03-31"),
    initial_cash: float = 1_000_000.0,
    final_nav: float = 1_050_000.0,
    nav_series: tuple[tuple[str, float], ...] = (
        ("2026-01-01", 1_000_000.0),
        ("2026-01-02", 1_005_000.0),
        ("2026-01-03", 1_050_000.0),
    ),
) -> BacktestReport:
    """构建真实 BacktestReport 实例（仅填充必要字段）."""
    return BacktestReport(
        run_id=run_id,
        period=period,
        initial_cash=initial_cash,
        final_nav=final_nav,
        trade_stats=(),
        portfolio_stats=(),
        aggregated_trade_stats=AggregatedTradeStatistics(
            total_trades=0,
            long_trades=0,
            short_trades=0,
            win_trades=0,
            loss_trades=0,
            win_rate=0.0,
            profit_factor=0.0,
            avg_win=0.0,
            avg_loss=0.0,
            avg_win_loss_ratio=0.0,
            max_consecutive_wins=0,
            max_consecutive_losses=0,
            avg_holding_days=0.0,
            median_holding_days=0.0,
            best_trade=0.0,
            worst_trade=0.0,
            avg_trade_return_pct=0.0,
        ),
        alpha_stats=AlphaStatistics(
            annualized_return=0.0,
            annualized_volatility=0.0,
            sharpe_ratio=0.0,
            sortino_ratio=0.0,
            max_drawdown=0.0,
            max_drawdown_duration_days=0,
            calmar_ratio=0.0,
            information_ratio=None,
            tracking_error=None,
            beta=None,
            alpha_annualized=None,
            total_turnover=0.0,
            avg_turnover_per_rebalance=0.0,
            total_fees=0.0,
            net_return_after_cost=0.0,
            cost_drag=0.0,
        ),
        nav_series=nav_series,
        trade_log=(),
        fill_log=(),
    )


# ---------------------------------------------------------------------------
# period 格式测试
# ---------------------------------------------------------------------------


class TestPeriodFormat:
    """period 字段应为 dict {"start": ..., "end": ...} 格式."""

    def test_period_is_dict_not_list(self) -> None:
        """序列化后 period 应为 dict，replay 按 .get('start') 读取."""
        from ditto_application.process.execution.backtest_serialization import (
            serialize_report,
        )

        report = _make_report(period=("2026-01-01", "2026-06-30"))
        json_bytes, _ = serialize_report(report)
        data = orjson.loads(json_bytes)

        period = data["period"]
        assert isinstance(period, dict), (
            f"period 应为 dict, 实际为 {type(period).__name__}"
        )
        assert period["start"] == "2026-01-01"
        assert period["end"] == "2026-06-30"

    def test_period_dict_keys_match_tuple(self) -> None:
        """period dict 的 start/end 应与 report.period 元组对应."""
        from ditto_application.process.execution.backtest_serialization import (
            serialize_report,
        )

        report = _make_report(period=("2025-06-15", "2025-12-31"))
        json_bytes, _ = serialize_report(report)
        data = orjson.loads(json_bytes)

        assert data["period"]["start"] == report.period[0]
        assert data["period"]["end"] == report.period[1]


# ---------------------------------------------------------------------------
# rebalance_freq 字段测试
# ---------------------------------------------------------------------------


class TestRebalanceFreq:
    """JSON 应包含 rebalance_freq 字段."""

    def test_rebalance_freq_present(self) -> None:
        """序列化后 JSON 应包含 rebalance_freq 字段."""
        from ditto_application.process.execution.backtest_serialization import (
            serialize_report,
        )

        report = _make_report()
        json_bytes, _ = serialize_report(report)
        data = orjson.loads(json_bytes)

        assert "rebalance_freq" in data, "JSON 应包含 rebalance_freq 字段"

    def test_rebalance_freq_default_daily(self) -> None:
        """默认 rebalance_freq 应为 'daily'."""
        from ditto_application.process.execution.backtest_serialization import (
            serialize_report,
        )

        report = _make_report()
        json_bytes, _ = serialize_report(report)
        data = orjson.loads(json_bytes)

        assert data["rebalance_freq"] == "daily"


# ---------------------------------------------------------------------------
# nav_series 字段测试
# ---------------------------------------------------------------------------


class TestNavSeries:
    """JSON 应包含 nav_series 字段."""

    def test_nav_series_present(self) -> None:
        """序列化后 JSON 应包含 nav_series 字段."""
        from ditto_application.process.execution.backtest_serialization import (
            serialize_report,
        )

        report = _make_report()
        json_bytes, _ = serialize_report(report)
        data = orjson.loads(json_bytes)

        assert "nav_series" in data, "JSON 应包含 nav_series 字段"

    def test_nav_series_values_match_report(self) -> None:
        """nav_series 应只包含数值列表（不含日期）."""
        from ditto_application.process.execution.backtest_serialization import (
            serialize_report,
        )

        nav_data = (
            ("2026-01-01", 1_000_000.0),
            ("2026-01-02", 1_005_000.0),
            ("2026-01-03", 1_050_000.0),
        )
        report = _make_report(nav_series=nav_data)
        json_bytes, _ = serialize_report(report)
        data = orjson.loads(json_bytes)

        expected = [v for _, v in nav_data]
        assert data["nav_series"] == expected

    def test_nav_series_none_when_empty(self) -> None:
        """nav_series 为空时，JSON 中应为 None."""
        from ditto_application.process.execution.backtest_serialization import (
            serialize_report,
        )

        report = _make_report(nav_series=())
        json_bytes, _ = serialize_report(report)
        data = orjson.loads(json_bytes)

        assert data["nav_series"] is None


# ---------------------------------------------------------------------------
# Round-trip 兼容性测试
# ---------------------------------------------------------------------------


class TestRoundTripCompatibility:
    """序列化输出与 replay 反序列化期望格式兼容."""

    def test_replay_can_extract_start_end_from_period(self) -> None:
        """replay._build_config 通过 period.get('start') 读取日期."""
        from ditto_application.process.execution.backtest_serialization import (
            serialize_report,
        )

        report = _make_report(period=("2026-01-15", "2026-04-10"))
        json_bytes, _ = serialize_report(report)
        data = orjson.loads(json_bytes)

        # 模拟 replay._build_config 中的读取方式
        period = data.get("period", {})
        start = period.get("start", "")
        end = period.get("end", "")

        assert start == "2026-01-15"
        assert end == "2026-04-10"

    def test_replay_can_extract_rebalance_freq(self) -> None:
        """replay._extract_rebalance_freq 通过 report.get('rebalance_freq') 读取."""
        from ditto_application.process.execution.backtest_serialization import (
            serialize_report,
        )

        report = _make_report()
        json_bytes, _ = serialize_report(report)
        data = orjson.loads(json_bytes)

        # 模拟 replay._extract_rebalance_freq 的读取方式
        freq = data.get("rebalance_freq")
        assert isinstance(freq, str), "rebalance_freq 应为字符串"
        assert freq, "rebalance_freq 应为非空"

    def test_replay_can_extract_nav_series(self) -> None:
        """replay._extract_nav 通过 report.get('nav_series') 读取."""
        from ditto_application.process.execution.backtest_serialization import (
            serialize_report,
        )

        nav_data = (
            ("2026-01-01", 1.0),
            ("2026-01-02", 1.01),
            ("2026-01-03", 1.02),
        )
        report = _make_report(nav_series=nav_data)
        json_bytes, _ = serialize_report(report)
        data = orjson.loads(json_bytes)

        # 模拟 replay._extract_nav 的读取方式
        nav_data_from_json = data.get("nav_series")
        assert nav_data_from_json is not None
        assert [float(v) for v in nav_data_from_json] == [1.0, 1.01, 1.02]
