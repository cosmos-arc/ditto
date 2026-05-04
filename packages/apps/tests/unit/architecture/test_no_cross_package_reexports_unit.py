"""No hidden cross-package re-export debt."""

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


def test_no_unapproved_cross_package_reexports() -> None:
    checker = _load_checker()
    check_cross_package_exports = checker.check_cross_package_exports  # type: ignore[attr-defined]

    errors: list[str] = check_cross_package_exports(Path.cwd())

    assert errors == [], "\n".join(errors)
