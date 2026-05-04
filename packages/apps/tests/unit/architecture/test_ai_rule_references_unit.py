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


def test_importlinter_has_no_unmatched_bare_barrel_ignore() -> None:
    text = Path(".importlinter").read_text(encoding="utf-8")
    # The bare barrel ignore (no trailing .**) is stale —
    # no code imports ditto_data.models directly.
    assert "ditto_data.storage.** -> ditto_data.models\n" not in text
