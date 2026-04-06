"""
策略运行共享类型 — Process 模块.

包含所有策略相关的协议、DTO、枚举、配置以及与具体服务无关的工具类。
BacktestService 与 StrategyRunService 共用此模块中的类型定义。
"""

from __future__ import annotations

import dataclasses
import tempfile
from dataclasses import replace
from pathlib import Path
from typing import Protocol, runtime_checkable

import orjson
import polars as pl
from ditto_data.services.metadata_service import MetadataService
from ditto_engine.alpha.pipeline import StrategyInputBundle
from ditto_engine.backtest.data_feed import Slice
from ditto_engine.backtest.manifest import RunManifest, serialize_manifest
from ditto_engine.backtest.statistics import (
    BacktestReport,
    PreTradeDecisionRecord,
    RiskScanRecord,
)
from ditto_infra.foundation.util.io import atomic_bytes_write, atomic_write
from ditto_kernel.identity import InstrumentId

from ditto_app.process.backtest_serialization import serialize_report

__all__ = [
    "RunLifecycleService",
    "StrategyInputAssembler",
    "build_display_map",
    "enrich_record_with_symbol",
    "write_backtest_artifacts",
]


# ===========================================================================
# RunLifecycleService — 策略运行生命周期协议
# ===========================================================================


@runtime_checkable
class RunLifecycleService(Protocol):
    """策略运行生命周期协议。"""

    def create_run(
        self,
        run_id: str,
        strategy_id: str,
        strategy_version: str = "",
        mode: str = "backtest",
    ) -> None:
        """创建运行记录。"""
        ...

    def mark_running(self, run_id: str) -> bool:
        """标记运行为 running。"""
        ...

    def mark_completed(self, run_id: str) -> bool:
        """标记运行为 completed。"""
        ...

    def mark_failed(self, run_id: str, error_message: str = "") -> bool:
        """标记运行为 failed。"""
        ...


# ===========================================================================
# artifact_writer — 将回测产物序列化到磁盘
# ===========================================================================


_AuditRecord = RiskScanRecord | PreTradeDecisionRecord


def enrich_record_with_symbol(
    record: _AuditRecord,
    display_map: dict[InstrumentId, str],
) -> dict[str, object]:
    """
    将审计记录转为 dict 并注入 ``instrument_symbol`` 展示字段。

    如果 ``display_map`` 中无对应映射，则 ``instrument_symbol`` 值为空字符串。
    """
    d: dict[str, object] = dataclasses.asdict(record)
    iid = record.instrument_id
    d["instrument_symbol"] = display_map.get(iid, "") if iid is not None else ""
    return d


def write_backtest_artifacts(
    report: BacktestReport,
    output_dir: Path | None = None,
    manifest: RunManifest | None = None,
    display_map: dict[InstrumentId, str] | None = None,
) -> dict[str, Path]:
    """
    将 BacktestReport 序列化到磁盘，返回产物文件路径映射.

    Args:
        report: 回测报告.
        output_dir: 输出目录 (None = 使用系统临时目录).
        manifest: 运行清单（如提供则写出 manifest.json 并回填 artifacts）.
        display_map: InstrumentId → standard_ticker 映射，用于在审计日志中注入
            ``instrument_symbol`` 展示字段.

    Returns:
        产物类型 → 文件路径的映射，至少包含 ``backtest_report`` 条目.

    """
    if output_dir is None:
        output_dir = Path(tempfile.gettempdir()) / "ditto" / report.run_id

    output_dir.mkdir(parents=True, exist_ok=True)

    # 序列化报告（纯计算在 Engine）+ 文件写入（App 层职责）
    json_bytes, parquet_tables = serialize_report(report)
    atomic_bytes_write(json_bytes, output_dir / "backtest_report.json")
    for name, df in parquet_tables.items():
        atomic_write(df, output_dir / f"{name}.parquet")

    _write_audit_json(
        output_dir / "risk_log.json",
        report.risk_log,
        display_map,
    )
    _write_audit_json(
        output_dir / "pre_trade_log.json",
        report.pre_trade_log,
        display_map,
    )

    if manifest is not None:
        manifest_path = output_dir / "manifest.json"
        existing = tuple(
            sorted(child.name for child in output_dir.iterdir() if child.is_file())
        )
        artifact_refs = (*existing, "manifest.json")
        finalized_manifest = replace(
            manifest,
            artifacts=tuple(sorted(artifact_refs)),
        )
        atomic_bytes_write(
            serialize_manifest(finalized_manifest).encode("utf-8"),
            manifest_path,
        )

    return _collect_written_artifacts(output_dir)


def _write_audit_json(
    path: Path,
    records: tuple[_AuditRecord, ...],
    display_map: dict[InstrumentId, str] | None,
) -> None:
    """将非空审计记录写为 JSON artifact，可选注入 instrument_symbol。"""
    if not records:
        return
    if display_map is not None:
        payload = [enrich_record_with_symbol(r, display_map) for r in records]
    else:
        payload = [dataclasses.asdict(r) for r in records]
    atomic_bytes_write(
        orjson.dumps(payload, option=orjson.OPT_INDENT_2),
        path,
    )


def _collect_written_artifacts(output_dir: Path) -> dict[str, Path]:
    """收集输出目录中的 artifact 文件。"""
    return {child.stem: child for child in output_dir.iterdir() if child.is_file()}


# ===========================================================================
# StrategyInputAssembler — 从 Slice 组装 StrategyInputBundle
# ===========================================================================


class StrategyInputAssembler:
    """
    从 Slice 组装 StrategyInputBundle.

    封装 strategy_id / run_id / parameters 等策略级别配置，
    ``assemble()`` 接收日期级别的 Slice 数据并产出完整的 bundle。

    可复用于 BACKTEST / RESEARCH / RECOMMENDATION 等模式。

    Parameters
    ----------
        strategy_id: 策略 ID
        run_id: 运行 ID
        parameters: 参数覆盖

    """

    def __init__(
        self,
        strategy_id: str = "default",
        run_id: str = "",
        parameters: dict[str, object] | None = None,
    ) -> None:
        self._strategy_id = strategy_id
        self._run_id = run_id
        self._parameters = parameters or {}

    @property
    def strategy_id(self) -> str:
        """策略 ID。"""
        return self._strategy_id

    @property
    def run_id(self) -> str:
        """运行 ID。"""
        return self._run_id

    @property
    def parameters(self) -> dict[str, object]:
        """参数覆盖。"""
        return dict(self._parameters)

    def assemble(
        self,
        trade_date: str,
        slice_: Slice,
        *,
        valid_until: str | None = None,
        run_id: str | None = None,
    ) -> StrategyInputBundle:
        """
        从 Slice 构建 StrategyInputBundle.

        从 bars 中提取 market_data (OHLCV) 和 signal_values
        (动量信号: close / prev_close - 1)。

        Args:
            trade_date: 交易日期 (YYYY-MM-DD)
            slice_: 当日市场数据切片
            valid_until: 信号有效期截止日期 (YYYY-MM-DD)，若早于
                trade_date 则视为过期，bundle 中 signal_values 为 None
            run_id: 覆盖默认 run_id，用于在运行前固化真实 run_id

        Returns:
            包含标的列表、市场数据、信号值的 StrategyInputBundle

        """
        instrument_ids = list(slice_.bars.keys())
        instruments = pl.DataFrame({"instrument_id": instrument_ids})

        market_rows: list[dict[str, object]] = []
        signal_rows: list[dict[str, object]] = []

        for iid, bar in slice_.bars.items():
            market_rows.append(
                {
                    "instrument_id": iid,
                    "open": bar.open,
                    "high": bar.high,
                    "low": bar.low,
                    "close": bar.close,
                    "volume": bar.volume,
                }
            )
            signal_rows.append(
                {
                    "instrument_id": iid,
                    "signal_value": (
                        (bar.close / bar.prev_close - 1.0) if bar.prev_close else 0.0
                    ),
                }
            )

        # 信号过期检查：valid_until < trade_date 时信号无效
        signals_expired = valid_until is not None and valid_until < trade_date

        return StrategyInputBundle(
            trade_date=trade_date,
            strategy_id=self._strategy_id,
            run_id=self._run_id if run_id is None else run_id,
            instruments=instruments,
            market_data=pl.DataFrame(market_rows),
            signal_values=None if signals_expired else pl.DataFrame(signal_rows),
            parameters=self._parameters,
            benchmark_close=slice_.benchmark_close,
        )


# ===========================================================================
# build_display_map — InstrumentId → standard_ticker 映射构建
# ===========================================================================


def build_display_map(
    instrument_ids: list[int],
    metadata_service: MetadataService,
) -> dict[InstrumentId, str]:
    """
    构建 InstrumentId → standard_ticker 映射。

    将 instrument_id 列表解析为 ``{InstrumentId: "510300.SH"}`` 格式的展示映射。
    """
    display_map: dict[InstrumentId, str] = {}
    for iid in instrument_ids:
        instrument_id = InstrumentId(iid)
        instrument = metadata_service.get_instrument(iid)
        if instrument is not None:
            ticker = instrument.get("ticker", str(iid))
            exchange = instrument.get("exchange", "")
            key = f"{ticker}.{exchange}" if exchange else str(iid)
            display_map[instrument_id] = key
        else:
            display_map[instrument_id] = str(iid)
    return display_map
