"""
回测审计持久化 — 审计日志 + 策略产物 + run_id 解析.

将 BacktestService 中与持久化相关的逻辑提取为模块级函数，
保持单一职责：审计日志存储、产物序列化、run_id 生成/解析。
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import orjson
from ditto_backtest.manifest import RunManifest
from ditto_backtest.statistics import BacktestReport
from ditto_execution.audit import ExecutionAuditService
from ditto_execution.audit.models import (
    PreTradeDecisionPayload,
    RiskScanPayload,
)
from ditto_kernel.identity import InstrumentId
from ditto_strategy.models import ArtifactKind, StrategyArtifactRecord
from ditto_strategy.storage.sqlite.services.strategy_artifact_service import (
    StrategyArtifactService,
)

from ditto_application.processes.execution.strategy_input import (
    BacktestArtifactWriteOptions,
)

__all__ = [
    "ArtifactPersistConfig",
    "ArtifactPersistContext",
    "persist_artifact",
    "persist_audit",
    "resolve_run_id",
]


@dataclass(frozen=True)
class ArtifactPersistContext:
    """调用上下文（每次调用不同）。"""

    run_id: str
    report: BacktestReport
    manifest: RunManifest | None = None
    resume_provenance: Mapping[str, object] | None = None


@dataclass(frozen=True)
class ArtifactPersistConfig:
    """持久化配置（BacktestService 级别不变）。"""

    strategy_id: str
    strategy_version: str
    initial_cash: float
    rebalance_freq: str
    artifact_service: StrategyArtifactService
    write_fn: Callable[..., dict[str, Path]]
    artifact_dir: str | None = None
    display_map: dict[InstrumentId, str] | None = None
    benchmark_id: InstrumentId | None = None
    parameter_overrides: tuple[str, ...] = ()
    code_version: str = ""
    data_catalog_identities: tuple[str, ...] = ()
    factor_report_refs: tuple[str, ...] = ()
    recommendation_status: str = "research"
    fee_model_name: str = ""
    slippage_model_name: str = ""


def resolve_run_id(configured_run_id: str) -> str:
    """
    在进入生命周期编排前固化 run_id.

    Args:
        configured_run_id: 来自 BacktestServiceConfig.run_id 的值。
            空字符串时自动生成短 UUID。

    Returns:
        确定的 run_id 字符串。

    """
    if configured_run_id:
        return configured_run_id
    return uuid.uuid4().hex[:8]


def persist_audit(
    run_id: str,
    report: BacktestReport,
    audit_service: ExecutionAuditService,
) -> None:
    """
    持久化审计日志到 ExecutionAuditService.

    App 层负责将 Core record 转换为 Data 本地 DTO。

    Args:
        run_id: 运行标识。
        report: 回测报告（含 risk_log 和 pre_trade_log）。
        audit_service: 审计日志持久化服务。

    """
    risk_payloads = tuple(
        RiskScanPayload(
            trade_date=r.trade_date,
            rule_id=r.rule_id,
            instrument_id=(
                int(r.instrument_id) if r.instrument_id is not None else None
            ),
            scope=r.scope,
            severity=str(r.severity),
            action_taken=str(r.action_taken),
            detail=r.detail,
            current_value=r.current_value,
            threshold=r.threshold,
        )
        for r in report.risk_log
    )
    pre_trade_payloads = tuple(
        PreTradeDecisionPayload(
            trade_date=r.trade_date,
            order_id=r.order_id,
            instrument_id=int(r.instrument_id),
            direction=r.direction,
            original_quantity=r.original_quantity,
            final_quantity=r.final_quantity,
            decision=r.decision,
            reason=r.reason,
            check_sequence=r.check_sequence,
        )
        for r in report.pre_trade_log
    )
    audit_service.save_risk_log(run_id, risk_payloads)
    audit_service.save_pre_trade_log(run_id, pre_trade_payloads)


def persist_artifact(
    ctx: ArtifactPersistContext,
    config: ArtifactPersistConfig,
) -> None:
    """
    持久化回测报告到磁盘 + StrategyArtifactService.

    Args:
        ctx: 调用上下文（run_id、report、manifest）。
        config: 持久化配置（策略信息、服务、输出设置）。

    """
    # 始终将产物序列化到磁盘
    output_dir: Path | None = None
    if config.artifact_dir is not None:
        output_dir = Path(config.artifact_dir) / ctx.run_id

    strategy_promotion = _strategy_promotion_artifact(ctx, config)
    artifacts_map = config.write_fn(
        ctx.report,
        output_dir=output_dir,
        manifest=ctx.manifest,
        display_map=config.display_map,
        options=BacktestArtifactWriteOptions(
            rebalance_freq=config.rebalance_freq,
            resume_provenance=ctx.resume_provenance,
            strategy_promotion=strategy_promotion,
        ),
    )
    # file_path 存储目录路径，匹配读取侧 _build_path 契约（Path(base) / filename）
    # 从返回值推导实际目录（artifact_dir=None 时内部解析到系统临时目录）
    if not artifacts_map:
        return
    resolved_dir = next(iter(artifacts_map.values())).parent
    file_path = str(resolved_dir)

    metadata: dict[str, object] = {
        "initial_cash": config.initial_cash,
        "final_nav": ctx.report.final_nav,
        "total_trades": ctx.report.aggregated_trade_stats.total_trades,
        "sharpe_ratio": ctx.report.alpha_stats.sharpe_ratio,
        "max_drawdown": ctx.report.alpha_stats.max_drawdown,
        "period_start": ctx.report.period[0],
        "period_end": ctx.report.period[1],
        "pit_policy": (ctx.manifest.pit_policy if ctx.manifest is not None else ""),
        "pit_time_column": (
            ctx.manifest.pit_time_column if ctx.manifest is not None else ""
        ),
        "unsafe_time_policy": (
            ctx.manifest.unsafe_time_policy if ctx.manifest is not None else ""
        ),
        "knowledge_lag_days": (
            ctx.manifest.knowledge_lag_days if ctx.manifest is not None else None
        ),
        "strategy_promotion": strategy_promotion,
    }
    metadata.update(_resume_artifact_metadata(ctx.resume_provenance))

    artifact = StrategyArtifactRecord(
        artifact_id=f"artifact-{ctx.run_id}",
        strategy_id=config.strategy_id,
        run_id=ctx.run_id,
        artifact_type=ArtifactKind.BACKTEST_REPORT,
        file_path=file_path,
        metadata=metadata,
        created_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )
    config.artifact_service.save_artifact(artifact)


def _strategy_promotion_artifact(
    ctx: ArtifactPersistContext,
    config: ArtifactPersistConfig,
) -> dict[str, object]:
    """Build the launch research-promotion evidence block for a backtest report."""
    manifest = ctx.manifest
    strategy_version = (
        manifest.strategy_version
        if manifest is not None and manifest.strategy_version
        else config.strategy_version
    )
    return {
        "strategy_id": config.strategy_id,
        "strategy_version": strategy_version,
        "code_version": _code_version(config, manifest),
        "data_catalog_identities": _data_catalog_identities(
            manifest,
            config.data_catalog_identities,
        ),
        "parameter_hash": _parameter_hash(
            manifest.parameter_overrides
            if manifest is not None and manifest.parameter_overrides
            else config.parameter_overrides,
        ),
        "benchmark": (
            int(config.benchmark_id) if config.benchmark_id is not None else None
        ),
        "cost_model": _cost_model_metadata(ctx.report, config),
        "backtest_metrics": _backtest_metrics(ctx.report),
        "factor_report_refs": list(config.factor_report_refs),
        "recommendation_status": config.recommendation_status,
    }


def _code_version(
    config: ArtifactPersistConfig,
    manifest: RunManifest | None,
) -> str:
    """Prefer explicit code version, then manifest spec hash, then strategy version."""
    if config.code_version:
        return config.code_version
    if manifest is not None and manifest.spec_hash:
        return manifest.spec_hash
    return config.strategy_version


def _data_catalog_identities(
    manifest: RunManifest | None,
    configured: tuple[str, ...],
) -> list[object]:
    """Return structured catalog/source identities from manifest input refs."""
    if manifest is not None and manifest.input_ref_details:
        return [
            {
                "instrument_id": int(ref.instrument_id),
                "source": ref.source,
                "source_snapshot_id": ref.source_snapshot_id,
                "data_hash": ref.data_hash,
                "date_range": list(ref.date_range),
            }
            for ref in manifest.input_ref_details
        ]
    return list(configured)


def _parameter_hash(parameter_overrides: tuple[str, ...]) -> str:
    """Hash parameter overrides into stable promotion evidence."""
    payload = orjson.dumps(list(parameter_overrides), option=orjson.OPT_SORT_KEYS)
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _cost_model_metadata(
    report: BacktestReport,
    config: ArtifactPersistConfig,
) -> dict[str, object]:
    """Summarize the cost model and realized cost metrics used by the run."""
    alpha = getattr(report, "alpha_stats", None)
    return {
        "fee_model": config.fee_model_name,
        "slippage_model": config.slippage_model_name,
        "total_fees": getattr(alpha, "total_fees", 0.0),
        "cost_drag": getattr(alpha, "cost_drag", 0.0),
        "net_return_after_cost": getattr(alpha, "net_return_after_cost", 0.0),
    }


def _backtest_metrics(report: BacktestReport) -> dict[str, object]:
    """Summarize promotion-relevant backtest metrics."""
    alpha = getattr(report, "alpha_stats", None)
    period = getattr(report, "period", ("", ""))
    aggregated = getattr(report, "aggregated_trade_stats", None)
    return {
        "period_start": period[0],
        "period_end": period[1],
        "initial_cash": getattr(report, "initial_cash", 0.0),
        "final_nav": getattr(report, "final_nav", 0.0),
        "total_trades": getattr(aggregated, "total_trades", 0),
        "sharpe_ratio": getattr(alpha, "sharpe_ratio", 0.0),
        "max_drawdown": getattr(alpha, "max_drawdown", 0.0),
        "annualized_return": getattr(alpha, "annualized_return", 0.0),
    }


def _resume_artifact_metadata(
    provenance: Mapping[str, object] | None,
) -> dict[str, object]:
    """Map normalized report provenance into searchable artifact metadata."""
    if provenance is None:
        return {}
    return {
        "resume_from_run_id": provenance.get("from_run_id", ""),
        "resume_checkpoint_trade_date": provenance.get("checkpoint_trade_date", ""),
        "resume_checkpoint_completed_days": provenance.get(
            "checkpoint_completed_days",
            0,
        ),
        "resume_checkpoint_total_days": provenance.get("checkpoint_total_days", 0),
        "resume_checkpoint_nav": provenance.get("checkpoint_nav", 0.0),
        "resume_checkpoint_order_count": provenance.get("checkpoint_order_count", 0),
        "resume_checkpoint_fill_count": provenance.get("checkpoint_fill_count", 0),
        "resume_account_state_hash": provenance.get("account_state_hash", ""),
        "resume_settlement_state_hash": provenance.get("settlement_state_hash", ""),
        "resume_runtime_state_hash": provenance.get("runtime_state_hash", ""),
    }
