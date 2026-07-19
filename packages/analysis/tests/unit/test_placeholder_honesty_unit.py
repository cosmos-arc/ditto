"""Tests that analysis product namespaces expose honest public contracts."""

from __future__ import annotations

import importlib
from pathlib import Path
from types import ModuleType

import pytest

PUBLIC_MODULE_NAMES = ("ditto_analysis.experiments",)
ANALYSIS_ROOT = Path(__file__).parents[2]
SUPERSEDED_EXPERIMENT_RECORDS = {
    "AttemptRecord",
    "CandidateRecord",
    "FoldRecord",
}


@pytest.fixture(params=PUBLIC_MODULE_NAMES)
def public_module(request: pytest.FixtureRequest) -> ModuleType:
    """Import one promoted analysis product namespace."""
    return importlib.import_module(str(request.param))


def test_experiment_namespace_exports_stable_domain_contracts(
    public_module: ModuleType,
) -> None:
    """The promoted namespace exposes contracts, not application behavior."""
    expected = {
        "ArtifactRecord",
        "AttemptId",
        "AttemptView",
        "CandidateId",
        "CandidateSpec",
        "FoldKey",
        "ExperimentId",
        "ExperimentLaunchSpec",
        "ExperimentStatus",
        "LeaseFence",
        "ResearchCycleIdentity",
        "FoldId",
        "validate_status_transition",
    }
    assert expected <= set(public_module.__all__)


def test_experiment_namespace_does_not_publish_superseded_record_types(
    public_module: ModuleType,
) -> None:
    """The promoted namespace exposes only the final typed persistence surface."""
    assert not SUPERSEDED_EXPERIMENT_RECORDS & set(public_module.__all__)
    assert all(
        not hasattr(public_module, record_name)
        for record_name in SUPERSEDED_EXPERIMENT_RECORDS
    )


def test_experiment_domain_does_not_define_superseded_record_types() -> None:
    """The obsolete parallel model hierarchy cannot be imported from its leaf."""
    domain_module = importlib.import_module("ditto_analysis.experiments.models")

    assert all(
        not hasattr(domain_module, record_name)
        for record_name in SUPERSEDED_EXPERIMENT_RECORDS
    )


def test_experiment_namespace_owns_contracts_but_keeps_runtime_in_storage_leaf(
    public_module: ModuleType,
) -> None:
    """Analysis owns pure contracts; scheduling and I/O remain elsewhere."""
    docstring = public_module.__doc__

    assert docstring is not None
    assert "domain and persistence contracts" in docstring
    assert "does not schedule" in docstring
    assert "storage adapters live under" in docstring
    assert not {
        "ExperimentCoordinator",
        "ExperimentStore",
        "ExperimentWorker",
        "ResearchExperimentDatabase",
        "SQLiteExperimentReader",
        "SQLiteExperimentWriter",
    } & set(public_module.__all__)


@pytest.mark.parametrize("guide_name", ["AGENTS.md", "CLAUDE.md"])
def test_analysis_guides_describe_experiments_as_contracts_not_runtime(
    guide_name: str,
) -> None:
    guide = (ANALYSIS_ROOT / guide_name).read_text(encoding="utf-8")

    assert "experiments" in guide
    assert "领域与持久化合同" in guide
    assert "调度" in guide
    assert "存储" in guide
    assert "experiments` 是 reserved" not in guide
