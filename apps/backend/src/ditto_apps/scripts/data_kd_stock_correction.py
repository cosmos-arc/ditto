"""
#658 批次2 存量 knowledge_date 有界纠正（两融/北向三数据集）.

B1（#653 修正安全链）把 margin_trading/hsgt_top10/hk_hold 的可知时间策略
改为「下一交易日／hk_hold 分段」并只对未来摄取生效；本脚本对已落库的
错误存量执行同款策略的有界纠正：

- **margin_trading / hsgt_top10 / hk_hold 日频段**：knowledge_date 旧值=
  自然日 T+1（映射层历史错误），新值= trade_date 后的下一个 A 股交易日
  （与写入路径 ``calibrate_knowledge_dates`` 同一权威实现，不另立规则）。
- **hk_hold 季度段**（trade_date >= 2024-08-19）：真实发布日=季末后第 5 个
  北向交易日，北向日历尚未入库；以 provider_snapshots 账本观察时间
  （覆盖该日且 row_count>0 的最新快照 created_at）为保守锚——不早于
  本机实际看到该数据的时间，无 PIT 泄漏；北向日历入库后按制度重算
  归后续批次。

纠正语义（#653「正确性修正与存量保护」）：

- 新版本行经标准写入端口按冲突键落库（新 effective_from/knowledge_date
  = 新身份），旧行原样保留——本地快照重放语义保留「当时机器所见」，
  普通/PIT 读取先排除撤销资格，再选择有效版本；原 payload／快照证据不动。
- 每个被纠正的 (dataset, trade_date) 在 ingestion_log 记一行
  source='kd_correction' 的 SUCCESS 账本行（rows=新版本行数），作为
  机读纠正记录；与 tushare 源行互不干扰（账本主键含 source）。
- 幂等：重复执行冲突键忽略、账本行 upsert。

用法（证据见 docs/data/stock-remediation-2026-11.md）::

    python -m ditto_apps.scripts.data_kd_stock_correction scan \
        --data-root <DITTO_DATA_ROOT> [--dataset margin_trading] [--output r.json]
    python -m ditto_apps.scripts.data_kd_stock_correction apply \
        --data-root <DITTO_DATA_ROOT> --dataset <ds>[,<ds>...] --confirm

apply 须在已核对目标的停写窗口内执行。先生成影响清单；#705 已明确暂缓
备份与完整恢复，不将其扩大成本批前提。
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from typing import Any, Protocol
from zoneinfo import ZoneInfo

import orjson
import polars as pl
from ditto_application.processes.ingestion.correction_ledger import (
    CORRECTION_LEDGER_SOURCE,
    CorrectionLogStore,
    publish_capital_correction,
    save_kd_correction_ledger_row,
)
from ditto_application.processes.ingestion.hk_hold_disclosure import (
    HK_HOLD_PUBLICATION_DATES,
)
from ditto_application.processes.ingestion.knowledge_date_policy import (
    HK_HOLD_QUARTERLY_REGIME_START,
    calibrate_knowledge_dates,
)
from ditto_platform.foundation.storage.types import OnDuplicate

from ditto_apps.registry.container import make_app_container
from ditto_apps.registry.contexts.ingestion import (
    CapitalStore,
    IngestionLogStore,
)

__all__ = [
    "CORRECTION_LEDGER_SOURCE",
    "KD_DATASETS",
    "apply_dataset",
    "main",
    "scan_dataset",
]

KD_DATASETS = ("margin_trading", "hsgt_top10", "hk_hold")
_SCHEMA = "ditto.data-kd-stock-correction.v1"
_SHANGHAI = ZoneInfo("Asia/Shanghai")

# margin_trading 表列（= MARGIN_TRADING_SPEC.all_columns；写入端口要求全列）。
_MARGIN_COLUMNS = (
    "instrument_id",
    "trade_date",
    "knowledge_date",
    "effective_from",
    "effective_to",
    "margin_buy_balance",
    "short_sell_balance",
    "margin_buy_amount",
    "short_sell_volume",
)
_MARGIN_SCHEMA: dict[str, Any] = {
    "instrument_id": pl.Int64,
    "trade_date": pl.String,
    "knowledge_date": pl.String,
    "effective_from": pl.String,
    "effective_to": pl.String,
    "margin_buy_balance": pl.Float64,
    "short_sell_balance": pl.Float64,
    "margin_buy_amount": pl.Float64,
    "short_sell_volume": pl.Float64,
}


class _CapitalWriterPort(Protocol):
    """纠正所需的最小资金面写入端口（CapitalStore 结构满足）."""

    def save_margin_trading(
        self, df: pl.DataFrame, on_duplicate: OnDuplicate = ...
    ) -> int: ...

    def save_hk_hold(
        self, df: pl.DataFrame, year: int, on_duplicate: OnDuplicate = ...
    ) -> int: ...

    def save_hsgt_top10(
        self, df: pl.DataFrame, year: int, on_duplicate: OnDuplicate = ...
    ) -> int: ...


@dataclass(frozen=True)
class DateImpact:
    """单个 (dataset, trade_date, 旧版本) 的纠正计划."""

    dataset: str
    trade_date: str
    rows: int
    old_knowledge_date: str
    new_knowledge_date: str
    anchor: str  # next_trading_day | observation_snapshot
    status: str  # correct（待写新版本） | unanchorable（无观察证据，拒绝动）


def scan_dataset(
    dataset: str,
    *,
    conn: sqlite3.Connection,
    data_root: Path,
) -> list[DateImpact]:
    """只读盘点：该数据集内 knowledge_date 偏离冻结策略的日期与行数."""
    if dataset not in KD_DATASETS:
        raise ValueError(f"unsupported dataset for kd correction: {dataset}")
    open_days = _open_days(conn)
    if dataset == "margin_trading":
        rows = conn.execute(
            "SELECT trade_date, knowledge_date, COUNT(*) FROM margin_trading "  # noqa: S608
            + "GROUP BY trade_date, knowledge_date"
        ).fetchall()
        groups = [(str(r[0]), str(r[1]), int(r[2])) for r in rows]
        expectations = _next_trading_day_expectations(
            [g[0] for g in groups], dataset=dataset, open_days=open_days
        )
        return _impacts_from_groups(
            dataset, groups, expectations, anchor="next_trading_day"
        )

    frames = []
    for f in sorted((data_root / "capital" / dataset).glob("*.parquet")):
        df = pl.read_parquet(f, columns=["trade_date", "knowledge_date"])
        frames.append(df.group_by(["trade_date", "knowledge_date"]).len(name="rows"))
    if not frames:
        return []
    groups_frame = (
        pl.concat(frames)
        .group_by(["trade_date", "knowledge_date"])
        .agg(pl.col("rows").sum())
    )
    groups = [
        (t.isoformat(), k.isoformat(), int(c))
        for t, k, c in zip(
            groups_frame["trade_date"].to_list(),
            groups_frame["knowledge_date"].to_list(),
            groups_frame["rows"].to_list(),
            strict=True,
        )
    ]

    daily_groups = [
        g
        for g in groups
        if dataset == "hsgt_top10"
        or date.fromisoformat(g[0]) < HK_HOLD_QUARTERLY_REGIME_START
    ]
    quarterly_groups = [g for g in groups if g not in daily_groups]

    impacts = []
    if daily_groups:
        expectations = _next_trading_day_expectations(
            [g[0] for g in daily_groups], dataset=dataset, open_days=open_days
        )
        impacts.extend(
            _impacts_from_groups(
                dataset, daily_groups, expectations, anchor="next_trading_day"
            )
        )
    impacts.extend(_quarterly_impacts(dataset, quarterly_groups, conn=conn))
    impacts.sort(key=lambda i: (i.trade_date, i.old_knowledge_date))
    return impacts


def _official_anchor_impacts(
    dataset: str,
    trade_date: str,
    versions: dict[str, int],
    official: date,
) -> list[DateImpact]:
    """官方发布日锚；即使正确行已存在，也撤销仍留在原投影的旧资格。"""
    expected = official.isoformat()
    wrong = {k: c for k, c in versions.items() if k != expected}
    if not wrong:
        return []
    return [
        DateImpact(
            dataset=dataset,
            trade_date=trade_date,
            rows=c,
            old_knowledge_date=k,
            new_knowledge_date=expected,
            anchor="official_disclosure",
            status="correct",
        )
        for k, c in sorted(wrong.items())
    ]


def _quarterly_impacts(
    dataset: str,
    groups: list[tuple[str, str, int]],
    *,
    conn: sqlite3.Connection,
) -> list[DateImpact]:
    """hk_hold 季度段：官方披露发布日优先，表外回退账本观察锚."""
    anchors = _observation_anchors(conn, sorted({g[0] for g in groups}))
    official_by_quarter = dict(HK_HOLD_PUBLICATION_DATES)
    by_date: dict[str, dict[str, int]] = {}
    for t, k, c in groups:
        by_date.setdefault(t, {})[k] = c
    impacts = []
    for t in sorted(by_date):
        versions = by_date[t]
        official = official_by_quarter.get(date.fromisoformat(t))
        if official is not None:
            impacts.extend(_official_anchor_impacts(dataset, t, versions, official))
            continue
        expected = anchors.get(t)
        # 已有观察锚版本（kd 晚于事实日 14 天＝任何披露制度锚之外）则该日
        # 首锚已立：后续新覆盖快照前移 MAX 锚不再重写（首锚胜，可见性不
        # 随重复回补单调后移）。
        anchored = any(
            date.fromisoformat(k) > date.fromisoformat(t) + _ANCHOR_ALREADY_SET_DAYS
            for k in versions
        )
        if anchored:
            continue
        if expected is None or date.fromisoformat(expected) <= date.fromisoformat(t):
            # 无覆盖快照，或锚不晚于事实日（不可作为可知时间）——拒绝动。
            impacts.append(
                DateImpact(
                    dataset=dataset,
                    trade_date=t,
                    rows=sum(versions.values()),
                    old_knowledge_date="|".join(sorted(versions)),
                    new_knowledge_date="?",
                    anchor="observation_snapshot",
                    status="unanchorable",
                )
            )
            continue
        for k, c in sorted(versions.items()):
            if k != expected:
                impacts.append(
                    DateImpact(
                        dataset=dataset,
                        trade_date=t,
                        rows=c,
                        old_knowledge_date=k,
                        new_knowledge_date=expected,
                        anchor="observation_snapshot",
                        status="correct",
                    )
                )
    return impacts


def _impacts_from_groups(
    dataset: str,
    groups: list[tuple[str, str, int]],
    expectations: dict[str, str],
    *,
    anchor: str,
) -> list[DateImpact]:
    """
    下一交易日策略的纠正计划.

    守卫（correctness W4/W5）：
    - 正确版本已存在也保留旧版本的资格撤销计划；重复应用幂等；
    - 同日存在多个旧版本（>1 个非期望 kd 组）→ 值谱系不可分辨，
      status=ambiguous 拒绝写入、响亮报告，人工分流。
    """
    by_date: dict[str, dict[str, int]] = {}
    for t, k, c in groups:
        by_date.setdefault(t, {})[k] = c
    impacts = []
    for t in sorted(by_date):
        expected = expectations.get(t)
        if expected is None:
            continue
        versions = by_date[t]
        wrong = {k: c for k, c in versions.items() if k != expected}
        if not wrong:
            continue
        if len(wrong) > 1:
            impacts.append(
                DateImpact(
                    dataset=dataset,
                    trade_date=t,
                    rows=sum(wrong.values()),
                    old_knowledge_date="|".join(sorted(wrong)),
                    new_knowledge_date=expected,
                    anchor=anchor,
                    status="ambiguous",
                )
            )
            continue
        for k, c in sorted(wrong.items()):
            impacts.append(
                DateImpact(
                    dataset=dataset,
                    trade_date=t,
                    rows=c,
                    old_knowledge_date=k,
                    new_knowledge_date=expected,
                    anchor=anchor,
                    status="correct",
                )
            )
    return impacts


def apply_dataset(
    dataset: str,
    impacts: list[DateImpact],
    *,
    conn: sqlite3.Connection,
    data_root: Path,
    capital_store: _CapitalWriterPort,
    log_store: CorrectionLogStore,
    run_at: datetime,
) -> dict[str, Any]:
    """
    按已确认的纠正计划写新版本行并落账本原因行（幂等）.

    账本原因行**先于**数据写落库（correctness W1）：数据写与账本是两个
    提交，先账本后数据使崩溃后的重跑收敛——账本存在不阻止 scan 重产
    impact（scan 看的是 canonical 版本而非账本），重跑补写数据并 upsert
    账本；反向顺序会让「已写数据、缺账本」的日期被 scan 跳过而永久失账。
    """
    correct = [i for i in impacts if i.status == "correct"]
    if not correct:
        return {"dataset": dataset, "dates_corrected": 0, "rows_written": 0}
    now = run_at.isoformat()
    written = 0
    dates: set[str] = set()
    _publish_eligibility(correct, conn=conn, data_root=data_root)
    _write_ledger_rows(correct, log_store=log_store, now=now)
    if dataset == "margin_trading":
        frame = _margin_corrected_frame(conn, correct)
        if frame.height:
            _assert_knowledge_after_trade(frame, dataset=dataset)
            written = capital_store.save_margin_trading(
                frame, on_duplicate=OnDuplicate.KEEP_FIRST
            )
            dates = set(frame["trade_date"].cast(pl.String).unique().to_list())
    else:
        by_year: dict[int, list[DateImpact]] = {}
        for impact in correct:
            by_year.setdefault(int(impact.trade_date[:4]), []).append(impact)
        for year in sorted(by_year):
            frame = _parquet_corrected_frame(data_root, dataset, year, by_year[year])
            if frame.is_empty():
                continue
            _assert_knowledge_after_trade(frame, dataset=dataset)
            if dataset == "hk_hold":
                written += capital_store.save_hk_hold(
                    frame, year, on_duplicate=OnDuplicate.KEEP_FIRST
                )
            else:
                written += capital_store.save_hsgt_top10(
                    frame, year, on_duplicate=OnDuplicate.KEEP_FIRST
                )
            dates.update(frame["trade_date"].cast(pl.String).unique().to_list())
    return {"dataset": dataset, "dates_corrected": len(dates), "rows_written": written}


def correction_impact_report(
    impacts: list[DateImpact], *, conn: sqlite3.Connection, data_root: Path
) -> dict[str, Any]:
    """一次性盘点事实键、规则、分区及既有来源/纠偏身份，不以快照相同免检。"""
    dataset = impacts[0].dataset
    keys = ["instrument_id", "trade_date", "knowledge_date"]
    if dataset == "hsgt_top10":
        keys.append("market_type")
    facts: list[dict[str, Any]] = []
    # 每个年度只读一次，避免长历史扫描反复加载同一大分区。
    partitions: dict[str, dict[tuple[object, ...], pl.DataFrame]] = {}
    tables = {
        r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    snapshot_columns = {
        r[1] for r in conn.execute("PRAGMA table_info(provider_snapshots)")
    }
    for impact in impacts:
        partition = (
            "metadata/metadata.sqlite#margin_trading"
            if dataset == "margin_trading"
            else f"capital/{dataset}/{impact.trade_date[:4]}.parquet"
        )
        if partition not in partitions:
            frame = (
                pl.read_database(
                    """SELECT instrument_id, trade_date, knowledge_date
                    FROM margin_trading""",
                    conn,
                )
                if dataset == "margin_trading"
                else pl.read_parquet(data_root / partition, columns=keys)
            ).select(pl.col(keys).cast(pl.String))
            partitions[partition] = frame.partition_by(
                ["trade_date", "knowledge_date"], as_dict=True
            )
        selected_frame = partitions[partition].get(
            (impact.trade_date, impact.old_knowledge_date)
        )
        selected = selected_frame.to_dicts() if selected_frame is not None else []
        snapshots = []
        if {
            "snapshot_id",
            "checksum",
            "dataset_id",
            "request_start",
            "request_end",
        } <= snapshot_columns:
            snapshots = [
                dict(zip(["snapshot_id", "checksum"], row, strict=True))
                for row in conn.execute(
                    """SELECT snapshot_id, checksum FROM provider_snapshots
                    WHERE dataset_id=? AND request_start<=? AND request_end>=?
                    ORDER BY snapshot_id""",
                    (dataset, impact.trade_date, impact.trade_date),
                )
            ]
        prior = []
        if "ingestion_log" in tables:
            prior = [
                r[0]
                for r in conn.execute(
                    """SELECT checksum FROM ingestion_log
                    WHERE dataset=? AND source=? AND trade_date=?""",
                    (dataset, CORRECTION_LEDGER_SOURCE, impact.trade_date),
                )
            ]
        facts.append(
            {
                **vars(impact),
                "target_partition": partition,
                "facts": sorted(selected, key=lambda row: tuple(row[k] for k in keys)),
                "source_snapshots": snapshots,
                "prior_kd_correction_checksums": prior,
                "old_eligibility": "revoked",
                "new_eligibility": "canonical_and_pit",
            }
        )
    return {
        "dataset": dataset,
        "rule_version": "capital-kd-v2",
        "keys": keys,
        "impacts": facts,
        "correction_checksum": _impact_checksum(impacts),
        "consumer_rule": "eligible-capital-v2/latest-profile-v2",
        "consumers": (
            ["margin HTTP", "margin CLI", "capital-profile query"]
            if dataset == "margin_trading"
            else [f"{dataset} HTTP"]
        ),
        "artifact_matching": (
            "dataset + business dates/instruments "
            + "+ interpretation/consumer rule; snapshot IDs alone are insufficient"
        ),
    }


def _publish_eligibility(
    impacts: list[DateImpact], *, conn: sqlite3.Connection, data_root: Path
) -> None:
    """在任何数据写入前持久化完整影响与紧凑资格规则。"""
    publish_capital_correction(
        data_root, correction_impact_report(impacts, conn=conn, data_root=data_root)
    )


_ANCHOR_ALREADY_SET_DAYS = timedelta(days=14)


def _write_ledger_rows(
    impacts: list[DateImpact], *, log_store: CorrectionLogStore, now: str
) -> None:
    """逐日落 kd_correction 原因行（模型构造在 application 助手）."""
    by_date: dict[str, list[DateImpact]] = {}
    for impact in impacts:
        by_date.setdefault(impact.trade_date, []).append(impact)
    for trade_date, day_impacts in sorted(by_date.items()):
        save_kd_correction_ledger_row(
            log_store,
            dataset=day_impacts[0].dataset,
            trade_date=trade_date,
            # 同日多旧版本可映射到同一新锚（#693 官方锚）：写入侧按
            # (instrument, trade_date) 去重后≈单版本行数，取 max 为
            # 去重后新键数的稳定近似，避免 ledger 双计。
            rows=max(i.rows for i in day_impacts),
            checksum=_impact_checksum(day_impacts),
            recorded_at=now,
        )


def _open_days(conn: sqlite3.Connection) -> list[date]:
    rows = conn.execute(
        "SELECT trade_date FROM trading_calendar WHERE is_open = 1 ORDER BY trade_date"
    ).fetchall()
    return [date.fromisoformat(str(r[0])) for r in rows]


def _next_trading_day_expectations(
    trade_dates: list[str], *, dataset: str, open_days: list[date]
) -> dict[str, str]:
    """trade_date(ISO) -> 期望 knowledge_date(ISO)，经 B1 权威策略模块."""
    unique = sorted({date.fromisoformat(t) for t in trade_dates})
    if not unique:
        return {}
    frame = pl.DataFrame(
        {"trade_date": unique, "knowledge_date": unique}  # 占位；策略必然覆写
    )
    calibrated = calibrate_knowledge_dates(
        frame, dataset=dataset, trading_days=tuple(open_days), run_date=date(1970, 1, 1)
    )
    return {
        d.isoformat(): k.isoformat()
        for d, k in zip(
            unique,
            calibrated["knowledge_date"].cast(pl.Date).to_list(),
            strict=True,
        )
    }


def _observation_anchors(
    conn: sqlite3.Connection, trade_dates: list[str]
) -> dict[str, str]:
    """
    hk_hold 季度段锚：覆盖该日且 row_count>0 的最新快照观察日（上海）.

    取 MAX(created_at)（fail-safe 宁晚不早）：本机真实写入时间不晚于最后
    一个覆盖快照，锚定值不会早于本机实际可知时间（无前视）。
    """
    anchors: dict[str, str] = {}
    for trade_date in trade_dates:
        row = conn.execute(
            "SELECT MAX(created_at) FROM provider_snapshots "  # noqa: S608
            + "WHERE dataset_id = 'hk_hold' AND source = 'tushare' "
            + "AND row_count > 0 AND request_start <= ? AND request_end >= ?",
            (trade_date, trade_date),
        ).fetchone()
        if row and row[0]:
            anchors[trade_date] = _shanghai_day(str(row[0]))
    return anchors


def _margin_corrected_frame(
    conn: sqlite3.Connection, impacts: list[DateImpact]
) -> pl.DataFrame:
    """从 SQLite 读旧版本行，按计划替换 knowledge_date/effective_from."""
    new_by_date = {i.trade_date: i.new_knowledge_date for i in impacts}
    frames = []
    for impact in impacts:
        rows = conn.execute(
            f"SELECT {', '.join(_MARGIN_COLUMNS)} FROM margin_trading "  # noqa: S608
            + "WHERE trade_date = ? AND knowledge_date = ?",
            (impact.trade_date, impact.old_knowledge_date),
        ).fetchall()
        frames.append(pl.DataFrame(rows, schema=_MARGIN_SCHEMA, orient="row"))
    if not frames:
        return pl.DataFrame(schema=_MARGIN_SCHEMA)
    df = pl.concat(frames)
    new_knowledge = df["trade_date"].replace_strict(new_by_date)
    return df.with_columns(
        pl.col("trade_date").str.to_date(),
        pl.col("knowledge_date").str.to_date(),
        pl.col("effective_from").str.to_date(),
        pl.col("effective_to").str.to_date(),
    ).with_columns(
        pl.Series(
            "knowledge_date",
            [date.fromisoformat(v) for v in new_knowledge.to_list()],
            dtype=pl.Date,
        ),
        pl.Series(
            "effective_from",
            [date.fromisoformat(v) for v in new_knowledge.to_list()],
            dtype=pl.Date,
        ),
    )


def _parquet_corrected_frame(
    data_root: Path, dataset: str, year: int, impacts: list[DateImpact]
) -> pl.DataFrame:
    """从年度 parquet 读旧版本行，按 (trade_date, 旧kd) 映射替换 knowledge_date."""
    mapping = {
        (i.trade_date, i.old_knowledge_date): i.new_knowledge_date for i in impacts
    }
    f = data_root / "capital" / dataset / f"{year}.parquet"
    df = pl.read_parquet(f)
    if dataset == "hk_hold" and "knowledge_date" in df.columns and df.height > 1:
        # 同键多旧版本映射到同一新锚时（#693），确定性保留最新旧版本的
        # payload——否则下游 PK 去重 keep=first 在无序 sort 后任意胜。
        # 只收窄 hk_hold（键=instrument+trade_date）；hsgt_top10 等带
        # 额外键维度的数据集不适用该塌缩。
        df = df.sort("knowledge_date").unique(
            subset=["instrument_id", "trade_date"], keep="last"
        )
    trade_keys = df["trade_date"].cast(pl.String).to_list()
    knowledge_keys = df["knowledge_date"].cast(pl.String).to_list()
    new_values = [
        mapping.get((t, k)) for t, k in zip(trade_keys, knowledge_keys, strict=True)
    ]
    keep = pl.Series([v is not None for v in new_values])
    new_dates = [date.fromisoformat(v) for v in new_values if v is not None]
    return df.filter(keep).with_columns(
        pl.Series("knowledge_date", new_dates, dtype=pl.Date)
    )


def _shanghai_day(created_at: str) -> str:
    """
    快照 created_at（tz-aware UTC 或裸本地）→ 上海观察日（correctness W3）.

    UTC 字符串直接截日期会把上海 00:00-08:00 的写入锚早一天（反「宁晚
    不早」方向）；裸字符串按上海本地既有约定解释。
    """
    moment = datetime.fromisoformat(created_at)
    if moment.tzinfo is None:
        return moment.date().isoformat()
    return moment.astimezone(_SHANGHAI).date().isoformat()


def _assert_knowledge_after_trade(frame: pl.DataFrame, *, dataset: str) -> None:
    """防御：纠正后的可知时间必须晚于事实日（fail closed，不写前视行）."""
    td = frame["trade_date"].cast(pl.Date)
    kd = frame["knowledge_date"].cast(pl.Date)
    if (kd <= td).any():
        raise ValueError(
            f"{dataset}: corrected knowledge_date not after trade_date — aborting"
        )


def _impact_checksum(impacts: list[DateImpact]) -> str:
    payload = "|".join(
        f"{i.trade_date}:{i.old_knowledge_date}>{i.new_knowledge_date}:{i.rows}"
        for i in sorted(impacts, key=lambda i: i.old_knowledge_date)
    )
    return sha256(payload.encode()).hexdigest()[:16]


def main(argv: list[str] | None = None) -> int:
    """执行 scan/apply 并输出 JSON 报告（退出码非零＝失败）."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command", choices=["scan", "apply"], help="scan=readonly report; apply=write"
    )
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument(
        "--dataset",
        default=",".join(KD_DATASETS),
        help=f"comma separated: {','.join(KD_DATASETS)} (default all)",
    )
    parser.add_argument("--confirm", action="store_true", help="apply 必须显式确认")
    parser.add_argument("--output", type=Path, default=None, help="报告落盘路径")
    args = parser.parse_args(argv)

    datasets = [d.strip() for d in args.dataset.split(",") if d.strip()]
    if not datasets:
        parser.error("--dataset resolved to an empty selection")
    unknown = [d for d in datasets if d not in KD_DATASETS]
    if unknown:
        parser.error(f"unsupported dataset(s): {unknown}")
    if args.command == "apply" and not args.confirm:
        parser.error("apply requires --confirm (bounded write to real data)")

    data_root = args.data_root.absolute()
    scan_conn = sqlite3.connect(
        f"file:{data_root / 'metadata/metadata.sqlite'}?mode=ro", uri=True
    )
    try:
        impacts: list[DateImpact] = []
        reports = []
        for dataset in datasets:
            selected = scan_dataset(dataset, conn=scan_conn, data_root=data_root)
            impacts.extend(selected)
            correct = [item for item in selected if item.status == "correct"]
            if correct:
                reports.append(
                    correction_impact_report(
                        correct, conn=scan_conn, data_root=data_root
                    )
                )
    finally:
        scan_conn.close()

    if args.command == "scan":
        _emit(
            {
                "schema": _SCHEMA,
                "command": "scan",
                "data_root": str(data_root),
                "scanned_at": datetime.now(_SHANGHAI).isoformat(),
                "totals": _totals(impacts),
                "impacts": [vars(i) for i in impacts],
                "impact_reports": reports,
            },
            args.output,
        )
        return 0

    _emit(
        _run_apply(datasets, impacts, data_root=data_root),
        args.output,
    )
    return 0


def _run_apply(
    datasets: list[str],
    impacts: list[DateImpact],
    *,
    data_root: Path,
) -> dict[str, Any]:
    """执行 apply（容器组装+逐数据集写入）并返回报告帧（主流程拆分）."""
    previous_root = os.environ.get("DITTO_STATE_ROOT")
    os.environ["DITTO_STATE_ROOT"] = str(data_root)
    try:
        container = make_app_container()
        try:
            capital_store = container.get(CapitalStore)
            log_store = container.get(IngestionLogStore)
            ledger_conn = sqlite3.connect(data_root / "metadata/metadata.sqlite")
            try:
                results = []
                for dataset in datasets:
                    dataset_impacts = [i for i in impacts if i.dataset == dataset]
                    results.append(
                        apply_dataset(
                            dataset,
                            dataset_impacts,
                            conn=ledger_conn,
                            data_root=data_root,
                            capital_store=capital_store,
                            log_store=log_store,
                            run_at=datetime.now(_SHANGHAI),
                        )
                    )
            finally:
                ledger_conn.close()
        finally:
            container.close()
    finally:
        if previous_root is None:
            os.environ.pop("DITTO_STATE_ROOT", None)
        else:
            os.environ["DITTO_STATE_ROOT"] = previous_root

    return {
        "schema": _SCHEMA,
        "command": "apply",
        "data_root": str(data_root),
        "applied_at": datetime.now(_SHANGHAI).isoformat(),
        "totals": _totals(impacts),
        "results": results,
        "unanchorable": [vars(i) for i in impacts if i.status == "unanchorable"],
        "ambiguous": [vars(i) for i in impacts if i.status == "ambiguous"],
    }


def _totals(impacts: list[DateImpact]) -> dict[str, dict[str, int]]:
    by_dataset: dict[str, dict[str, int]] = {}
    for i in impacts:
        if i.status != "correct":
            continue
        bucket = by_dataset.setdefault(i.dataset, {"dates": 0, "rows": 0})
        bucket["dates"] += 1
        bucket["rows"] += i.rows
    return by_dataset


def _emit(report: dict[str, Any], output: Path | None) -> None:
    text = orjson.dumps(report, option=orjson.OPT_INDENT_2)
    if output is not None:
        output.write_bytes(text)
    sys.stdout.write(text.decode() + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
