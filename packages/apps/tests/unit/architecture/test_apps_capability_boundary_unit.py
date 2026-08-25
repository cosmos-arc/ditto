"""Apps non-registry capability import boundary tests."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

_SCRIPT = (
    Path(__file__).resolve().parents[5]
    / "scripts"
    / "architecture"
    / "check_architecture_smells.py"
)


def _load_module() -> object:
    spec = spec_from_file_location("check_architecture_smells", _SCRIPT)
    if spec is None or spec.loader is None:
        msg = f"Cannot load {_SCRIPT}"
        raise ImportError(msg)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_MODULE = _load_module()


def test_apps_host_composition_allowances_are_owned_and_reasoned() -> None:
    allowances = _MODULE.APPS_HOST_COMPOSITION_ALLOWANCES  # type: ignore[attr-defined]

    assert allowances
    assert all(allowance.owner for allowance in allowances)
    assert all(allowance.reason for allowance in allowances)
    assert {allowance.path: allowance.allowed_modules for allowance in allowances} == {
        "packages/apps/src/ditto_apps/jobs/context.py": frozenset(
            {
                "ditto_data.quality",
                "ditto_data.quality.protocols",
            }
        ),
        "packages/apps/src/ditto_apps/jobs/tasks/monitoring.py": frozenset(
            {"ditto_data.quality.quality_types"}
        ),
        "packages/apps/src/ditto_apps/registry/infra/protocol_adapters.py": frozenset(
            {
                "ditto_data.quality.protocols",
                "ditto_data.services.source_accessor",
                "ditto_data.sources.tdx.source",
                "ditto_data.storage.metadata.instrument",
                "ditto_data.storage.runtime.quality",
                "ditto_features.compile_cache",
            }
        ),
        "packages/apps/src/ditto_apps/scripts/r5_sandbox_live_acceptance.py": (
            frozenset(
                {
                    "ditto_analysis.experiments.generated_code",
                    "ditto_analysis.experiments.models",
                }
            )
        ),
    }


def test_apps_registry_composition_allowances_are_owned_and_reasoned() -> None:
    allowances = _MODULE.APPS_REGISTRY_COMPOSITION_ALLOWANCES  # type: ignore[attr-defined]

    assert allowances
    assert all(allowance.owner for allowance in allowances)
    assert all(allowance.reason for allowance in allowances)
    assert {allowance.path: allowance.allowed_modules for allowance in allowances}[
        "packages/apps/src/ditto_apps/registry/agent/campaign_runtime.py"
    ] == frozenset(
        {
            "ditto_analysis.errors",
            "ditto_analysis.experiments.campaign_persistence",
            "ditto_analysis.experiments.models",
        }
    )
    assert {allowance.path: allowance.allowed_modules for allowance in allowances}[
        "packages/apps/src/ditto_apps/registry/agent/oci_sandbox.py"
    ] == frozenset(
        {
            "ditto_analysis.experiments.generated_code",
            "ditto_analysis.experiments.models",
            "ditto_analysis.experiments.persistence",
        }
    )
    assert {allowance.path: allowance.allowed_modules for allowance in allowances}[
        "packages/apps/src/ditto_apps/registry/agent/oci_sandbox_runner.py"
    ] == frozenset({"ditto_analysis.experiments.models"})
    assert {allowance.path: allowance.allowed_modules for allowance in allowances}[
        "packages/apps/src/ditto_apps/registry/agent/r5_sandbox_live_report.py"
    ] == frozenset(
        {
            "ditto_analysis.experiments.generated_code",
            "ditto_analysis.experiments.models",
        }
    )
    assert {allowance.path: allowance.allowed_modules for allowance in allowances}[
        "packages/apps/src/ditto_apps/registry/contexts/query.py"
    ] == frozenset(
        {
            "ditto_data.services.capital_store",
            "ditto_data.services.fundamental_store",
            "ditto_data.services.macro_service",
            "ditto_data.services.market_service",
            "ditto_data.services.metadata_service",
        }
    )
    assert {allowance.path: allowance.allowed_modules for allowance in allowances}[
        "packages/apps/src/ditto_apps/registry/contexts/ingestion.py"
    ] == frozenset(
        {
            "ditto_data.catalog",
            "ditto_data.catalog.fallback_policy",
            "ditto_data.ingestion.freeze_store",
            "ditto_data.ingestion.ingestion_cursor_store",
            "ditto_data.ingestion.ingestion_log_store",
            "ditto_data.lineage",
            "ditto_data.services.capital_store",
            "ditto_data.services.fundamental_store",
            "ditto_data.services.macro_service",
            "ditto_data.services.market_service",
            "ditto_data.services.market_write_service",
            "ditto_data.services.metadata_service",
            "ditto_data.services.source_accessor",
            "ditto_data.sources.exchange_transformers",
            "ditto_data.sources.registry",
        }
    )
    assert {allowance.path: allowance.allowed_modules for allowance in allowances}[
        "packages/apps/src/ditto_apps/registry/contexts/r3_recovery.py"
    ] == frozenset(
        {
            "ditto_analysis.storage.sqlite.experiments",
            "ditto_analysis.storage.sqlite.experiments.schema",
            "ditto_data.config.data_store",
            "ditto_strategy.governance.service",
            "ditto_strategy.storage.sqlite.strategy_governance_schema",
            "ditto_strategy.storage.sqlite.strategy_governance_store",
        }
    )
    assert {allowance.path: allowance.allowed_modules for allowance in allowances}[
        "packages/apps/src/ditto_apps/registry/infra/risk_persistence.py"
    ] == frozenset({"ditto_risk.continuous_gate"})


def test_apps_capability_import_guard_reports_non_registry_routes() -> None:
    check = _MODULE.check_apps_non_registry_capability_imports  # type: ignore[attr-defined]

    errors = check(
        "from ditto_data.sources.protocols import MarketFetcher",
        "packages/apps/src/ditto_apps/api/routes/source.py",
    )

    assert errors == [
        "packages/apps/src/ditto_apps/api/routes/source.py: "
        "apps non-registry module imports capability package "
        "'ditto_data.sources.protocols'; use application facades or "
        "registry composition",
    ]


def test_apps_capability_import_guard_reports_alias_imported_capability() -> None:
    check = _MODULE.check_apps_non_registry_capability_imports  # type: ignore[attr-defined]

    errors = check(
        "from ditto_data import services",
        "packages/apps/src/ditto_apps/api/routes/source.py",
    )

    assert errors == [
        "packages/apps/src/ditto_apps/api/routes/source.py: "
        "apps non-registry module imports capability package "
        "'ditto_data.services'; use application facades or registry composition",
    ]


def test_apps_capability_import_guard_allows_registry_composition() -> None:
    check = _MODULE.check_apps_non_registry_capability_imports  # type: ignore[attr-defined]

    errors = check(
        "from ditto_data.services.market_service import MarketService",
        "packages/apps/src/ditto_apps/registry/contexts/query.py",
    )

    assert errors == []


def test_apps_capability_import_guard_rejects_unowned_registry_future_file() -> None:
    check = _MODULE.check_apps_non_registry_capability_imports  # type: ignore[attr-defined]

    errors = check(
        "from ditto_data.services.market_service import MarketService",
        "packages/apps/src/ditto_apps/registry/contexts/future.py",
    )

    assert errors == [
        "packages/apps/src/ditto_apps/registry/contexts/future.py: "
        "apps registry module imports unowned capability package "
        "'ditto_data.services.market_service'; add an owned exact registry "
        "composition allowance or use application facades",
    ]


def test_apps_capability_import_guard_rejects_unowned_registry_module() -> None:
    check = _MODULE.check_apps_non_registry_capability_imports  # type: ignore[attr-defined]

    errors = check(
        "from ditto_features.di import get_features_providers",
        "packages/apps/src/ditto_apps/registry/contexts/query.py",
    )

    assert errors == [
        "packages/apps/src/ditto_apps/registry/contexts/query.py: "
        "apps registry module imports unowned capability package "
        "'ditto_features.di'; add an owned exact registry composition "
        "allowance or use application facades",
    ]


def test_apps_capability_import_guard_rejects_registry_wildcard_import() -> None:
    check = _MODULE.check_apps_non_registry_capability_imports  # type: ignore[attr-defined]

    errors = check(
        "from ditto_data.services.market_service import *",
        "packages/apps/src/ditto_apps/registry/contexts/query.py",
    )

    assert errors == [
        "packages/apps/src/ditto_apps/registry/contexts/query.py: "
        "apps registry composition allowance cannot use wildcard import "
        "from 'ditto_data.services.market_service'; import explicit owned "
        "symbols or protocols",
    ]


def test_apps_capability_import_guard_allows_prefect_host_quality_exception() -> None:
    check = _MODULE.check_apps_non_registry_capability_imports  # type: ignore[attr-defined]

    errors = check(
        "from ditto_data import quality",
        "packages/apps/src/ditto_apps/jobs/context.py",
    )

    assert errors == []


def test_apps_capability_import_guard_allows_prefect_host_quality_protocols() -> None:
    check = _MODULE.check_apps_non_registry_capability_imports  # type: ignore[attr-defined]

    errors = check(
        "from ditto_data.quality.protocols import QualityEngineProtocol",
        "packages/apps/src/ditto_apps/jobs/context.py",
    )

    assert errors == []


def test_apps_capability_import_guard_rejects_prefect_host_quality_submodule() -> None:
    check = _MODULE.check_apps_non_registry_capability_imports  # type: ignore[attr-defined]

    errors = check(
        "from ditto_data.quality import golden",
        "packages/apps/src/ditto_apps/jobs/context.py",
    )

    assert errors == [
        "packages/apps/src/ditto_apps/jobs/context.py: "
        "apps non-registry module imports capability package "
        "'ditto_data.quality.golden'; use application facades or "
        "registry composition",
    ]


def test_apps_capability_import_guard_rejects_prefect_host_wildcard_import() -> None:
    check = _MODULE.check_apps_non_registry_capability_imports  # type: ignore[attr-defined]

    errors = check(
        "from ditto_data.quality import *",
        "packages/apps/src/ditto_apps/jobs/context.py",
    )

    assert errors == [
        "packages/apps/src/ditto_apps/jobs/context.py: "
        "apps host composition allowance cannot use wildcard import from "
        "'ditto_data.quality'; import explicit owned symbols or protocols",
    ]


def test_apps_capability_import_guard_rejects_only_real_mixed_submodule() -> None:
    check = _MODULE.check_apps_non_registry_capability_imports  # type: ignore[attr-defined]

    errors = check(
        "from ditto_data.quality import QualityEngine, golden",
        "packages/apps/src/ditto_apps/jobs/context.py",
    )

    assert errors == [
        "packages/apps/src/ditto_apps/jobs/context.py: "
        "apps non-registry module imports capability package "
        "'ditto_data.quality.golden'; use application facades or "
        "registry composition",
    ]


def test_apps_capability_import_guard_limits_prefect_host_exception() -> None:
    check = _MODULE.check_apps_non_registry_capability_imports  # type: ignore[attr-defined]

    errors = check(
        "from ditto_data.services.market_service import MarketService",
        "packages/apps/src/ditto_apps/jobs/context.py",
    )

    assert errors == [
        "packages/apps/src/ditto_apps/jobs/context.py: "
        "apps non-registry module imports capability package "
        "'ditto_data.services.market_service'; use application facades or "
        "registry composition",
    ]


def test_apps_capability_import_guard_rejects_dq_batch_quality_types() -> None:
    check = _MODULE.check_apps_non_registry_capability_imports  # type: ignore[attr-defined]

    errors = check(
        "from ditto_data.quality.quality_types import DQIssue",
        "packages/apps/src/ditto_apps/jobs/tasks/dq_batch.py",
    )

    assert errors == [
        "packages/apps/src/ditto_apps/jobs/tasks/dq_batch.py: "
        "apps non-registry module imports capability package "
        "'ditto_data.quality.quality_types'; use application facades or "
        "registry composition"
    ]


def test_apps_capability_import_guard_allows_monitoring_quality_types() -> None:
    check = _MODULE.check_apps_non_registry_capability_imports  # type: ignore[attr-defined]

    errors = check(
        "from ditto_data.quality.quality_types import DQResult",
        "packages/apps/src/ditto_apps/jobs/tasks/monitoring.py",
    )

    assert errors == []


def test_apps_capability_import_guard_rejects_unowned_host_alias_import() -> None:
    check = _MODULE.check_apps_non_registry_capability_imports  # type: ignore[attr-defined]

    errors = check(
        "from ditto_data import services",
        "packages/apps/src/ditto_apps/jobs/context.py",
    )

    assert errors == [
        "packages/apps/src/ditto_apps/jobs/context.py: "
        "apps non-registry module imports capability package "
        "'ditto_data.services'; use application facades or registry composition",
    ]
