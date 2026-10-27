"""
例行 fuyao adjustment-factors dump 刷新任务（adj_factor 对账前置，#617）.

对账辅源 FuyaoAdjustmentEventsSource 消费当日 dump（陈旧守卫要求 dump 日期
≥ 目标交易日）；本任务在 daily flow 与 T0 并行下载，失败/未配置以 status
字段显式报告、不拖垮摄取链——对账按既有语义降级留痕（#515 A3），次日例行
自然重试。
"""

from __future__ import annotations

from ditto_platform.foundation import logger
from prefect import task

from ditto_apps.registry.fuyao_dump import (
    FuyaoSourceUnconfiguredError,
    download_fuyao_dump,
)

_DUMP_KIND = "adjustment-factors"


def _result(
    *,
    status: str = "success",
    path: str | None = None,
    rows: int | None = None,
    tickers: int | None = None,
    duplicate_keys: int | None = None,
    error: str | None = None,
) -> dict[str, object]:
    """固定键形状的结果构造（三种结局键集合一致）."""
    return {
        "kind": _DUMP_KIND,
        "status": status,
        "path": path,
        "rows": rows,
        "tickers": tickers,
        "duplicate_keys": duplicate_keys,
        "error": error,
    }


def run_fuyao_adjustment_factors_dump() -> dict[str, object]:
    """下载当日 adjustment-factors dump；失败以 status 字段显式返回，不抛出."""
    try:
        outcome = download_fuyao_dump(_DUMP_KIND)
    except FuyaoSourceUnconfiguredError as error:
        # 辅源可选（#515 A3 语义）：未配置=对账不可用，非例行链失败
        logger.warning(
            "fuyao dump skipped: source unconfigured",
            event="fuyao_dump_skipped",
            kind=_DUMP_KIND,
            reason="fuyao_unconfigured",
        )
        return _result(status="skipped", error=str(error))
    except Exception as error:
        logger.exception(
            "fuyao dump refresh failed",
            event="fuyao_dump_failed",
            kind=_DUMP_KIND,
            error_type=type(error).__name__,
        )
        return _result(
            status="failed",
            error=f"{type(error).__name__}: {error!s}",
        )
    logger.info(
        "fuyao dump refreshed",
        event="fuyao_dump_complete",
        kind=_DUMP_KIND,
        path=str(outcome.path),
        rows=outcome.rows,
        tickers=outcome.tickers,
        duplicate_keys=outcome.duplicate_keys,
    )
    return _result(
        path=str(outcome.path),
        rows=outcome.rows,
        tickers=outcome.tickers,
        duplicate_keys=outcome.duplicate_keys,
    )


@task(
    name="fuyao-dump-adjustment-factors",
    description="例行 fuyao 复权因子事件 dump 刷新(adj_factor 跨源对账前置)",
    tags=["fuyao", "dump"],
)
async def fuyao_dump_adjustment_factors() -> dict[str, object]:
    """Prefect wrapper for :func:`run_fuyao_adjustment_factors_dump`."""
    return run_fuyao_adjustment_factors_dump()
