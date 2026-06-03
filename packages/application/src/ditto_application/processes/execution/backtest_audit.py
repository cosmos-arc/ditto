"""
回测审计持久化 — 审计日志 + 策略产物 + run_id 解析.

将 BacktestService 中与持久化相关的逻辑提取为模块级函数，
保持单一职责：审计日志存储、产物序列化、run_id 生成/解析。
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

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
    initial_cash: float
    rebalance_freq: str
    artifact_service: StrategyArtifactService
    write_fn: Callable[..., dict[str, Path]]
    artifact_dir: str | None = None
    display_map: dict[InstrumentId, str] | None = None


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

    artifacts_map = config.write_fn(
        ctx.report,
        output_dir=output_dir,
        manifest=ctx.manifest,
        display_map=config.display_map,
        rebalance_freq=config.rebalance_freq,
        resume_provenance=ctx.resume_provenance,
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
