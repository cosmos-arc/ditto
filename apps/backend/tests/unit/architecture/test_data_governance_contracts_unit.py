from __future__ import annotations

import ast
from pathlib import Path

CONTRACT_MODULES = (
    "packages/data/src/ditto_data/catalog/contracts.py",
    "packages/data/src/ditto_data/lineage/contracts.py",
)

PRODUCTION_CODE_DIRS = (
    Path("packages/application/src"),
    Path("packages/apps/src"),
)

FORBIDDEN_DATASET_ENUM_ROUTE_METADATA_FRAGMENTS = (
    ".get_asset_class(",
    "dataset_enum.asset_class",
    "ds.asset_class",
)

FORBIDDEN_IMPORT_PREFIXES = (
    "ditto_analysis",
    "ditto_application",
    "ditto_apps",
    "ditto_backtest",
    "ditto_data.config",
    "ditto_data.di",
    "ditto_data.ingestion",
    "ditto_data.models",
    "ditto_data.observability",
    "ditto_data.quality",
    "ditto_data.runtime",
    "ditto_data.services",
    "ditto_data.sources",
    "ditto_data.storage",
    "ditto_execution",
    "ditto_features",
    "ditto_platform",
    "ditto_portfolio",
    "ditto_risk",
    "ditto_strategy",
    "polars",
)

GOVERNANCE_CONTRACT_NAMES = {
    "DataAssetRef",
    "DataCatalogEntry",
    "DataCatalogReader",
    "DataCatalogWriter",
    "DataLineageReader",
    "DataLineageRecorder",
    "DataSchemaFingerprint",
    "LineageEvent",
    "LineageInputRef",
    "LineageOutputRef",
}

LOCAL_CONTRACT_EXPORTS = {
    "packages/data/src/ditto_data/catalog/__init__.py": {
        "DataAssetRef",
        "DataCatalogEntry",
        "DataCatalogReader",
        "DataCatalogWriter",
        "DataSchemaFingerprint",
        "DatasetMetadata",
        "InMemoryDataCatalog",
        "default_dataset_metadata",
    },
    "packages/data/src/ditto_data/lineage/__init__.py": {
        "DataLineageReader",
        "DataLineageRecorder",
        "InMemoryDataLineage",
        "LineageEvent",
        "LineageInputRef",
        "LineageOutputRef",
    },
}

LOCAL_CONTRACT_IMPORTS = {
    "packages/data/src/ditto_data/catalog/__init__.py": {
        "ditto_data.catalog.contracts",
        "ditto_data.catalog.metadata",
        "ditto_data.catalog.store",
    },
    "packages/data/src/ditto_data/lineage/__init__.py": {
        "ditto_data.lineage.contracts",
        "ditto_data.lineage.store",
    },
}


def _module_name_for_path(path: Path) -> str:
    parts = path.with_suffix("").parts
    package_index = parts.index("ditto_data")
    module_parts = parts[package_index:]
    if module_parts[-1] == "__init__":
        module_parts = module_parts[:-1]
    return ".".join(module_parts)


def _root_package_for_path(path: Path) -> str:
    return _module_name_for_path(path).split(".", maxsplit=1)[0]


def _resolve_import_from_module(path: Path, node: ast.ImportFrom) -> str | None:
    if node.level == 0:
        return node.module

    current_module = _module_name_for_path(path)
    package_parts = current_module.split(".")
    if path.name != "__init__.py":
        package_parts = package_parts[:-1]

    base_parts = package_parts[: len(package_parts) - node.level + 1]
    if node.module is not None:
        base_parts.extend(node.module.split("."))
    return ".".join(base_parts)


def _should_record_import_from_alias_modules(
    path: Path,
    node: ast.ImportFrom,
    module: str,
) -> bool:
    return node.module is None or module == _root_package_for_path(path)


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = _resolve_import_from_module(path, node)
            if module is not None:
                modules.add(module)
                if _should_record_import_from_alias_modules(path, node, module):
                    modules.update(
                        f"{module}.{alias.name}"
                        for alias in node.names
                        if alias.name != "*"
                    )
    return modules


def _exported_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    exported_names: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if (
                    isinstance(target, ast.Name)
                    and target.id == "__all__"
                    and isinstance(node.value, ast.List)
                ):
                    exported_names.update(
                        item.value
                        for item in node.value.elts
                        if isinstance(item, ast.Constant)
                        and isinstance(item.value, str)
                    )
        elif isinstance(node, ast.ImportFrom):
            exported_names.update(alias.asname or alias.name for alias in node.names)

    return exported_names


def _python_files(paths: tuple[Path, ...]) -> tuple[Path, ...]:
    return tuple(
        sorted(
            file_path
            for root in paths
            for file_path in root.rglob("*.py")
            if "__pycache__" not in file_path.parts
        )
    )


def test_relative_imports_are_normalized_before_forbidden_scan(
    tmp_path: Path,
) -> None:
    contract_path = tmp_path / "packages/data/src/ditto_data/catalog/contracts.py"
    contract_path.parent.mkdir(parents=True)
    contract_path.write_text(
        "from __future__ import annotations\n"
        "from ..storage import SQLiteCatalogStore\n",
        encoding="utf-8",
    )

    assert "ditto_data.storage" in _imported_modules(contract_path)


def test_import_from_package_records_imported_alias_module(tmp_path: Path) -> None:
    contract_path = tmp_path / "packages/data/src/ditto_data/catalog/contracts.py"
    contract_path.parent.mkdir(parents=True)
    contract_path.write_text(
        "from __future__ import annotations\nfrom ditto_data import storage\n",
        encoding="utf-8",
    )

    assert "ditto_data.storage" in _imported_modules(contract_path)


def test_relative_import_from_package_records_imported_alias_module(
    tmp_path: Path,
) -> None:
    contract_path = tmp_path / "packages/data/src/ditto_data/catalog/contracts.py"
    contract_path.parent.mkdir(parents=True)
    contract_path.write_text(
        "from __future__ import annotations\nfrom .. import storage\n",
        encoding="utf-8",
    )

    assert "ditto_data.storage" in _imported_modules(contract_path)


def test_data_governance_contracts_do_not_import_forbidden_layers() -> None:
    offenders: dict[str, list[str]] = {}
    for module_path in CONTRACT_MODULES:
        path = Path(module_path)
        forbidden = sorted(
            module
            for module in _imported_modules(path)
            if any(
                module == prefix or module.startswith(f"{prefix}.")
                for prefix in FORBIDDEN_IMPORT_PREFIXES
            )
        )
        if forbidden:
            offenders[module_path] = forbidden

    assert offenders == {}


def test_data_root_does_not_reexport_governance_contracts() -> None:
    root = Path("packages/data/src/ditto_data/__init__.py")

    assert _exported_names(root).isdisjoint(GOVERNANCE_CONTRACT_NAMES)


def test_application_and_apps_do_not_read_route_metadata_from_dataset_enum() -> None:
    offenders: dict[str, list[str]] = {}
    for file_path in _python_files(PRODUCTION_CODE_DIRS):
        text = file_path.read_text(encoding="utf-8")
        fragments = [
            fragment
            for fragment in FORBIDDEN_DATASET_ENUM_ROUTE_METADATA_FRAGMENTS
            if fragment in text
        ]
        if fragments:
            offenders[str(file_path)] = fragments

    assert offenders == {}


def test_data_governance_subpackages_reexport_only_local_contracts() -> None:
    offenders: dict[str, dict[str, set[str]]] = {}

    for module_path, allowed_exports in LOCAL_CONTRACT_EXPORTS.items():
        path = Path(module_path)
        actual_exports = _exported_names(path)
        missing_exports = allowed_exports - actual_exports
        unexpected_exports = actual_exports - allowed_exports
        unexpected_imports = (
            _imported_modules(path) - LOCAL_CONTRACT_IMPORTS[module_path]
        )
        if missing_exports or unexpected_exports or unexpected_imports:
            offenders[module_path] = {
                "missing_exports": missing_exports,
                "exports": unexpected_exports,
                "imports": unexpected_imports,
            }

    assert offenders == {}
