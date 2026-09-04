from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import date
from types import SimpleNamespace
from typing import Any, cast

import pytest
from ditto_analysis.experiments import (
    CandidateId,
    ContentHash,
    DateWindow,
    ExperimentId,
    FoldId,
    ResearchMetricId,
    ResearchMetricValue,
    SnapshotId,
)
from ditto_application.exceptions import AppProcessError
from ditto_application.processes.experiments import _comparison_evidence as evidence

_HASH = ContentHash("a" * 64)
_WINDOW = DateWindow(date(2024, 1, 1), date(2024, 1, 3))
_NAVS = (("2024-01-01", 100.0), ("2024-01-03", 101.0))
_RETURNS = (("2024-01-01", 0.0), ("2024-01-03", 101.0 / 100.0 - 1.0))


def _assert_invalid(factory: Callable[[], object], reason: str) -> None:
    with pytest.raises(AppProcessError) as exc_info:
        factory()

    assert exc_info.value.details["reason"] == reason


def _capacity() -> evidence.CapacityEvidence:
    return evidence.CapacityEvidence(
        experiment_id=ExperimentId("experiment-r3"),
        candidate_id=CandidateId("candidate-alpha"),
        fold_id=FoldId("wf-1"),
        snapshot_id=SnapshotId("snapshot-r3"),
        snapshot_hash=_HASH,
        parameter_hash=ContentHash("b" * 64),
        resolved_spec_hash=ContentHash("c" * 64),
        test_window=_WINDOW,
        value_cny=1_000_000.0,
        evidence_ref="capacity://candidate-alpha/wf-1",
        method="participation_rate_stress_v1",
    )


def _valid_return_evidence() -> evidence.FoldReturnEvidence:
    return evidence.FoldReturnEvidence(
        initial_capital=100.0,
        nav_series=_NAVS,
        daily_returns=_RETURNS,
        evidence_refs=("report://candidate-alpha/wf-1",),
        evidence_hashes=(_HASH,),
    )


def _fold_source(
    nav_series: object,
    *,
    final_nav: object = 101.0,
    fill_log: object = (),
) -> Any:
    report = SimpleNamespace(
        initial_cash=100.0,
        final_nav=final_nav,
        nav_series=nav_series,
        fill_log=fill_log,
    )
    artifact = SimpleNamespace(
        evidence=report,
        record=SimpleNamespace(
            relative_path="experiments/report-evidence.json",
            content_hash=_HASH,
        ),
    )
    return SimpleNamespace(
        outcome=evidence.FoldOutcome.COMPLETED,
        report_artifact=artifact,
        test_window=_WINDOW,
        capacity=None,
    )


@pytest.mark.parametrize(
    ("factory", "reason"),
    [
        pytest.param(
            lambda: evidence._positive_ordinal(False, "candidate_ordinal"),
            "invalid_comparison_ordinal",
            id="boolean-ordinal",
        ),
        pytest.param(
            lambda: evidence._hashes(object()),
            "invalid_evidence_hashes",
            id="hashes-not-sequence",
        ),
        pytest.param(
            lambda: evidence._hashes((object(),)),
            "invalid_evidence_hashes",
            id="hashes-not-nominal",
        ),
        pytest.param(
            lambda: evidence._refs("report://one"),
            "invalid_evidence_refs",
            id="refs-text-not-sequence",
        ),
        pytest.param(
            lambda: evidence._refs(("report://one", "report://one")),
            "duplicate_evidence_ref",
            id="duplicate-ref",
        ),
    ],
)
def test_identity_and_lineage_inputs_fail_closed_before_projection(
    factory: Callable[[], object],
    reason: str,
) -> None:
    _assert_invalid(factory, reason)


def test_capacity_rejects_untyped_identity_and_invalid_value() -> None:
    valid = _capacity()

    _assert_invalid(
        lambda: replace(
            valid,
            experiment_id=cast(ExperimentId, "experiment-r3"),
        ),
        "invalid_capacity_evidence_identity",
    )
    _assert_invalid(
        lambda: replace(valid, value_cny=-1.0),
        "invalid_capacity_evidence",
    )


def test_capacity_validator_rejects_a_non_nominal_evidence_object() -> None:
    source = SimpleNamespace(capacity=object())

    _assert_invalid(
        lambda: evidence._validate_capacity_evidence(cast(Any, source)),
        "invalid_capacity_evidence",
    )


@pytest.mark.parametrize(
    ("factory", "reason"),
    [
        pytest.param(
            lambda: evidence.ScalarEvidence(
                cast(evidence.EvidenceStatus, "evaluated"),
                None,
                None,
            ),
            "invalid_evidence_status",
            id="scalar-status",
        ),
        pytest.param(
            lambda: evidence.ScalarEvidence(
                evidence.EvidenceStatus.EVALUATED,
                None,
                None,
            ),
            "invalid_evaluated_scalar_evidence",
            id="evaluated-scalar-payload",
        ),
        pytest.param(
            lambda: evidence.ScalarEvidence(
                evidence.EvidenceStatus.NOT_EVALUATED,
                None,
                None,
            ),
            "invalid_not_evaluated_scalar_evidence",
            id="not-evaluated-scalar-reason",
        ),
        pytest.param(
            lambda: evidence.DiagnosticEvidence(
                cast(evidence.EvidenceStatus, "evaluated"),
                None,
                None,
            ),
            "invalid_diagnostic_status",
            id="diagnostic-status",
        ),
        pytest.param(
            lambda: evidence.DiagnosticEvidence(
                evidence.EvidenceStatus.EVALUATED,
                None,
                None,
            ),
            "invalid_evaluated_diagnostic",
            id="evaluated-diagnostic-payload",
        ),
        pytest.param(
            lambda: evidence.DiagnosticEvidence(
                evidence.EvidenceStatus.NOT_EVALUATED,
                object(),
                "not available",
            ),
            "invalid_not_evaluated_diagnostic",
            id="not-evaluated-diagnostic-value",
        ),
    ],
)
def test_scalar_and_diagnostic_discriminated_unions_reject_ambiguous_states(
    factory: Callable[[], object],
    reason: str,
) -> None:
    _assert_invalid(factory, reason)


@pytest.mark.parametrize(
    "raw_nav",
    [
        pytest.param("2024-01-01", id="text-container"),
        pytest.param([["2024-01-01", 100.0]], id="row-not-tuple"),
        pytest.param([("2024-01-01",)], id="row-arity"),
        pytest.param([(date(2024, 1, 1), 100.0)], id="date-not-text"),
        pytest.param([("not-a-date", 100.0)], id="invalid-iso-date"),
        pytest.param(
            [("2024-01-02", 101.0), ("2024-01-01", 100.0)],
            id="non-increasing-date",
        ),
        pytest.param([], id="empty-series"),
    ],
)
def test_ordered_nav_rejects_ambiguous_or_noncanonical_rows(raw_nav: object) -> None:
    _assert_invalid(
        lambda: evidence._ordered_nav(raw_nav, reason="invalid_test_nav"),
        "invalid_test_nav",
    )


def test_fold_return_evidence_rejects_invalid_capital_shape_and_lineage() -> None:
    _assert_invalid(
        lambda: evidence.FoldReturnEvidence(
            initial_capital=0.0,
            nav_series=_NAVS,
            daily_returns=_RETURNS,
            evidence_refs=("report://candidate-alpha/wf-1",),
            evidence_hashes=(_HASH,),
        ),
        "invalid_fold_return_evidence",
    )
    _assert_invalid(
        lambda: evidence.FoldReturnEvidence(
            initial_capital=100.0,
            nav_series=_NAVS,
            daily_returns=cast(
                Any,
                (["2024-01-01", 0.0], ("2024-01-03", 0.01)),
            ),
            evidence_refs=("report://candidate-alpha/wf-1",),
            evidence_hashes=(_HASH,),
        ),
        "invalid_fold_return_evidence",
    )
    _assert_invalid(
        lambda: evidence.FoldReturnEvidence(
            initial_capital=100.0,
            nav_series=_NAVS,
            daily_returns=_RETURNS,
            evidence_refs=(),
            evidence_hashes=(),
        ),
        "fold_return_evidence_source_required",
    )


def test_fold_execution_evidence_rejects_invalid_totals_and_missing_lineage() -> None:
    _assert_invalid(
        lambda: evidence.FoldExecutionEvidence(
            initial_capital=0.0,
            nav_series=_NAVS,
            fill_notional=20.0,
            explicit_cost=1.0,
            evidence_refs=("report://candidate-alpha/wf-1",),
            evidence_hashes=(_HASH,),
        ),
        "invalid_fold_execution_evidence",
    )
    _assert_invalid(
        lambda: evidence.FoldExecutionEvidence(
            initial_capital=100.0,
            nav_series=_NAVS,
            fill_notional=20.0,
            explicit_cost=1.0,
            evidence_refs=(),
            evidence_hashes=(),
        ),
        "fold_execution_evidence_source_required",
    )


@pytest.mark.parametrize(
    "loader",
    [
        pytest.param(evidence._source_refs, id="refs"),
        pytest.param(evidence._source_hashes, id="hashes"),
    ],
)
def test_report_lineage_helpers_fail_closed_when_the_artifact_is_missing(
    loader: Callable[[Any], object],
) -> None:
    _assert_invalid(
        lambda: loader(SimpleNamespace(report_artifact=None)),
        "backtest_report_missing",
    )


@pytest.mark.parametrize(
    "source",
    [
        pytest.param(
            _fold_source([["2024-01-01", 100.0]]),
            id="row-not-tuple",
        ),
        pytest.param(
            _fold_source(((date(2024, 1, 1), 100.0),)),
            id="date-not-text",
        ),
        pytest.param(
            _fold_source((("not-a-date", 100.0),)),
            id="invalid-iso-date",
        ),
        pytest.param(
            _fold_source(
                (("2024-01-02", 101.0), ("2024-01-01", 100.0)),
                final_nav=100.0,
            ),
            id="non-increasing-date",
        ),
        pytest.param(
            _fold_source(
                (("2024-01-01", 100.0), ("2024-01-04", 101.0)),
            ),
            id="outside-test-window",
        ),
        pytest.param(
            _fold_source(
                (("2024-01-01", 100.0), ("2024-01-02", 101.0)),
            ),
            id="incomplete-window-boundary",
        ),
    ],
)
def test_report_return_parser_rejects_untrusted_nav_shapes(source: Any) -> None:
    assert evidence._return_evidence(source) is None


def test_execution_parser_rejects_non_nominal_fill_evidence() -> None:
    source = _fold_source(_NAVS, fill_log=(object(),))

    assert evidence._execution_evidence(source, _valid_return_evidence()) is None


def test_valid_scalar_fixture_uses_analysis_owned_metric_contract() -> None:
    """Prove invalid-state tests do not rely on an impossible metric fixture."""
    value = ResearchMetricValue(ResearchMetricId.NET_RETURN, 1.0)
    scalar = evidence.ScalarEvidence(
        evidence.EvidenceStatus.EVALUATED,
        value,
        None,
        ("report://candidate-alpha/wf-1",),
        (_HASH,),
    )

    assert scalar.metric_value is value
    assert scalar.value == 1.0
