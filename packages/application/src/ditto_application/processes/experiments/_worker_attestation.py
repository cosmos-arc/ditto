"""Verified research backtest build attestation contracts for the fold worker."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum

from ditto_application.exceptions import AppProcessError
from ditto_application.processes.execution.backtest_process import BacktestService
from ditto_application.processes.experiments.backtest_service_wiring import (
    ClosedBacktestServiceGraph,
    require_closed_backtest_service,
)
from ditto_application.processes.experiments.execution_bundle import (
    BacktestExecutionConfigBinding,
    BaselineExecutorBinding,
    CodeEnvironmentLock,
    ResearchExecutionAudit,
    ResearchSnapshotBinding,
    StrategyExecutionBinding,
)
from ditto_application.processes.experiments.scheduler_store import ContentHash

__all__ = [
    "ResearchBacktestBuildAttestation",
    "ResearchBacktestBuildSource",
    "VerifiedResearchBacktestBuild",
    "require_verified_research_backtest_build_seal",
    "seal_verified_research_backtest_build",
]


def _attestation_error(reason: str, **details: object) -> AppProcessError:
    return AppProcessError(
        "research experiment worker contract is invalid",
        details={
            "code": "REPRODUCIBILITY_FAILED",
            "reason": reason,
            **details,
        },
    )


class ResearchBacktestBuildSource(StrEnum):
    """Declared resolution path for an attested research backtest build."""

    FROZEN_AUDIT_BUNDLE = "frozen_audit_bundle"
    PROVIDER_LATEST = "provider_latest"
    CATALOG_LATEST = "catalog_latest"


@dataclass(frozen=True, slots=True)
class ResearchBacktestBuildAttestation:
    """Typed evidence proving a BacktestService was built from one audit."""

    source: ResearchBacktestBuildSource
    audit_bundle_hash: ContentHash
    reproduction_fingerprint: ContentHash
    backtest_run_id: str
    strategy: StrategyExecutionBinding | BaselineExecutorBinding
    snapshot: ResearchSnapshotBinding
    execution_config: BacktestExecutionConfigBinding
    execution_config_hash: ContentHash
    feed_manifest_hash: str
    policy_hash: str
    model_evidence_hash: ContentHash
    benchmark_binding_hash: ContentHash | None
    environment: CodeEnvironmentLock

    @classmethod
    def from_audit(
        cls,
        audit: ResearchExecutionAudit,
    ) -> ResearchBacktestBuildAttestation:
        """Build the only attestation accepted by the fold runner."""
        semantics = audit.semantics
        backtest = semantics.backtest
        benchmark_hash = (
            None if backtest.benchmark is None else backtest.benchmark.canonical_hash
        )
        return cls(
            source=ResearchBacktestBuildSource.FROZEN_AUDIT_BUNDLE,
            audit_bundle_hash=audit.bundle_hash,
            reproduction_fingerprint=audit.reproduction_fingerprint,
            backtest_run_id=audit.backtest_run_id,
            strategy=semantics.strategy,
            snapshot=semantics.snapshot,
            execution_config=backtest,
            execution_config_hash=backtest.canonical_hash,
            feed_manifest_hash=backtest.data_feed_manifest_hash,
            policy_hash=semantics.policy.canonical_hash,
            model_evidence_hash=backtest.policy_model_evidence_hash,
            benchmark_binding_hash=benchmark_hash,
            environment=semantics.environment,
        )


@dataclass(frozen=True, slots=True)
class VerifiedResearchBacktestBuild:
    """Backtest service plus exact construction evidence for runner validation."""

    service: BacktestService
    attestation: ResearchBacktestBuildAttestation
    graph: ClosedBacktestServiceGraph
    construction_seal: object | None = field(
        default=None,
        init=False,
        repr=False,
        compare=False,
    )


_RESEARCH_BACKTEST_BUILD_SEAL = object()


def seal_verified_research_backtest_build(
    *,
    service: BacktestService,
    attestation: ResearchBacktestBuildAttestation,
    graph: ClosedBacktestServiceGraph,
    audit: ResearchExecutionAudit,
    external_should_stop: Callable[[], bool],
) -> VerifiedResearchBacktestBuild:
    """Construct one official build only after full audit-bound verification."""
    if (
        type(attestation) is not ResearchBacktestBuildAttestation
        or attestation != ResearchBacktestBuildAttestation.from_audit(audit)
    ):
        raise _attestation_error("research_backtest_attestation_drift")
    if type(service) is not BacktestService or graph.service is not service:
        raise _attestation_error("invalid_research_backtest_service_graph")
    require_closed_backtest_service(
        graph,
        expected_audit=audit,
        expected_should_stop=external_should_stop,
    )
    build = VerifiedResearchBacktestBuild(service, attestation, graph)
    object.__setattr__(
        build,
        "construction_seal",
        _RESEARCH_BACKTEST_BUILD_SEAL,
    )
    return build


def require_verified_research_backtest_build_seal(
    build: VerifiedResearchBacktestBuild,
) -> None:
    """Reject builds that did not pass the official construction boundary."""
    if build.construction_seal is not _RESEARCH_BACKTEST_BUILD_SEAL:
        raise _attestation_error("unsealed_research_backtest_build")
