"""Capability package error taxonomy architecture guard."""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[5]

ERROR_MODULES = (
    "packages/features/src/ditto_features/errors.py",
    "packages/strategy/src/ditto_strategy/errors.py",
    "packages/analysis/src/ditto_analysis/errors.py",
    "packages/backtest/src/ditto_backtest/errors.py",
    "packages/execution/src/ditto_execution/errors.py",
    "packages/portfolio/src/ditto_portfolio/errors.py",
    "packages/risk/src/ditto_risk/errors.py",
    "packages/application/src/ditto_application/exceptions.py",
    "packages/data/src/ditto_data/errors.py",
)

BUILTIN_EXCEPTION_BASES = {
    "Exception",
    "KeyError",
    "RuntimeError",
    "TypeError",
    "ValueError",
}

DOMAIN_ERROR_BASES = {
    "AnalysisError",
    "ApplicationError",
    "BacktestError",
    "DataError",
    "DittoError",
    "ExecutionError",
    "FeaturesError",
    "PortfolioError",
    "RiskError",
    "StrategyError",
    "_DataError",
    "_IdentifierError",
}


def _base_name(base: ast.expr) -> str | None:
    if isinstance(base, ast.Name):
        return base.id
    if isinstance(base, ast.Attribute):
        return base.attr
    return None


def _class_base_names(node: ast.ClassDef) -> set[str]:
    return {name for base in node.bases if (name := _base_name(base)) is not None}


def _taxonomy_offenders(tree: ast.Module, relative_path: str) -> list[str]:
    offenders: list[str] = []
    local_error_classes = {
        node.name
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name.endswith("Error")
    }
    domain_error_bases = DOMAIN_ERROR_BASES | local_error_classes

    for node in (n for n in tree.body if isinstance(n, ast.ClassDef)):
        bases = _class_base_names(node)
        builtin_bases = bases & BUILTIN_EXCEPTION_BASES
        if builtin_bases and bases & domain_error_bases:
            offenders.append(
                f"{relative_path}:{node.lineno}: {node.name} mixes "
                f"domain bases {sorted(bases & domain_error_bases)} "
                f"with built-in exception bases {sorted(builtin_bases)}"
            )
    return offenders


def test_taxonomy_guard_treats_data_private_aliases_as_domain_errors() -> None:
    """Data error private aliases should still be domain taxonomy bases."""
    tree = ast.parse(
        "class AliasedDataError(_DataError, ValueError):\n"
        "    pass\n"
        "class AliasedIdentifierError(_IdentifierError, KeyError):\n"
        "    pass\n",
    )

    offenders = _taxonomy_offenders(tree, "example.py")

    assert offenders == [
        "example.py:1: AliasedDataError mixes domain bases ['_DataError'] "
        "with built-in exception bases ['ValueError']",
        "example.py:3: AliasedIdentifierError mixes domain bases "
        "['_IdentifierError'] with built-in exception bases ['KeyError']",
    ]


def test_domain_errors_do_not_also_inherit_builtin_exceptions() -> None:
    """Capability public errors should use Ditto/domain taxonomy only."""
    offenders: list[str] = []

    for relative_path in ERROR_MODULES:
        path = REPO_ROOT / relative_path
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        offenders.extend(_taxonomy_offenders(tree, relative_path))

    assert offenders == []
