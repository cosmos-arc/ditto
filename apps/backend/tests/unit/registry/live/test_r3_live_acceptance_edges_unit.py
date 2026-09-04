"""Fail-closed unit edges for the production-composed R3 live driver."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
from ditto_application.processes.experiments.planning_process import (
    ExperimentPreflightStatus,
)
from ditto_apps.registry.live import r3_live_acceptance_driver as driver
from ditto_apps.registry.live.r3_live_evidence_store import canonical_bytes


def _lane_result(*, lane: driver.LiveLane = "stock") -> driver.LiveGoldenLaneResult:
    return driver.LiveGoldenLaneResult(
        schema="ditto.r3-live-golden-lane.v1",
        generated_at="2026-09-04T00:00:00+00:00",
        lane=lane,
        purpose="unit",
        experiment_id=f"experiment-{lane}",
        status="completed",
        eligible_month_count=24,
        strategy_id=f"strategy-{lane}",
        candidate_version=2,
        candidate_id=f"candidate-{lane}",
        strategy_spec_hash="a" * 64,
        snapshot_id=f"snapshot-{lane}",
        snapshot_manifest_hash="b" * 64,
        planning_document_path=f"planning/{lane}.json",
        planning_document_hash="c" * 64,
        plan_hash="d" * 64,
        parameter_hash="e" * 64,
        registry_hash="f" * 64,
        review_bundle_hash="1" * 64,
        selection_evidence_hash="2" * 64,
        holdout_claim_id=f"claim-{lane}",
        holdout_duplicate_blocked=True,
        factor_contribution_count=2,
        industry_exposure_count=3,
        size_exposure_count=4,
        r2_live_gate="pass",
        replay_dispatch_count=1,
    )


def _write_result(root: Path, result: driver.LiveGoldenLaneResult) -> Path:
    path = root / "records" / f"{result.lane}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_bytes(asdict(result)))
    return path


def test_lane_index_round_trip_authenticates_relative_content(tmp_path: Path) -> None:
    result = _lane_result()
    path = _write_result(tmp_path, result)
    content_hash = sha256(path.read_bytes()).hexdigest()

    driver._write_lane_index(tmp_path, result, path, content_hash)

    assert driver._read_lane_result(tmp_path, "stock") == result


def test_lane_index_rejects_shape_hash_and_path_escape(tmp_path: Path) -> None:
    index = tmp_path / "lanes" / "stock" / "current.json"
    index.parent.mkdir(parents=True)
    index.write_bytes(canonical_bytes({"relative_path": 7, "sha256": "a" * 64}))
    with pytest.raises(ValueError, match="index is invalid"):
        driver._read_lane_result(tmp_path, "stock")

    result = _lane_result()
    path = _write_result(tmp_path, result)
    index.write_bytes(
        canonical_bytes(
            {
                "relative_path": path.relative_to(tmp_path).as_posix(),
                "sha256": "0" * 64,
            }
        )
    )
    with pytest.raises(ValueError, match="hash drifted"):
        driver._read_lane_result(tmp_path, "stock")

    escaped = tmp_path.parent / f"{tmp_path.name}-escaped.json"
    escaped.write_bytes(path.read_bytes())
    index.write_bytes(
        canonical_bytes(
            {
                "relative_path": f"../{escaped.name}",
                "sha256": sha256(escaped.read_bytes()).hexdigest(),
            }
        )
    )
    with pytest.raises(ValueError, match="is not in the subpath"):
        driver._read_lane_result(tmp_path, "stock")


class _Catalog:
    def __init__(self, specs: list[object | None]) -> None:
        self._specs = iter(specs)

    def get_spec(self, _strategy_id: str, _version: int) -> object | None:
        return next(self._specs)


@contextmanager
def _strategy_bundle(
    *,
    catalog: object | None,
    bootstrap: object | None,
) -> Iterator[SimpleNamespace]:
    yield SimpleNamespace(catalog_service=catalog, seed_bootstrap=bootstrap)


@pytest.mark.parametrize(
    ("catalog", "bootstrap", "message"),
    [
        (None, object(), "catalog is unavailable"),
        (_Catalog([None]), None, "seed bootstrap is unavailable"),
        (
            _Catalog([None, None]),
            SimpleNamespace(run=lambda: None),
            "did not create v1",
        ),
    ],
)
def test_seed_bootstrap_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    catalog: object | None,
    bootstrap: object | None,
    message: str,
) -> None:
    monkeypatch.setattr(
        driver,
        "create_strategy_bundle",
        lambda: _strategy_bundle(catalog=catalog, bootstrap=bootstrap),
    )

    with pytest.raises(ValueError, match=message):
        driver._ensure_seed_v1("stock")


def test_seed_bootstrap_skips_existing_and_confirms_created_seed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runs: list[bool] = []
    bundles = iter(
        (
            _strategy_bundle(catalog=_Catalog([object()]), bootstrap=None),
            _strategy_bundle(
                catalog=_Catalog([None, object()]),
                bootstrap=SimpleNamespace(run=lambda: runs.append(True)),
            ),
        )
    )
    monkeypatch.setattr(driver, "create_strategy_bundle", lambda: next(bundles))

    driver._ensure_seed_v1("stock")
    driver._ensure_seed_v1("stock")

    assert runs == [True]


def test_build_planning_closes_composition_and_writes_artifact(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    closed: list[bool] = []
    requested: list[type[object]] = []
    container = SimpleNamespace(
        get=lambda service: requested.append(service) or object(),
        close=lambda: closed.append(True),
    )
    artifact = cast("driver.LivePlanningArtifact", SimpleNamespace())
    output = tmp_path / "planning.json"
    monkeypatch.setattr(driver, "_ensure_seed_v1", lambda _lane: None)
    monkeypatch.setattr(driver, "make_app_container", lambda: container)
    monkeypatch.setattr(
        driver,
        "build_live_planning_artifact",
        lambda **_kwargs: artifact,
    )
    monkeypatch.setattr(
        driver,
        "write_live_planning_artifact",
        lambda _artifact, _root: output,
    )

    assert driver._build_planning(
        lane="stock",
        purpose="unit",
        data_root=tmp_path,
        evidence_root=tmp_path,
    ) == (artifact, output)
    assert closed == [True]
    assert len(requested) == 9


def test_build_planning_closes_composition_when_builder_raises(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    closed: list[bool] = []
    container = SimpleNamespace(
        get=lambda _service: object(), close=lambda: closed.append(True)
    )
    monkeypatch.setattr(driver, "_ensure_seed_v1", lambda _lane: None)
    monkeypatch.setattr(driver, "make_app_container", lambda: container)

    def fail_build(**_kwargs: object) -> driver.LivePlanningArtifact:
        raise RuntimeError("builder failed")

    monkeypatch.setattr(driver, "build_live_planning_artifact", fail_build)

    with pytest.raises(RuntimeError, match="builder failed"):
        driver._build_planning(
            lane="stock",
            purpose="unit",
            data_root=tmp_path,
            evidence_root=tmp_path,
        )
    assert closed == [True]


@contextmanager
def _research_bundle(bundle: SimpleNamespace) -> Iterator[SimpleNamespace]:
    yield bundle


def _launch_artifact(*, plan_hash: object = "a" * 64) -> driver.LivePlanningArtifact:
    return cast(
        "driver.LivePlanningArtifact",
        SimpleNamespace(
            planning_document={"experiment_id": "experiment-live"},
            plan_hash=plan_hash,
            lane="stock",
            purpose="unit",
        ),
    )


@pytest.mark.parametrize(
    ("status", "report_hash", "artifact_hash", "message"),
    [
        (ExperimentPreflightStatus.BLOCKED, "a" * 64, "a" * 64, "planning drifted"),
        (ExperimentPreflightStatus.READY, "b" * 64, "a" * 64, "planning drifted"),
        (ExperimentPreflightStatus.READY, None, None, "lost its confirmed plan hash"),
    ],
)
def test_launch_rejects_preflight_drift(
    monkeypatch: pytest.MonkeyPatch,
    status: ExperimentPreflightStatus,
    report_hash: str | None,
    artifact_hash: object,
    message: str,
) -> None:
    request = SimpleNamespace(experiment_id="experiment-live")
    bundle = SimpleNamespace(
        planning_process=SimpleNamespace(
            preflight=lambda _request: SimpleNamespace(
                status=status,
                plan_hash=report_hash,
            )
        )
    )
    monkeypatch.setattr(
        driver, "build_experiment_planning_request", lambda _doc: request
    )
    monkeypatch.setattr(
        driver, "create_research_bundle", lambda: _research_bundle(bundle)
    )

    with pytest.raises(ValueError, match=message):
        driver._launch(_launch_artifact(plan_hash=artifact_hash))


def test_launch_requires_idempotent_handler_replay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = SimpleNamespace(experiment_id="experiment-live")
    responses = iter((object(), object()))
    bundle = SimpleNamespace(
        planning_process=SimpleNamespace(
            preflight=lambda _request: SimpleNamespace(
                status=ExperimentPreflightStatus.READY,
                plan_hash="a" * 64,
            )
        ),
        launch_handler=SimpleNamespace(handle=lambda _command: next(responses)),
    )
    monkeypatch.setattr(
        driver, "build_experiment_planning_request", lambda _doc: request
    )
    monkeypatch.setattr(
        driver, "create_research_bundle", lambda: _research_bundle(bundle)
    )

    with pytest.raises(ValueError, match="idempotency replay drifted"):
        driver._launch(_launch_artifact())


@pytest.mark.parametrize(
    ("detail", "message"),
    [
        (None, "experiment is missing"),
        (
            SimpleNamespace(status="failed", failure_code="WORKER_FAILED"),
            "terminal failure: failed/WORKER_FAILED",
        ),
    ],
)
def test_detail_fails_closed_for_missing_or_terminal_state(
    monkeypatch: pytest.MonkeyPatch,
    detail: object | None,
    message: str,
) -> None:
    bundle = SimpleNamespace(
        experiment_query=SimpleNamespace(get=lambda _experiment_id: detail)
    )
    monkeypatch.setattr(
        driver, "create_research_bundle", lambda: _research_bundle(bundle)
    )

    with pytest.raises(ValueError, match=message):
        driver._detail("experiment-live")


def test_tick_until_accepts_completion_and_rejects_replay_stage_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    completed = SimpleNamespace(stage="evidence", status="completed")
    monkeypatch.setattr(driver, "_detail", lambda _experiment_id: completed)
    assert (
        driver._tick_until(
            "experiment-live",
            target="completed",
            scheduler_tick=lambda **_kwargs: {},
        )
        is completed
    )

    details = iter(
        (
            SimpleNamespace(stage="candidate_selection", status="running"),
            SimpleNamespace(stage="holdout", status="running"),
        )
    )
    monkeypatch.setattr(driver, "_detail", lambda _experiment_id: next(details))
    with pytest.raises(ValueError, match="replay changed stage"):
        driver._tick_until(
            "experiment-live",
            target="candidate_selection",
            scheduler_tick=lambda **_kwargs: {},
        )


def _selection_bundle(detail: object, *, claim: object | None = None) -> object:
    return cast(
        "object",
        SimpleNamespace(
            experiment_query=SimpleNamespace(get=lambda _experiment_id: detail),
            candidate_evidence_reader=SimpleNamespace(
                scheduler_store=SimpleNamespace(
                    load_snapshot=lambda _experiment_id: SimpleNamespace(
                        holdout_claim=claim
                    )
                ),
                load_current_bundle=lambda _experiment_id, _candidate_id: None,
            ),
        ),
    )


@pytest.mark.parametrize(
    ("detail", "message"),
    [
        (None, "not ready for candidate selection"),
        (SimpleNamespace(stage="holdout"), "lacks its persisted claim"),
        (SimpleNamespace(stage="planning"), "not ready for candidate selection"),
        (
            SimpleNamespace(
                stage="candidate_selection",
                candidates=(
                    SimpleNamespace(is_baseline=False, candidate_id="candidate"),
                ),
            ),
            "candidate evidence bundle is missing",
        ),
    ],
)
def test_select_and_claim_fails_closed_before_mutation(
    detail: object | None,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        driver.select_and_claim_with_bundle(
            cast("driver.ResearchBundle", _selection_bundle(detail)),
            "experiment-live",
        )


def _evidence_bundle(
    *,
    packet: object | None,
    loaded: object | None,
) -> SimpleNamespace:
    return SimpleNamespace(
        experiment_query=SimpleNamespace(
            get_review_packet=lambda _experiment_id: packet,
        ),
        candidate_evidence_reader=SimpleNamespace(
            load_current_bundle=lambda _experiment_id, _candidate_id: loaded,
        ),
    )


def test_completed_evidence_requires_packet_bundle_and_one_r2_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cases = (
        (None, (object(), object()), "lacks review evidence"),
        (SimpleNamespace(), None, "lacks review evidence"),
        (
            SimpleNamespace(
                hard_review_blocked=True,
                gate_outcomes=(SimpleNamespace(rule_id="risk", outcome="fail"),),
            ),
            (object(), object()),
            "hard-gate blocked: risk=fail",
        ),
        (
            SimpleNamespace(hard_review_blocked=False, gate_outcomes=()),
            (object(), object()),
            "ambiguous R2 gate evidence",
        ),
    )
    for packet, loaded, message in cases:
        bundle = _evidence_bundle(packet=packet, loaded=loaded)
        monkeypatch.setattr(
            driver,
            "create_research_bundle",
            lambda bundle=bundle: _research_bundle(bundle),
        )
        with pytest.raises(ValueError, match=message):
            driver._completed_evidence("experiment-live", "candidate-live")

    packet = SimpleNamespace(
        hard_review_blocked=False,
        gate_outcomes=(SimpleNamespace(rule_id="r2_live_gate", outcome="pass"),),
    )
    evidence = object()
    bundle = _evidence_bundle(packet=packet, loaded=(object(), evidence))
    monkeypatch.setattr(
        driver, "create_research_bundle", lambda: _research_bundle(bundle)
    )
    assert driver._completed_evidence("experiment-live", "candidate-live") == (
        packet,
        evidence,
        "pass",
    )


def _planning_artifact() -> driver.LivePlanningArtifact:
    return cast(
        "driver.LivePlanningArtifact",
        SimpleNamespace(
            experiment_id="experiment-live",
            eligible_month_count=24,
            strategy_id="strategy-live",
            strategy_version=2,
            strategy_spec_hash="a" * 64,
            snapshot_id="snapshot-live",
            snapshot_manifest_hash="b" * 64,
            planning_document_hash="c" * 64,
            plan_hash="d" * 64,
        ),
    )


def _review_packet(*, exposure: object | None) -> object:
    return SimpleNamespace(
        parameter_hash="e" * 64,
        registry_hash="f" * 64,
        bundle_hash="1" * 64,
        selection_exposure=exposure,
    )


def _patch_golden_lane_dependencies(
    monkeypatch: pytest.MonkeyPatch,
    *,
    tmp_path: Path,
    detail: object,
    packet: object,
    evidence: object,
) -> tuple[list[str], list[driver.LiveGoldenLaneResult]]:
    root = tmp_path / "evidence"
    ticks: list[str] = []
    indexed: list[driver.LiveGoldenLaneResult] = []
    monkeypatch.setattr(
        driver,
        "_build_planning",
        lambda **_kwargs: (_planning_artifact(), root / "planning.json"),
    )
    monkeypatch.setattr(driver, "_launch", lambda _artifact: None)
    monkeypatch.setattr(driver, "_detail", lambda _experiment_id: detail)
    monkeypatch.setattr(
        driver,
        "_completed_evidence",
        lambda _experiment_id, _candidate_id: (packet, evidence, "pass"),
    )
    monkeypatch.setattr(
        driver,
        "write_addressed",
        lambda **_kwargs: (root / "results" / "result.json", "9" * 64),
    )
    monkeypatch.setattr(
        driver,
        "_write_lane_index",
        lambda _root, result, _path, _content_hash: indexed.append(result),
    )
    return ticks, indexed


def test_golden_lane_recovers_completed_evidence_without_reselecting(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    detail = SimpleNamespace(status="completed", stage="completed")
    packet = _review_packet(exposure=None)
    evidence = SimpleNamespace(factor_contributions=(1, 2))
    _, indexed = _patch_golden_lane_dependencies(
        monkeypatch,
        tmp_path=tmp_path,
        detail=detail,
        packet=packet,
        evidence=evidence,
    )
    replay_packet = SimpleNamespace(
        candidate_id="candidate-live",
        holdout_claim_id="claim-live",
        selection_evidence_artifact_id="selection-artifact",
    )
    bundle = SimpleNamespace(
        experiment_query=SimpleNamespace(
            get_review_packet=lambda _experiment_id: replay_packet,
            list_artifacts=lambda _experiment_id: (
                SimpleNamespace(
                    artifact_id="selection-artifact",
                    content_hash="2" * 64,
                ),
            ),
        )
    )
    monkeypatch.setattr(
        driver, "create_research_bundle", lambda: _research_bundle(bundle)
    )
    selected: list[str] = []

    result = driver.run_live_golden_lane(
        lane="stock",
        data_root=tmp_path,
        evidence_root=tmp_path / "evidence",
        purpose="unit",
        scheduler_tick=lambda **_kwargs: {"dispatch_count": 3},
        select_and_claim=lambda experiment_id: (
            selected.append(experiment_id) or ("candidate", "claim", "evidence", True)
        ),
    )

    assert selected == []
    assert result.candidate_id == "candidate-live"
    assert result.holdout_claim_id == "claim-live"
    assert result.industry_exposure_count == 0
    assert result.size_exposure_count == 0
    assert result.replay_dispatch_count == 3
    assert indexed == [result]


@pytest.mark.parametrize(
    ("packet", "message"),
    [
        (None, "replay evidence is incomplete"),
        (
            SimpleNamespace(candidate_id=None, holdout_claim_id="claim-live"),
            "replay evidence is incomplete",
        ),
        (
            SimpleNamespace(candidate_id="candidate-live", holdout_claim_id=None),
            "replay evidence is incomplete",
        ),
    ],
)
def test_golden_lane_rejects_incomplete_completed_replay(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    packet: object | None,
    message: str,
) -> None:
    root = tmp_path / "evidence"
    detail = SimpleNamespace(status="completed", stage="completed")
    monkeypatch.setattr(
        driver,
        "_build_planning",
        lambda **_kwargs: (_planning_artifact(), root / "planning.json"),
    )
    monkeypatch.setattr(driver, "_launch", lambda _artifact: None)
    monkeypatch.setattr(driver, "_detail", lambda _experiment_id: detail)
    bundle = SimpleNamespace(
        experiment_query=SimpleNamespace(
            get_review_packet=lambda _experiment_id: packet,
            list_artifacts=lambda _experiment_id: (),
        )
    )
    monkeypatch.setattr(
        driver, "create_research_bundle", lambda: _research_bundle(bundle)
    )

    with pytest.raises(ValueError, match=message):
        driver.run_live_golden_lane(
            lane="stock",
            data_root=tmp_path,
            evidence_root=root,
            purpose="unit",
            scheduler_tick=lambda **_kwargs: {"dispatch_count": 1},
            select_and_claim=lambda experiment_id: (
                "candidate",
                "claim",
                "evidence",
                True,
            ),
        )


@pytest.mark.parametrize(
    ("stage", "expected_targets"),
    [
        ("planning", ["candidate_selection", "completed"]),
        ("holdout", ["completed"]),
    ],
)
def test_golden_lane_advances_incomplete_work_and_projects_exposure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    stage: str,
    expected_targets: list[str],
) -> None:
    detail = SimpleNamespace(status="running", stage=stage)
    exposure = SimpleNamespace(
        industry_weights={"bank": 0.5},
        size_bucket_weights={"large": 0.7, "small": 0.3},
    )
    packet = _review_packet(exposure=exposure)
    evidence = SimpleNamespace(factor_contributions=(1, 2, 3))
    _, indexed = _patch_golden_lane_dependencies(
        monkeypatch,
        tmp_path=tmp_path,
        detail=detail,
        packet=packet,
        evidence=evidence,
    )
    targets: list[str] = []
    monkeypatch.setattr(
        driver,
        "_tick_until",
        lambda _experiment_id, *, target, scheduler_tick: (
            targets.append(target) or detail
        ),
    )

    result = driver.run_live_golden_lane(
        lane="stock",
        data_root=tmp_path,
        evidence_root=tmp_path / "evidence",
        purpose="unit",
        scheduler_tick=lambda **_kwargs: {"dispatch_count": 4},
        select_and_claim=lambda experiment_id: (
            "candidate-live",
            "claim-live",
            "2" * 64,
            True,
        ),
    )

    assert targets == expected_targets
    assert result.factor_contribution_count == 3
    assert result.industry_exposure_count == 1
    assert result.size_exposure_count == 2
    assert indexed == [result]


class _StableHandler:
    def __init__(self, result: object, *, drift: bool = False) -> None:
        self._result = result
        self._drift = drift
        self._calls = 0

    def handle(self, _command: object) -> object:
        self._calls += 1
        if self._drift and self._calls == 2:
            return object()
        return self._result


class _GovernanceContainer:
    def __init__(
        self,
        *,
        drift: str | None = None,
        active_versions: tuple[int | None, int | None] = (2, 1),
    ) -> None:
        self.closed = False
        pointer = SimpleNamespace(active_version=2, pointer_revision=7)
        restored = SimpleNamespace(active_version=1, pointer_revision=8)
        self.handlers = {
            driver.SubmitReviewHandler: _StableHandler(
                SimpleNamespace(state="review"),
                drift=drift == "submit",
            ),
            driver.ApproveReviewHandler: _StableHandler(
                SimpleNamespace(state="approved"),
                drift=drift == "approve",
            ),
            driver.PublishStrategyVersionHandler: _StableHandler(
                pointer,
                drift=drift == "publish",
            ),
            driver.ReactivateStrategyHandler: _StableHandler(
                restored,
                drift=drift == "reactivate",
            ),
        }
        actives = iter(active_versions)

        def get_active(_strategy_id: str) -> object | None:
            version = next(actives)
            if version is None:
                return None
            return SimpleNamespace(version=version, spec_hash="a" * 64)

        self.catalog = SimpleNamespace(get_active_published=get_active)

    def get(self, service: type[object]) -> object:
        if service is driver.StrategyCatalogService:
            return self.catalog
        return self.handlers[service]

    def close(self) -> None:
        self.closed = True


def test_governance_lane_replays_every_mutation_and_restores_v1(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    container = _GovernanceContainer()
    monkeypatch.setattr(driver, "make_app_container", lambda: container)

    result = driver._govern_lane(lane_result=_lane_result(), actor="operator")

    assert result.strategy_id == "strategy-stock"
    assert result.candidate_version == 2
    assert result.published_active_version == 2
    assert result.published_pointer_revision == 7
    assert result.reactivated_active_version == 1
    assert result.reactivated_pointer_revision == 8
    assert container.closed is True


@pytest.mark.parametrize(
    ("drift", "message"),
    [
        ("submit", "submit-review idempotency replay drifted"),
        ("approve", "approve idempotency replay drifted"),
        ("publish", "publish idempotency replay drifted"),
        ("reactivate", "reactivation idempotency replay drifted"),
    ],
)
def test_governance_lane_rejects_idempotency_drift_and_closes_container(
    monkeypatch: pytest.MonkeyPatch,
    drift: str,
    message: str,
) -> None:
    container = _GovernanceContainer(drift=drift)
    monkeypatch.setattr(driver, "make_app_container", lambda: container)

    with pytest.raises(ValueError, match=message):
        driver._govern_lane(lane_result=_lane_result(), actor="operator")
    assert container.closed is True


@pytest.mark.parametrize(
    ("active_versions", "message"),
    [
        ((None, 1), "did not advance"),
        ((3, 1), "did not advance"),
        ((2, None), "did not restore"),
        ((2, 2), "did not restore"),
    ],
)
def test_governance_lane_requires_exact_active_pointer_transitions(
    monkeypatch: pytest.MonkeyPatch,
    active_versions: tuple[int | None, int | None],
    message: str,
) -> None:
    container = _GovernanceContainer(active_versions=active_versions)
    monkeypatch.setattr(driver, "make_app_container", lambda: container)

    with pytest.raises(ValueError, match=message):
        driver._govern_lane(lane_result=_lane_result(), actor="operator")
    assert container.closed is True


def test_governance_lifecycle_processes_both_lanes_and_writes_evidence(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    governed: list[str] = []
    writes: list[dict[str, object]] = []
    monkeypatch.setattr(
        driver,
        "_read_lane_result",
        lambda _root, lane: _lane_result(lane=lane),
    )

    def govern(
        *, lane_result: driver.LiveGoldenLaneResult, actor: str
    ) -> driver.LiveGovernanceLaneResult:
        governed.append(f"{lane_result.lane}:{actor}")
        return driver.LiveGovernanceLaneResult(
            lane=lane_result.lane,
            strategy_id=lane_result.strategy_id,
            candidate_version=2,
            bundle_hash=lane_result.review_bundle_hash,
            published_active_version=2,
            published_pointer_revision=7,
            r1_active_spec_hash="a" * 64,
            reactivated_active_version=1,
            reactivated_pointer_revision=8,
        )

    monkeypatch.setattr(driver, "_govern_lane", govern)
    monkeypatch.setattr(
        driver,
        "write_addressed",
        lambda **kwargs: writes.append(kwargs) or (tmp_path / "result.json", "a" * 64),
    )

    result = driver.run_live_governance_lifecycle(
        data_root=tmp_path,
        evidence_root=tmp_path,
        actor="operator",
    )

    assert governed == ["stock:operator", "etf:operator"]
    assert result.lanes == ("stock", "etf")
    assert len(result.results) == 2
    assert writes[0]["category"] == "governance"
