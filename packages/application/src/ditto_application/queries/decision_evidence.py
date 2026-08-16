"""Exact DailyDecision V3 evidence reads for governed consumers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Literal

from ditto_application.exceptions import AppQueryError
from ditto_application.queries.daily_decision_v3 import DailyDecisionV3QueryFacade
from ditto_application.queries.evidence_contracts import (
    DecisionEvidenceReadModel,
    EvidenceArtifactReference,
    EvidencePayloadReadModel,
    EvidenceTemporalContext,
)

__all__ = ["DecisionEvidenceQueryFacade"]


def _error(code: str, reason: str, **details: object) -> AppQueryError:
    return AppQueryError(
        f"decision evidence failed closed: {reason}",
        details={"code": code, "reason": reason, **details},
    )


def _required(value: object, *, field_name: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise _error(
            "EVIDENCE_IDENTITY_REQUIRED",
            "missing_or_noncanonical_identity",
            field=field_name,
        )
    return value


def _timestamp(value: str | None, *, field_name: str) -> datetime:
    if value is None or not value.strip():
        raise _error(
            "EVIDENCE_PROVENANCE_INCOMPLETE",
            "missing_timestamp",
            field=field_name,
        )
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise _error(
            "EVIDENCE_PROVENANCE_INCOMPLETE",
            "invalid_timestamp",
            field=field_name,
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise _error(
            "EVIDENCE_PROVENANCE_INCOMPLETE",
            "timestamp_must_be_utc",
            field=field_name,
        )
    return parsed.astimezone(UTC)


class DecisionEvidenceQueryFacade:
    """Validate exact V3 identity and provenance without recomputing risk facts."""

    def __init__(self, *, daily_decision_v3: DailyDecisionV3QueryFacade) -> None:
        self._daily_decision_v3 = daily_decision_v3

    def get_evidence(
        self,
        *,
        strategy_id: str,
        strategy_version: str,
        trade_date: str,
        account_id: str,
        sleeve_id: str,
        context: EvidenceTemporalContext,
    ) -> DecisionEvidenceReadModel:
        """Return portfolio/risk/V3 evidence only when every boundary matches."""
        identities = {
            "strategy_id": _required(strategy_id, field_name="strategy_id"),
            "strategy_version": _required(
                strategy_version,
                field_name="strategy_version",
            ),
            "signal_date": _required(trade_date, field_name="trade_date"),
            "account_id": _required(account_id, field_name="account_id"),
            "sleeve_id": _required(sleeve_id, field_name="sleeve_id"),
        }
        report = self._daily_decision_v3.get_report_v3(
            strategy_id=identities["strategy_id"],
            trade_date=identities["signal_date"],
            account_id=identities["account_id"],
        )
        for field_name, expected in identities.items():
            actual = report.v2.identity.get(field_name)
            if actual != expected:
                raise _error(
                    "EVIDENCE_IDENTITY_MISMATCH",
                    "daily_decision_identity_mismatch",
                    field=field_name,
                    expected=expected,
                    actual=actual,
                )
        if report.readiness == "blocked":
            raise _error(
                "DECISION_EVIDENCE_NOT_READY",
                "daily_decision_v3_blocked",
                blocking_reasons=report.blocking_reasons,
            )
        provenance = report.provenance
        expected_times = {
            "decision_time": context.decision_time,
            "knowledge_cutoff": context.knowledge_cutoff,
            "publication_cutoff": context.publication_cutoff,
        }
        for field_name, expected in expected_times.items():
            actual = _timestamp(getattr(provenance, field_name), field_name=field_name)
            if actual != expected:
                raise _error(
                    "EVIDENCE_TEMPORAL_MISMATCH",
                    "daily_decision_temporal_mismatch",
                    field=field_name,
                )
        if (
            not provenance.source_snapshot_ids
            or len(set(provenance.source_snapshot_ids))
            != len(provenance.source_snapshot_ids)
            or context.source_snapshot_id not in provenance.source_snapshot_ids
        ):
            raise _error(
                "EVIDENCE_SNAPSHOT_MISMATCH",
                "daily_decision_snapshot_mismatch",
            )
        payload = EvidencePayloadReadModel.seal(
            schema_version=1,
            value={
                "v2": report.v2,
                "readiness": report.readiness,
                "blocking_reasons": report.blocking_reasons,
                "portfolio_construction": report.portfolio_construction,
                "tail_risk": report.tail_risk,
                "factor_risk": report.factor_risk,
                "stress_tests": report.stress_tests,
                "reconciliation": report.reconciliation,
                "provenance": report.provenance,
            },
        )
        reference = EvidenceArtifactReference(
            artifact_id=(
                "daily-decision-v3:"
                f"{identities['strategy_id']}:{identities['signal_date']}:"
                f"{identities['account_id']}:{identities['sleeve_id']}"
            ),
            artifact_kind="daily_decision_v3",
            content_hash=payload.payload_hash,
        )
        readiness: Literal["ready", "review"] = report.readiness
        return DecisionEvidenceReadModel(
            strategy_id=identities["strategy_id"],
            strategy_version=identities["strategy_version"],
            trade_date=identities["signal_date"],
            account_id=identities["account_id"],
            sleeve_id=identities["sleeve_id"],
            readiness=readiness,
            temporal_context=context,
            payload=payload,
            artifact_refs=(reference,),
            lineage=(
                f"strategy:{identities['strategy_id']}:v{identities['strategy_version']}",
                f"decision:{identities['signal_date']}:{identities['account_id']}",
                f"sleeve:{identities['sleeve_id']}",
                f"snapshot:{context.source_snapshot_id}",
            ),
        )
