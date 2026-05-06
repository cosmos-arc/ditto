"""Unit tests for analysis placeholder honesty architecture checks."""

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


def _write_placeholder_files(tmp_path: Path, body: str) -> None:
    for rel_path in _MODULE.ANALYSIS_PLACEHOLDER_INIT_PATHS:  # type: ignore[attr-defined]
        path = tmp_path / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")


def test_empty_placeholder_requires_reserved_phrases(tmp_path: Path) -> None:
    check = _MODULE.check_analysis_placeholder_honesty  # type: ignore[attr-defined]
    body = '''"""
Reserved namespace.

This namespace is reserved for future analysis product work.
No public runtime API is exported yet.
"""

__all__: list[str] = []
'''
    _write_placeholder_files(tmp_path, body)

    errors = check(tmp_path)

    assert len(errors) == 4
    assert all(
        "missing required reserved placeholder phrase "
        "'Production code must not import this namespace for behavior'" in error
        for error in errors
    )


def test_empty_placeholder_rejects_misleading_availability_phrases(
    tmp_path: Path,
) -> None:
    check = _MODULE.check_analysis_placeholder_honesty  # type: ignore[attr-defined]
    body = '''"""
Reserved namespace.

This namespace is reserved for future analysis product work.
No public runtime API is exported yet.
Production code must not import this namespace for behavior.
This namespace handles reports and 负责未来产品说明.
"""

__all__: list[str] = []
'''
    _write_placeholder_files(tmp_path, body)

    errors = check(tmp_path)

    assert len(errors) >= 4
    assert all("misleading availability phrase" in error for error in errors)
    assert any("'handles'" in error for error in errors)
    assert any("'负责'" in error for error in errors)


def test_non_empty_literal_all_skips_placeholder_guard(tmp_path: Path) -> None:
    check = _MODULE.check_analysis_placeholder_honesty  # type: ignore[attr-defined]
    body = '''"""This future module provides a tested public contract."""

class PublicContract:
    pass

__all__ = ["PublicContract"]
'''
    _write_placeholder_files(tmp_path, body)

    errors = check(tmp_path)

    assert errors == []


def test_active_doc_checker_rejects_reserved_placeholder_capability_claims(
    tmp_path: Path,
) -> None:
    check = _MODULE.check_analysis_placeholder_active_docs  # type: ignore[attr-defined]
    path = tmp_path / "docs" / "architecture" / "agent-context-pack.md"
    path.parent.mkdir(parents=True)
    path.write_text(
        "| Reports, diagnostics, experiments, research | `analysis` |\n",
        encoding="utf-8",
    )

    errors = check(tmp_path)

    assert errors == [
        "docs/architecture/agent-context-pack.md:1: active docs imply "
        "reserved analysis capability "
        "'Reports, diagnostics, experiments, research'; describe research "
        "control-plane as current and "
        "reports/diagnostics/experiments/screeners as reserved/future"
    ]


def test_active_doc_checker_rejects_case_variants_of_english_claims(
    tmp_path: Path,
) -> None:
    check = _MODULE.check_analysis_placeholder_active_docs  # type: ignore[attr-defined]
    path = tmp_path / "docs" / "architecture" / "agent-context-pack.md"
    path.parent.mkdir(parents=True)
    path.write_text(
        "| reports, diagnostics, experiments, research | `analysis` |\n",
        encoding="utf-8",
    )

    errors = check(tmp_path)

    assert errors == [
        "docs/architecture/agent-context-pack.md:1: active docs imply "
        "reserved analysis capability "
        "'Reports, diagnostics, experiments, research'; describe research "
        "control-plane as current and "
        "reports/diagnostics/experiments/screeners as reserved/future"
    ]


def test_active_doc_checker_scans_agent_rules_for_chinese_placeholder_claims(
    tmp_path: Path,
) -> None:
    check = _MODULE.check_analysis_placeholder_active_docs  # type: ignore[attr-defined]
    path = tmp_path / ".claude" / "rules" / "architecture.md"
    path.parent.mkdir(parents=True)
    path.write_text(
        "| `ditto_analysis` | 报告、诊断、实验、筛选(非生产路径) |\n",
        encoding="utf-8",
    )

    errors = check(tmp_path)

    assert errors == [
        ".claude/rules/architecture.md:1: active docs imply reserved "
        "analysis capability '报告、诊断、实验、筛选'; describe research "
        "control-plane as current and "
        "reports/diagnostics/experiments/screeners as reserved/future"
    ]


def test_active_doc_checker_rejects_analysis_evaluation_tree_claim(
    tmp_path: Path,
) -> None:
    check = _MODULE.check_analysis_placeholder_active_docs  # type: ignore[attr-defined]
    path = tmp_path / "README.md"
    path.write_text(
        "\n".join(
            (
                "│   ├── analysis/                # research control-plane",
                "│   │   └── src/ditto_analysis/",
                "│   │       ├── evaluation/      # factor evaluation",
            )
        ),
        encoding="utf-8",
    )

    errors = check(tmp_path)

    assert errors == [
        "README.md:3: active docs list reserved or absent analysis namespace "
        "'evaluation/'; describe research control-plane as current and "
        "reports/diagnostics/experiments/screeners as reserved/future"
    ]


def test_active_doc_checker_scans_package_readmes(tmp_path: Path) -> None:
    check = _MODULE.check_analysis_placeholder_active_docs  # type: ignore[attr-defined]
    path = tmp_path / "packages" / "platform" / "README.md"
    path.parent.mkdir(parents=True)
    path.write_text("│     (纯研究分析)                     │\n", encoding="utf-8")

    errors = check(tmp_path)

    assert errors == [
        "packages/platform/README.md:1: active docs imply reserved "
        "analysis capability '纯研究分析'; describe research control-plane "
        "as current and reports/diagnostics/experiments/screeners as "
        "reserved/future"
    ]


def test_active_doc_checker_allows_reserved_future_placeholder_notice(
    tmp_path: Path,
) -> None:
    check = _MODULE.check_analysis_placeholder_active_docs  # type: ignore[attr-defined]
    path = tmp_path / "docs" / "architecture" / "agent-context-pack.md"
    path.parent.mkdir(parents=True)
    path.write_text(
        "Reports, diagnostics, experiments, and screeners are "
        "reserved/future analysis namespaces, not current runtime APIs.\n",
        encoding="utf-8",
    )

    errors = check(tmp_path)

    assert errors == []


def test_active_architecture_docs_do_not_imply_reserved_placeholder_capabilities() -> (
    None
):
    check = _MODULE.check_analysis_placeholder_active_docs  # type: ignore[attr-defined]

    errors = check(Path.cwd())

    assert errors == []
