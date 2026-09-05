"""Cross-package re-export detector behavior."""

from importlib import import_module
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
        "from ditto_platform.foundation import SQLiteClient\n"
        "__all__ = ['SQLiteClient']\n",
        encoding="utf-8",
    )

    assert find_cross_package_exports(tmp_path) == [
        CrossPackageExport(
            path=src.relative_to(tmp_path).as_posix(),
            exported_name="SQLiteClient",
            imported_from="ditto_platform.foundation",
            owner_package="data",
            source_package="platform",
        )
    ]


def test_detector_ignores_private_annotation_imports(tmp_path: Path) -> None:
    src = tmp_path / "packages" / "risk" / "src" / "ditto_risk" / "model.py"
    src.parent.mkdir(parents=True)
    src.write_text(
        "from ditto_kernel.strategy import RiskScope as _RiskScope\n"
        "__all__ = ['RiskResult']\n"
        "class RiskResult:\n"
        "    scope: _RiskScope\n",
        encoding="utf-8",
    )

    assert find_cross_package_exports(tmp_path) == []


def test_detector_finds_public_cross_import_in_strict_leaf_scope(
    tmp_path: Path,
) -> None:
    src = (
        tmp_path
        / "packages"
        / "execution"
        / "src"
        / "ditto_execution"
        / "reality"
        / "fee.py"
    )
    src.parent.mkdir(parents=True)
    src.write_text(
        "from ditto_kernel.trading import FeeSchedule\n"
        "__all__ = ['LocalFeeModel']\n"
        "class LocalFeeModel:\n"
        "    schedule: FeeSchedule\n",
        encoding="utf-8",
    )

    assert find_cross_package_exports(tmp_path) == [
        CrossPackageExport(
            path=src.relative_to(tmp_path).as_posix(),
            exported_name="FeeSchedule",
            imported_from="ditto_kernel.trading",
            owner_package="execution",
            source_package="kernel",
        )
    ]


def test_detector_ignores_private_cross_import_in_strict_leaf_scope(
    tmp_path: Path,
) -> None:
    src = (
        tmp_path
        / "packages"
        / "execution"
        / "src"
        / "ditto_execution"
        / "reality"
        / "fee.py"
    )
    src.parent.mkdir(parents=True)
    src.write_text(
        "from ditto_kernel.trading import FeeSchedule as _FeeSchedule\n"
        "__all__ = ['LocalFeeModel']\n"
        "class LocalFeeModel:\n"
        "    schedule: _FeeSchedule\n",
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


def test_removed_runtime_reexport_attrs_are_absent() -> None:
    old_reexports = {
        "ditto_features.models.derived": [
            "JsonDict",
            "JsonValue",
            "require_bool",
            "require_int",
            "require_payload",
            "require_str",
        ],
        "ditto_features.publication_safety": [
            "DerivedRole",
            "MaterializationProfile",
        ],
        "ditto_execution.audit.models": ["RiskScope"],
        "ditto_execution.reality.brokerage": ["FeeModel"],
        "ditto_execution.reality.fee": [
            "DEFAULT_COMMISSION_RATE",
            "DEFAULT_MIN_COMMISSION",
            "FeeSchedule",
            "Order",
            "OrderSide",
        ],
        "ditto_execution.reality.fill": [
            "FillEvent",
            "InstrumentDefinition",
            "MarketSnapshot",
            "Order",
            "OrderSide",
            "OrderType",
            "TradingRuleSet",
        ],
        "ditto_execution.reality.settlement": [
            "InstrumentId",
            "OrderSide",
            "Position",
            "TradingRuleSet",
        ],
        "ditto_execution.reality.slippage": [
            "InstrumentDefinition",
            "MarketSnapshot",
            "Order",
            "OrderSide",
        ],
        "ditto_portfolio.accounting": ["OrderSide", "OrderType"],
        "ditto_portfolio.accounting.order_book": ["OrderSide", "OrderType"],
        "ditto_risk.constraints.context": ["InstrumentId"],
        "ditto_risk.post_trade": ["RiskScope"],
        "ditto_risk.pre_trade": ["InstrumentId"],
    }

    leaked: dict[str, list[str]] = {}
    for module_name, names in old_reexports.items():
        try:
            module = import_module(module_name)
        except ModuleNotFoundError:
            continue
        module_leaks = [name for name in names if hasattr(module, name)]
        if module_leaks:
            leaked[module_name] = module_leaks

    assert leaked == {}
