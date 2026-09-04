"""PIT-bound Agent evidence over deterministic portfolio comparison queries."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from decimal import Decimal
from enum import Enum
from typing import Protocol, cast
from zoneinfo import ZoneInfo

from ditto_strategy.models import ArtifactKind, StrategyArtifactRecord

from ditto_application.catalog_freshness import aggregate_source_snapshot_ids
from ditto_application.exceptions import AppQueryError
from ditto_application.queries.evidence_contracts import (
    EvidenceArtifactReference,
    EvidencePayloadReadModel,
    EvidenceTemporalContext,
)
from ditto_application.queries.portfolio_comparison import (
    PortfolioComparisonQueryPort,
    PortfolioComparisonRequest,
    PortfolioComparisonView,
)
from ditto_application.queries.portfolio_comparison_evidence_contracts import (
    PortfolioComparisonEvidenceIdentity,
    PortfolioComparisonEvidenceReadModel,
    PortfolioScenarioEvidenceReadModel,
    PortfolioScenarioEvidenceRequest,
)
from ditto_application.queries.portfolio_scenario import (
    PortfolioScenarioPreviewPort,
    PortfolioScenarioPreviewView,
    PortfolioScenarioRequest,
)
from ditto_application.signal_package_contract import (
    canonical_signal_package_metadata,
    verify_signal_package_metadata,
)

__all__ = [
    "PortfolioComparisonEvidenceQueryFacade",
]

_SHANGHAI = ZoneInfo("Asia/Shanghai")
_SHA256_PREFIX = "sha256:"


class _SignalPackageReader(Protocol):
    def list_by_strategy(self, strategy_id: str) -> list[StrategyArtifactRecord]: ...


@dataclass(frozen=True, kw_only=True)
class _ResolvedPackage:
    request: PortfolioComparisonRequest
    artifact: EvidenceArtifactReference
    source_snapshot_set_id: str


def _error(code: str, reason: str, **details: object) -> AppQueryError:
    return AppQueryError(
        f"portfolio comparison evidence failed closed: {reason}",
        details={"code": code, "reason": reason, **details},
    )


def _canonical_identity(value: PortfolioComparisonEvidenceIdentity) -> None:
    for field_name, item in value.__dict__.items():
        if not item or item.strip() != item:
            raise _error(
                "PORTFOLIO_EVIDENCE_IDENTITY_INVALID",
                "portfolio identity is missing or noncanonical",
                field=field_name,
            )


def _exact_package(
    reader: _SignalPackageReader,
    identity: PortfolioComparisonEvidenceIdentity,
) -> StrategyArtifactRecord:
    matches = tuple(
        artifact
        for artifact in reader.list_by_strategy(identity.strategy_id)
        if artifact.artifact_id == identity.model_portfolio_id
        and artifact.artifact_type is ArtifactKind.SIGNAL_PACKAGE
        and artifact.status == "active"
    )
    if len(matches) != 1:
        raise _error(
            "PORTFOLIO_EVIDENCE_PACKAGE_NOT_FOUND",
            "exact active Signal Package was not found",
        )
    artifact = matches[0]
    if not verify_signal_package_metadata(artifact.metadata):
        raise _error(
            "PORTFOLIO_EVIDENCE_PACKAGE_INVALID",
            "Signal Package checksum verification failed",
        )
    return artifact


def _snapshot_ids(metadata: Mapping[str, object]) -> tuple[str, ...]:
    raw = metadata.get("dataset_snapshot_ids")
    if not isinstance(raw, Mapping):
        raise _error(
            "PORTFOLIO_EVIDENCE_LINEAGE_INVALID",
            "Signal Package source snapshots are absent",
        )
    raw_mapping = cast("Mapping[object, object]", raw)
    values = tuple(sorted(str(item) for item in raw_mapping.values()))
    if not values or any(not item or item.strip() != item for item in values):
        raise _error(
            "PORTFOLIO_EVIDENCE_LINEAGE_INVALID",
            "Signal Package source snapshots are invalid",
        )
    if len(set(values)) != len(values):
        raise _error(
            "PORTFOLIO_EVIDENCE_LINEAGE_INVALID",
            "Signal Package source snapshots are ambiguous",
        )
    return values


def _artifact_reference(
    artifact: StrategyArtifactRecord,
    metadata: Mapping[str, object],
) -> EvidenceArtifactReference:
    checksum = metadata.get("checksum")
    if not isinstance(checksum, str) or not checksum.startswith(_SHA256_PREFIX):
        raise _error(
            "PORTFOLIO_EVIDENCE_PACKAGE_INVALID",
            "Signal Package content hash is absent",
        )
    return EvidenceArtifactReference(
        artifact_id=artifact.artifact_id,
        artifact_kind="signal_package",
        content_hash=checksum.removeprefix(_SHA256_PREFIX),
    )


def _resolve_package(
    *,
    reader: _SignalPackageReader,
    identity: PortfolioComparisonEvidenceIdentity,
    context: EvidenceTemporalContext,
) -> _ResolvedPackage:
    _canonical_identity(identity)
    artifact = _exact_package(reader, identity)
    metadata = canonical_signal_package_metadata(artifact.metadata)
    signal_date = metadata.get("signal_date")
    host_date = context.decision_time.astimezone(_SHANGHAI).date().isoformat()
    if signal_date != host_date:
        raise _error(
            "PORTFOLIO_EVIDENCE_AS_OF_MISMATCH",
            "Signal Package date differs from host decision date",
            package_as_of=signal_date,
            host_as_of=host_date,
        )
    snapshots = _snapshot_ids(metadata)
    snapshot_set_id = aggregate_source_snapshot_ids(snapshots)
    if snapshot_set_id is None or snapshot_set_id != context.source_snapshot_id:
        raise _error(
            "PORTFOLIO_EVIDENCE_SNAPSHOT_MISMATCH",
            "Signal Package snapshot set differs from host snapshot set",
            expected=snapshot_set_id,
            actual=context.source_snapshot_id,
        )
    return _ResolvedPackage(
        request=PortfolioComparisonRequest(
            strategy_id=identity.strategy_id,
            model_portfolio_id=identity.model_portfolio_id,
            paper_account_id=identity.paper_account_id,
            manual_account_id=identity.manual_account_id,
            paper_session_id=identity.paper_session_id,
            as_of=host_date,
            knowledge_cutoff=context.knowledge_cutoff,
            publication_cutoff=context.publication_cutoff,
            source_snapshot_ids=snapshots,
        ),
        artifact=_artifact_reference(artifact, metadata),
        source_snapshot_set_id=snapshot_set_id,
    )


def _evidence_value(value: object) -> object:
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise _error(
                "PORTFOLIO_EVIDENCE_VALUE_INVALID",
                "portfolio evidence contains a non-finite Decimal",
            )
        return str(value)
    if isinstance(value, Enum):
        return _evidence_value(value.value)
    if isinstance(value, Mapping):
        raw_mapping = cast("Mapping[object, object]", value)
        return {str(key): _evidence_value(item) for key, item in raw_mapping.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        sequence = cast("Sequence[object]", value)
        return tuple(_evidence_value(item) for item in sequence)
    if isinstance(value, float) and not math.isfinite(value):
        raise _error(
            "PORTFOLIO_EVIDENCE_VALUE_INVALID",
            "portfolio evidence contains a non-finite float",
        )
    return value


def _payload(
    value: PortfolioComparisonView | PortfolioScenarioPreviewView,
    *,
    additions: Mapping[str, object] | None = None,
) -> EvidencePayloadReadModel:
    raw = asdict(value)
    if additions is not None:
        raw.update(additions)
    mapped = _evidence_value(raw)
    if not isinstance(mapped, Mapping):
        raise _error(
            "PORTFOLIO_EVIDENCE_VALUE_INVALID",
            "portfolio evidence payload is not an object",
        )
    return EvidencePayloadReadModel.seal(
        schema_version=1,
        value=cast("Mapping[str, object]", mapped),
    )


def _lineage(
    resolved: _ResolvedPackage,
    *,
    valuation_snapshot_id: str,
) -> tuple[str, ...]:
    return (
        f"signal-package:{resolved.artifact.artifact_id}",
        f"valuation:{valuation_snapshot_id}",
        *(f"snapshot:{item}" for item in resolved.request.source_snapshot_ids),
    )


class PortfolioComparisonEvidenceQueryFacade:
    """Authenticate package lineage before exposing comparison or preview facts."""

    def __init__(
        self,
        *,
        artifact_reader: _SignalPackageReader,
        comparison: PortfolioComparisonQueryPort,
        scenario: PortfolioScenarioPreviewPort,
    ) -> None:
        self._artifact_reader = artifact_reader
        self._comparison = comparison
        self._scenario = scenario

    def get_comparison_evidence(
        self,
        *,
        identity: PortfolioComparisonEvidenceIdentity,
        context: EvidenceTemporalContext,
    ) -> PortfolioComparisonEvidenceReadModel:
        """Seal only deterministic values from the application comparison query."""
        resolved = _resolve_package(
            reader=self._artifact_reader,
            identity=identity,
            context=context,
        )
        comparison = self._comparison.get(resolved.request)
        return PortfolioComparisonEvidenceReadModel(
            identity=identity,
            as_of=comparison.as_of,
            valuation_snapshot_id=comparison.valuation_snapshot_id,
            source_snapshot_set_id=resolved.source_snapshot_set_id,
            source_snapshot_ids=comparison.source_snapshot_ids,
            temporal_context=context,
            payload=_payload(comparison),
            artifact_refs=(resolved.artifact,),
            lineage=_lineage(
                resolved,
                valuation_snapshot_id=comparison.valuation_snapshot_id,
            ),
        )

    def preview_scenario(
        self,
        *,
        request: PortfolioScenarioEvidenceRequest,
        context: EvidenceTemporalContext,
    ) -> PortfolioScenarioEvidenceReadModel:
        """Seal a deterministic scenario preview without exposing an apply path."""
        resolved = _resolve_package(
            reader=self._artifact_reader,
            identity=request.identity,
            context=context,
        )
        preview = self._scenario.preview(
            PortfolioScenarioRequest(
                comparison=resolved.request,
                baseline_kind=request.baseline_kind,
                excluded_instrument_ids=request.excluded_instrument_ids,
                max_position_weight=request.max_position_weight,
                cash_reserve_weight=request.cash_reserve_weight,
                market_shock=request.market_shock,
                industry_shocks=request.industry_shocks,
            )
        )
        return PortfolioScenarioEvidenceReadModel(
            identity=request.identity,
            baseline_kind=request.baseline_kind,
            as_of=preview.risk.as_of,
            valuation_snapshot_id=preview.risk.valuation_snapshot_id,
            source_snapshot_set_id=resolved.source_snapshot_set_id,
            source_snapshot_ids=preview.risk.source_snapshot_ids,
            temporal_context=context,
            payload=_payload(
                preview,
                additions={
                    "scenario_inputs": {
                        "excluded_instrument_ids": tuple(
                            sorted(request.excluded_instrument_ids)
                        ),
                        "max_position_weight": request.max_position_weight,
                        "cash_reserve_weight": request.cash_reserve_weight,
                        "market_shock": request.market_shock,
                        "industry_shocks": request.industry_shocks or {},
                    }
                },
            ),
            artifact_refs=(resolved.artifact,),
            lineage=_lineage(
                resolved,
                valuation_snapshot_id=preview.risk.valuation_snapshot_id,
            ),
        )
