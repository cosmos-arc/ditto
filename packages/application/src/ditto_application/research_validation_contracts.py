"""Neutral validation-authority contracts shared by planning and adapters."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from typing import Protocol, cast

import orjson

from ditto_application.exceptions import AppProcessError
from ditto_application.research_certification_contracts import (
    ExperimentSnapshotIdentity,
    ResearchDatasetRequirement,
    is_canonical_content_hash,
    is_canonical_identity,
)
from ditto_application.research_validation_protocol import (
    ValidationProtocolRequest,
    canonical_validation_protocol_payload,
)

__all__ = [
    "ResearchValidationAuthorityEvidence",
    "ResearchValidationAuthorityProbe",
    "ResearchValidationAuthorityRequest",
    "ResearchValidationAuthorityResult",
    "RuntimeValidationEvidence",
    "protocol_sources_match_authority_bindings",
    "validation_authority_facts_match",
]


def _invalid(reason: str) -> AppProcessError:
    return AppProcessError(
        "research validation authority evidence is invalid",
        details={"code": "VALIDATION_AUTHORITY_INVALID", "reason": reason},
    )


def _canonical_id_tuple(value: object, *, field_name: str) -> tuple[str, ...]:
    if type(value) is not tuple:
        raise _invalid(f"invalid_{field_name}")
    values = cast("tuple[object, ...]", value)
    if (
        not values
        or not all(is_canonical_identity(item) for item in values)
        or len(set(values)) != len(values)
    ):
        raise _invalid(f"invalid_{field_name}")
    return tuple(sorted(cast("tuple[str, ...]", values)))


def _canonical_hash(payload: Mapping[str, object]) -> str:
    encoded = orjson.dumps(payload, option=orjson.OPT_SORT_KEYS)
    return hashlib.sha256(encoded).hexdigest()


def _canonical_dataset_bindings(
    value: object,
) -> tuple[ResearchDatasetRequirement, ...]:
    """Return exact, canonical per-dataset snapshot and PIT bindings."""
    if type(value) is not tuple:
        raise _invalid("invalid_authority_dataset_bindings")
    raw_bindings = cast("tuple[object, ...]", value)
    if not raw_bindings:
        raise _invalid("invalid_authority_dataset_bindings")
    bindings: list[ResearchDatasetRequirement] = []
    for raw_binding in raw_bindings:
        if type(raw_binding) is not ResearchDatasetRequirement:
            raise _invalid("invalid_authority_dataset_bindings")
        binding = raw_binding
        raw_snapshot_ids = cast("object", binding.expected_snapshot_ids)
        if type(raw_snapshot_ids) is not tuple:
            raise _invalid("invalid_authority_dataset_bindings")
        snapshot_ids = cast("tuple[object, ...]", raw_snapshot_ids)
        if (
            not is_canonical_identity(binding.dataset_id)
            or not snapshot_ids
            or not all(is_canonical_identity(item) for item in snapshot_ids)
            or len(set(snapshot_ids)) != len(snapshot_ids)
            or type(binding.requires_pit_universe) is not bool
            or type(binding.certified_from) is not date
        ):
            raise _invalid("invalid_authority_dataset_bindings")
        bindings.append(
            ResearchDatasetRequirement(
                binding.dataset_id,
                tuple(sorted(cast("tuple[str, ...]", snapshot_ids))),
                binding.requires_pit_universe,
                binding.certified_from,
            )
        )
    if len({binding.dataset_id for binding in bindings}) != len(bindings):
        raise _invalid("invalid_authority_dataset_bindings")
    return tuple(sorted(bindings, key=lambda item: item.dataset_id))


def _protocol_payload(protocol: ValidationProtocolRequest) -> Mapping[str, object]:
    try:
        return canonical_validation_protocol_payload(protocol)
    except Exception as exc:
        raise _invalid("invalid_authoritative_protocol") from exc


def _membership_projection_hash(
    protocol: ValidationProtocolRequest,
    *,
    source_artifact_hash: str,
) -> str:
    """Cross-bind the source membership artifact to its compiled month projection."""
    payload = _protocol_payload(protocol)
    instruments = cast("list[Mapping[str, object]]", payload["instrument_eligibility"])
    decisions = cast("list[Mapping[str, object]]", payload["coverage_decisions"])
    return _canonical_hash(
        {
            "source_artifact_hash": source_artifact_hash,
            "membership_source": payload["membership_source"],
            "required_input_start": payload["required_input_start"],
            "instrument_membership_intervals": [
                {
                    "instrument_id": item["instrument_id"],
                    "membership_intervals": item["membership_intervals"],
                }
                for item in instruments
            ],
            "monthly_membership_identities": [
                {
                    "month": item["month"],
                    "universe_instrument_count": item["universe_instrument_count"],
                    "universe_instrument_hash": item["universe_instrument_hash"],
                    "eligible_instrument_count": item["eligible_instrument_count"],
                    "eligible_instrument_hash": item["eligible_instrument_hash"],
                }
                for item in decisions
            ],
        }
    )


@dataclass(frozen=True, slots=True)
class RuntimeValidationEvidence:
    """Facts proven by every resolved candidate runtime, without guesses."""

    lane: str
    universe_id: str
    required_datasets: tuple[str, ...]
    max_lookback_sessions: int
    requires_pit_universe: bool
    forward_horizon_sessions: int | None = None
    holding_period_sessions: int | None = None
    execution_lag_sessions: int | None = None

    def __post_init__(self) -> None:
        """Reject guessed, partial, or non-canonical runtime validation facts."""
        if not is_canonical_identity(self.lane) or not is_canonical_identity(
            self.universe_id
        ):
            raise _invalid("invalid_runtime_validation_identity")
        object.__setattr__(
            self,
            "required_datasets",
            _canonical_id_tuple(
                cast("object", self.required_datasets),
                field_name="runtime_required_datasets",
            ),
        )
        if (
            type(self.max_lookback_sessions) is not int
            or self.max_lookback_sessions < 0
        ):
            raise _invalid("invalid_runtime_max_lookback")
        if type(self.requires_pit_universe) is not bool:
            raise _invalid("invalid_runtime_pit_requirement")
        semantics = (
            self.forward_horizon_sessions,
            self.holding_period_sessions,
            self.execution_lag_sessions,
        )
        if not (
            all(value is None for value in semantics)
            or all(type(value) is int and value >= 0 for value in semantics)
        ):
            raise _invalid("partial_runtime_isolation_semantics")

    def as_payload(self) -> Mapping[str, object]:
        """Return the canonical scalar payload used for runtime binding."""
        return {
            "lane": self.lane,
            "universe_id": self.universe_id,
            "required_datasets": list(self.required_datasets),
            "max_lookback_sessions": self.max_lookback_sessions,
            "requires_pit_universe": self.requires_pit_universe,
            "isolation": {
                "forward_horizon_sessions": self.forward_horizon_sessions,
                "holding_period_sessions": self.holding_period_sessions,
                "execution_lag_sessions": self.execution_lag_sessions,
            },
        }

    @property
    def payload_hash(self) -> str:
        """Return the canonical SHA-256 identity of these runtime facts."""
        return _canonical_hash(self.as_payload())

    @property
    def has_registered_isolation(self) -> bool:
        """Return whether all three runtime-owned isolation values are present."""
        return all(
            type(value) is int and value >= 0
            for value in (
                self.forward_horizon_sessions,
                self.holding_period_sessions,
                self.execution_lag_sessions,
            )
        )

    def is_well_formed(self) -> bool:
        """Revalidate exact runtime facts, including unregistered semantics."""
        try:
            semantics = (
                self.forward_horizon_sessions,
                self.holding_period_sessions,
                self.execution_lag_sessions,
            )
            return (
                type(self) is RuntimeValidationEvidence
                and is_canonical_identity(self.lane)
                and is_canonical_identity(self.universe_id)
                and self.required_datasets
                == _canonical_id_tuple(
                    cast("object", self.required_datasets),
                    field_name="runtime_required_datasets",
                )
                and type(self.max_lookback_sessions) is int
                and self.max_lookback_sessions >= 0
                and type(self.requires_pit_universe) is bool
                and (
                    all(value is None for value in semantics)
                    or all(type(value) is int and value >= 0 for value in semantics)
                )
            )
        except Exception:
            return False

    def is_valid(self) -> bool:
        """Require well-formed runtime facts with registered isolation semantics."""
        return self.is_well_formed() and self.has_registered_isolation


@dataclass(frozen=True, slots=True)
class ResearchValidationAuthorityRequest:
    """Authority input; ``declared_protocol`` is an untrusted caller assertion."""

    snapshot_identity: ExperimentSnapshotIdentity
    runtime_validation: RuntimeValidationEvidence | None
    declared_protocol: ValidationProtocolRequest
    declared_requirements: tuple[ResearchDatasetRequirement, ...]

    def __post_init__(self) -> None:
        """Canonicalize the untrusted requirement assertion by dataset identity."""
        raw_requirements = cast("object", self.declared_requirements)
        if type(raw_requirements) is not tuple:
            raise _invalid("invalid_declared_dataset_requirements")
        requirements = cast("tuple[object, ...]", raw_requirements)
        if (
            not requirements
            or not all(
                type(item) is ResearchDatasetRequirement for item in requirements
            )
            or len(
                {
                    cast("ResearchDatasetRequirement", item).dataset_id
                    for item in requirements
                }
            )
            != len(requirements)
        ):
            raise _invalid("invalid_declared_dataset_requirements")
        object.__setattr__(
            self,
            "declared_requirements",
            tuple(
                sorted(
                    cast("tuple[ResearchDatasetRequirement, ...]", requirements),
                    key=lambda item: item.dataset_id,
                )
            ),
        )

    def is_valid(self) -> bool:
        """Recheck exact request-owned assertions at the authority boundary."""
        try:
            return (
                type(self) is ResearchValidationAuthorityRequest
                and type(self.snapshot_identity) is ExperimentSnapshotIdentity
                and is_canonical_identity(self.snapshot_identity.snapshot_id)
                and is_canonical_content_hash(self.snapshot_identity.manifest_hash)
                and type(self.declared_protocol) is ValidationProtocolRequest
                and (
                    self.runtime_validation is None
                    or (
                        type(self.runtime_validation) is RuntimeValidationEvidence
                        and self.runtime_validation.is_well_formed()
                    )
                )
                and self.declared_requirements
                == _canonical_dataset_bindings(
                    cast("object", self.declared_requirements)
                )
            )
        except Exception:
            return False

    def fingerprint(self, *, declared_protocol_hash: str) -> str:
        """Hash every request fact before and after the untrusted probe call."""
        if not self.is_valid() or not is_canonical_content_hash(declared_protocol_hash):
            raise _invalid("invalid_validation_authority_request_fingerprint")
        runtime = self.runtime_validation
        return _canonical_hash(
            {
                "snapshot_identity": {
                    "snapshot_id": self.snapshot_identity.snapshot_id,
                    "manifest_hash": self.snapshot_identity.manifest_hash,
                },
                "runtime_validation": (
                    None if runtime is None else runtime.as_payload()
                ),
                "declared_protocol_hash": declared_protocol_hash,
                "declared_requirements": [
                    requirement.as_payload()
                    for requirement in self.declared_requirements
                ],
            }
        )


@dataclass(frozen=True, slots=True)
class ResearchValidationAuthorityEvidence:
    """One authoritative protocol bound to runtime and membership evidence."""

    protocol: ValidationProtocolRequest
    snapshot_identity: ExperimentSnapshotIdentity
    runtime_evidence_hash: str
    universe_membership_hash: str
    membership_projection_hash: str
    requires_pit_universe: bool
    dataset_bindings: tuple[ResearchDatasetRequirement, ...]
    payload_hash: str

    def __post_init__(self) -> None:
        """Reject authority evidence whose identities or content address drift."""
        raw_snapshot_identity = cast("object", self.snapshot_identity)
        if type(raw_snapshot_identity) is not ExperimentSnapshotIdentity:
            raise _invalid("invalid_authority_snapshot_identity")
        if type(self.requires_pit_universe) is not bool:
            raise _invalid("invalid_authority_pit_requirement")
        bindings = _canonical_dataset_bindings(cast("object", self.dataset_bindings))
        object.__setattr__(self, "dataset_bindings", bindings)
        if self.requires_pit_universe is not any(
            binding.requires_pit_universe for binding in bindings
        ):
            raise _invalid("authority_pit_binding_mismatch")
        if not is_canonical_content_hash(
            self.runtime_evidence_hash
        ) or not is_canonical_content_hash(self.universe_membership_hash):
            raise _invalid("invalid_authority_source_hash")
        if not is_canonical_content_hash(
            self.membership_projection_hash
        ) or self.membership_projection_hash != _membership_projection_hash(
            self.protocol,
            source_artifact_hash=self.universe_membership_hash,
        ):
            raise _invalid("authority_membership_projection_hash_mismatch")
        if not is_canonical_content_hash(self.payload_hash):
            raise _invalid("invalid_authority_payload_hash")
        if self.payload_hash != self._expected_payload_hash():
            raise _invalid("authority_payload_hash_mismatch")

    @classmethod
    def create(
        cls,
        *,
        protocol: ValidationProtocolRequest,
        snapshot_identity: ExperimentSnapshotIdentity,
        runtime_evidence_hash: str,
        universe_membership_hash: str,
        requires_pit_universe: bool,
        dataset_bindings: tuple[ResearchDatasetRequirement, ...],
    ) -> ResearchValidationAuthorityEvidence:
        """Construct content-addressed authority evidence from canonical facts."""
        canonical_bindings = _canonical_dataset_bindings(
            cast("object", dataset_bindings)
        )
        membership_projection_hash = _membership_projection_hash(
            protocol,
            source_artifact_hash=universe_membership_hash,
        )
        payload_hash = _canonical_hash(
            cls._payload(
                protocol=protocol,
                snapshot_identity=snapshot_identity,
                runtime_evidence_hash=runtime_evidence_hash,
                universe_membership_hash=universe_membership_hash,
                membership_projection_hash=membership_projection_hash,
                requires_pit_universe=requires_pit_universe,
                dataset_bindings=canonical_bindings,
            )
        )
        return cls(
            protocol=protocol,
            snapshot_identity=snapshot_identity,
            runtime_evidence_hash=runtime_evidence_hash,
            universe_membership_hash=universe_membership_hash,
            membership_projection_hash=membership_projection_hash,
            requires_pit_universe=requires_pit_universe,
            dataset_bindings=canonical_bindings,
            payload_hash=payload_hash,
        )

    @staticmethod
    def _payload(
        *,
        protocol: ValidationProtocolRequest,
        snapshot_identity: ExperimentSnapshotIdentity,
        runtime_evidence_hash: str,
        universe_membership_hash: str,
        membership_projection_hash: str,
        requires_pit_universe: bool,
        dataset_bindings: tuple[ResearchDatasetRequirement, ...],
    ) -> Mapping[str, object]:
        return {
            "protocol": _protocol_payload(protocol),
            "snapshot_identity": {
                "snapshot_id": snapshot_identity.snapshot_id,
                "manifest_hash": snapshot_identity.manifest_hash,
            },
            "runtime_evidence_hash": runtime_evidence_hash,
            "universe_membership_hash": universe_membership_hash,
            "membership_projection_hash": membership_projection_hash,
            "requires_pit_universe": requires_pit_universe,
            "dataset_bindings": [binding.as_payload() for binding in dataset_bindings],
        }

    def _expected_payload_hash(self) -> str:
        return _canonical_hash(
            self._payload(
                protocol=self.protocol,
                snapshot_identity=self.snapshot_identity,
                runtime_evidence_hash=self.runtime_evidence_hash,
                universe_membership_hash=self.universe_membership_hash,
                membership_projection_hash=self.membership_projection_hash,
                requires_pit_universe=self.requires_pit_universe,
                dataset_bindings=self.dataset_bindings,
            )
        )

    def is_valid(self) -> bool:
        """Recheck the content address after crossing an untrusted adapter."""
        try:
            raw_snapshot_identity = cast("object", self.snapshot_identity)
            return (
                type(self) is ResearchValidationAuthorityEvidence
                and type(raw_snapshot_identity) is ExperimentSnapshotIdentity
                and is_canonical_identity(self.snapshot_identity.snapshot_id)
                and is_canonical_content_hash(self.snapshot_identity.manifest_hash)
                and type(self.requires_pit_universe) is bool
                and is_canonical_content_hash(self.payload_hash)
                and is_canonical_content_hash(self.runtime_evidence_hash)
                and is_canonical_content_hash(self.universe_membership_hash)
                and is_canonical_content_hash(self.membership_projection_hash)
                and self.membership_projection_hash
                == _membership_projection_hash(
                    self.protocol,
                    source_artifact_hash=self.universe_membership_hash,
                )
                and self.dataset_bindings
                == _canonical_dataset_bindings(cast("object", self.dataset_bindings))
                and self.requires_pit_universe
                is any(
                    binding.requires_pit_universe for binding in self.dataset_bindings
                )
                and self.payload_hash == self._expected_payload_hash()
            )
        except Exception:
            return False

    @property
    def summaries(self) -> Mapping[str, Mapping[str, object]]:
        """Return all authority facts required by the persisted hard gate."""
        protocol = self.protocol
        protocol_payload = _protocol_payload(protocol)
        calendar_payload = cast(
            "Mapping[str, object]", protocol_payload["trading_calendar"]
        )
        sessions = protocol.trading_sessions
        calendar = protocol.trading_calendar
        isolation = protocol.isolation
        return {
            "calendar": {
                "content_hash": calendar.payload_hash,
                "calendar_id": calendar.calendar_id,
                "version": calendar.version,
                "source": calendar_payload["source"],
                "month_closures": calendar_payload["month_closures"],
                "session_count": len(sessions),
                "first_session": sessions[0].isoformat(),
                "last_session": sessions[-1].isoformat(),
                "planning_decision_date": protocol.planning_decision_date.isoformat(),
            },
            "membership": {
                "content_hash": self.universe_membership_hash,
                "projection_hash": self.membership_projection_hash,
                "research_snapshot_id": self.snapshot_identity.snapshot_id,
                "research_manifest_hash": self.snapshot_identity.manifest_hash,
                "requires_pit_universe": self.requires_pit_universe,
                "source": protocol_payload["membership_source"],
                "dataset_bindings": [
                    binding.as_payload() for binding in self.dataset_bindings
                ],
            },
            "eligibility": {
                "content_hash": _canonical_hash(
                    {
                        "strategy_eligible_start": protocol_payload[
                            "strategy_eligible_start"
                        ],
                        "required_input_start": protocol_payload[
                            "required_input_start"
                        ],
                        "last_complete_month": protocol_payload["last_complete_month"],
                        "coverage_decisions": protocol_payload["coverage_decisions"],
                        "instrument_eligibility": protocol_payload[
                            "instrument_eligibility"
                        ],
                    }
                ),
                "strategy_eligible_start": protocol.strategy_eligible_start.isoformat(),
                "required_input_start": protocol.required_input_start.isoformat(),
                "instrument_eligibility": protocol_payload["instrument_eligibility"],
            },
            "policy": {
                "policy_id": protocol.coverage_policy.policy_id,
                "version": protocol.coverage_policy.version,
                "min_eligible_instrument_count": (
                    protocol.coverage_policy.min_eligible_instrument_count
                ),
                "min_coverage_ratio_bps": (
                    protocol.coverage_policy.min_coverage_ratio_bps
                ),
                "evaluator_hash": protocol.coverage_policy.evaluator_hash,
            },
            "semantics": {
                "forward_horizon_sessions": isolation.forward_horizon_sessions,
                "holding_period_sessions": isolation.holding_period_sessions,
                "execution_lag_sessions": isolation.execution_lag_sessions,
            },
        }


def protocol_sources_match_authority_bindings(
    evidence: ResearchValidationAuthorityEvidence,
    runtime: RuntimeValidationEvidence,
) -> bool:
    """Cross-bind protocol sources to certified bindings and umbrella snapshot."""
    try:
        if (
            type(evidence) is not ResearchValidationAuthorityEvidence
            or type(runtime) is not RuntimeValidationEvidence
        ):
            return False
        protocol = evidence.protocol
        bindings = {
            binding.dataset_id: binding for binding in evidence.dataset_bindings
        }
        certification_starts = tuple(
            binding.certified_from for binding in evidence.dataset_bindings
        )
        if not certification_starts or not all(
            type(value) is date for value in certification_starts
        ):
            return False
        latest_certified_from = max(cast("tuple[date, ...]", certification_starts))
        calendar = protocol.trading_calendar
        membership = protocol.membership_source
        calendar_binding = bindings.get(calendar.dataset_id)
        membership_binding = bindings.get(membership.dataset_id)
        umbrella_manifest = evidence.snapshot_identity.manifest_hash
        return (
            protocol.required_input_start == latest_certified_from
            and calendar_binding is not None
            and calendar.snapshot_id in calendar_binding.expected_snapshot_ids
            and membership_binding is not None
            and membership_binding.requires_pit_universe is True
            and membership.snapshot_id in membership_binding.expected_snapshot_ids
            and membership.universe_id == runtime.universe_id
            and calendar.manifest_hash == umbrella_manifest
            and membership.manifest_hash == umbrella_manifest
        )
    except Exception:
        return False


def validation_authority_facts_match(
    evidence: ResearchValidationAuthorityEvidence,
    runtime: RuntimeValidationEvidence,
    *,
    snapshot_identity: ExperimentSnapshotIdentity,
    dataset_requirements: tuple[ResearchDatasetRequirement, ...],
) -> bool:
    """Replay every live runtime/declaration trust cross-link without I/O."""
    try:
        if (
            type(evidence) is not ResearchValidationAuthorityEvidence
            or type(runtime) is not RuntimeValidationEvidence
            or type(snapshot_identity) is not ExperimentSnapshotIdentity
            or type(dataset_requirements) is not tuple
        ):
            return False
        declared_bindings = _canonical_dataset_bindings(
            cast("object", dataset_requirements)
        )
        authority_binding_identity = tuple(
            (
                item.dataset_id,
                item.expected_snapshot_ids,
                item.requires_pit_universe,
                item.certified_from,
            )
            for item in evidence.dataset_bindings
        )
        declared_binding_identity = tuple(
            (
                item.dataset_id,
                item.expected_snapshot_ids,
                item.requires_pit_universe,
                item.certified_from,
            )
            for item in declared_bindings
        )
        declared_datasets = tuple(item.dataset_id for item in declared_bindings)
        authority_datasets = tuple(
            item.dataset_id for item in evidence.dataset_bindings
        )
        declared_pit = any(item.requires_pit_universe for item in declared_bindings)
        protocol = evidence.protocol
        runtime_isolation = (
            runtime.forward_horizon_sessions,
            runtime.holding_period_sessions,
            runtime.execution_lag_sessions,
        )
        authority_isolation = (
            protocol.isolation.forward_horizon_sessions,
            protocol.isolation.holding_period_sessions,
            protocol.isolation.execution_lag_sessions,
        )
        return (
            evidence.snapshot_identity.snapshot_id == snapshot_identity.snapshot_id
            and evidence.snapshot_identity.manifest_hash
            == snapshot_identity.manifest_hash
            and authority_datasets == runtime.required_datasets == declared_datasets
            and authority_binding_identity == declared_binding_identity
            and evidence.requires_pit_universe
            is runtime.requires_pit_universe
            is declared_pit
            and runtime_isolation == authority_isolation
            and protocol_sources_match_authority_bindings(evidence, runtime)
            and all(
                item.warmup_sessions == runtime.max_lookback_sessions
                for item in protocol.instrument_eligibility
            )
        )
    except Exception:
        return False


@dataclass(frozen=True, slots=True)
class ResearchValidationAuthorityResult:
    """Typed fail-closed result returned by the validation authority."""

    ready: bool
    code: str | None
    reason: str | None
    remediation: str | None
    evidence: ResearchValidationAuthorityEvidence | None


class ResearchValidationAuthorityProbe(Protocol):
    """Derive validation authority without launching or writing."""

    def probe(
        self,
        request: ResearchValidationAuthorityRequest,
    ) -> ResearchValidationAuthorityResult:
        """Return one authoritative protocol or an explicit blocker."""
        ...
