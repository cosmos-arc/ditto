from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

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
_is_semantic_scan_target = _MOD._is_semantic_scan_target  # type: ignore[attr-defined]


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
