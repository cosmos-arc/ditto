from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest

_SCRIPT = (
    Path(__file__).resolve().parents[5]
    / "scripts"
    / "architecture"
    / "check_architecture_smells.py"
)


def _load_checker() -> object:
    spec = spec_from_file_location("check_architecture_smells", _SCRIPT)
    if spec is None or spec.loader is None:
        msg = f"Cannot load {_SCRIPT}"
        raise ImportError(msg)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_MOD = _load_checker()
APPS_CAPABILITY_IMPORT_ROOTS = _MOD.APPS_CAPABILITY_IMPORT_ROOTS  # type: ignore[attr-defined]
DATA_FORBIDDEN_SEMANTIC_TERMS = _MOD.DATA_FORBIDDEN_SEMANTIC_TERMS  # type: ignore[attr-defined]
PLATFORM_FORBIDDEN_DOMAIN_TERMS = _MOD.PLATFORM_FORBIDDEN_DOMAIN_TERMS  # type: ignore[attr-defined]
check_data_no_derived_feature_ownership = _MOD.check_data_no_derived_feature_ownership  # type: ignore[attr-defined]
check_platform_no_domain_semantics = _MOD.check_platform_no_domain_semantics  # type: ignore[attr-defined]
check_production_no_analysis = _MOD.check_production_no_analysis  # type: ignore[attr-defined]
_is_semantic_scan_target = _MOD._is_semantic_scan_target  # type: ignore[attr-defined]


def test_task8_experiment_sources_forbid_type_checking_cycle_hides():
    assert hasattr(_MOD, "check_experiment_source_no_type_checking")
    checker = _MOD.check_experiment_source_no_type_checking  # type: ignore[attr-defined]

    errors = checker(
        "from typing import TYPE_CHECKING\n\nif TYPE_CHECKING:\n    from x import Y\n",
        ("packages/application/src/ditto_application/processes/experiments/example.py"),
    )

    assert errors == [
        "packages/application/src/ditto_application/processes/experiments/"
        "example.py: experiment source imports TYPE_CHECKING; extract a neutral "
        "contract instead of hiding an import cycle"
    ]

    authority_errors = checker(
        "from typing import TYPE_CHECKING\n\nif TYPE_CHECKING:\n    from x import Y\n",
        "packages/application/src/ditto_application/research_validation_contracts.py",
    )

    assert authority_errors == [
        "packages/application/src/ditto_application/"
        "research_validation_contracts.py: experiment source imports "
        "TYPE_CHECKING; extract a neutral contract instead of hiding an "
        "import cycle"
    ]

    certification_errors = checker(
        "from typing import TYPE_CHECKING\n\nif TYPE_CHECKING:\n    from x import Y\n",
        "packages/application/src/ditto_application/"
        "research_certification_contracts.py",
    )

    assert certification_errors == [
        "packages/application/src/ditto_application/"
        "research_certification_contracts.py: experiment source imports "
        "TYPE_CHECKING; extract a neutral contract instead of hiding an "
        "import cycle"
    ]


def test_task8_type_checking_gate_rejects_module_and_extension_alias_bypasses():
    checker = _MOD.check_experiment_source_no_type_checking  # type: ignore[attr-defined]
    rel_path = (
        "packages/application/src/ditto_application/research_certification_contracts.py"
    )
    expected = [
        f"{rel_path}: experiment source imports TYPE_CHECKING; extract a neutral "
        "contract instead of hiding an import cycle"
    ]

    for source in (
        "import typing\n\nif typing.TYPE_CHECKING:\n    from x import Y\n",
        (
            "import typing as type_api\n\n"
            "if type_api.TYPE_CHECKING:\n    from x import Y\n"
        ),
        (
            "from typing_extensions import TYPE_CHECKING as TC\n\n"
            "if TC:\n    from x import Y\n"
        ),
        (
            "import typing_extensions as type_ext\n\n"
            "if type_ext.TYPE_CHECKING:\n    from x import Y\n"
        ),
    ):
        assert checker(source, rel_path) == expected


def test_task8_type_checking_gate_covers_the_whole_experiment_application_surface():
    checker = _MOD.check_experiment_source_no_type_checking  # type: ignore[attr-defined]

    for rel_path in (
        "packages/application/src/ditto_application/commands/experiments.py",
        "packages/application/src/ditto_application/queries/experiments.py",
        (
            "packages/application/src/ditto_application/processes/experiments/"
            "nested/example.py"
        ),
    ):
        assert checker(
            "from typing import TYPE_CHECKING\n",
            rel_path,
        ) == [
            f"{rel_path}: experiment source imports TYPE_CHECKING; extract a neutral "
            "contract instead of hiding an import cycle"
        ]


def test_task8_type_checking_gate_rejects_arbitrarily_deep_module_aliases():
    checker = _MOD.check_experiment_source_no_type_checking  # type: ignore[attr-defined]
    rel_path = "packages/application/src/ditto_application/commands/experiments.py"

    for module_name in ("typing", "typing_extensions"):
        errors = checker(
            f"import {module_name} as type_api\n"
            "type_guard = type_api\n"
            "next_guard = type_guard\n"
            "final_guard = next_guard\n\n"
            "if final_guard.TYPE_CHECKING:\n"
            "    from x import Y\n",
            rel_path,
        )

        assert errors == [
            f"{rel_path}: experiment source imports TYPE_CHECKING; extract a neutral "
            "contract instead of hiding an import cycle"
        ]


def test_task8_type_checking_gate_allows_ordinary_typing_module_use():
    checker = _MOD.check_experiment_source_no_type_checking  # type: ignore[attr-defined]

    errors = checker(
        "import typing as type_api\n\nvalue = type_api.cast(str, 'ok')\n",
        "packages/application/src/ditto_application/"
        "research_certification_contracts.py",
    )

    assert errors == []


def test_task8_type_checking_gate_allows_propagated_typing_cast_and_plain_text():
    checker = _MOD.check_experiment_source_no_type_checking  # type: ignore[attr-defined]
    rel_path = "packages/application/src/ditto_application/queries/experiments.py"

    errors = checker(
        "import typing as type_api\n"
        "type_guard = type_api\n"
        "next_guard = type_guard\n"
        "value = next_guard.cast(str, 'ok')\n"
        "message = 'typing.TYPE_CHECKING'\n"
        "# if next_guard.TYPE_CHECKING: ignored\n",
        rel_path,
    )

    assert errors == []


def test_task8_process_provider_forbids_behavior_adapters():
    assert hasattr(_MOD, "check_process_provider_wiring_only")
    checker = _MOD.check_process_provider_wiring_only  # type: ignore[attr-defined]

    errors = checker(
        "class DataReadinessCertificationProbe:\n    def assess(self): ...\n",
        "packages/application/src/ditto_application/providers_process.py",
    )

    assert errors == [
        "packages/application/src/ditto_application/providers_process.py: "
        "application process provider declares behavior class "
        "'DataReadinessCertificationProbe'; move behavior to its owning "
        "query, builder, or process adapter module"
    ]


def test_apps_capability_roots_include_all_domain_packages():
    assert {"ditto_portfolio", "ditto_risk"} <= APPS_CAPABILITY_IMPORT_ROOTS


def test_semantic_forbidden_terms_include_derived_feature_ownership():
    assert {
        "features/",
        "factors/",
        "publication_safety",
        "publication_shadow",
        "ditto_data.storage.runtime.publication_safety",
        "ditto_data.storage.runtime.publication_shadow_sqlite",
    } <= DATA_FORBIDDEN_SEMANTIC_TERMS
    assert {
        "instrument_id",
        "trade_date",
        "factor_",
        "portfolio_",
        "risk.",
        "dq_",
        "golden_dataset",
        "ticker",
    } <= PLATFORM_FORBIDDEN_DOMAIN_TERMS


def test_data_semantic_scanner_reports_publication_safety_ownership():
    errors = check_data_no_derived_feature_ownership(
        'PUBLICATION_TABLE = "publication_safety"',
        "packages/data/src/ditto_data/storage/publication.py",
    )

    assert errors == [
        "packages/data/src/ditto_data/storage/publication.py: "
        "data owns derived feature semantic term 'publication_safety'; "
        "move ownership to ditto_features/application boundary"
    ]


def test_platform_semantic_scanner_reports_instrument_id_ownership():
    errors = check_platform_no_domain_semantics(
        'COLUMN = "instrument_id"',
        "packages/platform/src/ditto_platform/db/schema.py",
    )

    assert errors == [
        "packages/platform/src/ditto_platform/db/schema.py: "
        "platform owns domain semantic term 'instrument_id'; "
        "keep platform as technical infrastructure"
    ]


def test_semantic_scanners_ignore_non_data_and_non_platform_sources():
    source = '"publication_safety", "instrument_id"'
    rel_path = "packages/apps/src/ditto_apps/routes/example.py"

    assert check_data_no_derived_feature_ownership(source, rel_path) == []
    assert check_platform_no_domain_semantics(source, rel_path) == []


def test_semantic_scan_target_uses_repo_relative_skip_parts():
    assert _is_semantic_scan_target(
        "packages/data/src/ditto_data/storage/publication.py"
    )
    assert not _is_semantic_scan_target("docs/architecture/publication.py")
    assert not _is_semantic_scan_target(
        "packages/data/src/ditto_data/migrations/001_publication.py"
    )
    assert not _is_semantic_scan_target(
        "packages/platform/src/ditto_platform/archive/schema.py"
    )


def test_production_analysis_wiring_allowances_are_owned_and_reasoned():
    allowances = _MOD.PRODUCTION_ANALYSIS_WIRING_ALLOWANCES  # type: ignore[attr-defined]

    assert allowances
    assert all(allowance.owner for allowance in allowances)
    assert all(allowance.reason for allowance in allowances)
    assert {
        "packages/application/src/ditto_application/providers.py",
        "packages/application/src/ditto_application/providers_market.py",
        "packages/application/src/ditto_application/providers_portfolio.py",
        "packages/application/src/ditto_application/providers_process.py",
        "packages/application/src/ditto_application/providers_strategy.py",
        (
            "packages/application/src/ditto_application/processes/experiments/"
            "_executor_probe.py"
        ),
        (
            "packages/application/src/ditto_application/processes/experiments/"
            "_launch_material.py"
        ),
        (
            "packages/application/src/ditto_application/processes/experiments/"
            "_launch_saga.py"
        ),
        (
            "packages/application/src/ditto_application/processes/experiments/"
            "_launch_reconstruction.py"
        ),
        (
            "packages/application/src/ditto_application/processes/experiments/"
            "_preflight_codec.py"
        ),
        (
            "packages/application/src/ditto_application/processes/experiments/"
            "_comparison_evidence.py"
        ),
        (
            "packages/application/src/ditto_application/processes/experiments/"
            "_factor_diagnostics_evidence.py"
        ),
        (
            "packages/application/src/ditto_application/processes/experiments/"
            "_oos_fold_registration.py"
        ),
        (
            "packages/application/src/ditto_application/processes/experiments/"
            "_persisted_execution_evidence.py"
        ),
        (
            "packages/application/src/ditto_application/processes/experiments/"
            "_report_evidence.py"
        ),
        (
            "packages/application/src/ditto_application/processes/experiments/"
            "_walk_forward_evidence.py"
        ),
        (
            "packages/application/src/ditto_application/processes/experiments/"
            "comparison.py"
        ),
        (
            "packages/application/src/ditto_application/processes/experiments/"
            "coordinator.py"
        ),
        (
            "packages/application/src/ditto_application/processes/experiments/"
            "_control_runtime.py"
        ),
        (
            "packages/application/src/ditto_application/processes/experiments/"
            "execution_bundle.py"
        ),
        (
            "packages/application/src/ditto_application/processes/experiments/"
            "_execution_resolution_evidence.py"
        ),
        (
            "packages/application/src/ditto_application/processes/experiments/"
            "lease_authority.py"
        ),
        (
            "packages/application/src/ditto_application/processes/experiments/"
            "planning.py"
        ),
        (
            "packages/application/src/ditto_application/processes/experiments/"
            "planning_process.py"
        ),
        (
            "packages/application/src/ditto_application/processes/experiments/"
            "planning_contracts.py"
        ),
        (
            "packages/application/src/ditto_application/processes/experiments/"
            "scheduler_store.py"
        ),
        (
            "packages/application/src/ditto_application/processes/experiments/"
            "trial_evidence_bridge.py"
        ),
        (
            "packages/application/src/ditto_application/processes/experiments/"
            "walk_forward.py"
        ),
        ("packages/application/src/ditto_application/processes/experiments/worker.py"),
        ("packages/application/src/ditto_application/research_validation_windows.py"),
        "packages/application/src/ditto_application/queries/experiments.py",
        "packages/application/src/ditto_application/queries/research.py",
        (
            "packages/application/src/ditto_application/queries/"
            "research_certification.py"
        ),
        "packages/application/src/ditto_application/queries/research_helpers.py",
        (
            "packages/application/src/ditto_application/processes/execution/"
            "_research_replay_artifacts.py"
        ),
        "packages/application/src/ditto_application/processes/experiments/evidence.py",
        "packages/application/src/ditto_application/processes/strategy/promotion.py",
    } == {allowance.path for allowance in allowances}
    assert not any(hasattr(allowance, "match") for allowance in allowances)


def test_application_research_query_is_allowed_to_wire_analysis():
    errors = check_production_no_analysis(
        "from ditto_analysis.research.catalog_service import ResearchCatalogService",
        "packages/application/src/ditto_application/queries/research.py",
    )

    assert errors == []


def test_launch_reconstruction_is_exactly_allowed_to_wire_analysis_contracts():
    rel_path = (
        "packages/application/src/ditto_application/processes/experiments/"
        "_launch_reconstruction.py"
    )
    near_miss = rel_path.replace(
        "_launch_reconstruction.py",
        "_launch_reconstruction_extra.py",
    )

    assert (
        check_production_no_analysis(
            "from ditto_analysis.experiments import FoldPersistenceSpec",
            rel_path,
        )
        == []
    )
    assert check_production_no_analysis(
        "from ditto_analysis.experiments import FoldPersistenceSpec",
        near_miss,
    ) == [f"{near_miss}: production imports ditto_analysis (check import-linter)"]


@pytest.mark.parametrize(
    "filename",
    [
        "coordinator.py",
        "execution_bundle.py",
        "_execution_resolution_evidence.py",
        "lease_authority.py",
        "scheduler_store.py",
        "worker.py",
    ],
)
def test_experiment_runtime_wiring_allowances_are_exact_paths(filename: str) -> None:
    rel_path = (
        f"packages/application/src/ditto_application/processes/experiments/{filename}"
    )
    near_miss = rel_path.removesuffix(".py") + "_extra.py"
    source = "from ditto_analysis.experiments import ExperimentId"

    assert check_production_no_analysis(source, rel_path) == []
    assert check_production_no_analysis(source, near_miss) == [
        f"{near_miss}: production imports ditto_analysis (check import-linter)"
    ]


def test_application_provider_modules_are_allowed_to_wire_analysis():
    source = (
        "from ditto_analysis.research.catalog_service import ResearchCatalogService"
    )

    for rel_path in (
        "packages/application/src/ditto_application/providers.py",
        "packages/application/src/ditto_application/providers_market.py",
        "packages/application/src/ditto_application/providers_portfolio.py",
        "packages/application/src/ditto_application/providers_strategy.py",
    ):
        assert check_production_no_analysis(source, rel_path) == []


def test_application_provider_near_miss_cannot_import_analysis():
    errors = check_production_no_analysis(
        "from ditto_analysis.research.catalog_service import ResearchCatalogService",
        "packages/application/src/ditto_application/providers_extra.py",
    )

    assert errors == [
        "packages/application/src/ditto_application/providers_extra.py: "
        "production imports ditto_analysis (check import-linter)"
    ]


def test_application_provider_directory_near_miss_cannot_import_analysis():
    errors = check_production_no_analysis(
        "from ditto_analysis.research.catalog_service import ResearchCatalogService",
        "packages/application/src/ditto_application/providers/extra.py",
    )

    assert errors == [
        "packages/application/src/ditto_application/providers/extra.py: "
        "production imports ditto_analysis (check import-linter)"
    ]


def test_ordinary_application_query_cannot_import_analysis():
    errors = check_production_no_analysis(
        "from ditto_analysis.research.catalog_service import ResearchCatalogService",
        "packages/application/src/ditto_application/queries/market.py",
    )

    assert errors == [
        "packages/application/src/ditto_application/queries/market.py: "
        "production imports ditto_analysis (check import-linter)"
    ]


def test_research_query_near_miss_cannot_import_analysis():
    errors = check_production_no_analysis(
        "from ditto_analysis.research.catalog_service import ResearchCatalogService",
        "packages/application/src/ditto_application/queries/research_extra.py",
    )

    assert errors == [
        "packages/application/src/ditto_application/queries/research_extra.py: "
        "production imports ditto_analysis (check import-linter)"
    ]


def test_data_di_path_cannot_import_analysis():
    errors = check_production_no_analysis(
        "from ditto_analysis.research.catalog_service import ResearchCatalogService",
        "packages/data/src/ditto_data/di/example.py",
    )

    assert errors == [
        "packages/data/src/ditto_data/di/example.py: "
        "production imports ditto_analysis (check import-linter)"
    ]
