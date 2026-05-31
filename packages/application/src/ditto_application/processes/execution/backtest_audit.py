"""
回测审计持久化 — 审计日志 + 策略产物 + run_id 解析.

将 BacktestService 中与持久化相关的逻辑提取为模块级函数，
保持单一职责：审计日志存储、产物序列化、run_id 生成/解析。
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
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
    "persist_artifact",
    "persist_audit",
    "resolve_run_id",
]


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


def persist_artifact(  # noqa: PLR0913
    *,
    run_id: str,
    report: BacktestReport,
    manifest: RunManifest | None,
    strategy_id: str,
    initial_cash: float,
    rebalance_freq: str,
    artifact_service: StrategyArtifactService,
    artifact_dir: str | None,
    display_map: dict[InstrumentId, str] | None,
    write_fn: Callable[..., dict[str, Path]],
) -> None:
    """
    持久化回测报告到磁盘 + StrategyArtifactService.

    Args:
        run_id: 运行标识。
        report: 回测报告。
        manifest: 引擎运行清单（可选）。
        strategy_id: 策略 ID。
        initial_cash: 初始资金。
        rebalance_freq: 调仓频率。
        artifact_service: 策略产物持久化服务。
        artifact_dir: 产物输出目录（None = 临时目录）。
        display_map: InstrumentId → 标的代码展示映射。
        write_fn: 产物序列化函数（由调用方注入，支持 test monkeypatch）。

    """
    # 始终将产物序列化到磁盘
    output_dir: Path | None = None
    if artifact_dir is not None:
        output_dir = Path(artifact_dir) / run_id

    artifacts_map = write_fn(
        report,
        output_dir=output_dir,
        manifest=manifest,
        display_map=display_map,
        rebalance_freq=rebalance_freq,
    )
    # file_path 存储目录路径，匹配读取侧 _build_path 契约（Path(base) / filename）
    # 从返回值推导实际目录（artifact_dir=None 时内部解析到系统临时目录）
    if not artifacts_map:
        return
    resolved_dir = next(iter(artifacts_map.values())).parent
    file_path = str(resolved_dir)

    artifact = StrategyArtifactRecord(
        artifact_id=f"artifact-{run_id}",
        strategy_id=strategy_id,
        run_id=run_id,
        artifact_type=ArtifactKind.BACKTEST_REPORT,
        file_path=file_path,
        metadata={
            "initial_cash": initial_cash,
            "final_nav": report.final_nav,
            "total_trades": report.aggregated_trade_stats.total_trades,
            "sharpe_ratio": report.alpha_stats.sharpe_ratio,
            "max_drawdown": report.alpha_stats.max_drawdown,
            "period_start": report.period[0],
            "period_end": report.period[1],
        },
        created_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )
    artifact_service.save_artifact(artifact)
