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


_mod = _load_checker()


def test_package_metadata_matches_internal_imports() -> None:
    result: list[str] = _mod.check_package_metadata(Path.cwd())  # type: ignore[attr-defined]
    assert result == [], "\n".join(result)
