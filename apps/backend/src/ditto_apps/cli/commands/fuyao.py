"""fuyao 冗余源命令 — 全市场 dump 不可变快照回填."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import polars as pl
import typer
from dishka import Container

from ditto_apps.registry.container import make_app_container
from ditto_apps.registry.infra.protocol_adapters import FuyaoSource

app = typer.Typer(help="fuyao 冗余源: 对账与降级")


def _fuyao_source(container: Container) -> FuyaoSource:
    """从容器解析 FuyaoSource, 未配置时退出."""
    source = container.get(FuyaoSource | None)
    if source is None:
        typer.secho(
            "fuyao 未配置(FUYAO_API_KEY 缺失), 源未创建",
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
