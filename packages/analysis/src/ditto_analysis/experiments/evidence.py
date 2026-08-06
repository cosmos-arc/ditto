"""
Immutable review evidence bundle for governed R3 promotion.

A review packet freezes the complete lineage, reproduction hashes, gate
results, comparison/R1 impact hashes, holdout and selection evidence, plus the
candidate rationale. Once assembled the payload is read-only and the bundle
hash lets promotion refuse any stale evidence drift.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from math import isfinite
from typing import cast

from ditto_analysis.experiments.gates import GateEvaluation, GateLayer, GateOutcome
from ditto_analysis.experiments.models import ContentHash
from ditto_analysis.experiments.persistence import canonical_payload

__all__ = [
    "REVIEW_PACKET_SCHEMA_VERSION",
    "REVIEW_PACKET_SCHEMA_VERSION_V1",
    "REVIEW_PACKET_SCHEMA_VERSION_V2",
    "REVIEW_PACKET_SELECTION_TRACE_KINDS",
    "REVIEW_PACKET_SELECTION_TRACE_KINDS_V2",
    "ReviewExposureWeight",
    "ReviewPacket",
    "ReviewPacketLineage",
    "ReviewSelectionExposure",
    "SelectionTraceArtifactRef",
    "review_packet_from_payload",
]

REVIEW_PACKET_SCHEMA_VERSION_V1 = 1
REVIEW_PACKET_SCHEMA_VERSION_V2 = 2
REVIEW_PACKET_SCHEMA_VERSION = 3
REVIEW_PACKET_SELECTION_TRACE_KINDS_V2 = (
    "fold_selection_trace_candidate_universe_v1",
    "fold_selection_trace_candidate_exclusions_v1",
    "fold_selection_trace_candidate_selections_v1",
    "fold_selection_trace_factor_contributions_v1",
)
REVIEW_PACKET_SELECTION_TRACE_KINDS = (
    *REVIEW_PACKET_SELECTION_TRACE_KINDS_V2,
    "fold_selection_trace_exposures_v1",
)
_SUPPORTED_REVIEW_PACKET_SCHEMA_VERSIONS = frozenset(
    {
        REVIEW_PACKET_SCHEMA_VERSION_V1,
        REVIEW_PACKET_SCHEMA_VERSION_V2,
        REVIEW_PACKET_SCHEMA_VERSION,
    }
)


@dataclass(frozen=True, slots=True)
class ReviewPacketLineage:
    """Experiment/candidate/fold/attempt identity carried by a bundle."""

    experiment_id: str
    candidate_id: str | None
    fold_ids: tuple[str, ...]
    attempt_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        """Reject empty or mistyped lineage identity."""
        if type(self.experiment_id) is not str or not self.experiment_id:
            raise ValueError("lineage experiment_id must be a non-empty string")
        if self.candidate_id is not None and (
            type(self.candidate_id) is not str or not self.candidate_id
        ):
            raise ValueError("lineage candidate_id must be a non-empty string or None")
        if type(self.fold_ids) is not tuple or not self.fold_ids:
            raise ValueError("lineage fold_ids must be a non-empty tuple")
        if type(self.attempt_ids) is not tuple or not self.attempt_ids:
            raise ValueError("lineage attempt_ids must be a non-empty tuple")

    def canonical_payload(self) -> dict[str, object]:
        """Return the JSON-ready lineage identity payload."""
        return {
            "experiment_id": self.experiment_id,
            "candidate_id": self.candidate_id,
            "fold_ids": list(self.fold_ids),
            "attempt_ids": list(self.attempt_ids),
        }


def _require_hash(value: object, field_name: str) -> ContentHash:
    if type(value) is not ContentHash:
        raise ValueError(f"{field_name} must be a ContentHash")
    return value


@dataclass(frozen=True, slots=True)
class SelectionTraceArtifactRef:
    """One verified positive reference to an attempt-scoped trace fact."""

    artifact_kind: str
    artifact_id: str
    content_hash: ContentHash

    def __post_init__(self) -> None:
        """Reject erased, untyped, or non-trace artifact identity."""
        if (
            type(self.artifact_kind) is not str
            or self.artifact_kind not in REVIEW_PACKET_SELECTION_TRACE_KINDS
        ):
            raise ValueError("unsupported selection trace artifact_kind")
        if (
            type(self.artifact_id) is not str
            or not self.artifact_id
            or self.artifact_id != self.artifact_id.strip()
        ):
            raise ValueError("selection trace artifact_id must be non-empty")
        _require_hash(self.content_hash, "selection trace content_hash")

    def canonical_payload(self) -> dict[str, object]:
        """Return the JSON-ready positive artifact identity."""
        return {
            "artifact_kind": self.artifact_kind,
            "artifact_id": self.artifact_id,
            "content_hash": str(self.content_hash),
        }


@dataclass(frozen=True, slots=True)
class ReviewExposureWeight:
    """One canonical exposure dimension key and its mean selected weight."""

    key: str
    weight: float

    def __post_init__(self) -> None:
        """Reject ambiguous exposure keys and weights."""
        if type(self.key) is not str or not self.key or self.key != self.key.strip():
            raise ValueError("exposure weight key must be non-empty and unpadded")
        raw_weight = cast("object", self.weight)
        if (
            type(raw_weight) not in (int, float)
            or not isfinite(float(self.weight))
            or self.weight < 0
        ):
            raise ValueError("exposure weight must be finite and non-negative")

    def canonical_payload(self) -> dict[str, object]:
        """Return the JSON-ready dimension weight."""
        return {"key": self.key, "weight": float(self.weight)}


@dataclass(frozen=True, slots=True)
class ReviewSelectionExposure:
    """Selected candidate's aggregated exposure plus its positive artifact refs."""

    applicability: str
    lane: str
    industry_weights: tuple[ReviewExposureWeight, ...]
    size_bucket_weights: tuple[ReviewExposureWeight, ...]
    artifact_refs: tuple[SelectionTraceArtifactRef, ...]

    def __post_init__(self) -> None:
        """Validate lane applicability and canonical aggregate weights."""
        if (self.applicability, self.lane) not in {
            ("APPLICABLE", "STOCK_LANE"),
            ("NOT_APPLICABLE", "ETF_LANE"),
        }:
            raise ValueError("selection exposure applicability/lane is invalid")
        for field_name in ("industry_weights", "size_bucket_weights"):
            values = cast("object", getattr(self, field_name))
            if type(values) is not tuple or any(
                type(item) is not ReviewExposureWeight
                for item in cast("tuple[object, ...]", values)
            ):
                raise ValueError(f"{field_name} must be a typed tuple")
            typed_values = cast("tuple[ReviewExposureWeight, ...]", values)
            keys = tuple(item.key for item in typed_values)
            if len(set(keys)) != len(keys):
                raise ValueError(f"{field_name} contains duplicate keys")
        if type(self.artifact_refs) is not tuple or any(
            type(ref) is not SelectionTraceArtifactRef
            or ref.artifact_kind != "fold_selection_trace_exposures_v1"
            for ref in cast("tuple[object, ...]", self.artifact_refs)
        ):
            raise ValueError("selection exposure artifact_refs are invalid")
        if not self.artifact_refs:
            raise ValueError("selection exposure requires positive artifact refs")
        if self.applicability == "APPLICABLE":
            if not self.industry_weights or not self.size_bucket_weights:
                raise ValueError("applicable selection exposure cannot be empty")
            return
        if self.industry_weights or self.size_bucket_weights:
            raise ValueError("not-applicable selection exposure cannot carry weights")

    def canonical_payload(self) -> dict[str, object]:
        """Return the JSON-ready immutable exposure summary."""
        return {
            "applicability": self.applicability,
            "lane": self.lane,
            "industry_weights": [
                item.canonical_payload() for item in self.industry_weights
            ],
            "size_bucket_weights": [
                item.canonical_payload() for item in self.size_bucket_weights
            ],
            "artifact_refs": [ref.canonical_payload() for ref in self.artifact_refs],
        }


@dataclass(frozen=True, slots=True)
class ReviewPacket:
    """Immutable promotion evidence bundle; hash refuses stale evidence."""

    schema_version: int
    lineage: ReviewPacketLineage
    spec_hash: ContentHash
    resolved_spec_hash: ContentHash
    parameter_hash: ContentHash
    snapshot_hash: ContentHash
    registry_hash: ContentHash
    objective_payload_hash: ContentHash
    gate_evaluations: tuple[GateEvaluation, ...]
    comparison_payload_hash: ContentHash | None
    r1_impact_payload_hash: ContentHash | None
    selection_evidence_artifact_id: str | None
    holdout_claim_id: str | None
    candidate_rationale: str
    selection_trace_artifact_refs: tuple[SelectionTraceArtifactRef, ...] = ()
    selection_exposure: ReviewSelectionExposure | None = None

    def __post_init__(self) -> None:  # noqa: C901
        """Validate schema version, reproduction hashes, and rationale."""
        if (
            type(self.schema_version) is not int
            or self.schema_version not in _SUPPORTED_REVIEW_PACKET_SCHEMA_VERSIONS
        ):
            raise ValueError("unsupported review packet schema_version")
        for field_name in (
            "spec_hash",
            "resolved_spec_hash",
            "parameter_hash",
            "snapshot_hash",
            "registry_hash",
            "objective_payload_hash",
        ):
            _require_hash(getattr(self, field_name), field_name)
        if self.comparison_payload_hash is not None:
            _require_hash(self.comparison_payload_hash, "comparison_payload_hash")
        if self.r1_impact_payload_hash is not None:
            _require_hash(self.r1_impact_payload_hash, "r1_impact_payload_hash")
        if type(self.gate_evaluations) is not tuple:
            raise ValueError("gate_evaluations must be a tuple")
        if (
            type(self.candidate_rationale) is not str
            or not self.candidate_rationale
            or self.candidate_rationale != self.candidate_rationale.strip()
        ):
            raise ValueError("candidate_rationale must be a non-empty unpadded string")
        raw_refs: object = self.selection_trace_artifact_refs
        if type(raw_refs) is not tuple or any(
            type(item) is not SelectionTraceArtifactRef
            for item in cast("tuple[object, ...]", raw_refs)
        ):
            raise ValueError("selection_trace_artifact_refs must be a typed tuple")
        if self.schema_version == REVIEW_PACKET_SCHEMA_VERSION_V1:
            if (
                self.selection_trace_artifact_refs
                or self.selection_exposure is not None
            ):
                raise ValueError("v1 review packets cannot carry selection trace refs")
            return
        if self.schema_version == REVIEW_PACKET_SCHEMA_VERSION_V2:
            if self.selection_exposure is not None:
                raise ValueError("v2 review packets cannot carry selection exposure")
            self._validate_selection_trace_refs(
                kinds=REVIEW_PACKET_SELECTION_TRACE_KINDS_V2,
                version_label="v2",
            )
            return
        if (
            self.selection_exposure is not None
            and type(self.selection_exposure) is not ReviewSelectionExposure
        ):
            raise ValueError("v3 review packet selection exposure is invalid")
        self._validate_selection_trace_refs(
            kinds=REVIEW_PACKET_SELECTION_TRACE_KINDS,
            version_label="v3",
        )

    def _validate_selection_trace_refs(
        self,
        *,
        kinds: tuple[str, ...],
        version_label: str,
    ) -> None:
        """Validate canonical positive blocks without inventing missing facts."""
        if len(self.lineage.fold_ids) != len(self.lineage.attempt_ids):
            raise ValueError(
                f"{version_label} review packet fold/attempt lineage count differs"
            )
        for field_name, values in (
            ("fold_ids", self.lineage.fold_ids),
            ("attempt_ids", self.lineage.attempt_ids),
        ):
            if any(
                type(value) is not str or not value or value != value.strip()
                for value in cast("tuple[object, ...]", values)
            ):
                raise ValueError(
                    f"{version_label} review packet {field_name} are invalid"
                )
        refs = self.selection_trace_artifact_refs
        kind_count = len(kinds)
        if len(refs) % kind_count:
            raise ValueError(
                f"{version_label} selection trace refs contain a partial kind block"
            )
        expected_kinds = kinds * (len(refs) // kind_count)
        if tuple(ref.artifact_kind for ref in refs) != expected_kinds:
            raise ValueError(
                f"{version_label} selection trace refs are not canonically ordered"
            )
        artifact_ids = tuple(ref.artifact_id for ref in refs)
        if len(set(artifact_ids)) != len(artifact_ids):
            raise ValueError(
                f"{version_label} selection trace refs contain duplicate artifact ids"
            )

    def canonical_payload(self) -> dict[str, object]:
        """Return the JSON-ready immutable bundle payload."""
        payload: dict[str, object] = {
            "schema_version": self.schema_version,
            "lineage": self.lineage.canonical_payload(),
            "spec_hash": str(self.spec_hash),
            "resolved_spec_hash": str(self.resolved_spec_hash),
            "parameter_hash": str(self.parameter_hash),
            "snapshot_hash": str(self.snapshot_hash),
            "registry_hash": str(self.registry_hash),
            "objective_payload_hash": str(self.objective_payload_hash),
            "gate_evaluations": [_gate_payload(item) for item in self.gate_evaluations],
            "comparison_payload_hash": _opt_hash(self.comparison_payload_hash),
            "r1_impact_payload_hash": _opt_hash(self.r1_impact_payload_hash),
            "selection_evidence_artifact_id": self.selection_evidence_artifact_id,
            "holdout_claim_id": self.holdout_claim_id,
            "candidate_rationale": self.candidate_rationale,
        }
        if self.schema_version in (
            REVIEW_PACKET_SCHEMA_VERSION_V2,
            REVIEW_PACKET_SCHEMA_VERSION,
        ):
            payload["selection_trace_artifact_refs"] = [
                ref.canonical_payload() for ref in self.selection_trace_artifact_refs
            ]
        if self.schema_version == REVIEW_PACKET_SCHEMA_VERSION:
            payload["selection_exposure"] = (
                None
                if self.selection_exposure is None
                else self.selection_exposure.canonical_payload()
            )
        return payload

    @property
    def bundle_hash(self) -> ContentHash:
        """Canonical hash over the complete bundle; refuses stale evidence."""
        return canonical_payload(self.canonical_payload()).content_hash


def _gate_payload(evaluation: GateEvaluation) -> dict[str, object]:
    return {
        "rule_id": evaluation.rule_id,
        "layer": evaluation.layer.value,
        "outcome": evaluation.outcome.value,
        "observed": evaluation.observed,
        "policy": evaluation.policy,
        "artifact_id": evaluation.artifact_id,
    }


def _opt_hash(value: ContentHash | None) -> str | None:
    return None if value is None else str(value)


def _payload_str(payload: Mapping[str, object], key: str) -> str:
    """Read one required string field from a canonical payload."""
    return cast("str", payload[key])


def _payload_optional_str(payload: Mapping[str, object], key: str) -> str | None:
    """Read one optional string field from a canonical payload."""
    return cast("str | None", payload[key])


def review_packet_from_payload(payload: Mapping[str, object]) -> ReviewPacket:
    """Rebuild an immutable review packet from its canonical payload."""
    schema_version = cast("int", payload["schema_version"])
    selection_trace_artifact_refs = _selection_trace_refs_from_payload(
        payload,
        schema_version=schema_version,
    )
    selection_exposure = _selection_exposure_from_payload(
        payload,
        schema_version=schema_version,
    )
    return ReviewPacket(
        schema_version=schema_version,
        lineage=_lineage_from_payload(payload["lineage"]),
        spec_hash=ContentHash(_payload_str(payload, "spec_hash")),
        resolved_spec_hash=ContentHash(_payload_str(payload, "resolved_spec_hash")),
        parameter_hash=ContentHash(_payload_str(payload, "parameter_hash")),
        snapshot_hash=ContentHash(_payload_str(payload, "snapshot_hash")),
        registry_hash=ContentHash(_payload_str(payload, "registry_hash")),
        objective_payload_hash=ContentHash(
            _payload_str(payload, "objective_payload_hash")
        ),
        gate_evaluations=_gate_tuple_from_payload(payload["gate_evaluations"]),
        comparison_payload_hash=_opt_hash_from_payload(
            payload["comparison_payload_hash"]
        ),
        r1_impact_payload_hash=_opt_hash_from_payload(
            payload["r1_impact_payload_hash"]
        ),
        selection_evidence_artifact_id=_payload_optional_str(
            payload,
            "selection_evidence_artifact_id",
        ),
        holdout_claim_id=_payload_optional_str(payload, "holdout_claim_id"),
        candidate_rationale=_payload_str(payload, "candidate_rationale"),
        selection_trace_artifact_refs=selection_trace_artifact_refs,
        selection_exposure=selection_exposure,
    )


def _selection_trace_refs_from_payload(
    payload: Mapping[str, object],
    *,
    schema_version: object,
) -> tuple[SelectionTraceArtifactRef, ...]:
    """Decode only the schema-owned trace-ref shape; never synthesize absence."""
    key = "selection_trace_artifact_refs"
    if schema_version == REVIEW_PACKET_SCHEMA_VERSION_V1:
        if key in payload:
            raise ValueError("v1 review packet payload contains v2 trace refs")
        return ()
    if schema_version not in (
        REVIEW_PACKET_SCHEMA_VERSION_V2,
        REVIEW_PACKET_SCHEMA_VERSION,
    ):
        return ()
    raw = payload.get(key)
    if type(raw) is not list:
        raise ValueError("review packet payload trace refs must be a list")
    refs: list[SelectionTraceArtifactRef] = []
    required_keys = {"artifact_kind", "artifact_id", "content_hash"}
    for item in cast("list[object]", raw):
        if type(item) is not dict:
            raise ValueError("invalid v2 selection trace artifact ref payload")
        raw_data = cast("dict[object, object]", item)
        if set(raw_data) != required_keys:
            raise ValueError("invalid v2 selection trace artifact ref payload")
        data = cast("Mapping[str, object]", raw_data)
        refs.append(
            SelectionTraceArtifactRef(
                artifact_kind=_payload_str(data, "artifact_kind"),
                artifact_id=_payload_str(data, "artifact_id"),
                content_hash=ContentHash(_payload_str(data, "content_hash")),
            )
        )
    return tuple(refs)


def _selection_exposure_from_payload(
    payload: Mapping[str, object],
    *,
    schema_version: object,
) -> ReviewSelectionExposure | None:
    key = "selection_exposure"
    if schema_version in (
        REVIEW_PACKET_SCHEMA_VERSION_V1,
        REVIEW_PACKET_SCHEMA_VERSION_V2,
    ):
        if key in payload:
            raise ValueError("legacy review packet payload contains v3 exposure")
        return None
    if schema_version != REVIEW_PACKET_SCHEMA_VERSION:
        return None
    raw = payload.get(key)
    if raw is None:
        return None
    if type(raw) is not dict:
        raise ValueError("v3 review packet payload exposure must be an object")
    data = cast("Mapping[str, object]", raw)
    required_keys = {
        "applicability",
        "lane",
        "industry_weights",
        "size_bucket_weights",
        "artifact_refs",
    }
    if set(data) != required_keys:
        raise ValueError("invalid v3 selection exposure payload")
    return ReviewSelectionExposure(
        applicability=_payload_str(data, "applicability"),
        lane=_payload_str(data, "lane"),
        industry_weights=_exposure_weights_from_payload(data["industry_weights"]),
        size_bucket_weights=_exposure_weights_from_payload(data["size_bucket_weights"]),
        artifact_refs=_artifact_refs_from_payload(data["artifact_refs"]),
    )


def _exposure_weights_from_payload(payload: object) -> tuple[ReviewExposureWeight, ...]:
    if type(payload) is not list:
        raise ValueError("selection exposure weights must be a list")
    values: list[ReviewExposureWeight] = []
    for item in cast("list[object]", payload):
        if type(item) is not dict:
            raise ValueError("invalid selection exposure weight payload")
        data = cast("Mapping[str, object]", item)
        if set(data) != {"key", "weight"}:
            raise ValueError("invalid selection exposure weight payload")
        values.append(
            ReviewExposureWeight(
                key=_payload_str(data, "key"),
                weight=cast("float", data["weight"]),
            )
        )
    return tuple(values)


def _artifact_refs_from_payload(
    payload: object,
) -> tuple[SelectionTraceArtifactRef, ...]:
    if type(payload) is not list:
        raise ValueError("selection exposure artifact refs must be a list")
    refs: list[SelectionTraceArtifactRef] = []
    for item in cast("list[object]", payload):
        if type(item) is not dict:
            raise ValueError("invalid selection exposure artifact ref payload")
        data = cast("Mapping[str, object]", item)
        if set(data) != {
            "artifact_kind",
            "artifact_id",
            "content_hash",
        }:
            raise ValueError("invalid selection exposure artifact ref payload")
        refs.append(
            SelectionTraceArtifactRef(
                artifact_kind=_payload_str(data, "artifact_kind"),
                artifact_id=_payload_str(data, "artifact_id"),
                content_hash=ContentHash(_payload_str(data, "content_hash")),
            )
        )
    return tuple(refs)


def _lineage_from_payload(payload: object) -> ReviewPacketLineage:
    """Rebuild one lineage identity from its canonical payload."""
    data: Mapping[str, object] = (
        cast("Mapping[str, object]", payload) if isinstance(payload, Mapping) else {}
    )
    return ReviewPacketLineage(
        experiment_id=_payload_str(data, "experiment_id"),
        candidate_id=_payload_optional_str(data, "candidate_id"),
        fold_ids=tuple(
            cast("str", item) for item in cast("Iterable[object]", data["fold_ids"])
        ),
        attempt_ids=tuple(
            cast("str", item) for item in cast("Iterable[object]", data["attempt_ids"])
        ),
    )


def _gate_from_payload(payload: object) -> GateEvaluation:
    """Rebuild one gate evaluation from its canonical payload."""
    data: Mapping[str, object] = (
        cast("Mapping[str, object]", payload) if isinstance(payload, Mapping) else {}
    )
    return GateEvaluation(
        rule_id=_payload_str(data, "rule_id"),
        layer=GateLayer(_payload_str(data, "layer")),
        outcome=GateOutcome(_payload_str(data, "outcome")),
        observed=data["observed"],
        policy=data["policy"],
        artifact_id=_payload_optional_str(data, "artifact_id"),
    )


def _gate_tuple_from_payload(payload: object) -> tuple[GateEvaluation, ...]:
    items = cast("Iterable[object]", payload)
    return tuple(_gate_from_payload(item) for item in items)


def _opt_hash_from_payload(value: object) -> ContentHash | None:
    return None if value is None else ContentHash(cast("str", value))
