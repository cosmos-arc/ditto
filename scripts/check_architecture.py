#!/usr/bin/env python3
"""Architecture boundary checker for Ditto."""

from __future__ import annotations

import ast
import re
import sys
from dataclasses import dataclass
from pathlib import Path

PROJECT_IMPORT_ROOTS = ("ditto_foundation", "ditto_datahub", "ditto_core", "ditto_port")
REGISTRY_MIN_PARTS = 6
MIN_ATTR_CHAIN_LENGTH = 2
LEGACY_DATAHUB_ALIAS_ATTRS = frozenset(
    {"calendar", "universe", "index", "securities", "ingestion_log"}
)
HUB_REFERENCE_NAMES = frozenset({"hub", "_hub", "datahub"})
LEGACY_FIELD_PATTERNS: tuple[tuple[re.Pattern[str], str, str], ...] = (
    (
        re.compile(r"\bsid\b"),
        "ARCH500",
        "禁止使用 legacy 字段 sid, 请统一为 instrument_id",
    ),
    (
        re.compile(r"\bsrc_code\b"),
        "ARCH510",
        "禁止使用 legacy 字段 src_code, 请统一为 source_ticker",
    ),
)


@dataclass(frozen=True)
class ImportRef:
    """One import reference extracted from a python file."""

    module: str
    symbol: str
    line: int


@dataclass(frozen=True)
class Violation:
    """Architecture violation."""

    code: str
    file: Path
    line: int
    message: str


def _extract_imports(tree: ast.AST) -> list[ImportRef]:
    refs: list[ImportRef] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                refs.append(
                    ImportRef(
                        module=alias.name,
                        symbol=alias.asname or alias.name.split(".")[-1],
                        line=node.lineno,
                    )
                )
        elif isinstance(node, ast.ImportFrom):
            if not node.module:
                continue
            for alias in node.names:
                if alias.name == "*":
                    full_module = node.module
                else:
                    full_module = f"{node.module}.{alias.name}"
                refs.append(
                    ImportRef(
                        module=full_module,
                        symbol=alias.asname or alias.name,
                        line=node.lineno,
                    )
                )
    return refs


def _is_project_import(module: str) -> bool:
    return module.startswith(PROJECT_IMPORT_ROOTS)


def _is_foundation_file(path: Path) -> bool:
    return path.parts[:4] == ("packages", "foundation", "src", "ditto_foundation")


def _is_datahub_file(path: Path) -> bool:
    return path.parts[:4] == ("packages", "datahub", "src", "ditto_datahub")


def _is_core_file(path: Path) -> bool:
    return path.parts[:4] == ("packages", "core", "src", "ditto_core")


def _is_port_file(path: Path) -> bool:
    return path.parts[:4] == ("apps", "port", "src", "ditto_port")


def _is_port_registry_file(path: Path) -> bool:
    if not _is_port_file(path):
        return False
    parts = path.parts
    return len(parts) >= REGISTRY_MIN_PARTS and parts[4] == "registry"


def _annotation_name(annotation: ast.expr | None) -> str | None:
    if annotation is None:
        return None
    if isinstance(annotation, ast.Name):
        return annotation.id
    if isinstance(annotation, ast.Attribute):
        # typing aliases like module.Type
        return annotation.attr
    if isinstance(annotation, ast.Subscript):
        return _annotation_name(annotation.value)
    if isinstance(annotation, ast.BinOp):
        # Handles X | Y
        left = _annotation_name(annotation.left)
        right = _annotation_name(annotation.right)
        return left or right
    return None


class ArchitectureChecker:
    """AST-based architecture checker."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def _iter_target_files(self) -> list[Path]:
        patterns = [
            "packages/foundation/src/**/*.py",
            "packages/datahub/src/**/*.py",
            "packages/core/src/**/*.py",
            "apps/port/src/**/*.py",
        ]
        files: list[Path] = []
        for pattern in patterns:
            files.extend(self.root.glob(pattern))
        return sorted({p for p in files if p.is_file()})

    def _iter_legacy_term_scan_files(self) -> list[Path]:
        patterns = [
            "packages/foundation/src/**/*.py",
            "packages/datahub/src/**/*.py",
            "packages/core/src/**/*.py",
            "apps/port/src/**/*.py",
            "config/**/*.yml",
            "config/**/*.yaml",
            "packages/datahub/config/**/*.yml",
            "packages/datahub/config/**/*.yaml",
            "packages/datahub/src/**/*.sql",
        ]
        files: list[Path] = []
        for pattern in patterns:
            files.extend(self.root.glob(pattern))
        return sorted({p for p in files if p.is_file()})

    def run(self) -> list[Violation]:
        violations: list[Violation] = []
        for file_path in self._iter_target_files():
            rel_path = file_path.relative_to(self.root)
            violations.extend(self._check_file(file_path, rel_path))
        for file_path in self._iter_legacy_term_scan_files():
            rel_path = file_path.relative_to(self.root)
            violations.extend(self._check_legacy_terms(file_path, rel_path))
        return sorted(violations, key=lambda v: (str(v.file), v.line, v.code))

    def _check_file(self, abs_path: Path, rel_path: Path) -> list[Violation]:
        try:
            source = abs_path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(rel_path))
        except SyntaxError as exc:
            return [
                Violation(
                    code="ARCH000",
                    file=rel_path,
                    line=exc.lineno or 1,
                    message=f"语法错误导致无法执行架构检查: {exc.msg}",
                )
            ]

        imports = _extract_imports(tree)
        violations: list[Violation] = []

        for ref in imports:
            if not _is_project_import(ref.module):
                continue
            violations.extend(self._check_foundation_import(rel_path, ref))
            violations.extend(self._check_datahub_import(rel_path, ref))
            violations.extend(self._check_core_import(rel_path, ref))
            violations.extend(self._check_port_import(rel_path, ref))

        if _is_port_registry_file(rel_path):
            violations.extend(
                self._check_registry_direct_usage(tree, rel_path, imports)
            )
        violations.extend(self._check_legacy_datahub_alias_usage(tree, rel_path))

        return violations

    def _check_legacy_terms(self, abs_path: Path, rel_path: Path) -> list[Violation]:
        text = abs_path.read_text(encoding="utf-8")
        violations: list[Violation] = []
        for line_no, line in enumerate(text.splitlines(), start=1):
            for pattern, code, message in LEGACY_FIELD_PATTERNS:
                if pattern.search(line):
                    violations.append(
                        Violation(
                            code=code,
                            file=rel_path,
                            line=line_no,
                            message=message,
                        )
                    )
        return violations

    def _check_foundation_import(
        self,
        rel_path: Path,
        ref: ImportRef,
    ) -> list[Violation]:
        if not _is_foundation_file(rel_path):
            return []
        if not ref.module.startswith(("ditto_datahub", "ditto_core", "ditto_port")):
            return []
        return [
            Violation(
                code="ARCH100",
                file=rel_path,
                line=ref.line,
                message=f"Foundation 层禁止依赖 DataHub/Core/Port: {ref.module}",
            )
        ]

    def _check_datahub_import(
        self,
        rel_path: Path,
        ref: ImportRef,
    ) -> list[Violation]:
        if not _is_datahub_file(rel_path):
            return []
        if not ref.module.startswith(("ditto_core", "ditto_port")):
            return []
        return [
            Violation(
                code="ARCH200",
                file=rel_path,
                line=ref.line,
                message=f"DataHub 层禁止依赖 Core/Port: {ref.module}",
            )
        ]

    def _check_core_import(
        self,
        rel_path: Path,
        ref: ImportRef,
    ) -> list[Violation]:
        if not _is_core_file(rel_path):
            return []
        if not ref.module.startswith("ditto_datahub"):
            return []
        if ref.module == "ditto_datahub.models" or ref.module.startswith(
            "ditto_datahub.models."
        ):
            return []
        return [
            Violation(
                code="ARCH300",
                file=rel_path,
                line=ref.line,
                message=(
                    f"Core 层仅可依赖 DataHub models, 禁止依赖实现模块: {ref.module}"
                ),
            )
        ]

    def _check_port_import(
        self,
        rel_path: Path,
        ref: ImportRef,
    ) -> list[Violation]:
        if not _is_port_file(rel_path) or _is_port_registry_file(rel_path):
            return []
        if not ref.module.startswith(
            (
                "ditto_datahub.stores",
                "ditto_datahub.sources",
                "ditto_datahub.runtime",
            )
        ):
            return []
        return [
            Violation(
                code="ARCH410",
                file=rel_path,
                line=ref.line,
                message=(
                    "Port 非 registry 模块禁止直接依赖 "
                    f"DataHub stores/sources/runtime: {ref.module}"
                ),
            )
        ]

    @staticmethod
    def _registry_import_symbols(imports: list[ImportRef]) -> set[str]:
        return {
            ref.symbol
            for ref in imports
            if ref.module.startswith(("ditto_datahub.stores", "ditto_datahub.sources"))
        }

    @staticmethod
    def _registry_param_names(
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        symbols: set[str],
    ) -> set[str]:
        param_names: set[str] = set()
        all_args = [
            *node.args.args,
            *node.args.kwonlyargs,
        ]
        if node.args.vararg:
            all_args.append(node.args.vararg)
        if node.args.kwarg:
            all_args.append(node.args.kwarg)
        for arg in all_args:
            annotation_name = _annotation_name(arg.annotation)
            if annotation_name in symbols:
                param_names.add(arg.arg)
        return param_names

    @staticmethod
    def _registry_has_direct_call(
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        param_names: set[str],
    ) -> list[tuple[int, str]]:
        calls: list[tuple[int, str]] = []
        for sub in ast.walk(node):
            if not isinstance(sub, ast.Call):
                continue
            if not isinstance(sub.func, ast.Attribute):
                continue
            if not isinstance(sub.func.value, ast.Name):
                continue
            if sub.func.value.id in param_names:
                method = f"{sub.func.value.id}.{sub.func.attr}()"
                calls.append((sub.lineno, method))
        return calls

    def _check_registry_direct_usage(
        self,
        tree: ast.AST,
        rel_path: Path,
        imports: list[ImportRef],
    ) -> list[Violation]:
        imported_store_source_symbols = self._registry_import_symbols(imports)
        if not imported_store_source_symbols:
            return []

        violations: list[Violation] = []

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            param_names = self._registry_param_names(
                node,
                imported_store_source_symbols,
            )
            if not param_names:
                continue

            for lineno, method in self._registry_has_direct_call(node, param_names):
                violations.append(
                    Violation(
                        code="ARCH430",
                        file=rel_path,
                        line=lineno,
                        message=(
                            "Port registry 中允许注入 stores/sources, "
                            f"但禁止直接调用其业务方法: {method}"
                        ),
                    )
                )

        return violations

    @staticmethod
    def _attribute_chain(node: ast.Attribute) -> list[str]:
        parts: list[str] = []
        current: ast.AST = node
        while isinstance(current, ast.Attribute):
            parts.append(current.attr)
            current = current.value
        if isinstance(current, ast.Name):
            parts.append(current.id)
        return list(reversed(parts))

    def _check_legacy_datahub_alias_usage(
        self,
        tree: ast.AST,
        rel_path: Path,
    ) -> list[Violation]:
        if not (_is_datahub_file(rel_path) or _is_port_file(rel_path)):
            return []

        violations: list[Violation] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Attribute):
                continue
            if node.attr not in LEGACY_DATAHUB_ALIAS_ATTRS:
                continue

            chain = self._attribute_chain(node)
            if len(chain) < MIN_ATTR_CHAIN_LENGTH:
                continue
            if chain[-2] not in HUB_REFERENCE_NAMES:
                continue

            violations.append(
                Violation(
                    code="ARCH520",
                    file=rel_path,
                    line=node.lineno,
                    message=(
                        f"禁止使用 DataHub legacy 别名 '{node.attr}', "
                        "请使用 metadata/market/ingestion_log_store 等正式入口"
                    ),
                )
            )
        return violations


def _print_result(violations: list[Violation]) -> None:
    if not violations:
        print("Architecture check passed.")
        return

    print("Architecture check failed:")
    for item in violations:
        print(f"- [{item.code}] {item.file}:{item.line} {item.message}")


def main(argv: list[str]) -> int:
    root = Path.cwd()
    if "--root" in argv:
        index = argv.index("--root")
        if index + 1 >= len(argv):
            print("Missing value for --root", file=sys.stderr)
            return 2
        root = Path(argv[index + 1]).resolve()

    checker = ArchitectureChecker(root=root)
    violations = checker.run()
    _print_result(violations)
    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
