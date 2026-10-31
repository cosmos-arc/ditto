"""coverage_audit 纯函数单测（#624 / #621 P2）.

反例矩阵：停牌/退市/新上市（幸存者偏差防护）+ 各失败/受限归因分支 +
日历健全性核验 + 词汇闭合守卫。
"""

from collections.abc import Sequence
from datetime import date

import polars as pl
import pytest
from ditto_data.quality.coverage_audit import (
    ANOMALY_KINDS,
    COVERAGE_GAP_KINDS,
    FAILURE_ANOMALY_KINDS,
    FAILURE_GAP_KINDS,
    LIMITATION_GAP_KINDS,
    audit_session_coverage,
    audit_trading_calendar,
)

MON, TUE, WED, THU, FRI = (
    date(2024, 1, 1),
    date(2024, 1, 2),
    date(2024, 1, 3),
    date(2024, 1, 4),
    date(2024, 1, 5),
)
TRADING_DAYS = [MON, TUE, WED, THU, FRI]
ERA_START = date(2024, 1, 2)


def _master(*rows: tuple[int, date | None, date | None]) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "instrument_id": [r[0] for r in rows],
            "list_date": [r[1] for r in rows],
            "delist_date": [r[2] for r in rows],
        },
        schema={
            "instrument_id": pl.Int64,
            "list_date": pl.Date,
            "delist_date": pl.Date,
        },
    )


def _keys(rows: list[tuple[int, date]]) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "instrument_id": [r[0] for r in rows],
            "trade_date": [r[1] for r in rows],
        },
        schema={"instrument_id": pl.Int64, "trade_date": pl.Date},
    )


def _status(rows: Sequence[tuple[int, date, bool | None]]) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "instrument_id": [r[0] for r in rows],
            "trade_date": [r[1] for r in rows],
            "is_suspended": [r[2] for r in rows],
        },
        schema={
            "instrument_id": pl.Int64,
            "trade_date": pl.Date,
            "is_suspended": pl.Boolean,
        },
    )


class TestVocabularyClosure:
    """词汇闭合：失败/受限二分穷尽词汇表，异常失败集穷尽异常表."""

    def test_gap_kinds_partition_is_closed(self) -> None:
        assert FAILURE_GAP_KINDS | LIMITATION_GAP_KINDS == COVERAGE_GAP_KINDS
        assert not (FAILURE_GAP_KINDS & LIMITATION_GAP_KINDS)
        assert "suspended" in LIMITATION_GAP_KINDS
        assert "no_status_dataset" in LIMITATION_GAP_KINDS
        assert "pre_status_era" in LIMITATION_GAP_KINDS

    def test_failure_anomaly_kinds_subset_of_anomaly_kinds(self) -> None:
        assert FAILURE_ANOMALY_KINDS < ANOMALY_KINDS
        assert "master_list_date_missing" not in FAILURE_ANOMALY_KINDS


class TestLifecycleCounterExamples:
    """停牌/退市/新上市反例：生命周期语义下正常缺席不构成缺口."""

    def test_suspension_gap_is_attributed_and_passes(self) -> None:
        """停牌反例：缺失会话由状态行归因，审计通过."""
        master = _master((1, date(2023, 6, 1), None))
        bars = _keys([(1, MON), (1, TUE), (1, THU), (1, FRI)])  # 缺 WED
        status = _status([(1, d, d == WED) for d in TRADING_DAYS])
        result = audit_session_coverage(
            trading_days=TRADING_DAYS,
            master=master,
            bars=bars,
            status=status,
            status_available_from=ERA_START,
        )
        assert result.expected_sessions == 5
        assert result.present_sessions == 4
        assert result.gap_counts == {"suspended": 1}
        assert result.passed

    def test_delisted_security_retained_without_post_delist_gaps(self) -> None:
        """退市反例：退市证券保留在名册，退市日后的交易日不构成缺口."""
        delist = WED
        master = _master((1, date(2023, 6, 1), delist), (2, date(2023, 6, 1), None))
        bars = _keys([(1, MON), (1, TUE), (1, delist)] + [(2, d) for d in TRADING_DAYS])
        status = _status([(2, d, False) for d in TRADING_DAYS])
        result = audit_session_coverage(
            trading_days=TRADING_DAYS,
            master=master,
            bars=bars,
            status=status,
            status_available_from=ERA_START,
        )
        # 名册含退市证券（幸存者偏差防护），其期望会话只到退市日。
        assert result.roster_total == 2
        assert result.securities_with_sessions == 2
        assert result.expected_sessions == 5 + 3
        assert result.gap_counts == {}
        assert result.passed

    def test_new_listing_has_no_pre_listing_gaps(self) -> None:
        """新上市反例：上市日前的交易日不构成缺口."""
        list_late = THU
        master = _master((1, date(2023, 6, 1), None), (9, list_late, None))
        bars = _keys([(1, d) for d in TRADING_DAYS] + [(9, THU), (9, FRI)])
        status = _status([(1, d, False) for d in TRADING_DAYS])
        result = audit_session_coverage(
            trading_days=TRADING_DAYS,
            master=master,
            bars=bars,
            status=status,
            status_available_from=ERA_START,
        )
        assert result.securities_with_sessions == 2
        assert result.expected_sessions == 7
        assert result.gap_counts == {}
        assert result.passed


class TestGapAttributionFailClosed:
    """无法归因的缺失按失败处理，不冒充正常."""

    def test_status_says_trading_but_no_bar_fails(self) -> None:
        master = _master((1, date(2023, 6, 1), None))
        bars = _keys([(1, MON), (1, TUE), (1, THU), (1, FRI)])
        status = _status([(1, d, False) for d in TRADING_DAYS])
        result = audit_session_coverage(
            trading_days=TRADING_DAYS,
            master=master,
            bars=bars,
            status=status,
            status_available_from=ERA_START,
        )
        assert result.gap_counts == {"status_trading_no_bar": 1}
        assert not result.passed

    def test_status_row_null_flag_fails(self) -> None:
        master = _master((1, date(2023, 6, 1), None))
        bars = _keys([(1, MON), (1, TUE), (1, THU), (1, FRI)])
        status = _status([(1, d, None if d == WED else False) for d in TRADING_DAYS])
        result = audit_session_coverage(
            trading_days=TRADING_DAYS,
            master=master,
            bars=bars,
            status=status,
            status_available_from=ERA_START,
        )
        assert result.gap_counts == {"status_flag_null": 1}
        assert not result.passed

    def test_missing_status_row_after_era_fails(self) -> None:
        master = _master((1, date(2023, 6, 1), None))
        bars = _keys([(1, MON), (1, TUE), (1, THU), (1, FRI)])
        status = _status([(1, d, False) for d in TRADING_DAYS if d != WED])
        result = audit_session_coverage(
            trading_days=TRADING_DAYS,
            master=master,
            bars=bars,
            status=status,
            status_available_from=ERA_START,
        )
        assert result.gap_counts == {"status_row_missing": 1}
        assert not result.passed

    def test_missing_status_row_before_era_is_limitation(self) -> None:
        master = _master((1, date(2023, 6, 1), None))
        bars = _keys([(1, TUE), (1, WED), (1, THU), (1, FRI)])  # 缺 MON（期前）
        status = _status([(1, d, False) for d in [TUE, WED, THU, FRI]])
        result = audit_session_coverage(
            trading_days=TRADING_DAYS,
            master=master,
            bars=bars,
            status=status,
            status_available_from=ERA_START,
        )
        assert result.gap_counts == {"pre_status_era": 1}
        assert result.limitation_gaps == 1
        assert result.passed

    def test_absent_status_dataset_attributed_as_limitation(self) -> None:
        """无状态数据集（ETF 现状）：缺口诚实归因 no_status_dataset，不冒充通过归因."""
        master = _master((1, date(2023, 6, 1), None))
        bars = _keys([(1, MON), (1, TUE)])
        result = audit_session_coverage(
            trading_days=TRADING_DAYS,
            master=master,
            bars=bars,
            status=None,
        )
        assert result.gap_counts == {"no_status_dataset": 3}
        assert result.limitation_gaps == 3
        assert result.passed

    def test_no_era_and_no_status_row_fails_closed(self) -> None:
        """status_available_from 未提供时，缺失状态行不得借 era 豁免."""
        master = _master((1, date(2023, 6, 1), None))
        bars = _keys([(1, MON), (1, TUE), (1, THU), (1, FRI)])
        status = _status([(1, d, False) for d in TRADING_DAYS if d != WED])
        result = audit_session_coverage(
            trading_days=TRADING_DAYS,
            master=master,
            bars=bars,
            status=status,
        )
        assert result.gap_counts == {"status_row_missing": 1}
        assert not result.passed


class TestAnomalies:
    """不应存在的事实分类与计数."""

    def test_bar_outside_lifecycle_and_calendar(self) -> None:
        master = _master((1, TUE, THU))
        bars = _keys(
            [
                (1, MON),  # 早于上市日
                (1, TUE),
                (1, THU),
                (1, FRI),  # 晚于退市日
                (2, WED),  # 名册外标的
            ]
        )
        status = _status([(1, TUE, False), (1, THU, False)])
        result = audit_session_coverage(
            trading_days=[TUE, WED, THU],
            master=master,
            bars=bars,
            status=status,
            status_available_from=ERA_START,
        )
        # WED 对证券 1 是期望会话但无日线：无状态行（期后）→ 失败缺口。
        assert result.gap_counts == {"status_row_missing": 1}
        assert result.anomaly_counts["bar_before_list_date"] == 1
        assert result.anomaly_counts["bar_after_delist_date"] == 1
        assert result.anomaly_counts["bar_security_not_in_master"] == 1
        assert not result.passed

    def test_bar_on_non_trading_day(self) -> None:
        weekend = date(2024, 1, 6)
        master = _master((1, date(2023, 6, 1), None))
        bars = _keys([(1, MON), (1, weekend)])
        status = _status([(1, MON, False)])
        result = audit_session_coverage(
            trading_days=[MON],
            master=master,
            bars=bars,
            status=status,
        )
        assert result.anomaly_counts == {"bar_on_non_trading_day": 1}
        assert not result.passed

    def test_master_null_list_date_excluded_but_counted(self) -> None:
        master = _master((1, date(2023, 6, 1), None), (2, None, None))
        bars = _keys([(1, MON), (2, MON)])
        status = _status([(1, MON, False)])
        result = audit_session_coverage(
            trading_days=[MON],
            master=master,
            bars=bars,
            status=status,
        )
        assert result.anomaly_counts["master_list_date_missing"] == 1
        assert result.anomaly_counts["bar_master_list_date_missing"] == 1
        # 名册行缺口本身是证据边界（非失败）；该证券却有日线、无法界定期望
        # 区间 → 失败异常。
        assert result.failure_anomalies == 1
        assert not result.passed

    def test_duplicate_keys_counted(self) -> None:
        master = _master((1, date(2023, 6, 1), None))
        bars = _keys([(1, MON), (1, MON), (1, TUE)])
        status = _status([(1, MON, False), (1, MON, False), (1, TUE, False)])
        result = audit_session_coverage(
            trading_days=[MON, TUE],
            master=master,
            bars=bars,
            status=status,
        )
        assert result.anomaly_counts["duplicate_bar_keys"] == 1
        assert result.anomaly_counts["duplicate_status_keys"] == 1
        assert not result.passed

    def test_suspended_with_bar_contradiction(self) -> None:
        master = _master((1, date(2023, 6, 1), None))
        bars = _keys([(1, MON), (1, TUE)])
        status = _status([(1, MON, True), (1, TUE, False)])
        result = audit_session_coverage(
            trading_days=[MON, TUE],
            master=master,
            bars=bars,
            status=status,
        )
        assert result.anomaly_counts == {"suspended_with_bar": 1}
        assert not result.passed

    def test_adj_factor_missing(self) -> None:
        master = _master((1, date(2023, 6, 1), None))
        bars = _keys([(1, MON), (1, TUE)])
        adj = _keys([(1, MON)])
        result = audit_session_coverage(
            trading_days=[MON, TUE],
            master=master,
            bars=bars,
            status=_status([(1, MON, False), (1, TUE, False)]),
            adj_factors=adj,
        )
        assert result.adj_factor_checked
        assert result.adj_factor_missing == 1
        assert not result.passed

    def test_adj_factor_not_checked_when_absent(self) -> None:
        master = _master((1, date(2023, 6, 1), None))
        result = audit_session_coverage(
            trading_days=[MON],
            master=master,
            bars=_keys([(1, MON)]),
            status=_status([(1, MON, False)]),
        )
        assert not result.adj_factor_checked
        assert result.adj_factor_missing == 0
        assert result.passed

    def test_adj_factor_revision_versions_count_once(self) -> None:
        """append_only 修订：同键多 knowledge_date 版本只算一次在场."""
        master = _master((1, date(2023, 6, 1), None))
        adj = _keys([(1, MON), (1, MON)])
        result = audit_session_coverage(
            trading_days=[MON],
            master=master,
            bars=_keys([(1, MON)]),
            status=_status([(1, MON, False)]),
            adj_factors=adj,
        )
        assert result.adj_factor_missing == 0
        assert result.passed


class TestSummaryCounts:
    """摘要计数（含分母）与明细帧形状."""

    def test_summary_and_detail_shape(self) -> None:
        master = _master((1, date(2023, 6, 1), None))
        bars = _keys([(1, MON), (1, TUE), (1, THU), (1, FRI)])
        status = _status([(1, d, d == WED) for d in TRADING_DAYS])
        result = audit_session_coverage(
            trading_days=TRADING_DAYS,
            master=master,
            bars=bars,
            status=status,
            status_available_from=ERA_START,
        )
        summary = result.summary()
        assert summary["expected_sessions"] == 5
        assert summary["present_sessions"] == 4
        assert summary["limitation_gaps"] == 1
        assert summary["failure_gaps"] == 0
        assert summary["passed"] is True
        assert set(result.gap_detail.columns) == {"instrument_id", "trade_date", "kind"}
        wed_rows = result.gap_detail.filter(
            (pl.col("instrument_id") == 1) & (pl.col("trade_date") == WED)
        )
        assert wed_rows["kind"].to_list() == ["suspended"]

    def test_empty_window_yields_zero_counts(self) -> None:
        master = _master((1, date(2023, 6, 1), None))
        result = audit_session_coverage(
            trading_days=[],
            master=master,
            bars=_keys([]),
            status=_status([]),
        )
        assert result.expected_sessions == 0
        assert result.securities_with_sessions == 0
        assert result.passed


class TestTradingCalendarAudit:
    """日历序列健全性核验."""

    def test_healthy_calendar_passes(self) -> None:
        result = audit_trading_calendar(TRADING_DAYS, window_start=MON, window_end=FRI)
        assert result.trading_days == 5
        assert result.passed
        assert result.yearly_counts == ((2024, 5),)

    def test_duplicate_and_weekend_fail(self) -> None:
        dup = [*TRADING_DAYS, WED]
        result = audit_trading_calendar(dup, window_start=MON, window_end=FRI)
        assert result.duplicate_days == 1
        assert not result.passed

        weekend = date(2024, 1, 6)
        result = audit_trading_calendar(
            [*TRADING_DAYS, weekend], window_start=MON, window_end=FRI
        )
        assert result.weekend_days == 1
        assert not result.passed

    def test_missing_year_fails(self) -> None:
        result = audit_trading_calendar(
            [MON], window_start=date(2023, 1, 1), window_end=FRI
        )
        assert result.missing_years == (2023,)
        assert not result.passed

    def test_year_out_of_bounds_fails(self) -> None:
        """近全年窗口（≥120 天）下会话数低于工作日 80% → 判缺."""
        days = [date(2024, 1, d) for d in range(1, 21)]  # 20 个会话，远低于下界
        result = audit_trading_calendar(
            days,
            window_start=date(2024, 1, 1),
            window_end=date(2024, 6, 30),
        )
        assert result.years_out_of_bounds == (2024,)
        assert not result.passed

    def test_sessions_exceeding_weekdays_fails(self) -> None:
        """会话数超过窗口工作日数（如周末混入）按区间上界失败."""
        days = [date(2024, 1, d) for d in range(2, 30, 2)]  # 含周六的 14 天
        result = audit_trading_calendar(
            days,
            window_start=date(2024, 1, 1),
            window_end=date(2024, 6, 30),
        )
        assert result.weekend_days > 0
        assert not result.passed

    def test_partial_window_years_do_not_fail_bounds(self) -> None:
        """窗口首末年仅覆盖部分年份时不按全年区间判定."""
        days = [MON, TUE]
        result = audit_trading_calendar(days, window_start=MON, window_end=TUE)
        assert result.years_out_of_bounds == ()
        assert result.missing_years == ()
        assert result.passed


@pytest.mark.parametrize(
    ("gap_kind", "expected_failure"),
    [
        ("suspended", False),
        ("status_trading_no_bar", True),
        ("status_flag_null", True),
        ("status_row_missing", True),
        ("pre_status_era", False),
        ("no_status_dataset", False),
    ],
)
def test_every_gap_kind_is_classified(gap_kind: str, expected_failure: bool) -> None:
    """词汇表逐项可达：每个 gap kind 都能由审计产出（防死分支）."""
    master = _master((1, date(2023, 6, 1), None))
    bars = _keys([(1, MON), (1, TUE), (1, THU), (1, FRI)])  # 缺 WED
    if gap_kind == "no_status_dataset":
        status = None
        era = None
    else:
        if gap_kind == "suspended":
            rows = [(1, d, d == WED) for d in TRADING_DAYS]
        elif gap_kind == "status_flag_null":
            rows = [(1, d, None if d == WED else False) for d in TRADING_DAYS]
        else:
            rows = [(1, d, False) for d in TRADING_DAYS]
        if gap_kind in {"status_row_missing", "pre_status_era"}:
            rows = [r for r in rows if r[1] != WED]
        status = _status(rows)
        if gap_kind == "status_row_missing":
            era = None
        elif gap_kind == "pre_status_era":
            era = THU  # 缺失日 WED 早于状态期起点 → 证据边界
        else:
            era = ERA_START
    result = audit_session_coverage(
        trading_days=TRADING_DAYS,
        master=master,
        bars=bars,
        status=status,
        status_available_from=era,
    )
    assert result.gap_counts == {gap_kind: 1}
    assert result.passed is not expected_failure
