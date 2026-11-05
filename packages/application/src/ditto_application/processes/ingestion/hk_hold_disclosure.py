"""
hk_hold 季度制度段的官方披露发布日（#693）.

HKEX 2024-04-12 公告（https://www.hkex.com.hk/News/Market-Communications/
2024/2404122news?sc_lang=en）：北向持股自 2024-08-19 起改为季度披露，
「前一季度数据在季末后第 5 个北向交易日公布」。下表把该规则落到每个
季度末的**官方发布日**（= 季末后第 5 个北向交易日），来源：

- 2025/2026：HKEX 官方 Stock Connect 交易日历 CSV（Northbound Trading
  列），原件留档 docs/evidence/hkex-stock-connect-calendar/，抓取日
  2026-11-05；
- 2024-09-30 季：2024 无 Stock Connect 日历 CSV，由 SSE trade_cal
  （库内 tushare 官方日历）扣 2024 年四季度 HKEX 休市日推导——该窗口
  内与 SSE 重叠的 HKEX 额外休市仅 10-11（重阳）；12-25/26 两地同休。

已知保守边界：tushare 侧可能早于官方发布日供数（2026Q3 于 2026-10-06
实拉成功，官方发布日 2026-10-14）——kd 取官方日只会晚标、不会早标，
PIT 安全方向；差异留档 #693。
"""

from __future__ import annotations

from datetime import date

from ditto_platform.foundation import logger

__all__ = [
    "DISCLOSURE_CALENDAR_HORIZON",
    "HK_HOLD_PUBLICATION_DATES",
    "hk_hold_quarterly_knowledge_date",
]

# 季末 → 官方发布日（5th 北向交易日）。HKEX 每年秋季发布次年 Stock
# Connect 日历后在此追加（2027-01 的 2026Q4 披露在该日历发布前落地时，
# 走 run_date fail-safe）。
HK_HOLD_PUBLICATION_DATES: frozenset[tuple[date, date]] = frozenset(
    {
        (date(2024, 9, 30), date(2024, 10, 15)),
        (date(2024, 12, 31), date(2025, 1, 8)),
        (date(2025, 3, 31), date(2025, 4, 8)),
        (date(2025, 6, 30), date(2025, 7, 8)),
        (date(2025, 9, 30), date(2025, 10, 15)),
        (date(2025, 12, 31), date(2026, 1, 9)),
        (date(2026, 3, 31), date(2026, 4, 10)),
        (date(2026, 6, 30), date(2026, 7, 8)),
        (date(2026, 9, 30), date(2026, 10, 14)),
    }
)

# 官方日历可锚定的最后一个季末（其发布日落在本日历覆盖内）。晚于它的
# 季度（如 2026-12-31 季发布于 2027-01）在 2027 日历入库前走 run_date
# fail-safe 并触发 horizon 警告。
DISCLOSURE_CALENDAR_HORIZON = date(2026, 9, 30)

_BY_QUARTER = dict(HK_HOLD_PUBLICATION_DATES)


def hk_hold_quarterly_knowledge_date(
    trade_date: date,
    *,
    run_date: date,
) -> date:
    """
    季度段 knowledge_date：官方发布日；表外 fail-safe run_date.

    返回值与 run_date 无关的确定区间内（表内季度）跨日重放恒等——
    根治 SNAPSHOT_CANONICAL_DRIFT（#658 批次1 correctness F1）。表外
    （未来季或日历未更新）维持 run_date 下界并响亮提示。
    """
    published = _BY_QUARTER.get(trade_date)
    if published is not None:
        return published
    if trade_date > DISCLOSURE_CALENDAR_HORIZON:
        logger.warning(
            "disclosure calendar horizon exceeded; run_date fallback in effect",
            event="hk_hold_disclosure_calendar_horizon",
            trade_date=trade_date.isoformat(),
            horizon=DISCLOSURE_CALENDAR_HORIZON.isoformat(),
        )
    return run_date
