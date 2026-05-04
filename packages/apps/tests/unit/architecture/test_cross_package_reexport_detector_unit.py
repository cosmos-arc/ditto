"""Cross-package re-export detector behavior."""

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
CrossPackageExport = _MOD.CrossPackageExport  # type: ignore[attr-defined]
find_cross_package_exports = _MOD.find_cross_package_exports  # type: ignore[attr-defined]


def test_detector_finds_imported_symbol_exported_in_all(tmp_path: Path) -> None:
    src = tmp_path / "packages" / "data" / "src" / "ditto_data" / "shim.py"
    src.parent.mkdir(parents=True)
    src.write_text(
        "from ditto_platform.foundation.storage.sqlite_client import SQLiteClient\n"
        "__all__ = ['SQLiteClient']\n",
        encoding="utf-8",
    )

    assert find_cross_package_exports(tmp_path) == [
        CrossPackageExport(
            path=src.relative_to(tmp_path).as_posix(),
            exported_name="SQLiteClient",
            imported_from="ditto_platform.foundation.storage.sqlite_client",
            owner_package="data",
            source_package="platform",
        )
    ]


def test_detector_ignores_private_annotation_imports(tmp_path: Path) -> None:
    src = tmp_path / "packages" / "risk" / "src" / "ditto_risk" / "model.py"
    src.parent.mkdir(parents=True)
    src.write_text(
        "from ditto_kernel.strategy import RiskScope\n"
        "__all__ = ['RiskResult']\n"
        "class RiskResult: ...\n",
        encoding="utf-8",
    )

    assert find_cross_package_exports(tmp_path) == []


def test_detector_ignores_function_local_imports(tmp_path: Path) -> None:
    src = tmp_path / "packages" / "execution" / "src" / "ditto_execution" / "model.py"
    src.parent.mkdir(parents=True)
    src.write_text(
        "__all__ = ['Foo']\n"
        "def load_foo():\n"
        "    from ditto_kernel.trading import Foo\n"
        "    return Foo\n",
        encoding="utf-8",
    )

    assert find_cross_package_exports(tmp_path) == []
