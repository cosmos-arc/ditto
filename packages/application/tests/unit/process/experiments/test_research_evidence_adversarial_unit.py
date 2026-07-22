"""Adversarial exact-scalar tests for research planning evidence."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import replace
from datetime import date
from types import SimpleNamespace
from typing import cast
from unicodedata import category

import pytest
from ditto_application.exceptions import AppProcessError
from ditto_application.processes.experiments._executor_probe import probe_executor
from ditto_application.processes.experiments._planning_evidence import (
    candidate_evidence_tuple,
    canonical_text,
    canonical_text_tuple,
    snapshot_payload,
)
from ditto_application.processes.experiments.planning import CandidateMatrixPlan
from ditto_application.processes.experiments.planning_contracts import (
    ExperimentPlanningRequest,
)
from ditto_application.processes.experiments.planning_probes import (
    R3_RESEARCH_CERTIFICATION_PROFILE,
    CandidateExecutorEvidence,
    ResearchCertificationRequest,
    ResearchCertificationResult,
    ResearchExecutorProbeResult,
    ResearchSnapshotEvidence,
)
from ditto_application.processes.experiments.planning_process import (
    ExperimentPlanningProcess,
)
from ditto_application.research_certification_contracts import (
    ExperimentSnapshotIdentity,
    ResearchDatasetRequirement,
    is_canonical_content_hash,
    is_canonical_identity,
)


class _EvilStr(str):
    pass


class _EvilDate(date):
    pass


class _EvilTuple(tuple):
    pass


class _StatefulTupleSpoof:
    def __init__(self) -> None:
        self.iterations = 0

    @property
    def __class__(self) -> type[object]:
        return tuple

    def __iter__(self) -> Iterator[str]:
        self.iterations += 1
        return iter(("source-1",) if self.iterations == 1 else ())


def _certification_request() -> ResearchCertificationRequest:
    return ResearchCertificationRequest(
        R3_RESEARCH_CERTIFICATION_PROFILE,
        date(2016, 1, 1),
        date(2025, 12, 31),
        (ResearchDatasetRequirement("etf_daily", ("source-1",)),),
        ExperimentSnapshotIdentity("snapshot-1", "d" * 64),
    )


def _snapshot(*, known_at_policy: str = "sample_time") -> ResearchSnapshotEvidence:
    return ResearchSnapshotEvidence(
        "snapshot-1",
        "research-etf",
        "d" * 64,
        ("source-1",),
        date(2016, 1, 1),
        date(2025, 12, 31),
        known_at_policy,
        "builder-v1",
    )


def test_shared_identity_and_hash_validators_reject_str_subclasses() -> None:
    assert is_canonical_identity(_EvilStr("dataset")) is False
    assert is_canonical_content_hash(_EvilStr("d" * 64)) is False
    assert canonical_text(_EvilStr("reason")) is False
    assert canonical_text_tuple((_EvilStr("source"),), nonempty=True) is False


def test_planning_evidence_rejects_tuple_class_spoof_without_iteration() -> None:
    spoof = _StatefulTupleSpoof()
    assert spoof.__class__ is tuple

    assert canonical_text_tuple(spoof, nonempty=True) is False
    assert candidate_evidence_tuple(spoof) is None
    assert spoof.iterations == 0


@pytest.mark.parametrize(
    "unsafe_text",
    [
        pytest.param("identity\x00control", id="control"),
        pytest.param("identity\u200bformat", id="format"),
        pytest.param(f"identity{chr(0xD800)}surrogate", id="surrogate"),
        pytest.param("identity\ue000private", id="private-use"),
        pytest.param("identity\u0378unassigned", id="unassigned"),
    ],
)
def test_canonical_text_rejects_every_unicode_other_category(
    unsafe_text: str,
) -> None:
    assert any(category(char).startswith("C") for char in unsafe_text)
    assert is_canonical_identity(unsafe_text) is False
    assert canonical_text(unsafe_text) is False
    assert canonical_text_tuple((unsafe_text,), nonempty=True) is False


def test_canonical_text_retains_utf8_encodable_visible_unicode() -> None:
    assert is_canonical_identity("研究-snapshot") is True
    assert canonical_text("blocked-原因") is True


@pytest.mark.parametrize(
    "build",
    [
        lambda: ResearchDatasetRequirement(
            cast("str", _EvilStr("etf_daily")),
            ("source-1",),
        ),
        lambda: ResearchDatasetRequirement(
            "etf_daily",
            (cast("str", _EvilStr("source-1")),),
        ),
        lambda: ExperimentSnapshotIdentity(
            cast("str", _EvilStr("snapshot-1")),
            "d" * 64,
        ),
        lambda: ExperimentSnapshotIdentity(
            "snapshot-1",
            cast("str", _EvilStr("d" * 64)),
        ),
    ],
    ids=("dataset", "source", "snapshot", "hash"),
)
def test_canonical_contracts_never_retain_evil_strings(
    build: Callable[[], object],
) -> None:
    with pytest.raises(AppProcessError):
        build()


def test_snapshot_payload_does_not_serialize_evil_string_or_date_subclasses() -> None:
    evidence = ResearchSnapshotEvidence(
        snapshot_id=cast("str", _EvilStr("snapshot-1")),
        dataset_id=cast("str", _EvilStr("research-etf")),
        manifest_hash=cast("str", _EvilStr("d" * 64)),
        source_snapshot_ids=(cast("str", _EvilStr("source-1")),),
        snapshot_start=_EvilDate(2016, 1, 1),
        snapshot_end=cast("object", SimpleNamespace(isoformat=lambda: "2025-12-31")),
        known_at_policy=cast("str", _EvilStr("sample_time")),
        builder_version=cast("str", _EvilStr("builder-v1")),
    )

    assert snapshot_payload(evidence) == {
        "snapshot_id": None,
        "dataset_id": None,
        "manifest_hash": None,
        "source_snapshot_ids": [],
        "snapshot_start": None,
        "snapshot_end": None,
        "known_at_policy": None,
        "builder_version": None,
    }


def test_certification_check_rejects_snapshot_subclass_before_field_access() -> None:
    class _SnapshotSubclass(ResearchSnapshotEvidence):
        pass

    request = _certification_request()
    valid = _snapshot()
    snapshot = _SnapshotSubclass(
        valid.snapshot_id,
        valid.dataset_id,
        valid.manifest_hash,
        valid.source_snapshot_ids,
        valid.snapshot_start,
        valid.snapshot_end,
        valid.known_at_policy,
        valid.builder_version,
    )
    result = ResearchCertificationResult(
        True,
        request.profile,
        ("etf_daily",),
        ("report-1",),
        (),
        snapshot,
    )

    check = ExperimentPlanningProcess._certification_check(result, request)

    assert check.outcome.value == "fail"
    assert check.observed["snapshot_evidence"] is None


def test_certification_check_rejects_evil_known_at_policy_string() -> None:
    request = _certification_request()
    result = ResearchCertificationResult(
        True,
        request.profile,
        ("etf_daily",),
        ("report-1",),
        (),
        _snapshot(known_at_policy=cast("str", _EvilStr("sample_time"))),
    )

    check = ExperimentPlanningProcess._certification_check(result, request)

    assert check.outcome.value == "fail"
    payload = cast("dict[str, object]", check.observed["snapshot_evidence"])
    assert payload["known_at_policy"] is None


def test_certification_boundary_sanitizes_surrogate_snapshot_identity() -> None:
    request = _certification_request()
    result = ResearchCertificationResult(
        True,
        request.profile,
        ("etf_daily",),
        ("report-1",),
        (),
        replace(_snapshot(), snapshot_id=chr(0xD800)),
    )

    check = ExperimentPlanningProcess._certification_check(result, request)

    assert check.outcome.value == "fail"
    payload = cast("dict[str, object]", check.observed["snapshot_evidence"])
    assert payload["snapshot_id"] is None


def test_executor_boundary_replaces_surrogate_blocker_text() -> None:
    surrogate = chr(0xD800)
    result = ResearchExecutorProbeResult(
        False,
        surrogate,
        surrogate,
        surrogate,
        None,
        None,
        (),
        (),
    )
    matrix = cast("CandidateMatrixPlan", SimpleNamespace(binder_candidates=()))
    request = cast(
        "ExperimentPlanningRequest",
        SimpleNamespace(dataset_requirements=()),
    )

    check = ExperimentPlanningProcess._executor_check(result, matrix, request)

    assert check.outcome.value == "fail"
    assert check.code == "REPRODUCIBILITY_FAILED"
    assert check.reason == "executor_or_dataset_evidence_mismatch"
    assert check.remediation is None


def test_candidate_evidence_subclass_and_evil_hash_fail_closed() -> None:
    class _EvidenceSubclass(CandidateExecutorEvidence):
        pass

    assert (
        candidate_evidence_tuple(
            (
                _EvidenceSubclass(
                    "a" * 64,
                    "b" * 64,
                    "c" * 64,
                    "d" * 64,
                    "e" * 64,
                ),
            )
        )
        is None
    )
    assert (
        candidate_evidence_tuple(
            _EvilTuple(
                (
                    CandidateExecutorEvidence(
                        "a" * 64,
                        "b" * 64,
                        "c" * 64,
                        "d" * 64,
                        "e" * 64,
                    ),
                )
            )
        )
        is None
    )
    assert (
        candidate_evidence_tuple(
            (
                CandidateExecutorEvidence(
                    cast("str", _EvilStr("a" * 64)),
                    "b" * 64,
                    "c" * 64,
                    "d" * 64,
                    "e" * 64,
                ),
            )
        )
        is None
    )


def test_executor_probe_result_subclass_is_normalized_to_typed_blocker() -> None:
    class _ResultSubclass(ResearchExecutorProbeResult):
        pass

    class _Probe:
        def probe(self, _request: object) -> ResearchExecutorProbeResult:
            return _ResultSubclass(
                True,
                None,
                None,
                None,
                "a" * 64,
                "b" * 64,
                ("etf_daily",),
                (),
            )

    request = SimpleNamespace(
        strategy_record=object(),
        snapshot_identity=object(),
    )
    matrix = SimpleNamespace(
        baseline_candidate=SimpleNamespace(descriptor=object()),
        binder_candidates=(),
    )

    result = probe_executor(
        cast("object", _Probe()),
        cast("object", request),
        cast("object", matrix),
    )

    assert type(result) is ResearchExecutorProbeResult
    assert result.available is False
    assert result.reason == "invalid_executor_probe_result"
