"""Process-layer factor diagnostics projection over verified experiment evidence."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from typing import NoReturn, Protocol

from ditto_application.exceptions import AppProcessError
from ditto_application.processes.experiments._evidence_inputs import (
    project_snapshot_manifest,
    read_unique_preflight_detail,
)
from ditto_application.processes.experiments._factor_diagnostics_evidence import (
    FactorDiagnosticsArtifactEvidence,
)
from ditto_application.processes.experiments._walk_forward_evidence_collection import (
    WalkForwardEvidenceAssembler,
)
from ditto_application.processes.experiments.scheduler_store import (
    ExperimentSchedulerStoreProtocol,
)

__all__ = [
    "FactorDiagnosticsReader",
    "FactorDiagnosticsScope",
    "FactorDiagnosticsView",
    "PersistedFactorDiagnosticsSource",
]

_HASH_LENGTH = 64


def _error(code: str, reason: str, message: str, **details: object) -> NoReturn:
    raise AppProcessError(
        message,
        details={"code": code, "reason": reason, **details},
    )


def _text(value: object, *, field: str) -> str:
    if type(value) is not str or not value or value != value.strip():
        _error(
            "INVALID_DIAGNOSTIC_SCOPE",
            "factor_diagnostic_scope_invalid",
            "factor diagnostic scope is invalid",
            field=field,
        )
    return value


def _hash(value: object, *, field: str) -> str:
    text = _text(value, field=field)
    if len(text) != _HASH_LENGTH or any(
        character not in "0123456789abcdef" for character in text
    ):
        _error(
            "INVALID_DIAGNOSTIC_SCOPE",
            "factor_diagnostic_hash_invalid",
            "factor diagnostic scope is invalid",
            field=field,
        )
    return text


@dataclass(frozen=True, slots=True)
class FactorDiagnosticsScope:
    """Complete immutable request identity for one factor evaluation window."""

    factor_id: str
    snapshot_id: str
    start_date: date
    end_date: date
    registry_hash: str

    def __post_init__(self) -> None:
        """Validate the exact diagnostics request identity."""
        _text(self.factor_id, field="factor_id")
        _text(self.snapshot_id, field="snapshot_id")
        _hash(self.registry_hash, field="registry_hash")
        if (
            type(self.start_date) is not date
            or type(self.end_date) is not date
            or self.start_date > self.end_date
        ):
            _error(
                "INVALID_DIAGNOSTIC_SCOPE",
                "factor_diagnostic_window_invalid",
                "factor diagnostic window is invalid",
            )


class FactorDiagnosticsSource(Protocol):
    """Narrow verified-evidence lookup used by the process reader."""

    def list_factor_diagnostics(
        self,
        scope: FactorDiagnosticsScope,
    ) -> tuple[FactorDiagnosticsArtifactEvidence, ...]: ...


@dataclass(frozen=True, slots=True)
class FactorDiagnosticsView:
    """Application-owned API projection with immutable identity hashes."""

    factor_id: str
    snapshot_id: str
    snapshot_hash: str
    registry_hash: str
    start_date: date
    end_date: date
    provenance: Mapping[str, object]
    metrics: Mapping[str, object]
    artifact_id: str
    content_hash: str


@dataclass(frozen=True, slots=True)
class FactorDiagnosticsReader:
    """Validate exact scope and project one unambiguous diagnostic artifact."""

    source: FactorDiagnosticsSource
    expected_registry_hash: str

    def __post_init__(self) -> None:
        """Validate the configured registry identity."""
        _hash(self.expected_registry_hash, field="expected_registry_hash")

    def read(self, scope: FactorDiagnosticsScope) -> FactorDiagnosticsView | None:
        """Return exact diagnostics, ``None`` when the factor/scope is absent."""
        if type(scope) is not FactorDiagnosticsScope:
            _error(
                "INVALID_DIAGNOSTIC_SCOPE",
                "factor_diagnostic_scope_invalid",
                "factor diagnostic scope is invalid",
            )
        if scope.registry_hash != self.expected_registry_hash:
            _error(
                "SNAPSHOT_IDENTITY_MISMATCH",
                "factor_registry_hash_mismatch",
                "factor registry identity does not match",
                expected_registry_hash=self.expected_registry_hash,
                actual_registry_hash=scope.registry_hash,
            )
        matches = tuple(
            evidence
            for evidence in self.source.list_factor_diagnostics(scope)
            if _matches_scope(evidence, scope)
        )
        unique = {str(evidence.artifact_hash): evidence for evidence in matches}
        if not unique:
            return None
        if len(unique) != 1:
            _error(
                "INVALID_DIAGNOSTIC_SCOPE",
                "factor_diagnostic_scope_ambiguous",
                "factor diagnostic scope resolves to multiple artifacts",
                artifact_hashes=tuple(sorted(unique, key=str.encode)),
            )
        evidence = next(iter(unique.values()))
        projection = evidence.projection
        return FactorDiagnosticsView(
            factor_id=scope.factor_id,
            snapshot_id=scope.snapshot_id,
            snapshot_hash=str(evidence.snapshot_hash),
            registry_hash=scope.registry_hash,
            start_date=scope.start_date,
            end_date=scope.end_date,
            provenance=projection.provenance.canonical_payload(),
            metrics=dict(projection.values),
            artifact_id=evidence.artifact_ref,
            content_hash=str(evidence.artifact_hash),
        )


def _matches_scope(
    evidence: FactorDiagnosticsArtifactEvidence,
    scope: FactorDiagnosticsScope,
) -> bool:
    if type(evidence) is not FactorDiagnosticsArtifactEvidence:
        _error(
            "INVALID_DIAGNOSTIC_SCOPE",
            "factor_diagnostic_source_contract_invalid",
            "factor diagnostic source returned invalid evidence",
        )
    provenance = evidence.projection.provenance
    return (
        provenance.factor_id == scope.factor_id
        and str(evidence.snapshot_id) == scope.snapshot_id
        and evidence.test_window.start == scope.start_date
        and evidence.test_window.end == scope.end_date
        and provenance.evaluation_period
        == (scope.start_date.isoformat(), scope.end_date.isoformat())
        and provenance.catalog_snapshot_id == scope.snapshot_id
    )


@dataclass(frozen=True, slots=True)
class PersistedFactorDiagnosticsSource:
    """Find diagnostics through the same verified comparison assembly path."""

    scheduler_store: ExperimentSchedulerStoreProtocol
    walk_forward_assembler: WalkForwardEvidenceAssembler

    def list_factor_diagnostics(
        self,
        scope: FactorDiagnosticsScope,
    ) -> tuple[FactorDiagnosticsArtifactEvidence, ...]:
        """Scan only experiments bound to the requested immutable snapshot."""
        results: list[FactorDiagnosticsArtifactEvidence] = []
        for projection in self.scheduler_store.list_experiments():
            experiment_id = projection.record.experiment_id
            launch = self.scheduler_store.get_launch_spec(experiment_id)
            if launch is None or str(launch.snapshot_id) != scope.snapshot_id:
                continue
            events = self.scheduler_store.list_status_events(experiment_id)
            detail = read_unique_preflight_detail(events, experiment_id)
            collected = self.walk_forward_assembler.assemble(
                self.scheduler_store.load_snapshot(experiment_id),
                project_snapshot_manifest(detail),
            )
            results.extend(
                evidence
                for row in collected.source_rows
                if (evidence := row.factor_diagnostics) is not None
                and _matches_scope(evidence, scope)
            )
        return tuple(
            sorted(
                results,
                key=lambda item: (
                    str(item.experiment_id).encode(),
                    str(item.candidate_id).encode(),
                    str(item.fold_id).encode(),
                    str(item.artifact_hash),
                ),
            )
        )
