"""Research replay manifest codec preserves exact product context identity."""

from __future__ import annotations

from dataclasses import replace
from typing import cast

import orjson
import pytest
from ditto_application.exceptions import AppProcessError
from ditto_application.processes.execution._research_replay_codec import (
    build_research_replay_metadata,
    deserialize_manifest,
    research_replay_pointer,
)
from ditto_backtest.context_inputs import ContextInputKind, ReplayContextInputRef
from ditto_backtest.manifest import RunManifest, RunMode, serialize_manifest
from ditto_backtest.manifest_types import ReplayArtifactRef, ResearchReplayEvidence
from ditto_strategy.alpha.parameters import canonical_parameter_hash
from ditto_strategy.models import ArtifactKind, StrategyArtifactRecord

pytestmark = [pytest.mark.unit, pytest.mark.pit]


def _replay_artifact(
    artifact_id: str,
    artifact_kind: str,
    *,
    artifact_format: str = "json",
) -> ReplayArtifactRef:
    return ReplayArtifactRef(
        artifact_id=artifact_id,
        artifact_kind=artifact_kind,
        artifact_format=artifact_format,
        content_hash="a" * 64,
        schema_hash="b" * 64,
        row_count=1,
        byte_size=10,
    )


def _replay_evidence() -> ResearchReplayEvidence:
    report = _replay_artifact("report-1", "backtest_report")
    return ResearchReplayEvidence(
        reproduction_fingerprint="c" * 64,
        key_result_summary_artifact_id=report.artifact_id,
        required_artifacts=(report,),
    )


def _manifest_artifact() -> ReplayArtifactRef:
    return _replay_artifact("manifest-1", "run_manifest")


def _metadata() -> dict[str, object]:
    value = build_research_replay_metadata(
        manifest_artifact=_manifest_artifact(),
        replay_evidence=_replay_evidence(),
    )
    return cast("dict[str, object]", orjson.loads(orjson.dumps(value)))


def _record(metadata: dict[str, object]) -> StrategyArtifactRecord:
    return StrategyArtifactRecord(
        artifact_id="strategy-artifact-1",
        strategy_id="strategy-1",
        run_id="run-1",
        artifact_type=ArtifactKind.BACKTEST_REPORT,
        file_path="artifacts/report.json",
        metadata=metadata,
    )


def _manifest_raw() -> dict[str, object]:
    manifest = RunManifest(
        run_id="run-replay-codec",
        strategy_id="strategy-1",
        strategy_version="1",
        mode=RunMode.BACKTEST,
        created_at="2026-03-31T08:00:00Z",
        spec_hash="d" * 64,
        base_spec_hash="e" * 64,
        parameter_hash=canonical_parameter_hash(()),
        effective_parameters=(),
        research_snapshot_id=None,
        research_snapshot_manifest_hash=None,
        replay_evidence=_replay_evidence(),
    )
    return cast("dict[str, object]", orjson.loads(serialize_manifest(manifest)))


def _reason(exc_info: pytest.ExceptionInfo[AppProcessError]) -> object:
    return exc_info.value.details["reason"]


def test_context_inputs_round_trip_through_persisted_manifest_json() -> None:
    context_ref = ReplayContextInputRef(
        context_kind=ContextInputKind.TECHNICAL_ANALYSIS,
        context_id="technical-510300-2026-03-31",
        content_hash="a" * 64,
        as_of="2026-03-31T07:00:00Z",
        knowledge_cutoff="2026-03-31T06:30:00Z",
        publication_cutoff="2026-03-31T06:00:00Z",
        source_snapshot_ids=("bars-snapshot-1",),
    )
    manifest = RunManifest(
        run_id="run-context-codec",
        strategy_id="strategy-1",
        strategy_version="1",
        mode=RunMode.BACKTEST,
        created_at="2026-03-31T08:00:00Z",
        spec_hash="b" * 64,
        base_spec_hash="c" * 64,
        parameter_hash=canonical_parameter_hash(()),
        effective_parameters=(),
        research_snapshot_id=None,
        research_snapshot_manifest_hash=None,
        context_input_refs=(context_ref,),
    )

    raw = orjson.loads(serialize_manifest(manifest))
    restored = deserialize_manifest(raw)

    assert restored.context_input_refs == (context_ref,)


def test_metadata_builder_rejects_invalid_membership_and_fill() -> None:
    evidence = _replay_evidence()
    with pytest.raises(AppProcessError) as exc_info:
        build_research_replay_metadata(
            manifest_artifact=replace(
                _manifest_artifact(),
                artifact_kind="backtest_report",
            ),
            replay_evidence=evidence,
        )
    assert _reason(exc_info) == "invalid_replay_evidence"

    with pytest.raises(AppProcessError) as exc_info:
        build_research_replay_metadata(
            manifest_artifact=replace(
                _manifest_artifact(),
                artifact_id=evidence.key_result_summary_artifact_id,
            ),
            replay_evidence=evidence,
        )
    assert _reason(exc_info) == "invalid_replay_evidence"

    with pytest.raises(AppProcessError) as exc_info:
        build_research_replay_metadata(
            manifest_artifact=_manifest_artifact(),
            replay_evidence=evidence,
            fill_log_artifact_id="fill-missing",
        )
    assert _reason(exc_info) == "invalid_replay_evidence"


@pytest.mark.parametrize(
    "mutation",
    [
        "schema_version",
        "bundle_container",
        "required_empty",
        "manifest_member",
        "report_missing",
        "fill_missing",
        "path_identity",
    ],
)
def test_pointer_decoder_rejects_every_corrupt_bundle_shape(mutation: str) -> None:
    metadata = _metadata()
    if mutation == "bundle_container":
        metadata["research_replay_bundle"] = []
    else:
        bundle = cast("dict[str, object]", metadata["research_replay_bundle"])
        if mutation == "schema_version":
            bundle["schema_version"] = 2
        elif mutation == "required_empty":
            bundle["required_artifact_ids"] = []
        elif mutation == "manifest_member":
            bundle["manifest_artifact_id"] = "report-1"
        elif mutation == "report_missing":
            bundle["report_artifact_id"] = "report-missing"
        elif mutation == "fill_missing":
            bundle["fill_log_artifact_id"] = "fill-missing"
        else:
            bundle["manifest_artifact_id"] = "../manifest-1"

    with pytest.raises(AppProcessError) as exc_info:
        research_replay_pointer(_record(metadata))

    assert _reason(exc_info) == "invalid_replay_evidence_marker"


def test_pointer_decoder_round_trips_authoritative_metadata() -> None:
    pointer = research_replay_pointer(_record(_metadata()))

    assert pointer is not None
    assert pointer.manifest_artifact_id == "manifest-1"
    assert pointer.report_artifact_id == "report-1"
    assert pointer.required_artifact_ids == ("report-1",)
    assert pointer.fill_log_artifact_id is None


def _corrupt_manifest(raw: dict[str, object], mutation: str) -> None:
    if mutation == "manifest_semantics":
        raw["mode"] = "unsupported"
    elif mutation == "evidence_container":
        raw["replay_evidence"] = []
    else:
        evidence = cast("dict[str, object]", raw["replay_evidence"])
        if mutation == "schema_version_type":
            evidence["schema_version"] = True
        elif mutation == "artifacts_container":
            evidence["required_artifacts"] = "not-an-array"
        elif mutation == "fingerprint_type":
            evidence["reproduction_fingerprint"] = 1
        elif mutation == "evidence_semantics":
            evidence["schema_version"] = 2
        else:
            _corrupt_replay_artifact(evidence, mutation)


def _corrupt_replay_artifact(evidence: dict[str, object], mutation: str) -> None:
    artifacts = cast("list[object]", evidence["required_artifacts"])
    if mutation == "artifact_container":
        artifacts[0] = []
        return
    artifact = cast("dict[str, object]", artifacts[0])
    if mutation == "artifact_fields":
        artifact.pop("schema_hash")
    elif mutation == "artifact_hash":
        artifact["content_hash"] = "not-a-hash"
    else:
        artifact["row_count"] = True


@pytest.mark.parametrize(
    ("mutation", "expected_reason"),
    [
        ("evidence_container", "invalid_replay_evidence"),
        ("schema_version_type", "invalid_replay_evidence"),
        ("artifacts_container", "invalid_replay_evidence"),
        ("artifact_container", "invalid_replay_evidence"),
        ("artifact_fields", "invalid_replay_evidence"),
        ("artifact_hash", "invalid_replay_evidence"),
        ("fingerprint_type", "invalid_replay_evidence"),
        ("row_count_type", "invalid_replay_evidence"),
        ("evidence_semantics", "invalid_replay_evidence"),
        ("manifest_semantics", "invalid_reproduction_identity"),
    ],
)
def test_manifest_decoder_rejects_corrupt_replay_evidence(
    mutation: str,
    expected_reason: str,
) -> None:
    raw = _manifest_raw()
    _corrupt_manifest(raw, mutation)

    with pytest.raises(AppProcessError) as exc_info:
        deserialize_manifest(cast("dict[str, object]", raw))

    assert _reason(exc_info) == expected_reason
