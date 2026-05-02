from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

_SCRIPT = (
    Path(__file__).resolve().parents[5]
    / "scripts"
    / "architecture"
    / "check_architecture_smells.py"
)


def _load_stale_references() -> tuple[str, ...]:
    spec = spec_from_file_location("check_architecture_smells", _SCRIPT)
    if spec is None or spec.loader is None:
        msg = f"Cannot load {_SCRIPT}"
        raise ImportError(msg)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.STALE_AI_RULE_REFERENCES  # type: ignore[no-any-return]


STALE_REFERENCES = _load_stale_references()


def test_stale_ai_rule_reference_list_covers_legacy_packages() -> None:
    assert "ditto_engine" in STALE_REFERENCES
    assert "ditto_analytics" in STALE_REFERENCES
    assert "ditto_interfaces" in STALE_REFERENCES
    assert "interfaces/src" in STALE_REFERENCES
    assert "packages/engine" in STALE_REFERENCES
    assert "packages/infra" in STALE_REFERENCES
