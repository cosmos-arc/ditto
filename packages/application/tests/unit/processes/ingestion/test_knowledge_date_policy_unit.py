"""可知时间策略单元测试（#658 批次1E）.

两融/北向此前用自然日 T+1 伪造可知时间：周五/节前数据的自然日 T+1
早于交易所真实发布（开市前公布前一交易日数据），构成 PIT 泄漏；
hk_hold 2024-08-19 季度改制后自然日 T+1 同样泄漏。
"""

from __future__ import annotations

from datetime import date

import polars as pl
import pytest
from ditto_application.processes.ingestion.knowledge_date_policy import (
    HK_HOLD_QUARTERLY_REGIME_START,
    calibrate_knowledge_dates,
    knowledge_date_policy_for,
)

# 覆盖 2024 国庆长假的 A 股交易日片段：09-30（节前最后交易日）、
# 10-08（节后首个交易日）、以及 2024-11-01（周五）→ 11-04（周一）。
TRADING_DAYS: tuple[date, ...] = (
    date(2024, 9, 27),
    date(2024, 9, 30),
    date(2024, 10, 8),
    date(2024, 10, 9),
    date(2024, 11, 1),
    date(2024, 11, 4),
    date(2024, 11, 5),
)

RUN_DATE = date(2026, 11, 3)


def _frame(dataset_trade_dates: list[date]) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "source_ticker": ["000001.SZ"] * len(dataset_trade_dates),
            "trade_date": dataset_trade_dates,
            "knowledge_date": [
                d.replace(day=min(d.day + 1, 28)) for d in dataset_trade_dates
            ],
        }
    )


class TestPolicySelection:
    def test_registered_datasets(self) -> None:
        assert knowledge_date_policy_for("margin_trading") == "next_trading_day"
        assert knowledge_date_policy_for("hsgt_top10") == "next_trading_day"
        assert knowledge_date_policy_for("hk_hold") == "hk_hold_segmented"

    def test_unregistered_dataset_untouched(self) -> None:
        assert knowledge_date_policy_for("stock_daily") is None
        assert knowledge_date_policy_for("moneyflow") is None


class TestNextTradingDay:
    def test_friday_rolls_to_monday_not_saturday(self) -> None:
        """深市周五数据下周一上午更新——自然日 T+1（周六）是 PIT 泄漏."""
        result = calibrate_knowledge_dates(
            _frame([date(2024, 11, 1)]),
            dataset="margin_trading",
            trading_days=TRADING_DAYS,
            run_date=RUN_DATE,
        )
        assert result["knowledge_date"].to_list() == [date(2024, 11, 4)]

    def test_pre_holiday_rolls_past_golden_week(self) -> None:
        """节前最后交易日的两融数据节后首个交易日开市前才发布."""
        result = calibrate_knowledge_dates(
            _frame([date(2024, 9, 30)]),
            dataset="margin_trading",
            trading_days=TRADING_DAYS,
            run_date=RUN_DATE,
        )
        assert result["knowledge_date"].to_list() == [date(2024, 10, 8)]

    def test_midweek_rolls_to_next_day(self) -> None:
        result = calibrate_knowledge_dates(
            _frame([date(2024, 10, 8)]),
            dataset="margin_trading",
            trading_days=TRADING_DAYS,
            run_date=RUN_DATE,
        )
        assert result["knowledge_date"].to_list() == [date(2024, 10, 9)]

    def test_effective_from_follows_knowledge_date(self) -> None:
        frame = _frame([date(2024, 11, 1)]).with_columns(
            pl.lit(date(2024, 11, 2)).alias("effective_from")
        )
        result = calibrate_knowledge_dates(
            frame,
            dataset="margin_trading",
            trading_days=TRADING_DAYS,
            run_date=RUN_DATE,
        )
        assert result["effective_from"].to_list() == [date(2024, 11, 4)]

    def test_calendar_exhausted_fails_closed(self) -> None:
        """日历给不出下一交易日＝可知时间不可证明，拒绝写入."""
        with pytest.raises(ValueError, match="no trading day after"):
            calibrate_knowledge_dates(
                _frame([date(2024, 11, 5)]),
                dataset="margin_trading",
                trading_days=TRADING_DAYS,
                run_date=RUN_DATE,
            )


class TestHkHoldSegmented:
    def test_daily_regime_uses_next_trading_day(self) -> None:
        result = calibrate_knowledge_dates(
            _frame([date(2024, 8, 16)]),
            dataset="hk_hold",
            trading_days=(
                date(2024, 8, 16),
                date(2024, 8, 19),
                date(2024, 8, 20),
            ),
            run_date=RUN_DATE,
        )
        assert result["knowledge_date"].to_list() == [date(2024, 8, 19)]

    def test_quarterly_regime_uses_observation_date(self) -> None:
        """季度段真实发布=季末后第 5 个北向交易日；北向日历未入库前
        以观察日兜底——保守推迟可知时间，不伪造早于发布的可知性."""
        result = calibrate_knowledge_dates(
            _frame([date(2024, 9, 30)]),
            dataset="hk_hold",
            trading_days=TRADING_DAYS,
            run_date=RUN_DATE,
        )
        assert result["knowledge_date"].to_list() == [RUN_DATE]

    def test_mixed_regimes_in_one_frame(self) -> None:
        result = calibrate_knowledge_dates(
            _frame([date(2024, 8, 16), date(2024, 9, 30)]),
            dataset="hk_hold",
            trading_days=(
                date(2024, 8, 16),
                date(2024, 8, 19),
                date(2024, 8, 20),
            ),
            run_date=RUN_DATE,
        )
        assert result["knowledge_date"].to_list() == [
            date(2024, 8, 19),
            RUN_DATE,
        ]

    def test_regime_boundary_is_2024_08_19(self) -> None:
        assert date(2024, 8, 19) == HK_HOLD_QUARTERLY_REGIME_START


class TestPassThrough:
    def test_unregistered_dataset_returns_input(self) -> None:
        frame = _frame([date(2024, 11, 1)])
        result = calibrate_knowledge_dates(
            frame,
            dataset="moneyflow",
            trading_days=TRADING_DAYS,
            run_date=RUN_DATE,
        )
        assert result.equals(frame)

    def test_empty_frame_passes_through(self) -> None:
        empty = _frame([]).clear()
        result = calibrate_knowledge_dates(
            empty,
            dataset="margin_trading",
            trading_days=TRADING_DAYS,
            run_date=RUN_DATE,
        )
        assert result.height == 0
