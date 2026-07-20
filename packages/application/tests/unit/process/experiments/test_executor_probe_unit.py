"""Canonical identity tests for the untrusted executor probe boundary."""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast

from ditto_application.processes.experiments._executor_probe import probe_executor
from ditto_application.processes.experiments.planning import (
    BaselineCandidatePlan,
    BaselineDescriptor,
    CandidateMatrixPlan,
)
from ditto_application.processes.experiments.planning_contracts import (
    ExperimentPlanningRequest,
)
from ditto_application.processes.experiments.planning_probes import (
    ExperimentSnapshotIdentity,
    ResearchExecutorProbeRequest,
    ResearchExecutorProbeResult,
)
from ditto_strategy.models import StrategySpecRecord


class _Probe:
    def __init__(self, required_datasets: tuple[str, ...]) -> None:
        self._required_datasets = required_datasets

    def probe(
        self,
        _request: ResearchExecutorProbeRequest,
    ) -> ResearchExecutorProbeResult:
        return ResearchExecutorProbeResult(
            available=True,
            code=None,
            reason=None,
            remediation=None,
            strategy_spec_hash="a" * 64,
            node_registry_manifest_hash="b" * 64,
            required_datasets=self._required_datasets,
            candidates=(),
        )


def _probe_result(required_datasets: tuple[str, ...]) -> ResearchExecutorProbeResult:
    request = cast(
        "ExperimentPlanningRequest",
        SimpleNamespace(
            strategy_record=StrategySpecRecord(
                strategy_id="seed_etf_rotation",
                name="ETF rotation",
                spec_json={"strategy_id": "seed_etf_rotation"},
                version=1,
                status="draft",
            ),
            snapshot_identity=ExperimentSnapshotIdentity(
                "certified-snapshot-1",
                "d" * 64,
            ),
        ),
    )
    baseline = BaselineCandidatePlan(
        BaselineDescriptor(
            descriptor_type="etf-current-active",
            payload={"strategy_id": "seed_etf_rotation", "version": 1},
        ),
    )
    matrix = CandidateMatrixPlan(128, baseline, (), "e" * 64)
    return probe_executor(_Probe(required_datasets), request, matrix)


def test_required_dataset_permutations_have_one_executor_identity() -> None:
    forward = _probe_result(("etf_daily", "trade_cal"))
    reverse = _probe_result(("trade_cal", "etf_daily"))

    assert forward.required_datasets == ("etf_daily", "trade_cal")
    assert reverse == forward
