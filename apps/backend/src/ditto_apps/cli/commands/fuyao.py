"""fuyao 冗余源命令 — 全市场 dump 不可变快照回填."""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import polars as pl
import typer
from dishka import Container
from ditto_application.processes.ingestion.date_range import list_ingestion_dates

from ditto_apps.registry.container import make_app_container
from ditto_apps.registry.infra.protocol_adapters import (
    FuyaoDailyKDumpFetcher,
    FuyaoSource,
    IngestionResult,
    InstrumentService,
    MarketService,
    MetadataService,
    SourceFetchError,
    latest_fuyao_dump,
)

app = typer.Typer(help="fuyao 冗余源: 对账与降级")

# dry-run 重叠冲突比较字段（价格/量额 + 可用性口径；与写入侧
# VERIFY_IDENTICAL 全行校验相比为 advisory 报告，写入门仍是权威）
_OVERLAP_COMPARE_FIELDS = (
    "open",
    "high",
    "low",
    "close",
    "pre_close",
    "volume",
    "amount",
    "pct_change",
    "knowledge_date",
)


def _fuyao_source(container: Container) -> FuyaoSource:
    """从容器解析 FuyaoSource, 未配置时退出."""
    source = container.get(FuyaoSource | None)
    if source is None:
        typer.secho(
            "fuyao 未配置: 在 DITTO_CONFIG_ROOT 的 data_source 配置中设置 "
            "FUYAO_API_KEY (经 DataSourceSettings.fuyao_api_key 注入), "
            "源未创建",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(1)
    return source


def _dump_dest(data_root: Path, kind: str) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%d")
    return Path(data_root) / "fuyao" / "dumps" / kind / f"{stamp}.parquet"


def _verify_dump(frame: pl.DataFrame, kind: str) -> None:
    """打印快照统计并校验主键唯一性(复现官方解读脚本的检查)."""
    rows = len(frame)
    typer.echo(f"rows={rows}")
    if kind == "daily-k":
        key = ["thscode", "date_ms"]
        typer.echo(f"tickers={frame['thscode'].n_unique()}")
        dates = (
            frame["date_ms"]
            .map_elements(
                lambda ms: datetime.fromtimestamp(ms / 1000).date(),
                return_dtype=pl.Date,
            )
            .min(),
            frame["date_ms"]
            .map_elements(
                lambda ms: datetime.fromtimestamp(ms / 1000).date(),
                return_dtype=pl.Date,
            )
            .max(),
        )
        typer.echo(f"date_range={dates[0]}..{dates[1]}")
    else:
        key = ["thscode", "ex_date_ms"]
        typer.echo(f"tickers={frame['thscode'].n_unique()}")
    # 不可变快照保留上游原样, 重复键只告警(消费端按主键去重)
    dup = frame.height - frame.unique(subset=key).height
    if dup:
        typer.secho(f"上游主键重复 {dup} 行(快照原样保留)", fg=typer.colors.YELLOW)
    else:
        typer.secho("主键唯一性校验通过", fg=typer.colors.GREEN)


def _run_dump(kind: str, description: str) -> None:
    container: Container = make_app_container()
    try:
        source = _fuyao_source(container)
        data_root = container.get(Path)
        dest = _dump_dest(data_root, kind)
        typer.echo(f"下载 {description} → {dest}")
        source.download_market_dump(kind, dest)
        _verify_dump(pl.read_parquet(dest), kind)
        typer.secho(f"完成: {dest}", fg=typer.colors.GREEN)
    finally:
        container.close()


@app.command("dump-daily-k")
def dump_daily_k() -> None:
    """下载全市场 10 年日 K(原始价 adjust=none)Parquet 不可变快照."""
    _run_dump("daily-k", "10 年全量日 K")


@app.command("dump-adjustment-factors")
def dump_adjustment_factors() -> None:
    """下载全市场复权因子事件流(分红/送转/配股)Parquet 不可变快照."""
    _run_dump("adjustment-factors", "复权因子事件流")


def _overlap_report(
    dump_frame: pl.DataFrame,
    existing: pl.DataFrame,
    resolver: InstrumentService,
) -> tuple[int, int, int, list[str]]:
    """
    主源重叠分析：返回 (未解析标的数, 重叠行数, 冲突行数, 冲突样本).

    身份只读反解（与对账同规则）；冲突 = 任一比较字段不等（null 感知，
    数值统一 Float64）。除权日 pre_close 口径差异（原始前收 vs 除权参考价）
    会如实计入冲突，由人工决定选源。
    """
    thscodes = dump_frame["source_ticker"].unique().to_list()
    resolved = resolver.resolve_fuyao_instrument_ids(thscodes, register_missing=False)
    unresolved = len(set(thscodes)) - len(resolved)
    if existing.is_empty() or not resolved:
        return unresolved, 0, 0, []
    mapping = pl.DataFrame(
        {
            "source_ticker": list(resolved),
            "instrument_id": list(resolved.values()),
        },
        schema={"source_ticker": pl.String, "instrument_id": pl.Int64},
    )
    numeric = [f for f in _OVERLAP_COMPARE_FIELDS if f != "knowledge_date"]
    incoming = (
        dump_frame.join(mapping, on="source_ticker", how="inner")
        .select("instrument_id", "trade_date", *_OVERLAP_COMPARE_FIELDS)
        .with_columns(pl.col(numeric).cast(pl.Float64))
    )
    stored = existing.select("instrument_id", "trade_date", *_OVERLAP_COMPARE_FIELDS)
    if stored["trade_date"].dtype == pl.String:
        stored = stored.with_columns(pl.col("trade_date").str.to_date())
    stored = stored.with_columns(pl.col(numeric).cast(pl.Float64))
    joined = incoming.join(stored, on=["instrument_id", "trade_date"], how="inner")
    equal = pl.all_horizontal(
        [pl.col(f).eq_missing(pl.col(f"{f}_right")) for f in _OVERLAP_COMPARE_FIELDS]
    )
    conflicts = joined.filter(~equal)
    samples: list[str] = []
    for row in conflicts.head(10).to_dicts():
        differing = [
            f
            for f in _OVERLAP_COMPARE_FIELDS
            if not (
                row.get(f) == row.get(f"{f}_right")
                or (row.get(f) is None and row.get(f"{f}_right") is None)
            )
        ]
        samples.append(
            f"instrument_id={row['instrument_id']} {row['trade_date']} "
            f"差异字段={','.join(differing)}"
        )
    return unresolved, joined.height, conflicts.height, samples


def _effective_window(
    coverage: tuple[date, date],
    start_date: date,
    end_date: date,
) -> tuple[date, date] | None:
    """请求区间与 dump 覆盖取交（不要求末根等于请求 end）；无交集返回 None."""
    effective_start = max(start_date, coverage[0])
    effective_end = min(end_date, coverage[1])
    if effective_start > effective_end:
        return None
    return effective_start, effective_end


def _print_backfill_plan(
    fetcher: FuyaoDailyKDumpFetcher,
    effective_start: date,
    effective_end: date,
    metadata_service: MetadataService,
    market: MarketService,
) -> None:
    """打印 dry-run 计划：交易日、行数、身份与主源重叠冲突。"""
    trading_days = list_ingestion_dates(
        "stock_daily",
        effective_start.isoformat(),
        effective_end.isoformat(),
        metadata_service=metadata_service,
    )
    typer.echo(f"有效交易日: {len(trading_days)}")
    window = fetcher.frame.filter(
        (pl.col("trade_date") >= effective_start)
        & (pl.col("trade_date") <= effective_end)
    )
    typer.echo(f"dump 行数(区间内): {window.height}")
    unresolved, overlap, conflicts, samples = _overlap_report(
        window,
        market.get_stock_bars(effective_start.isoformat(), effective_end.isoformat()),
        metadata_service.instrument,
    )
    identical = overlap - conflicts
    typer.echo(f"身份未解析标的: {unresolved}(执行时由摄取链路按证据登记)")
    typer.echo(f"主源重叠行: {overlap}(完全一致 {identical} / 冲突 {conflicts})")
    if conflicts:
        typer.secho(
            "重叠冲突样本(除权日 pre_close 口径差异属预期, 人工决定选源):",
            fg=typer.colors.YELLOW,
        )
        for sample in samples:
            typer.echo(f"  {sample}")


def _print_backfill_results(results: list[IngestionResult]) -> None:
    """逐失败日打印（半写不报完整）并汇总; 存在失败时退出码非零。"""
    counts = {"success": 0, "failed": 0, "skipped": 0}
    rows_written = 0
    for result in results:
        counts[result.status] = counts.get(result.status, 0) + 1
        rows_written += result.row_count or 0
        if result.status == "failed":
            typer.secho(
                f"  失败 {result.trade_date}: {result.error or result.message}",
                fg=typer.colors.RED,
            )
    typer.echo(
        f"回填完成: 成功 {counts['success']} / 跳过 {counts['skipped']} / "
        f"失败 {counts['failed']}, 写入行数 {rows_written}"
    )
    typer.echo(
        "证据: 每成功日独立 ProviderSnapshot(source=fuyao), 观察时间为真实回填时刻"
    )
    if counts["failed"]:
        typer.secho(
            "存在失败交易日, 回填不完整; 修复后可重跑(幂等)", fg=typer.colors.RED
        )
        raise typer.Exit(1)


@app.command("backfill-daily-k")
def backfill_daily_k(
    start: str = typer.Option(..., "--start", "-s", help="回填起始日 YYYY-MM-DD"),
    end: str = typer.Option(..., "--end", "-e", help="回填结束日 YYYY-MM-DD"),
    dump: Path | None = typer.Option(
        None,
        "--dump",
        help="daily-k dump 路径(默认取 data_root/fuyao/dumps/daily-k/ 最新)",
    ),
    execute: bool = typer.Option(
        False, "--execute", help="执行回填写入(默认 dry-run 仅报告不写入)"
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="重叠差异行按 KEEP_LAST 覆盖主源(默认 VERIFY_IDENTICAL 拒绝差异)",
    ),
) -> None:
    """daily-k dump 手动回填(#439): dry-run 展示主源重叠冲突, 执行走正常摄取链路."""
    from ditto_apps.registry.contexts.ingestion import (  # noqa: PLC0415
        create_ingestion_bundle,
    )

    try:
        start_date = date.fromisoformat(start)
        end_date = date.fromisoformat(end)
    except ValueError as error:
        raise typer.BadParameter(
            "日期格式应为 YYYY-MM-DD", param_hint="--start/--end"
        ) from error
    if start_date > end_date:
        raise typer.BadParameter("start 不能晚于 end", param_hint="--start/--end")

    container: Container = make_app_container()
    try:
        dump_path = dump or latest_fuyao_dump(container.get(Path), "daily-k")
        if dump_path is None:
            typer.secho(
                "未找到 daily-k dump: 先运行 ditto fuyao dump-daily-k",
                fg=typer.colors.RED,
                err=True,
            )
            raise typer.Exit(1)
        typer.echo(f"daily-k dump: {dump_path}")
        try:
            fetcher = FuyaoDailyKDumpFetcher(dump_path)
        except SourceFetchError as error:
            typer.secho(f"dump 契约校验失败: {error}", fg=typer.colors.RED, err=True)
            raise typer.Exit(1) from error

        coverage = fetcher.coverage
        if coverage is None:
            typer.secho("dump 无数据行", fg=typer.colors.RED, err=True)
            raise typer.Exit(1)
        typer.echo(f"dump 覆盖: {coverage[0]}..{coverage[1]}")
        window = _effective_window(coverage, start_date, end_date)
        if window is None:
            typer.secho(
                f"请求区间 {start_date}..{end_date} 与 dump 覆盖无交集",
                fg=typer.colors.RED,
                err=True,
            )
            raise typer.Exit(1)
        effective_start, effective_end = window
        if (effective_start, effective_end) != (start_date, end_date):
            typer.secho(
                f"区间收敛为 dump 覆盖内: {effective_start}..{effective_end}",
                fg=typer.colors.YELLOW,
            )
        _print_backfill_plan(
            fetcher,
            effective_start,
            effective_end,
            container.get(MetadataService),
            container.get(MarketService),
        )
    finally:
        container.close()

    if not execute:
        typer.secho(
            "dry-run 完成, 未写入任何数据; 确认后加 --execute 执行回填",
            fg=typer.colors.GREEN,
        )
        return

    with create_ingestion_bundle("fuyao", market_fetcher_override=fetcher) as bundle:
        results = bundle.coordinator.ingest_range(
            "stock_daily",
            effective_start.isoformat(),
            effective_end.isoformat(),
            force=force,
        )
    _print_backfill_results(results)
