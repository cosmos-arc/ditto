"""
artifact_writer — 将回测产物序列化到磁盘.

提供 `write_backtest_artifacts()` 函数，封装 BacktestReport 序列化逻辑，
确保无论是否指定 artifact_dir，都能将产物写入默认输出目录。

输出文件:
  - backtest_report.json: 报告元数据
  - manifest.json: 运行清单（如提供 manifest）
  - nav.parquet: NAV 时间序列 (如有)
  - trade_log.parquet: 交易记录 (如有)
  - fill_log.parquet: 成交记录 (如有)
  - portfolio_stats.parquet: 每日组合统计 (如有)
  - risk_log.json: 风控日志 (如有)
  - pre_trade_log.json: PreTrade 决策日志 (如有)
"""

from __future__ import annotations

import dataclasses
import tempfile
from dataclasses import replace
from pathlib import Path

import orjson
from ditto_core.backtest.manifest import RunManifest, serialize_manifest
from ditto_core.backtest.serialization import serialize
from ditto_core.backtest.statistics import (
    BacktestReport,
    PreTradeDecisionRecord,
    RiskScanRecord,
)
from ditto_infra.foundation.util.io import atomic_bytes_write
from ditto_kernel.identity import InstrumentId

__all__ = ["enrich_record_with_symbol", "write_backtest_artifacts"]

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
    d["instrument_symbol"] = display_map.get(record.instrument_id, "")
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

    serialize(report, output_dir)
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
