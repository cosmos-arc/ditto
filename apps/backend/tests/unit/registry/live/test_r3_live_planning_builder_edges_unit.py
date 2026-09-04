"""Fail-closed edge contracts for the R3 live planning builder."""

from __future__ import annotations

import hashlib
from contextlib import nullcontext
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import orjson
import pytest
from apps.backend.tests.unit.scripts import (
    test_r3_live_planning_builder_unit as fixtures,
)
from ditto_application.commands.strategy import UpdateStrategyHandler
from ditto_apps.registry.live import r3_live_planning_builder as subject
from ditto_strategy.models import StrategySpecRecord
from ditto_strategy.storage.sqlite.services.strategy_catalog_service import (
    StrategyCatalogService,
)


class _Catalog:
    def __init__(
        self,
        *,
        seed: StrategySpecRecord | None,
        latest: StrategySpecRecord | None = None,
        seed_state: str | None = "published",
        latest_state: str | None = "draft",
        hide_updated_version: bool = False,
    ) -> None:
        self.seed = seed
        self.latest = latest if latest is not None else seed
        self.seed_state = seed_state
        self.latest_state = latest_state
        self.hide_updated_version = hide_updated_version

    def get_spec(
        self,
        strategy_id: str,
        version: int | None = None,
    ) -> StrategySpecRecord | None:
        del strategy_id
        if version == 1:
            return self.seed
        if version is not None and self.hide_updated_version:
            return None
        return self.latest

    def get_version_state(self, strategy_id: str, version: int) -> str | None:
        del strategy_id
        return self.seed_state if version == 1 else self.latest_state


class _NoUpdate:
    def handle(self, _command: object) -> object:
        return object()


def _catalog(value: _Catalog) -> StrategyCatalogService:
    return cast(StrategyCatalogService, value)


def _update() -> UpdateStrategyHandler:
    return cast(UpdateStrategyHandler, _NoUpdate())


@pytest.mark.parametrize("condition", ["missing", "drift"])
def test_seed_record_requires_exact_published_canonical_v1(condition: str) -> None:
    strategy_id = "seed_stock_selection_rotation"
    seed = fixtures._seed_record(strategy_id, 1)
    catalog = _Catalog(seed=None if condition == "missing" else seed)
    if condition == "drift":
        catalog.seed_state = "draft"

    with pytest.raises(ValueError, match="canonical seed v1"):
        subject._require_seed_record(_catalog(catalog), strategy_id)


@pytest.mark.parametrize(
    ("strategy_id", "strategy_version", "message"),
    [
        ("candidate", None, "requires both"),
        (" candidate ", 2, "identity is invalid"),
    ],
)
def test_explicit_candidate_requires_complete_normalized_identity(
    strategy_id: str,
    strategy_version: int | None,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        subject.ensure_research_candidate(
            lane="stock",
            catalog=_catalog(_Catalog(seed=None)),
            update_handler=_update(),
            strategy_id=strategy_id,
            strategy_version=strategy_version,
        )


def test_explicit_candidate_must_remain_an_exact_open_record() -> None:
    record = fixtures._seed_record("seed_stock_selection_rotation", 2)
    catalog = _Catalog(
        seed=None,
        latest=record,
        latest_state="published",
    )

    with pytest.raises(ValueError, match="exact research candidate is unavailable"):
        subject.ensure_research_candidate(
            lane="stock",
            catalog=_catalog(catalog),
            update_handler=_update(),
            strategy_id=record.strategy_id,
            strategy_version=record.version,
        )


def test_seed_bootstrap_must_leave_a_latest_candidate() -> None:
    strategy_id = "seed_stock_selection_rotation"
    seed = fixtures._seed_record(strategy_id, 1)
    catalog = _Catalog(seed=seed)
    catalog.latest = None

    with pytest.raises(ValueError, match="catalog is empty"):
        subject.ensure_research_candidate(
            lane="stock",
            catalog=_catalog(catalog),
            update_handler=_update(),
        )


def test_published_candidate_update_must_be_immediately_visible() -> None:
    strategy_id = "seed_stock_selection_rotation"
    seed = fixtures._seed_record(strategy_id, 1)
    catalog = _Catalog(
        seed=seed,
        latest=seed,
        latest_state="published",
        hide_updated_version=True,
    )

    with pytest.raises(ValueError, match="strategy update disappeared"):
        subject.ensure_research_candidate(
            lane="stock",
            catalog=_catalog(catalog),
            update_handler=_update(),
        )


@pytest.mark.parametrize("condition", ["state", "semantics"])
def test_reusable_candidate_requires_open_state_and_seed_semantics(
    condition: str,
) -> None:
    strategy_id = "seed_stock_selection_rotation"
    seed = fixtures._seed_record(strategy_id, 1)
    candidate = fixtures._seed_record(strategy_id, 2)
    if condition == "semantics":
        candidate = replace(candidate, spec_hash="a" * 64)
    catalog = _Catalog(
        seed=seed,
        latest=candidate,
        latest_state="archived" if condition == "state" else "draft",
    )

    with pytest.raises(ValueError, match=r"no reusable|drifted from seed"):
        subject.ensure_research_candidate(
            lane="stock",
            catalog=_catalog(catalog),
            update_handler=_update(),
        )


def test_baseline_identity_is_lane_specific() -> None:
    seed = fixtures._seed_record("seed_etf_industry_rotation", 1)

    stock = subject._baseline("stock", seed)
    etf = subject._baseline("etf", seed)

    assert stock.payload == {}
    assert etf.payload == {
        "strategy_id": seed.strategy_id,
        "version": seed.version,
        "spec_hash": seed.spec_hash,
    }


def test_planning_authority_time_must_be_timezone_aware() -> None:
    candidate = replace(
        fixtures._seed_record("seed_stock_selection_rotation", 2),
        created_at="2026-08-01T00:00:00",
    )
    snapshot = cast(
        subject.LiveResearchSnapshotBuild,
        SimpleNamespace(dataset_bindings=()),
    )

    with pytest.raises(ValueError, match="timezone-aware"):
        subject._planning_time(candidate, snapshot)


def test_requirements_reject_missing_certification_binding() -> None:
    snapshot = cast(
        subject.LiveResearchSnapshotBuild,
        SimpleNamespace(dataset_bindings=(), snapshot_start="2015-01-01"),
    )

    with pytest.raises(ValueError, match="lacks required certification"):
        subject._requirements(snapshot, ("stock_daily",))


def _artifact(document: dict[str, object]) -> subject.LivePlanningArtifact:
    digest = hashlib.sha256(
        orjson.dumps(document, option=orjson.OPT_SORT_KEYS)
    ).hexdigest()
    return subject.LivePlanningArtifact(
        schema="ditto.r3-live-planning-artifact.v1",
        lane="stock",
        purpose="edge-contract",
        strategy_id="strategy-1",
        strategy_version=2,
        strategy_spec_hash="a" * 64,
        snapshot_id="snapshot-1",
        snapshot_manifest_hash="b" * 64,
        experiment_id="experiment-1",
        research_cycle_id="cycle-1",
        planning_document_hash=digest,
        plan_hash="c" * 64,
        preflight_status="ready",
        eligible_month_count=96,
        candidate_count=1,
        planning_document=document,
    )


def test_planning_artifact_write_is_immutable_and_idempotent(tmp_path: Path) -> None:
    artifact = _artifact({"experiment_id": "experiment-1"})

    path = subject.write_live_planning_artifact(artifact, tmp_path)
    assert subject.write_live_planning_artifact(artifact, tmp_path) == path
    path.write_bytes(b"drifted")

    with pytest.raises(ValueError, match="replay drift"):
        subject.write_live_planning_artifact(artifact, tmp_path)


def test_planning_artifact_rejects_document_hash_drift(tmp_path: Path) -> None:
    artifact = replace(
        _artifact({"experiment_id": "experiment-1"}),
        planning_document_hash="d" * 64,
    )

    with pytest.raises(ValueError, match="changed before artifact publication"):
        subject.write_live_planning_artifact(artifact, tmp_path)


def test_build_rejects_noncanonical_purpose_before_accessing_services(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="canonical lowercase kebab-case"):
        subject.build_live_planning_artifact(
            lane="stock",
            purpose="Not Canonical",
            data_root=tmp_path,
            services=cast(subject.LivePlanningServices, object()),
        )


def _main_args(tmp_path: Path, *extra: str) -> list[str]:
    data_root = tmp_path / "state"
    data_root.mkdir(exist_ok=True)
    return [
        "--lane",
        "stock",
        "--purpose",
        "edge-contract",
        "--data-root",
        str(data_root),
        "--output-root",
        str(tmp_path / "evidence"),
        *extra,
    ]


def test_cli_rejects_state_root_and_partial_strategy_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(subject, "state_root_matches", lambda _root: False)
    with pytest.raises(SystemExit, match="DITTO_STATE_ROOT"):
        subject.main(_main_args(tmp_path))

    monkeypatch.setattr(subject, "state_root_matches", lambda _root: True)
    with pytest.raises(SystemExit, match="provided together"):
        subject.main(_main_args(tmp_path, "--strategy-id", "strategy-1"))


@pytest.mark.parametrize("condition", ["catalog", "bootstrap", "bootstrap_run"])
def test_cli_seed_bootstrap_fails_closed_before_container_composition(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    condition: str,
) -> None:
    class _Bootstrap:
        def run(self) -> None:
            raise RuntimeError("bootstrap-sentinel")

    catalog = None
    bootstrap: object | None = None
    if condition != "catalog":
        catalog = SimpleNamespace(get_spec=lambda *_args: None)
        bootstrap = None if condition == "bootstrap" else _Bootstrap()
    bundle = SimpleNamespace(catalog_service=catalog, seed_bootstrap=bootstrap)
    monkeypatch.setattr(subject, "state_root_matches", lambda _root: True)
    monkeypatch.setattr(subject, "create_strategy_bundle", lambda: nullcontext(bundle))

    expected = RuntimeError if condition == "bootstrap_run" else SystemExit
    with pytest.raises(expected):
        subject.main(_main_args(tmp_path))
