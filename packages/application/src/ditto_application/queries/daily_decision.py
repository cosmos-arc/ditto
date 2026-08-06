"""Daily decision cockpit query facade."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from ditto_strategy.models import ArtifactKind, StrategyArtifactRecord
from ditto_strategy.runs.models import StrategyRunRecord

import ditto_application.queries.daily_decision_projection as decision_projection
from ditto_application.execution_dto import ActualPositionSnapshot, TradeIntent
from ditto_application.queries.account import (
    AccountBaselineQuery,
    AccountBaselineReadModel,
)
from ditto_application.queries.deviation import (
    SignalDeviationQueryFacade,
    SignalDeviationReport,
)
from ditto_application.queries.portfolio_actual import (
    PnlSummary,
    PortfolioActualQueryFacade,
)
from ditto_application.queries.signal import SignalQueryFacade
from ditto_application.queries.strategy import StrategyQueryFacade
from ditto_application.signal_package_contract import (
    canonical_signal_package_metadata,
    verify_signal_package_metadata,
)

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


class StrategyRunReader(Protocol):
    """Daily Decision 所需的窄运行生命周期读取接口。"""

    def get_run(self, run_id: str) -> StrategyRunRecord | None: ...


@dataclass(frozen=True)
class ReadinessFacts:
    """readiness 真值表的全部输入事实。"""

    active_strategy: bool = True
    data_ready: bool = True
    account_ready: bool = True
    run_exists: bool = True
    run_failed: bool = False
    package_exists: bool = True
    checksum_valid: bool = True
    run_outcome: str = "completed"
    no_rebalance: bool = False
    risk_warning: bool = False
    date_mismatch: bool = False
    unresolved_conflict: bool = False
    fill_quantity_exceeded: bool = False
    quantity_available: bool = True
    intent_persistence_valid: bool = True


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
        account_query: AccountBaselineQuery | None = None,
        strategy_query: StrategyQueryFacade | None = None,
        run_reader: StrategyRunReader | None = None,
    ) -> None:
        self._signal_facade = signal_facade
        self._portfolio_facade = portfolio_facade
        self._deviation_facade = deviation_facade
        self._package_reader = package_reader
        self._account_query = account_query
        self._strategy_query = strategy_query
        self._run_reader = run_reader

    def get_report_v2(
        self,
        *,
        strategy_id: str,
        trade_date: str | None = None,
        account_id: str | None = None,
    ) -> DailyDecisionV2Report:
        """从持久化 package 构造 V2；不以 intents 是否为空推断运行状态。"""
        active_spec = (
            self._strategy_query.get_active_published(strategy_id)
            if self._strategy_query is not None
            else None
        )
        active_strategy = active_spec is not None or self._strategy_query is None
        active_version = str(active_spec.version) if active_spec is not None else None
        package = self._latest_package(strategy_id, trade_date, active_version)
        raw_metadata = package.metadata if package is not None else {}
        metadata = canonical_signal_package_metadata(raw_metadata)
        signal_date = (
            decision_projection.optional_string(metadata.get("signal_date"))
            or trade_date
        )
        package_account_id = decision_projection.optional_string(
            metadata.get("account_id")
        )
        if package is None and account_id is not None:
            package_account_id = account_id
        package_sleeve_id = decision_projection.optional_string(
            metadata.get("sleeve_id")
        )
        if package is None and package_account_id is not None:
            package_sleeve_id = f"manual-{package_account_id}-{strategy_id}"
        account_identity_valid = (
            package_account_id is not None
            and package_sleeve_id is not None
            and (account_id is None or account_id == package_account_id)
        )
        strategy_version = active_version or decision_projection.optional_string(
            metadata.get("strategy_version")
        )
        batch_key = package.run_id if package is not None else None
        if batch_key is None and signal_date is not None and strategy_version:
            batch_key = f"eod-{signal_date}-{strategy_id}-{strategy_version}"
        run = (
            self._run_reader.get_run(batch_key)
            if self._run_reader is not None and batch_key is not None
            else None
        )
        run = decision_projection.matching_deterministic_run(
            run,
            expected_batch_key=batch_key,
            expected_strategy_id=strategy_id,
            expected_strategy_version=strategy_version,
            expected_mode="recommendation",
        )
        missing_package_run = (
            decision_projection.project_missing_package_run(
                run,
                expected_batch_key=batch_key,
                expected_signal_date=signal_date,
                expected_strategy_id=strategy_id,
                expected_strategy_version=strategy_version,
                expected_mode="recommendation",
            )
            if package is None
            else None
        )
        conflict = self._latest_conflict(
            strategy_id=strategy_id,
            trade_date=signal_date,
            strategy_version=strategy_version,
            batch_key=batch_key,
            active_artifact_id=package.artifact_id if package is not None else None,
        )
        run_status = str(run.status) if run is not None else None
        if conflict is not None and run_status == "completed":
            run_outcome = "rerun_conflict"
        elif missing_package_run is not None:
            run_outcome = missing_package_run.outcome
        else:
            run_outcome = decision_projection.resolve_run_outcome(
                package=package,
                run=run,
                metadata=raw_metadata,
            )
        dataset_projection = decision_projection.project_datasets(
            metadata,
            package_exists=package is not None,
            missing_package_run=missing_package_run,
        )
        raw_intents = decision_projection.intent_payloads(metadata.get("intents"))
        no_rebalance = package is not None and not raw_intents
        risk_flags = decision_projection.string_tuple(metadata.get("risk_flags"))
        raw_baseline = self._account_baseline(
            account_id=package_account_id if account_identity_valid else None,
            strategy_id=strategy_id,
            signal_date=signal_date,
        )
        baseline = (
            raw_baseline
            if decision_projection.baseline_matches_identity(
                raw_baseline,
                account_id=package_account_id,
                sleeve_id=package_sleeve_id,
                strategy_id=strategy_id,
            )
            else None
        )
        persisted_intents = self._persisted_intents(
            strategy_id=strategy_id,
            signal_date=signal_date,
            batch_key=batch_key,
        )
        intent_ids = {
            str(raw["intent_id"])
            for raw in raw_intents
            if isinstance(raw.get("intent_id"), str)
        }
        intent_persistence_valid = decision_projection.persisted_intents_match_package(
            raw_intents=raw_intents,
            persisted_intents=persisted_intents,
        )
        effective_fills = tuple(
            fill
            for fill in self._portfolio_facade.get_effective_fills(strategy_id)
            if fill.intent_id in intent_ids
        )
        actions = decision_projection.project_actions(
            raw_intents=raw_intents,
            persisted_intents=persisted_intents,
            risk_flags=risk_flags,
            effective_fills=effective_fills,
        )
        intended_trade_date = decision_projection.optional_string(
            metadata.get("intended_trade_date")
        )
        date_mismatch = bool(
            intended_trade_date
            and any(fill.trade_date != intended_trade_date for fill in effective_fills)
        )
        unresolved_conflicts = decision_projection.unresolved_conflicts(
            actions=actions,
            run_outcome=run_outcome,
        )
        facts = ReadinessFacts(
            active_strategy=active_strategy,
            data_ready=dataset_projection.data_ready,
            account_ready=account_identity_valid and baseline is not None,
            run_exists=(
                run is not None if self._run_reader is not None else package is not None
            ),
            run_failed=run_outcome == "failed",
            package_exists=package is not None,
            checksum_valid=(
                verify_signal_package_metadata(raw_metadata)
                if package is not None
                else True
            ),
            run_outcome=run_outcome,
            no_rebalance=no_rebalance,
            risk_warning=bool(risk_flags),
            date_mismatch=date_mismatch,
            unresolved_conflict="RERUN_CONFLICT" in unresolved_conflicts,
            fill_quantity_exceeded=any(
                conflict.startswith("OVERFILLED:") for conflict in unresolved_conflicts
            ),
            quantity_available=(
                no_rebalance
                or (
                    bool(actions)
                    and all(map(decision_projection.has_ready_sizing_evidence, actions))
                )
            ),
            intent_persistence_valid=intent_persistence_valid,
        )
        status, reason_codes = evaluate_readiness(facts)
        positions = decision_projection.project_baseline_positions(baseline)
        review_date = intended_trade_date or signal_date
        deviation = (
            self._deviation_facade.get_deviation(
                strategy_id=strategy_id,
                signal_date=signal_date,
                execution_date=intended_trade_date,
                intent_ids=tuple(sorted(intent_ids)),
            )
            if signal_date is not None and raw_intents
            else None
        )
        pnl = (
            self._portfolio_facade.compute_pnl(strategy_id, review_date)
            if review_date is not None
            else None
        )
        return DailyDecisionV2Report(
            identity={
                "strategy_id": strategy_id,
                "strategy_version": strategy_version,
                "account_id": package_account_id,
                "sleeve_id": package_sleeve_id,
                "signal_date": signal_date,
                "decision_date": decision_projection.optional_string(
                    metadata.get("decision_date")
                ),
                "intended_trade_date": intended_trade_date,
            },
            readiness={
                "status": status,
                "reason_codes": reason_codes,
                "details": tuple(_reason_detail(code) for code in reason_codes),
            },
            data={
                "required_datasets": dataset_projection.required_datasets,
                "snapshot_ids": dataset_projection.dataset_snapshots,
                "dataset_states": dataset_projection.dataset_states,
                "freshness": ("ready" if dataset_projection.data_ready else "blocked"),
                "dq_state": ("passed" if dataset_projection.data_ready else "failed"),
            },
            run_package={
                "outcome": run_outcome,
                "batch_key": batch_key,
                "artifact_id": package.artifact_id if package else None,
                "conflict_artifact_id": (
                    conflict.artifact_id if conflict is not None else None
                ),
                "checksum": metadata.get("checksum"),
                "checksum_valid": facts.checksum_valid,
                "no_rebalance": no_rebalance,
                "factor_evidence": metadata.get("factor_values", {}),
                "risk_evidence": risk_flags,
            },
            account_positions=decision_projection.project_account_positions(
                baseline,
                positions,
            ),
            actions=actions,
            execution_review={
                "effective_fills": effective_fills,
                "deviation": deviation,
                "pnl": pnl,
                "exceptions": (("TRADE_DATE_MISMATCH",) if date_mismatch else ()),
                "unresolved_conflicts": unresolved_conflicts,
            },
        )

    def _account_baseline(
        self,
        *,
        account_id: str | None,
        strategy_id: str,
        signal_date: str | None,
    ) -> AccountBaselineReadModel | None:
        if account_id is None or signal_date is None or self._account_query is None:
            return None
        return self._account_query.get_latest(
            account_id=account_id,
            strategy_id=strategy_id,
            signal_date=signal_date,
        )

    def _persisted_intents(
        self,
        *,
        strategy_id: str,
        signal_date: str | None,
        batch_key: str | None,
    ) -> dict[str, TradeIntent]:
        if signal_date is None or batch_key is None:
            return {}
        intent_prefix = f"sig-{batch_key}-"
        return {
            intent.intent_id: intent
            for intent in self._signal_facade.get_intents_by_date(
                strategy_id=strategy_id,
                signal_date=signal_date,
            )
            if intent.intent_id.startswith(intent_prefix)
        }

    def _latest_package(
        self,
        strategy_id: str,
        trade_date: str | None,
        strategy_version: str | None,
    ) -> StrategyArtifactRecord | None:
        if self._package_reader is None:
            return None
        packages = [
            artifact
            for artifact in self._package_reader.list_by_strategy(strategy_id)
            if artifact.artifact_type == ArtifactKind.SIGNAL_PACKAGE
            and artifact.status == "active"
            and (
                strategy_version is None
                or decision_projection.optional_string(
                    artifact.metadata.get("strategy_version")
                )
                == strategy_version
            )
            and (
                trade_date is None or artifact.metadata.get("signal_date") == trade_date
            )
        ]
        return (
            max(
                packages,
                key=lambda artifact: (
                    decision_projection.optional_string(
                        artifact.metadata.get("signal_date")
                    )
                    or "",
                    artifact.created_at,
                    artifact.artifact_id,
                ),
            )
            if packages
            else None
        )

    def _latest_conflict(
        self,
        *,
        strategy_id: str,
        trade_date: str | None,
        strategy_version: str | None,
        batch_key: str | None,
        active_artifact_id: str | None,
    ) -> StrategyArtifactRecord | None:
        if self._package_reader is None or batch_key is None:
            return None
        conflicts = [
            artifact
            for artifact in self._package_reader.list_by_strategy(strategy_id)
            if artifact.artifact_type == ArtifactKind.SIGNAL_PACKAGE
            and artifact.status == "conflict"
            and artifact.run_id == batch_key
            and artifact.metadata.get("batch_key") == batch_key
            and artifact.metadata.get("outcome") == "rerun_conflict"
            and (
                trade_date is None or artifact.metadata.get("signal_date") == trade_date
            )
            and (
                strategy_version is None
                or decision_projection.optional_string(
                    artifact.metadata.get("strategy_version")
                )
                == strategy_version
            )
            and (
                active_artifact_id is None
                or artifact.metadata.get("conflicting_artifact_id")
                == active_artifact_id
            )
            and verify_signal_package_metadata(artifact.metadata)
        ]
        return (
            max(
                conflicts,
                key=lambda artifact: (artifact.created_at, artifact.artifact_id),
            )
            if conflicts
            else None
        )

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


def evaluate_readiness(  # noqa: C901, PLR0911, PLR0912 - explicit truth table
    facts: ReadinessFacts,
) -> tuple[DailyDecisionReadinessStatus, tuple[str, ...]]:
    """按 fail-closed 优先级计算 readiness 和稳定 reason codes。"""
    if not facts.active_strategy:
        return "blocked", ("NO_ACTIVE_STRATEGY",)
    if not facts.data_ready:
        return "blocked", ("REQUIRED_DATA_NOT_READY",)
    if not facts.account_ready:
        return "blocked", ("ACCOUNT_BASELINE_MISSING",)
    if facts.run_failed or facts.run_outcome == "failed":
        return "blocked", ("EOD_RUN_FAILED",)
    if not facts.run_exists:
        return "blocked", ("EOD_RUN_MISSING",)
    if facts.run_outcome not in {"completed", "no_rebalance", "rerun_conflict"}:
        return "blocked", ("EOD_RUN_INCOMPLETE",)
    if not facts.package_exists:
        return "blocked", ("SIGNAL_PACKAGE_MISSING",)
    if not facts.checksum_valid:
        return "blocked", ("CHECKSUM_MISMATCH",)
    if not facts.intent_persistence_valid:
        return "blocked", ("SIGNAL_INTENT_MISMATCH",)
    reasons: list[str] = []
    if facts.no_rebalance:
        reasons.append("NO_REBALANCE_REQUIRED")
    if facts.risk_warning:
        reasons.append("RISK_WARNING")
    if facts.date_mismatch:
        reasons.append("TRADE_DATE_MISMATCH")
    if facts.unresolved_conflict or facts.run_outcome == "rerun_conflict":
        reasons.append("RERUN_CONFLICT")
    if facts.fill_quantity_exceeded:
        reasons.append("FILL_QUANTITY_EXCEEDED")
    if not facts.quantity_available:
        reasons.append("QUANTITY_UNAVAILABLE")
    if reasons:
        return "review", tuple(reasons)
    return "ready", ("READY_FOR_REVIEW",)


def _reason_detail(reason_code: str) -> str:
    return {
        "NO_ACTIVE_STRATEGY": "没有可用于人工执行的活动 published 策略",
        "REQUIRED_DATA_NOT_READY": "策略所需数据缺失、过期或质量检查未通过",
        "ACCOUNT_BASELINE_MISSING": "未找到不晚于信号日的完整账户基线",
        "EOD_RUN_MISSING": "目标信号日尚无 EOD 运行记录",
        "EOD_RUN_FAILED": "目标信号日的 EOD 策略运行失败",
        "SIGNAL_PACKAGE_MISSING": "EOD 运行存在但 Signal Package 缺失",
        "CHECKSUM_MISMATCH": "持久化 Signal Package 校验失败",
        "SIGNAL_INTENT_MISMATCH": "Signal Package 与当前持久化交易意图不一致",
        "EOD_RUN_INCOMPLETE": "目标信号日的 EOD 运行尚未完成",
        "NO_REBALANCE_REQUIRED": "本日无需调仓, 请复核 package 证据",
        "RERUN_CONFLICT": "同日重跑输入冲突, 需要人工处理",
        "FILL_QUANTITY_EXCEEDED": "有效成交数量超过建议数量, 需要人工复核",
        "RISK_WARNING": "存在风险提示, 需要人工确认",
        "TRADE_DATE_MISMATCH": "实际成交日期与预期交易日不一致",
        "QUANTITY_UNAVAILABLE": "权重可复核, 但建议数量或参考价不可用",
        "READY_FOR_REVIEW": "建议、数据、账户与风险证据已就绪, 请人工复核",
    }.get(reason_code, reason_code)
