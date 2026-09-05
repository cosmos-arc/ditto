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
STALE_REFERENCES: tuple[str, ...] = _MODULE.STALE_AI_RULE_REFERENCES  # type: ignore[union-attr]
STALE_PKG_REFS: tuple[str, ...] = _MODULE.STALE_ACTIVE_PACKAGE_REFERENCES  # type: ignore[union-attr]
STALE_SOURCE_ARCHITECTURE_TERMS: tuple[str, ...] = (
    _MODULE.STALE_SOURCE_ARCHITECTURE_TERMS  # type: ignore[union-attr]
)
check_source_architecture_terms = (
    _MODULE.check_source_architecture_terms  # type: ignore[union-attr]
)


def test_stale_ai_rule_reference_list_covers_legacy_packages() -> None:
    assert "ditto_engine" in STALE_REFERENCES
    assert "ditto_analytics" in STALE_REFERENCES
    assert "ditto_interfaces" in STALE_REFERENCES
    assert "interfaces/src" in STALE_REFERENCES
    assert "packages/engine" in STALE_REFERENCES
    assert "packages/infra" in STALE_REFERENCES


def test_stale_active_package_references_covers_legacy_names() -> None:
    assert "ditto_app." in STALE_PKG_REFS
    assert "ditto_analytics" in STALE_PKG_REFS
    assert "ditto_engine" in STALE_PKG_REFS
    assert "ditto_interfaces" in STALE_PKG_REFS
    assert "ditto_infra" in STALE_PKG_REFS
    assert "packages/app/" in STALE_PKG_REFS
    assert "packages/analytics" in STALE_PKG_REFS
    assert "packages/engine" in STALE_PKG_REFS
    assert "packages/infra" in STALE_PKG_REFS
    assert "interfaces/" in STALE_PKG_REFS
    assert "interfaces/tests" in STALE_PKG_REFS
    assert "interfaces/src" in STALE_PKG_REFS
    assert "apps → analytics" in STALE_PKG_REFS
    assert "analytics →" in STALE_PKG_REFS
    assert "→ analytics" in STALE_PKG_REFS
    assert "Analytics" in STALE_PKG_REFS


def test_stale_source_architecture_terms_cover_legacy_names() -> None:
    assert STALE_SOURCE_ARCHITECTURE_TERMS == (
        "Interfaces 层",
        "interfaces/",
        "infra/",
        "analytics layer",
        "engine 层",
    )


def test_source_architecture_term_checker_scans_comments_and_docstrings() -> None:
    source = '''
"""Interfaces 层 docstring."""

OPERATION = "analytics layer"
engine_version = "engine 层"

# infra/
# execution engine is generic and should stay allowed.
def run() -> None:
    """engine 层 function docstring."""
'''
    rel_path = "apps/backend/src/ditto_apps/example.py"

    assert check_source_architecture_terms(source, rel_path) == [
        f"{rel_path}: contains stale source architecture term 'Interfaces 层'",
        f"{rel_path}: contains stale source architecture term 'infra/'",
        f"{rel_path}: contains stale source architecture term 'engine 层'",
    ]


def test_active_source_docstrings_use_current_architecture_terms() -> None:
    errors: list[str] = []
    for path in _MODULE.iter_source_files():  # type: ignore[attr-defined]
        source = path.read_text(encoding="utf-8")
        rel_path = str(path.relative_to(Path(__file__).resolve().parents[5]))
        errors.extend(check_source_architecture_terms(source, rel_path))

    assert errors == []


def test_importlinter_has_no_unmatched_bare_barrel_ignore() -> None:
    text = Path(".importlinter").read_text(encoding="utf-8")
    # The bare barrel ignore (no trailing .**) is stale —
    # no code imports ditto_data.models directly.
    assert "ditto_data.storage.** -> ditto_data.models\n" not in text


def test_importlinter_apps_service_isolation_fails_on_stale_ignores() -> None:
    text = Path(".importlinter").read_text(encoding="utf-8")

    assert "ditto_apps.jobs.context -> ditto_data.quality\n" not in text
    assert "ditto_apps.jobs.context -> ditto_data.quality.protocols\n" not in text
    assert "unmatched_ignore_imports_alerting = error" in text
