"""
逐证券交易日覆盖审计（#624 / 父规格 #621 P2）.

按「证券生命周期 × 交易日历」构造期望会话集，与实际日线/复权因子比对：

- 生命周期语义沿用 #581 union+lifecycle：退市证券保留在名册（is_active=False
  行不删除），生命周期外的交易日不构成缺口——上市前与退市后缺失是正常状态，
  不是数据覆盖失败（幸存者偏差防护）。
- 每个缺失会话归因到闭合词汇表 ``COVERAGE_GAP_KINDS``；无法归因的缺失按
  失败处理（fail-closed），不冒充正常。
- 本模块是 **ops 物理覆盖核验**，不是 PIT 消费查询：它审计存储里物理存在
  什么（含全部 knowledge_date 版本，按业务键去重后判在场），决策时点的
  知识可见性由 snapshot readiness 与图表/查询层负责。adj_factor 为
  append_only 修订语义，此处只回答「该会话是否存在任一版本因子」。

纯函数模块：全部输入经参数注入，零 I/O。
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

import polars as pl

__all__ = [
    "ANOMALY_KINDS",
    "COVERAGE_GAP_KINDS",
    "FAILURE_ANOMALY_KINDS",
    "FAILURE_GAP_KINDS",
    "LIMITATION_GAP_KINDS",
    "CalendarAudit",
    "SessionCoverageAudit",
    "audit_session_coverage",
    "audit_trading_calendar",
]


# --- 闭合词汇表 ------------------------------------------------------------
#
# 缺失会话（生命周期内、期望有日线但缺席）：
COVERAGE_GAP_KINDS = frozenset(
    {
        # 状态行存在且停牌 → 可归因缺席（正常）
        "suspended",
        # 状态行存在、未停牌却无日线 → 真缺口（失败）
        "status_trading_no_bar",
        # 状态行存在但 is_suspended 为 null → 无法归因（失败）
        "status_flag_null",
        # 状态期已开始却无状态行 → 状态集本身有洞，缺口无法归因（失败）
        "status_row_missing",
        # 状态数据集起点之前（stock_status 自 2016-08-09）→ 证据边界（受限，非失败）
        "pre_status_era",
        # 该资产类没有状态数据集（当前 ETF 现实）→ 证据边界（受限，非失败）
        "no_status_dataset",
    }
)

# 失败/受限二分必须穷尽词汇表（守卫测试锁定）。
FAILURE_GAP_KINDS = frozenset(
    {"status_trading_no_bar", "status_flag_null", "status_row_missing"}
)
LIMITATION_GAP_KINDS = COVERAGE_GAP_KINDS - FAILURE_GAP_KINDS

# 异常（不应存在的事实，与缺口归因分开计数）：
ANOMALY_KINDS = frozenset(
    {
        # 日线早于上市日
        "bar_before_list_date",
        # 日线晚于退市日
        "bar_after_delist_date",
        # 日线落在日历非交易日
        "bar_on_non_trading_day",
        # 日线标的缺席主数据名册
        "bar_security_not_in_master",
        # 名册行 list_date 为 null，无法界定期望区间（计入后从期望网格剔除）
        "master_list_date_missing",
        # 名册行 list_date 为 null 的证券却有日线
        "bar_master_list_date_missing",
        # 同键重复日线（按业务键去重后计一次在场）
        "duplicate_bar_keys",
        # 同键重复状态行
        "duplicate_status_keys",
        # 状态声明停牌却有日线（矛盾证据，沿用 #507 C1 语义：报告不裁决）
        "suspended_with_bar",
        # 有日线会话却无任一版本复权因子（消费者按 #514 fail-closed）
        "adj_factor_missing",
    }
)

FAILURE_ANOMALY_KINDS = ANOMALY_KINDS - {"master_list_date_missing"}

_WEEKEND_WEEKDAY = 5
_FULL_YEAR_MIN_SPAN_DAYS = 120

_DETAIL_SCHEMA = {
    "instrument_id": pl.Int64,
    "trade_date": pl.Date,
    "kind": pl.String,
}


@dataclass(frozen=True)
class CalendarAudit:
    """交易日历核验结果（窗口内物理会话序列的健全性）."""

    trading_days: int
    duplicate_days: int
    weekend_days: int
    missing_years: tuple[int, ...]
    years_out_of_bounds: tuple[int, ...]
    yearly_counts: tuple[tuple[int, int], ...]

    @property
    def passed(self) -> bool:
        """序列健全（无重复/周末/缺年/区间外年份）."""
        return (
            self.duplicate_days == 0
            and self.weekend_days == 0
            and not self.missing_years
            and not self.years_out_of_bounds
        )


@dataclass(frozen=True)
class SessionCoverageAudit:
    """单资产类 × 窗口的逐证券会话覆盖审计结果."""

    roster_total: int
    securities_with_sessions: int
    expected_sessions: int
    present_sessions: int
    gap_counts: dict[str, int]
    anomaly_counts: dict[str, int]
    bar_sessions: int
    adj_factor_missing: int
    adj_factor_checked: bool
    gap_detail: pl.DataFrame
    anomaly_detail: pl.DataFrame

    @property
    def failure_gaps(self) -> int:
        """失败桶缺口总数（无法归因的缺失会话）."""
        return sum(self.gap_counts.get(k, 0) for k in FAILURE_GAP_KINDS)

    @property
    def limitation_gaps(self) -> int:
        """证据边界桶缺口总数（状态期前/无状态数据集）."""
        return sum(self.gap_counts.get(k, 0) for k in LIMITATION_GAP_KINDS)

    @property
    def failure_anomalies(self) -> int:
        """失败桶异常总数（不应存在的事实）."""
        return sum(self.anomaly_counts.get(k, 0) for k in FAILURE_ANOMALY_KINDS)

    @property
    def passed(self) -> bool:
        """无失败桶缺口/异常且复权因子覆盖完整."""
        return (
            self.failure_gaps == 0
            and self.failure_anomalies == 0
            and (not self.adj_factor_checked or self.adj_factor_missing == 0)
        )

    def summary(self) -> dict[str, int | bool]:
        """不含明细的计数摘要（报告/日志用）."""
        return {
            "roster_total": self.roster_total,
            "securities_with_sessions": self.securities_with_sessions,
            "expected_sessions": self.expected_sessions,
            "present_sessions": self.present_sessions,
            "failure_gaps": self.failure_gaps,
            "limitation_gaps": self.limitation_gaps,
            "failure_anomalies": self.failure_anomalies,
            "bar_sessions": self.bar_sessions,
            "adj_factor_checked": self.adj_factor_checked,
            "adj_factor_missing": self.adj_factor_missing,
            "passed": self.passed,
        }


def audit_trading_calendar(
    trading_days: Sequence[date],
    *,
    window_start: date,
    window_end: date,
) -> CalendarAudit:
    """
    核验窗口内交易日序列：重复、周末、缺失年份与年度会话数区间.

    年度会话数只对窗口覆盖 ≥120 天的年份按工作日比例判定（下界 0.8，
    上界=窗口内工作日数）；被窗口裁剪的年份不做区间判定，避免把部分
    覆盖误判为缺年。日历自身的绝对完整性（对照交易所真值）不在本函数
    能力内——这里只做序列健全性启发式；对拍真值由来源摄取与对账负责。
    """
    days = list(trading_days)
    duplicates = len(days) - len(set(days))
    weekend = sum(1 for d in days if d.weekday() >= _WEEKEND_WEEKDAY)

    by_year: dict[int, int] = dict.fromkeys(
        range(window_start.year, window_end.year + 1), 0
    )
    for day in days:
        if day.year in by_year:
            by_year[day.year] += 1

    missing_years = tuple(y for y, c in by_year.items() if c == 0)
    years_out_of_bounds = tuple(
        y
        for y, c in by_year.items()
        if c > 0 and not _yearly_sessions_within_bounds(y, c, window_start, window_end)
    )
    return CalendarAudit(
        trading_days=len(days),
        duplicate_days=duplicates,
        weekend_days=weekend,
        missing_years=missing_years,
        years_out_of_bounds=years_out_of_bounds,
        yearly_counts=tuple(sorted(by_year.items())),
    )


def _yearly_sessions_within_bounds(
    year: int, sessions: int, window_start: date, window_end: date
) -> bool:
    """
    年度会话数是否落在窗口内工作日数的合理比例区间（[80%, 100%]）.

    仅当窗口覆盖该年 ≥120 天时判定（近全年）；裁剪年信息不足，跳过。
    """
    year_start = max(window_start, date(year, 1, 1))
    year_end = min(window_end, date(year, 12, 31))
    if (year_end - year_start).days + 1 < _FULL_YEAR_MIN_SPAN_DAYS:
        return True
    weekdays = 0
    day = year_start
    while day <= year_end:
        if day.weekday() < _WEEKEND_WEEKDAY:
            weekdays += 1
        day = date.fromordinal(day.toordinal() + 1)
    return weekdays * 4 // 5 <= sessions <= weekdays


def audit_session_coverage(
    *,
    trading_days: Sequence[date],
    master: pl.DataFrame,
    bars: pl.DataFrame,
    status: pl.DataFrame | None = None,
    status_available_from: date | None = None,
    adj_factors: pl.DataFrame | None = None,
) -> SessionCoverageAudit:
    """
    逐证券交易日覆盖审计（纯函数）.

    Args:
        trading_days: 窗口内交易日历会话（由调用方从日历服务取得）.
        master: 证券名册，需含 instrument_id/list_date/delist_date
            （delist_date null = 未退市；含退市行——is_active=False 不剔除）.
        bars: 日线，需含 instrument_id/trade_date.
        status: 逐日状态快照，需含 instrument_id/trade_date/is_suspended；
            None 表示该资产类无状态数据集（缺口归因到 no_status_dataset）.
        status_available_from: 状态数据集覆盖起点；早于该日且无状态行的缺失
            归因 pre_status_era（证据边界，非失败）。None 且 status 提供时，
            缺失状态行一律按失败处理.
        adj_factors: 复权因子业务键（instrument_id/trade_date，任一版本在场
            即算覆盖）；None 表示跳过复权覆盖检查.

    """
    calendar = pl.DataFrame(
        {"trade_date": pl.Series(list(trading_days), dtype=pl.Date)}
    )

    roster = master.select(
        pl.col("instrument_id").cast(pl.Int64),
        pl.col("list_date").cast(pl.Date),
        pl.col("delist_date").cast(pl.Date),
    )
    roster_total = roster.height
    usable = roster.filter(pl.col("list_date").is_not_null())
    excluded = roster.join(
        usable.select("instrument_id"), on="instrument_id", how="anti"
    )

    bars_keys = (
        bars.select(
            pl.col("instrument_id").cast(pl.Int64),
            pl.col("trade_date").cast(pl.Date),
        )
        .unique(subset=["instrument_id", "trade_date"])
        .sort(["instrument_id", "trade_date"])
    )
    duplicate_bar_keys = bars.height - bars_keys.height

    status_keys: pl.DataFrame | None = None
    duplicate_status_keys = 0
    if status is not None:
        status_keys = (
            status.select(
                pl.col("instrument_id").cast(pl.Int64),
                pl.col("trade_date").cast(pl.Date),
                pl.col("is_suspended").cast(pl.Boolean),
            )
            .unique(subset=["instrument_id", "trade_date"])
            .with_columns(pl.lit(True).alias("_status_present"))
            .sort(["instrument_id", "trade_date"])
        )
        duplicate_status_keys = status.height - status_keys.height

    # 期望会话 = 名册 × 日历 ∩ 生命周期（含上市日与退市日当日）。
    expected = (
        usable.select("instrument_id", "list_date", "delist_date")
        .join(calendar, how="cross")
        .filter(
            (pl.col("trade_date") >= pl.col("list_date"))
            & (
                pl.col("delist_date").is_null()
                | (pl.col("trade_date") <= pl.col("delist_date"))
            )
        )
        .select("instrument_id", "trade_date")
    )
    expected_sessions = expected.height

    missing = expected.join(bars_keys, on=["instrument_id", "trade_date"], how="anti")
    present_sessions = expected_sessions - missing.height

    gap_rows = _attribute_gaps(
        missing,
        status_keys,
        status_available_from=status_available_from,
    )

    anomaly_counts, detail = _collect_anomalies(
        bars_keys=bars_keys,
        expected=expected,
        usable=usable,
        excluded=excluded,
        status_keys=status_keys,
        adj_factors=adj_factors,
        duplicate_keys={
            "duplicate_bar_keys": duplicate_bar_keys,
            "duplicate_status_keys": duplicate_status_keys,
        },
    )

    gap_counts: dict[str, int] = {}
    if gap_rows.height:
        counted = gap_rows.group_by("kind").len()
        gap_counts = dict(
            zip(counted["kind"].to_list(), counted["len"].to_list(), strict=True)
        )

    securities_with_sessions = (
        expected["instrument_id"].n_unique() if expected_sessions else 0
    )

    return SessionCoverageAudit(
        roster_total=roster_total,
        securities_with_sessions=securities_with_sessions,
        expected_sessions=expected_sessions,
        present_sessions=present_sessions,
        gap_counts=gap_counts,
        anomaly_counts=anomaly_counts,
        bar_sessions=bars_keys.height,
        adj_factor_missing=anomaly_counts.get("adj_factor_missing", 0),
        adj_factor_checked=adj_factors is not None,
        gap_detail=gap_rows,
        anomaly_detail=detail,
    )


def _collect_anomalies(
    *,
    bars_keys: pl.DataFrame,
    expected: pl.DataFrame,
    usable: pl.DataFrame,
    excluded: pl.DataFrame,
    status_keys: pl.DataFrame | None,
    adj_factors: pl.DataFrame | None,
    duplicate_keys: dict[str, int],
) -> tuple[dict[str, int], pl.DataFrame]:
    """收集异常事实：生命周期/日历外日线、重复键、停牌矛盾、缺因子."""
    counts: dict[str, int] = {}
    frames: list[pl.DataFrame] = []

    def _record_rows(frame: pl.DataFrame, kind: str) -> None:
        if frame.height:
            counts[kind] = frame.height
            frames.append(
                frame.select(
                    "instrument_id",
                    "trade_date",
                    pl.lit(kind, dtype=pl.String).alias("kind"),
                )
            )

    outside = bars_keys.join(expected, on=["instrument_id", "trade_date"], how="anti")
    outside_rows = _classify_bar_anomalies(outside, usable, excluded)
    if outside_rows.height:
        counted = outside_rows.group_by("kind").len()
        counts.update(
            dict(zip(counted["kind"].to_list(), counted["len"].to_list(), strict=True))
        )
        frames.append(outside_rows)

    counts.update({kind: n for kind, n in duplicate_keys.items() if n})
    if excluded.height:
        counts["master_list_date_missing"] = excluded.height

    if status_keys is not None:
        contradictions = bars_keys.join(
            status_keys.filter(pl.col("is_suspended") == True),  # noqa: E712
            on=["instrument_id", "trade_date"],
            how="semi",
        )
        _record_rows(contradictions, "suspended_with_bar")

    if adj_factors is not None:
        adj_keys = adj_factors.select(
            pl.col("instrument_id").cast(pl.Int64),
            pl.col("trade_date").cast(pl.Date),
        ).unique(subset=["instrument_id", "trade_date"])
        adj_missing = bars_keys.join(
            adj_keys, on=["instrument_id", "trade_date"], how="anti"
        )
        _record_rows(adj_missing, "adj_factor_missing")

    detail = pl.concat(frames) if frames else pl.DataFrame(schema=_DETAIL_SCHEMA)
    return counts, detail


def _attribute_gaps(
    missing: pl.DataFrame,
    status_keys: pl.DataFrame | None,
    *,
    status_available_from: date | None,
) -> pl.DataFrame:
    """把缺失会话归因到闭合词汇表（fail-closed：无证据即失败）."""
    if missing.height == 0:
        return pl.DataFrame(schema=_DETAIL_SCHEMA)

    if status_keys is None:
        return missing.select(
            "instrument_id",
            "trade_date",
            pl.lit("no_status_dataset", dtype=pl.String).alias("kind"),
        )

    joined = missing.join(status_keys, on=["instrument_id", "trade_date"], how="left")
    era_start = status_available_from
    # _status_present（主函数注入的在场指示列）区分「无状态行」与「状态行
    # flag 为 null」两种 null——前者按 era 判定，后者直接失败。
    kind = (
        pl.when(
            pl.col("_status_present") & (pl.col("is_suspended") == True)  # noqa: E712
        )
        .then(pl.lit("suspended"))
        .when(
            pl.col("_status_present") & (pl.col("is_suspended") == False)  # noqa: E712
        )
        .then(pl.lit("status_trading_no_bar"))
        .when(pl.col("_status_present"))
        .then(pl.lit("status_flag_null"))
        .when(
            (era_start is None)
            | (pl.col("trade_date") >= pl.lit(era_start, dtype=pl.Date))
        )
        .then(pl.lit("status_row_missing"))
        .otherwise(pl.lit("pre_status_era"))
        .alias("kind")
    )
    return joined.select("instrument_id", "trade_date", kind).sort(
        ["instrument_id", "trade_date"]
    )


def _classify_bar_anomalies(
    outside: pl.DataFrame, usable: pl.DataFrame, excluded: pl.DataFrame
) -> pl.DataFrame:
    """把生命周期/日历外的日线分类到异常词汇表（逐行明细）."""
    if outside.height == 0:
        return pl.DataFrame(schema=_DETAIL_SCHEMA)

    matched = outside.join(
        usable.select("instrument_id", "list_date", "delist_date"),
        on="instrument_id",
        how="inner",
    )
    lifecycle_kind = (
        pl.when(pl.col("trade_date") < pl.col("list_date"))
        .then(pl.lit("bar_before_list_date"))
        .when(
            pl.col("delist_date").is_not_null()
            & (pl.col("trade_date") > pl.col("delist_date"))
        )
        .then(pl.lit("bar_after_delist_date"))
        .otherwise(pl.lit("bar_on_non_trading_day"))
        .alias("kind")
    )
    rows = [matched.select("instrument_id", "trade_date", lifecycle_kind)]

    unmatched = outside.join(
        usable.select("instrument_id"), on="instrument_id", how="anti"
    )
    if unmatched.height:
        known_excluded = unmatched.join(
            excluded.select("instrument_id"), on="instrument_id", how="semi"
        )
        not_in_master = unmatched.join(
            excluded.select("instrument_id"), on="instrument_id", how="anti"
        )
        for frame, kind in (
            (known_excluded, "bar_master_list_date_missing"),
            (not_in_master, "bar_security_not_in_master"),
        ):
            if frame.height:
                rows.append(
                    frame.select(
                        "instrument_id",
                        "trade_date",
                        pl.lit(kind, dtype=pl.String).alias("kind"),
                    )
                )
    return pl.concat(rows).sort(["instrument_id", "trade_date"])
