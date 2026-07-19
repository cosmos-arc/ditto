"""Tests that analysis product namespaces expose honest public contracts."""

from __future__ import annotations

import importlib
from pathlib import Path
from types import ModuleType

import pytest

PUBLIC_MODULE_NAMES = ("ditto_analysis.experiments",)
ANALYSIS_ROOT = Path(__file__).parents[2]


@pytest.fixture(params=PUBLIC_MODULE_NAMES)
def public_module(request: pytest.FixtureRequest) -> ModuleType:
    """Import one promoted analysis product namespace."""
    return importlib.import_module(str(request.param))


def test_experiment_namespace_exports_stable_domain_contracts(
    public_module: ModuleType,
) -> None:
    """The promoted namespace exposes contracts, not application behavior."""
    expected = {
        "AttemptId",
        "CandidateId",
        "CandidateSpec",
        "ExperimentId",
        "ExperimentLaunchSpec",
        "ExperimentStatus",
        "FoldId",
        "validate_status_transition",
    }
    assert expected <= set(public_module.__all__)


def test_experiment_namespace_does_not_claim_or_export_runtime_behavior(
    public_module: ModuleType,
) -> None:
    """Analysis owns pure contracts; scheduling and I/O remain elsewhere."""
    docstring = public_module.__doc__

    assert docstring is not None
    assert "pure domain contracts" in docstring
    assert "does not schedule" in docstring
    assert "does not persist" in docstring
    assert not {"ExperimentCoordinator", "ExperimentStore", "ExperimentWorker"} & set(
        public_module.__all__
    )


@pytest.mark.parametrize("guide_name", ["AGENTS.md", "CLAUDE.md"])
def test_analysis_guides_describe_experiments_as_contracts_not_runtime(
    guide_name: str,
) -> None:
    guide = (ANALYSIS_ROOT / guide_name).read_text(encoding="utf-8")

    assert "experiments" in guide
    assert "纯领域合同" in guide
    assert "调度" in guide
    assert "存储" in guide
    assert "experiments` 是 reserved" not in guide
