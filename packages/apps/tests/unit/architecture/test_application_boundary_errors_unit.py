"""Application boundary raises typed AppError subclasses."""

from __future__ import annotations

import ast
from collections.abc import Mapping
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[5]
APPLICATION_ROOT = REPO_ROOT / "packages" / "application" / "src" / "ditto_application"

SCANNED_DIRS = (
    APPLICATION_ROOT / "commands",
    APPLICATION_ROOT / "queries",
    APPLICATION_ROOT / "builders",
    APPLICATION_ROOT / "processes",
)
LOCAL_PRECONDITION_HELPERS: frozenset[Path] = frozenset()
FORBIDDEN_BOUNDARY_ERRORS = {"KeyError", "RuntimeError", "TypeError", "ValueError"}
MAPPING_SUBSCRIPT_NAME_MARKERS = (
    "payload",
    "_map",
    "_dict",
    "_to_",
)
EXTERNAL_HYDRATION_SOURCE_NAMES = {"payload", "raw", "spec_json"}
BOUNDARY_CONVERSION_NAMES = {"float", "int"}
HYDRATION_ENUM_NAMES = {"DerivedRole", "MaterializationProfile"}
DELEGATED_BOUNDARY_METHOD_NAMES = {"check", "ingest_date"}


def _scanned_files() -> list[Path]:
    files: set[Path] = set()
    for directory in SCANNED_DIRS:
        files.update(directory.rglob("*.py"))
    return sorted(files)


def _raised_error_name(node: ast.Raise) -> str | None:
    exc = node.exc
    if isinstance(exc, ast.Call):
        exc = exc.func
    if isinstance(exc, ast.Name):
        return exc.id
    if isinstance(exc, ast.Attribute):
        return exc.attr
    return None


def _forbidden_boundary_raises(path: Path) -> list[str]:
    if path in LOCAL_PRECONDITION_HELPERS:
        return []

    tree = ast.parse(path.read_text(encoding="utf-8"), filename=path.as_posix())
    offenders: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Raise):
            continue
        error_name = _raised_error_name(node)
        if error_name in FORBIDDEN_BOUNDARY_ERRORS:
            rel_path = path.relative_to(REPO_ROOT).as_posix()
            offenders.append(f"{rel_path}:{node.lineno} raises {error_name}")
    return offenders


def _is_public_boundary_function(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    return not node.name.startswith("_")


def _is_mapping_like_subscript(node: ast.Subscript) -> bool:
    value = node.value
    if isinstance(value, ast.Name):
        name = value.id
    elif isinstance(value, ast.Attribute):
        name = value.attr
    else:
        return False

    lower_name = name.lower()
    return any(marker in lower_name for marker in MAPPING_SUBSCRIPT_NAME_MARKERS)


def _name_of(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _parent_map(tree: ast.AST) -> dict[ast.AST, ast.AST]:
    return {
        child: parent
        for parent in ast.walk(tree)
        for child in ast.iter_child_nodes(parent)
    }


def _is_inside_value_error_handler(
    node: ast.AST, parents: Mapping[ast.AST, ast.AST]
) -> bool:
    return _is_inside_error_handler(node, parents, {"ValueError"})


def _handler_catches(handler_type: ast.expr | None, error_names: set[str]) -> bool:
    if handler_type is None:
        return True
    if _name_of(handler_type) in error_names:
        return True
    if isinstance(handler_type, ast.Tuple):
        return any(_name_of(elt) in error_names for elt in handler_type.elts)
    return False


def _is_inside_error_handler(
    node: ast.AST,
    parents: Mapping[ast.AST, ast.AST],
    error_names: set[str],
) -> bool:
    current: ast.AST | None = node
    while current is not None:
        parent = parents.get(current)
        if isinstance(parent, ast.Try) and current in parent.body:
            for handler in parent.handlers:
                if _handler_catches(handler.type, error_names):
                    return True
        current = parent
    return False


def _call_name(node: ast.Call) -> str | None:
    return _name_of(node.func)


def _is_external_hydration_source(node: ast.expr) -> bool:
    name = _name_of(node)
    return name in EXTERNAL_HYDRATION_SOURCE_NAMES


def _is_dict_cast_from_external_hydration_source(node: ast.expr) -> bool:
    if not isinstance(node, ast.Call):
        return False
    if not isinstance(node.func, ast.Name) or node.func.id != "cast":
        return False
    if len(node.args) < 2:
        return False
    return _is_external_hydration_source(node.args[1])


def _external_hydration_mapping_names(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> set[str]:
    names: set[str] = set()
    for child in ast.walk(node):
        if not isinstance(child, ast.Assign):
            continue
        if not _is_dict_cast_from_external_hydration_source(child.value):
            continue
        for target in child.targets:
            if isinstance(target, ast.Name):
                names.add(target.id)
    return names


def _is_local_external_mapping_subscript(
    node: ast.Subscript, mapping_names: set[str]
) -> bool:
    return isinstance(node.value, ast.Name) and node.value.id in mapping_names


def _is_validated_local_mapping_subscript(
    node: ast.Subscript,
    parents: Mapping[ast.AST, ast.AST],
) -> bool:
    if not isinstance(node.value, ast.Name):
        return False
    mapping_name = node.value.id

    current: ast.AST | None = node
    while current is not None:
        parent = parents.get(current)
        if isinstance(parent, (ast.ListComp, ast.SetComp, ast.GeneratorExp)):
            for generator in parent.generators:
                if _comprehension_guards_subscript(
                    generator.ifs,
                    mapping_name,
                    node.slice,
                ):
                    return True
        current = parent
    return False


def _comprehension_guards_subscript(
    guards: list[ast.expr],
    mapping_name: str,
    subscript_key: ast.expr,
) -> bool:
    for guard in guards:
        if not isinstance(guard, ast.Compare):
            continue
        if len(guard.ops) != 1 or not isinstance(guard.ops[0], ast.In):
            continue
        if len(guard.comparators) != 1:
            continue
        comparator = guard.comparators[0]
        if not isinstance(comparator, ast.Name) or comparator.id != mapping_name:
            continue
        if ast.dump(guard.left) == ast.dump(subscript_key):
            return True
    return False


def _forbidden_implicit_key_errors(path: Path) -> list[str]:
    if path in LOCAL_PRECONDITION_HELPERS:
        return []

    tree = ast.parse(path.read_text(encoding="utf-8"), filename=path.as_posix())
    parents = _parent_map(tree)
    offenders: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        local_mapping_names = _external_hydration_mapping_names(node)
        for child in ast.walk(node):
            if not isinstance(child, ast.Subscript):
                continue
            if not isinstance(child.ctx, ast.Load):
                continue
            if not (
                (
                    _is_public_boundary_function(node)
                    and _is_mapping_like_subscript(child)
                )
                or _is_local_external_mapping_subscript(child, local_mapping_names)
            ):
                continue
            if _is_validated_local_mapping_subscript(child, parents):
                continue
            rel_path = path.relative_to(REPO_ROOT).as_posix()
            offenders.append(f"{rel_path}:{child.lineno} uses mapping subscript")
    return offenders


def _forbidden_unguarded_conversions(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=path.as_posix())
    parents = _parent_map(tree)
    offenders: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        call_name = _call_name(node)
        guards_boundary_conversion = (
            path.parent == APPLICATION_ROOT / "commands"
            and call_name in BOUNDARY_CONVERSION_NAMES
        )
        guards_hydration_enum = (
            path == APPLICATION_ROOT / "processes" / "materialization" / "types.py"
            and call_name in HYDRATION_ENUM_NAMES
        )
        if not (guards_boundary_conversion or guards_hydration_enum):
            continue
        if _is_inside_value_error_handler(node, parents):
            continue
        rel_path = path.relative_to(REPO_ROOT).as_posix()
        offenders.append(f"{rel_path}:{node.lineno} calls {call_name} without guard")
    return offenders


def _is_self_private_attribute_call(node: ast.Call) -> bool:
    if not isinstance(node.func, ast.Attribute):
        return False
    value = node.func.value
    return (
        isinstance(value, ast.Attribute)
        and isinstance(value.value, ast.Name)
        and value.value.id == "self"
        and value.attr.startswith("_")
    )


def _forbidden_unguarded_delegated_boundary_calls(path: Path) -> list[str]:
    if path.parent != APPLICATION_ROOT / "commands":
        return []

    tree = ast.parse(path.read_text(encoding="utf-8"), filename=path.as_posix())
    parents = _parent_map(tree)
    offenders: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not _is_self_private_attribute_call(node):
            continue
        call_name = _call_name(node)
        if call_name not in DELEGATED_BOUNDARY_METHOD_NAMES:
            continue
        if _is_inside_error_handler(node, parents, {"AppProcessError", "ValueError"}):
            continue
        rel_path = path.relative_to(REPO_ROOT).as_posix()
        offenders.append(
            f"{rel_path}:{node.lineno} delegates {call_name} without app error guard"
        )
    return offenders


def test_application_boundary_raises_use_typed_app_errors() -> None:
    offenders = [
        offender
        for path in _scanned_files()
        for offender in _forbidden_boundary_raises(path)
    ]

    assert offenders == []


def test_application_boundary_conversions_use_typed_app_errors() -> None:
    offenders = [
        offender
        for path in _scanned_files()
        for offender in _forbidden_unguarded_conversions(path)
    ]

    assert offenders == []


def test_application_boundary_delegates_use_typed_app_errors() -> None:
    offenders = [
        offender
        for path in _scanned_files()
        for offender in _forbidden_unguarded_delegated_boundary_calls(path)
    ]

    assert offenders == []


def test_application_boundary_mapping_lookups_use_typed_app_errors() -> None:
    offenders = [
        offender
        for path in _scanned_files()
        for offender in _forbidden_implicit_key_errors(path)
    ]

    assert offenders == []
