"""Daily decision cockpit query facade."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from ditto_strategy.models import ArtifactKind, StrategyArtifactRecord

from ditto_application.execution_dto import ActualPositionSnapshot, TradeIntent
from ditto_application.queries.deviation import (
    SignalDeviationQueryFacade,
    SignalDeviationReport,
)
from ditto_application.queries.portfolio_actual import (
    PnlSummary,
    PortfolioActualQueryFacade,
)
from ditto_application.queries.signal import SignalQueryFacade

__all__ = [
    "DailyDecisionQueryFacade",
    "DailyDecisionReport",
    "DailyDecisionV2Report",
    "ReadinessFacts",
    "evaluate_readiness",
]

DailyDecisionReadinessStatus = Literal["ready", "blocked", "review"]


class SignalPackageArtifactReader(Protocol):
    """Daily Decision 所需的窄 Signal Package 读取接口。"""

    def list_by_strategy(self, strategy_id: str) -> list[StrategyArtifactRecord]: ...


@dataclass(frozen=True)
class ReadinessFacts:
    """readiness 真值表的全部输入事实。"""

    package_exists: bool = True
    run_outcome: str = "completed"
    data_ready: bool = True
    account_ready: bool = True
    no_rebalance: bool = False
    risk_warning: bool = False
    date_mismatch: bool = False
    unresolved_conflict: bool = False


@dataclass(frozen=True)
class DailyDecisionV2Report:
    """面向人工交易复核的稳定 V2 read model。"""

    identity: dict[str, object]
    readiness: dict[str, object]
    data: dict[str, object]
    run_package: dict[str, object]
    account_positions: dict[str, object]
    actions: tuple[dict[str, object], ...]
    execution_review: dict[str, object]


@dataclass(frozen=True)
class DailyDecisionReport:
    """Read model for one daily trading decision review."""

    strategy_id: str
    trade_date: str | None
    readiness_status: DailyDecisionReadinessStatus
    readiness_reasons: tuple[str, ...]
    signal_intents: tuple[TradeIntent, ...]
    deviation: SignalDeviationReport | None
    positions: tuple[ActualPositionSnapshot, ...]
    pnl: PnlSummary | None


class DailyDecisionQueryFacade:
    """Compose the daily cockpit read model from existing query facades."""

    def __init__(
        self,
        *,
        signal_facade: SignalQueryFacade,
        portfolio_facade: PortfolioActualQueryFacade,
        deviation_facade: SignalDeviationQueryFacade,
        package_reader: SignalPackageArtifactReader | None = None,
    ) -> None:
        self._signal_facade = signal_facade
        self._portfolio_facade = portfolio_facade
        self._deviation_facade = deviation_facade
        self._package_reader = package_reader

    def get_report_v2(
        self,
        *,
        strategy_id: str,
        trade_date: str | None = None,
    ) -> DailyDecisionV2Report:
        """从持久化 package 构造 V2；不以 intents 是否为空推断运行状态。"""
        legacy = self.get_report(strategy_id=strategy_id, trade_date=trade_date)
        package = self._latest_package(strategy_id, legacy.trade_date)
        metadata = package.metadata if package is not None else {}
        run_outcome = str(metadata.get("outcome", "missing"))
        required_datasets = metadata.get("required_datasets", [])
        dataset_snapshots = metadata.get("dataset_snapshot_ids", {})
        no_rebalance = bool(metadata.get("no_rebalance", False))
        risk_flags = metadata.get("risk_flags", [])
        facts = ReadinessFacts(
            package_exists=package is not None,
            run_outcome=run_outcome,
            data_ready=bool(dataset_snapshots) or not required_datasets,
            account_ready=bool(legacy.positions),
            no_rebalance=no_rebalance,
            risk_warning=bool(risk_flags),
            unresolved_conflict=run_outcome == "rerun_conflict",
        )
        status, reason_codes = evaluate_readiness(facts)
        actions = tuple(
            {
                "intent_id": intent.intent_id,
                "instrument_id": intent.instrument_id,
                "direction": intent.direction,
                "target_weight": intent.target_weight,
                "current_weight": intent.current_weight,
                "delta_weight": intent.delta_weight,
                "suggested_quantity": intent.quantity,
                "reference_price": None,
                "lot_size": None,
                "reason": "persisted_intent",
                "risk_flags": risk_flags,
                "intent_status": intent.status,
            }
            for intent in legacy.signal_intents
        )
        return DailyDecisionV2Report(
            identity={
                "strategy_id": strategy_id,
                "strategy_version": metadata.get("strategy_version", ""),
                "account_id": None,
                "sleeve_id": None,
                "signal_date": legacy.trade_date,
                "decision_date": metadata.get("decision_date", legacy.trade_date),
                "intended_trade_date": metadata.get(
                    "intended_trade_date", legacy.trade_date
                ),
            },
            readiness={
                "status": status,
                "reason_codes": reason_codes,
                "details": [_reason_detail(code) for code in reason_codes],
            },
            data={
                "required_datasets": required_datasets,
                "snapshot_ids": dataset_snapshots,
                "freshness": "ready" if facts.data_ready else "blocked",
                "dq_state": "passed" if facts.data_ready else "unknown",
            },
            run_package={
                "outcome": run_outcome,
                "artifact_id": package.artifact_id if package else None,
                "checksum": metadata.get("checksum"),
                "no_rebalance": no_rebalance,
                "factor_evidence": metadata.get("factor_values", {}),
                "risk_evidence": risk_flags,
            },
            account_positions={
                "baseline_id": None,
                "cash": None,
                "nav": None,
                "as_of": legacy.trade_date,
                "positions": legacy.positions,
            },
            actions=actions,
            execution_review={
                "effective_fills": (),
                "deviation": legacy.deviation,
                "pnl": legacy.pnl,
                "exceptions": (),
                "unresolved_conflicts": (
                    ("rerun_conflict",) if facts.unresolved_conflict else ()
                ),
            },
        )

    def _latest_package(
        self, strategy_id: str, trade_date: str | None
    ) -> StrategyArtifactRecord | None:
        if self._package_reader is None:
            return None
        packages = [
            artifact
            for artifact in self._package_reader.list_by_strategy(strategy_id)
            if artifact.artifact_type == ArtifactKind.SIGNAL_PACKAGE
            and (
                trade_date is None or artifact.metadata.get("signal_date") == trade_date
            )
        ]
        return packages[0] if packages else None

    def get_report(
        self,
        *,
        strategy_id: str,
        trade_date: str | None = None,
    ) -> DailyDecisionReport:
        """Return the daily decision report for a strategy/date."""
        signal_intents = self._get_signal_intents(
            strategy_id=strategy_id,
            trade_date=trade_date,
        )
        resolved_trade_date = trade_date or _latest_signal_date(signal_intents)
        if resolved_trade_date is None or not signal_intents:
            return DailyDecisionReport(
                strategy_id=strategy_id,
                trade_date=resolved_trade_date,
                readiness_status="blocked",
                readiness_reasons=("no signal intents available",),
                signal_intents=(),
                deviation=None,
                positions=(),
                pnl=None,
            )

        positions = tuple(
            self._portfolio_facade.get_position_history(
                strategy_id,
                snapshot_date=resolved_trade_date,
            )
        )
        deviation = self._deviation_facade.get_deviation(
            strategy_id=strategy_id,
            signal_date=resolved_trade_date,
        )
        pnl = self._portfolio_facade.compute_pnl(
            strategy_id,
            resolved_trade_date,
        )
        readiness_reasons = _readiness_reasons(
            signal_intents=signal_intents,
            positions=positions,
        )
        return DailyDecisionReport(
            strategy_id=strategy_id,
            trade_date=resolved_trade_date,
            readiness_status=_readiness_status(readiness_reasons),
            readiness_reasons=readiness_reasons,
            signal_intents=tuple(signal_intents),
            deviation=deviation,
            positions=positions,
            pnl=pnl,
        )

    def _get_signal_intents(
        self,
        *,
        strategy_id: str,
        trade_date: str | None,
    ) -> list[TradeIntent]:
        if trade_date is None:
            return self._signal_facade.get_latest_intents(strategy_id)
        return self._signal_facade.get_intents_by_date(
            strategy_id=strategy_id,
            signal_date=trade_date,
        )


def _latest_signal_date(intents: list[TradeIntent]) -> str | None:
    if not intents:
        return None
    return max(intent.signal_date for intent in intents)


def _readiness_reasons(
    *,
    signal_intents: list[TradeIntent],
    positions: tuple[ActualPositionSnapshot, ...],
) -> tuple[str, ...]:
    reasons: list[str] = []
    if not signal_intents:
        reasons.append("no signal intents available")
    if not positions:
        reasons.append("positions unavailable for trade date")
    return tuple(reasons)


def _readiness_status(
    readiness_reasons: tuple[str, ...],
) -> DailyDecisionReadinessStatus:
    if not readiness_reasons:
        return "ready"
    if "no signal intents available" in readiness_reasons:
        return "blocked"
    return "review"


def evaluate_readiness(  # noqa: PLR0911 - explicit truth-table priority
    facts: ReadinessFacts,
) -> tuple[DailyDecisionReadinessStatus, tuple[str, ...]]:
    """按 fail-closed 优先级计算 readiness 和稳定 reason codes。"""
    if facts.unresolved_conflict or facts.run_outcome == "rerun_conflict":
        return "blocked", ("RERUN_CONFLICT",)
    if facts.run_outcome == "failed":
        return "blocked", ("RUN_FAILED",)
    if not facts.package_exists:
        return "blocked", ("PACKAGE_MISSING",)
    if not facts.data_ready:
        return "blocked", ("DATA_BLOCKED",)
    if not facts.account_ready:
        return "blocked", ("ACCOUNT_BASELINE_MISSING",)
    reasons: list[str] = []
    if facts.no_rebalance:
        reasons.append("NO_REBALANCE")
    if facts.risk_warning:
        reasons.append("RISK_WARNING")
    if facts.date_mismatch:
        reasons.append("DATE_MISMATCH")
    if reasons:
        return "review", tuple(reasons)
    return "ready", ()


def _reason_detail(reason_code: str) -> str:
    return {
        "RERUN_CONFLICT": "同日重跑输入冲突, 需要人工处理",
        "RUN_FAILED": "策略运行失败",
        "PACKAGE_MISSING": "未找到持久化 Signal Package",
        "DATA_BLOCKED": "策略所需数据未就绪",
        "ACCOUNT_BASELINE_MISSING": "账户基线不可用",
        "NO_REBALANCE": "本日无需调仓, 请复核证据",
        "RISK_WARNING": "存在风险提示, 需要人工确认",
        "DATE_MISMATCH": "决策日期与预期交易日期不一致",
    }.get(reason_code, reason_code)
