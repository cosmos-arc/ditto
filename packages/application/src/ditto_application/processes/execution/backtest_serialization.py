"""
BacktestReportSerializer — 将 BacktestReport 序列化为 JSON + Parquet.

纯计算模块（零 I/O）：
  - serialize_report() 返回 JSON bytes + Parquet DataFrame 字典
  - 文件写入由 App 层负责
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping

import orjson
import polars as pl
from ditto_backtest.manifest import RunManifest
from ditto_backtest.result import BacktestAccountStateSnapshot
from ditto_backtest.statistics import BacktestReport
from ditto_strategy.alpha.selection_evidence import SelectionEvidenceLog

from ditto_application.exceptions import AppProcessError

__all__ = ["serialize_report"]

_INITIAL_UNIVERSE_SCHEMA = pl.Schema(
    {
        "run_id": pl.String,
        "trade_date": pl.String,
        "instrument_id": pl.String,
        "instrument_id_kind": pl.String,
        "ordinal": pl.Int64,
    },
)
_EXCLUSION_SCHEMA = pl.Schema(
    {
        "run_id": pl.String,
        "trade_date": pl.String,
        "instrument_id": pl.String,
        "instrument_id_kind": pl.String,
        "stage": pl.String,
        "reason_code": pl.String,
        "message": pl.String,
    },
)
_SELECTION_SCHEMA = pl.Schema(
    {
        "run_id": pl.String,
        "trade_date": pl.String,
        "instrument_id": pl.String,
        "instrument_id_kind": pl.String,
        "score": pl.Float64,
        "rank": pl.Int64,
        "selected": pl.Boolean,
    },
)
_FACTOR_CONTRIBUTION_SCHEMA = pl.Schema(
    {
        "run_id": pl.String,
        "trade_date": pl.String,
        "instrument_id": pl.String,
        "instrument_id_kind": pl.String,
        "factor_name": pl.String,
        "raw_value": pl.Float64,
        "processed_value": pl.Float64,
        "normalized_value": pl.Float64,
        "weight": pl.Float64,
        "contribution": pl.Float64,
        "factor_signal_score": pl.Float64,
        "rank": pl.Int64,
        "selected": pl.Boolean,
    },
)


def serialize_report(
    report: BacktestReport,
    *,
    rebalance_freq: str = "daily",
    manifest: RunManifest | None = None,
    resume_provenance: Mapping[str, object] | None = None,
    strategy_promotion: Mapping[str, object] | None = None,
    risk_report: Mapping[str, object] | None = None,
    selection_evidence: SelectionEvidenceLog | None = None,
) -> tuple[bytes, dict[str, pl.DataFrame]]:
    """
    将 BacktestReport 序列化为 JSON bytes + Parquet DataFrame 字典.

    Args:
        report: 回测报告.
        rebalance_freq: 调仓频率 (daily / weekly / monthly).
            写入 JSON 供 replay 反序列化时恢复配置，默认 "daily".
        manifest: 可选运行清单，用于将 PIT policy 等审计字段写入报告 JSON。
        resume_provenance: 可选 checkpoint 恢复来源证据。
        strategy_promotion: 可选策略晋级证据 block，写入报告 JSON。
        risk_report: 可选最小 launch risk report block，写入报告 JSON。
        selection_evidence: 可选策略选择证据；仅增加独立列式表，不改变 JSON。

    Returns:
        (json_bytes, parquet_tables) 二元组.
        json_bytes: 报告元数据的 JSON 字节.
        parquet_tables: 名称到 DataFrame 的映射.
            既有键: nav / portfolio_stats / trade_log / fill_log.
            ``selection_evidence`` 非 None 时另含 initial_universe_evidence /
            exclusion_evidence / selection_evidence /
            factor_contribution_evidence；四表均以 trade_date 区分调仓日。

    """
    json_data = _serialize_json_data(
        report,
        rebalance_freq=rebalance_freq,
        manifest=manifest,
        resume_provenance=resume_provenance,
        strategy_promotion=strategy_promotion,
        risk_report=risk_report,
    )
    json_bytes = orjson.dumps(json_data, option=orjson.OPT_INDENT_2)
    parquet_tables = _serialize_report_tables(report)
    if selection_evidence is not None:
        _append_selection_evidence_tables(
            parquet_tables,
            run_id=report.run_id,
            evidence=selection_evidence,
        )
    return json_bytes, parquet_tables


def _serialize_json_data(
    report: BacktestReport,
    *,
    rebalance_freq: str,
    manifest: RunManifest | None,
    resume_provenance: Mapping[str, object] | None,
    strategy_promotion: Mapping[str, object] | None,
    risk_report: Mapping[str, object] | None,
) -> dict[str, object]:
    """Serialize JSON-owned report metadata without columnar artifacts."""
    json_data: dict[str, object] = {
        "run_id": report.run_id,
        "period": {"start": report.period[0], "end": report.period[1]},
        "initial_cash": report.initial_cash,
        "final_nav": report.final_nav,
        "aggregated_trade_stats": dataclasses.asdict(report.aggregated_trade_stats),
        "alpha_stats": dataclasses.asdict(report.alpha_stats),
        "rebalance_freq": rebalance_freq,
        "nav_series": (
            [v for _, v in report.nav_series] if report.nav_series else None
        ),
    }
    if manifest is not None:
        json_data["pit_policy"] = {
            "time_column": manifest.pit_time_column,
            "policy": manifest.pit_policy,
            "unsafe_time_policy": manifest.unsafe_time_policy,
            "knowledge_lag_days": manifest.knowledge_lag_days,
        }
    if resume_provenance is not None:
        json_data["resume_provenance"] = dict(resume_provenance)
    if strategy_promotion is not None:
        json_data["strategy_promotion"] = dict(strategy_promotion)
    if risk_report is not None:
        json_data["risk_report"] = dict(risk_report)
    if report.final_account_state is not None:
        json_data["final_account_state"] = (
            BacktestAccountStateSnapshot.from_account_view(
                report.final_account_state,
            ).to_payload()
        )
    return json_data


def _serialize_report_tables(report: BacktestReport) -> dict[str, pl.DataFrame]:
    """Serialize the established backtest columnar tables."""
    parquet_tables: dict[str, pl.DataFrame] = {}
    if report.nav_series:
        parquet_tables["nav"] = pl.DataFrame(
            [{"trade_date": d, "nav": v} for d, v in report.nav_series],
        )

    if report.portfolio_stats:
        parquet_tables["portfolio_stats"] = pl.DataFrame(
            [dataclasses.asdict(r) for r in report.portfolio_stats],
        )

    if report.trade_log:
        parquet_tables["trade_log"] = pl.DataFrame(
            [dataclasses.asdict(r) for r in report.trade_log],
        )

    if report.fill_log:
        parquet_tables["fill_log"] = pl.DataFrame(
            [dataclasses.asdict(r) for r in report.fill_log],
        )
    return parquet_tables


def _append_selection_evidence_tables(
    tables: dict[str, pl.DataFrame],
    *,
    run_id: str,
    evidence: SelectionEvidenceLog,
) -> None:
    """Append evidence tables while refusing any existing-table collision."""
    evidence_tables = _serialize_selection_evidence(
        run_id=run_id,
        evidence=evidence,
    )
    for table_name, table in evidence_tables.items():
        if table_name in tables:
            raise AppProcessError(
                "selection evidence table collides with report artifact",
                details={"table_name": table_name},
            )
        tables[table_name] = table


def _serialize_selection_evidence(
    *,
    run_id: str,
    evidence: SelectionEvidenceLog,
) -> dict[str, pl.DataFrame]:
    """Map strategy DTOs to application-owned stable Polars schemas."""
    initial_rows: list[dict[str, object]] = []
    for event in evidence.initial_universe:
        instrument_id, instrument_id_kind = _serialize_instrument_id(
            event.instrument_id,
        )
        initial_rows.append(
            {
                "run_id": run_id,
                "trade_date": event.trade_date,
                "instrument_id": instrument_id,
                "instrument_id_kind": instrument_id_kind,
                "ordinal": event.ordinal,
            },
        )

    exclusion_rows: list[dict[str, object]] = []
    for event in evidence.exclusions:
        instrument_id, instrument_id_kind = _serialize_instrument_id(
            event.instrument_id,
        )
        exclusion_rows.append(
            {
                "run_id": run_id,
                "trade_date": event.trade_date,
                "instrument_id": instrument_id,
                "instrument_id_kind": instrument_id_kind,
                "stage": event.stage,
                "reason_code": event.reason_code.value,
                "message": event.message,
            },
        )

    selection_rows: list[dict[str, object]] = []
    for event in evidence.selections:
        instrument_id, instrument_id_kind = _serialize_instrument_id(
            event.instrument_id,
        )
        selection_rows.append(
            {
                "run_id": run_id,
                "trade_date": event.trade_date,
                "instrument_id": instrument_id,
                "instrument_id_kind": instrument_id_kind,
                "score": event.score,
                "rank": event.rank,
                "selected": event.selected,
            },
        )

    contribution_rows: list[dict[str, object]] = []
    for event in evidence.factor_contributions:
        instrument_id, instrument_id_kind = _serialize_instrument_id(
            event.instrument_id,
        )
        contribution_rows.append(
            {
                "run_id": run_id,
                "trade_date": event.trade_date,
                "instrument_id": instrument_id,
                "instrument_id_kind": instrument_id_kind,
                "factor_name": event.factor_name,
                "raw_value": event.raw_value,
                "processed_value": event.processed_value,
                "normalized_value": event.normalized_value,
                "weight": event.weight,
                "contribution": event.contribution,
                "factor_signal_score": event.factor_signal_score,
                "rank": event.rank,
                "selected": event.selected,
            },
        )

    return {
        "initial_universe_evidence": _frame_with_schema(
            initial_rows,
            _INITIAL_UNIVERSE_SCHEMA,
        ),
        "exclusion_evidence": _frame_with_schema(
            exclusion_rows,
            _EXCLUSION_SCHEMA,
        ),
        "selection_evidence": _frame_with_schema(
            selection_rows,
            _SELECTION_SCHEMA,
        ),
        "factor_contribution_evidence": _frame_with_schema(
            contribution_rows,
            _FACTOR_CONTRIBUTION_SCHEMA,
        ),
    }


def _frame_with_schema(
    rows: list[dict[str, object]],
    schema: pl.Schema,
) -> pl.DataFrame:
    """Create the same schema for empty and populated artifact tables."""
    if not rows:
        return pl.DataFrame(schema=schema)
    return pl.DataFrame(rows, schema=schema)


def _serialize_instrument_id(instrument_id: int | str) -> tuple[str, str]:
    """Preserve numeric-versus-text identity while using one stable column dtype."""
    kind = "integer" if isinstance(instrument_id, int) else "string"
    return str(instrument_id), kind
