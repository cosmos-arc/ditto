"""Unit tests for src ``__init__.py`` ``__all__`` coverage architecture check."""

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


def _write_init(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def test_flags_init_without_dunder_all(tmp_path: Path) -> None:
    check = _MODULE.check_missing_dunder_all  # type: ignore[attr-defined]
    _write_init(
        tmp_path / "packages" / "demo" / "src" / "demo_pkg" / "__init__.py",
        '"""Demo package without explicit surface."""\n',
    )

    errors = check(tmp_path)

    assert any("missing __all__ declaration" in error for error in errors)


def test_accepts_init_with_assign_dunder_all(tmp_path: Path) -> None:
    check = _MODULE.check_missing_dunder_all  # type: ignore[attr-defined]
    _write_init(
        tmp_path / "packages" / "demo" / "src" / "demo_pkg" / "__init__.py",
        '"""Demo."""\n\n__all__ = ["Thing"]\n',
    )

    assert check(tmp_path) == []


def test_accepts_init_with_annotated_dunder_all(tmp_path: Path) -> None:
    check = _MODULE.check_missing_dunder_all  # type: ignore[attr-defined]
    _write_init(
        tmp_path / "packages" / "demo" / "src" / "demo_pkg" / "__init__.py",
        '"""Demo."""\n\n__all__: list[str] = []\n',
    )

    assert check(tmp_path) == []


def test_real_repo_has_full_dunder_all_coverage() -> None:
    """Baseline guard: every src ``__init__.py`` declares ``__all__``."""
    check = _MODULE.check_missing_dunder_all  # type: ignore[attr-defined]

    assert check() == []
