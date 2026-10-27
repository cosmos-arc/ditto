"""
fuyao 全市场 dump 下载编排（CLI 手动入口与例行任务的单一权威）.

dump 目标定位（北京日命名）与下载/统计校验原散在 CLI（#438/#439）；例行
adj_factor 对账（#515 A3）需要每日刷新 adjustment-factors dump（陈旧守卫
要求 dump 日期 ≥ 目标交易日，#617），故将「解析源 → 定位目标 → 下载 →
统计」提为共享编排，CLI 与 Prefect 前置任务消费同一实现。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, cast
from zoneinfo import ZoneInfo

import polars as pl
from dishka import Container

from ditto_apps.registry.container import make_app_container
from ditto_apps.registry.infra.protocol_adapters import DumpKind, FuyaoSource

# 各 dump 主键列（统计校验共用；不可变快照对重复键只统计不拒绝）
_DUMP_KEYS: dict[DumpKind, tuple[str, ...]] = {
    "daily-k": ("thscode", "date_ms"),
    "daily-k-10d": ("thscode", "date_ms"),
    "adjustment-factors": ("thscode", "ex_date_ms"),
}


class FuyaoSourceUnconfiguredError(RuntimeError):
    """fuyao 源未配置（FUYAO_API_KEY 缺失）：显式失败，调用方各自决定降级形态."""


@dataclass(frozen=True)
class FuyaoDumpDownload:
    """一次成功下载的落盘路径与快照统计."""

    kind: DumpKind
    path: Path
    rows: int
    tickers: int
    duplicate_keys: int
    date_range: tuple[date, date] | None


def dump_dest(data_root: Path, kind: DumpKind) -> Path:
    """
    Dump 落盘目标：data_root/fuyao/dumps/<kind>/YYYYMMDD.parquet.

    北京日期命名：陈旧守卫（protocol_adapters）与交易日语义同用北京日界；
    早前 UTC 命名会让北京 00:00-07:59 生成的当日 dump 被误判为陈旧
    （#515 correctness F4）。字典序 = 时间序不变。
    """
    stamp = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y%m%d")
    return Path(data_root) / "fuyao" / "dumps" / kind / f"{stamp}.parquet"


def _dump_stats(frame: pl.DataFrame, kind: DumpKind, path: Path) -> FuyaoDumpDownload:
    """快照统计：行数/标的数/主键重复数；daily-k 附日期覆盖（advisory）."""
    key = list(_DUMP_KEYS[kind])
    date_range: tuple[date, date] | None = None
    if kind in ("daily-k", "daily-k-10d"):
        # date_ms 是北京零点毫秒戳（client.date_to_ms）：显式走 UTC→北京时区
        # 链取日期，不依赖进程本地时区；空帧/null 无覆盖（None）
        day_values = [
            day
            for day in frame.select(
                pl.from_epoch(pl.col("date_ms"), time_unit="ms")
                .dt.replace_time_zone("UTC")
                .dt.convert_time_zone("Asia/Shanghai")
                .dt.date()
                .alias("d")
            )["d"].to_list()
            if day is not None
        ]
        if day_values:
            date_range = (min(day_values), max(day_values))
    return FuyaoDumpDownload(
        kind=kind,
        path=path,
        rows=frame.height,
        tickers=frame["thscode"].n_unique(),
        duplicate_keys=frame.height - frame.unique(subset=key).height,
        date_range=date_range,
    )


def _resolve_fuyao_source(container: Container) -> FuyaoSource:
    """从容器解析 FuyaoSource，未配置时显式失败（不再静默跳过）."""
    # dishka 运行时支持 Optional 提供键（ditto_data.di.sources fuyao_source 的
    # 返回类型即键），但 get() 注解只声明 type[_T]，联合键需显式放宽；外层
    # cast 恢复静态类型。
    source = cast(
        "FuyaoSource | None",
        container.get(cast(Any, FuyaoSource | None)),
    )
    if source is None:
        raise FuyaoSourceUnconfiguredError(
            "fuyao 未配置: 在 DITTO_CONFIG_ROOT 的 data_source 配置中设置 "
            + "FUYAO_API_KEY (经 DataSourceSettings.fuyao_api_key 注入), "
            + "源未创建"
        )
    return source


def download_fuyao_dump(kind: DumpKind) -> FuyaoDumpDownload:
    """
    下载全市场 dump 不可变快照并返回统计；源未配置抛 FuyaoSourceUnconfiguredError.

    坏帧（不可读/空快照）当场清理并抛错——空 dump 过滤任何目标日同样得
    零事件，会在对账层被误读为「无除权事件的正常日」（correctness F2）；
    清掉当日名让 latest 回到上一份，陈旧守卫会响亮拒绝而非静默误判。
    """
    container = make_app_container()
    try:
        source = _resolve_fuyao_source(container)
        data_root = container.get(Path)
        dest = dump_dest(data_root, kind)
        source.download_market_dump(kind, dest)
        try:
            frame = pl.read_parquet(dest)
        except Exception:
            dest.unlink(missing_ok=True)
            raise
        outcome = _dump_stats(frame, kind, dest)
        if outcome.rows == 0 or outcome.tickers == 0:
            dest.unlink(missing_ok=True)
            raise ValueError(
                f"fuyao dump {kind} snapshot is empty "
                + f"(rows={outcome.rows}, tickers={outcome.tickers}): rejected"
            )
        return outcome
    finally:
        container.close()
