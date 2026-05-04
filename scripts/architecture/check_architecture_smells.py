#!/usr/bin/env python3
"""Read-only architecture smell checks for Ditto.

Checks only stable, low-noise smells that are already agreed upon and cleaned up:

1. f-string logging calls in source code (use lazy formatting instead)
2. Missing __init__.py in Python package directories
3. Oversized source files (>800 lines)
4. Platform must not contain business table prefixes
5. Production packages must not import ditto_analysis
6. Kernel must not import ditto_platform

Usage:
    python scripts/architecture/check_architecture_smells.py
    python scripts/architecture/check_architecture_smells.py --verbose
"""

from __future__ import annotations

import argparse
import ast
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

SRC_ROOTS = [
    ROOT / "packages",
]

MAX_FILE_LINES = 800

# Logger methods that should NOT use f-strings (lazy formatting is preferred).
FORBIDDEN_FSTRING_LOG_PATTERNS = (
    "logger.debug(f",
    "logger.info(f",
    "logger.warning(f",
    "logger.error(f",
    "logger.critical(f",
)

# Business table prefixes that must not appear in platform source files.
BUSINESS_TABLE_PREFIXES = (
    "execution_",
    "strategy_",
    "portfolio_",
    "risk_",
    "features_",
)

# Known safe metric/config names in platform that contain business prefixes.
PLATFORM_PREFIX_ALLOWLIST = frozenset(
    {
        "portfolio_value",
        "portfolio_drawdown",
        "portfolio_drawdown_3d",
    }
)

PRODUCTION_PACKAGES = (
    "ditto_data",
    "ditto_features",
    "ditto_strategy",
    "ditto_portfolio",
    "ditto_risk",
    "ditto_execution",
    "ditto_backtest",
    "ditto_application",
)

# DI wiring / service re-export paths that legitimately cross analysis boundary.
# Keep in sync with .importlinter data-boundary + analysis-no-production-dependency.
PRODUCTION_ANALYSIS_WIRING_ALLOWLIST = (
    "ditto_data/di/",
    "ditto_data/services/__init__",
    "ditto_application/providers_",
    "ditto_application/queries/research",
)

# AI rule files that should use current package names.
AI_RULE_ROOTS = [
    ROOT / "CLAUDE.md",
    ROOT / "AGENTS.md",
    ROOT / ".claude" / "rules",
    ROOT / ".claude" / "commands",
    ROOT / ".claude" / "checklists",
    ROOT / ".factory" / "commands",
]

# Active package docs (CLAUDE.md, README.md under packages/) roots.
PACKAGE_DOC_ROOTS = [
    ROOT / "packages",
]

# Stale package references that should not appear in active AI rules.
STALE_AI_RULE_REFERENCES = (
    "ditto_infra",
    "ditto_interfaces",
    "ditto_app.",  # ditto_application is OK, ditto_app. is stale
    "ditto_analytics",
    "ditto_engine",
    "packages/infra",
    "packages/app/",  # packages/application is OK
    "packages/analytics",
    "packages/engine",
    "interfaces/src",
    "interfaces/tests",
)

# Stale package references that should not appear in active package docs
# (CLAUDE.md, README.md under packages/).
STALE_ACTIVE_PACKAGE_REFERENCES = (
    "ditto_app.",  # ditto_application / ditto_apps are OK
    "ditto_analytics",
    "ditto_engine",
    "ditto_interfaces",
    "ditto_infra",
    "packages/app/",
    "packages/analytics",
    "packages/engine",
    "packages/infra",
    "interfaces/tests",
    "interfaces/src",
)


def iter_source_files() -> list[Path]:
    """Collect all Python source files under SRC_ROOTS."""
    files: list[Path] = []
    for root in SRC_ROOTS:
        files.extend(root.glob("**/src/**/*.py"))
    return sorted(files)


def _is_package_source(rel_path: str, *packages: str) -> bool:
    if "/tests/" in rel_path:
        return False
    return any(pkg in rel_path for pkg in packages)


def _has_import(source: str, module: str) -> bool:
    return f"from {module}" in source or f"import {module}" in source


def check_fstring_logging(source: str, rel_path: str) -> list[str]:
    """Check for f-string usage in logger calls."""
    errors: list[str] = []
    for pattern in FORBIDDEN_FSTRING_LOG_PATTERNS:
        if pattern in source:
            errors.append(f"{rel_path}: contains {pattern!r}")
    return errors


def check_missing_init_py() -> list[str]:
    """Check for Python directories under src/ that lack __init__.py."""
    errors: list[str] = []
    for root in SRC_ROOTS:
        src_dirs = root.glob("**/src")
        for src_dir in src_dirs:
            for py_dir in src_dir.rglob("*"):
                if not py_dir.is_dir():
                    continue
                if any(
                    skip in py_dir.name
                    for skip in ("__pycache__", ".pixi", ".egg-info", "egg-info")
                ):
                    continue
                init_file = py_dir / "__init__.py"
                if not init_file.exists():
                    has_py = any(py_dir.glob("*.py"))
                    if has_py:
                        errors.append(
                            f"{py_dir.relative_to(ROOT)}: missing __init__.py"
                        )
    return errors


def check_oversized_files(line_count: int, rel_path: str) -> list[str]:
    """Check for source files exceeding the line limit."""
    if line_count > MAX_FILE_LINES:
        return [f"{rel_path}: {line_count} lines (max {MAX_FILE_LINES})"]
    return []


def check_platform_business_tables(source: str, rel_path: str) -> list[str]:
    """Check for business table prefixes in platform source files."""
    if not _is_package_source(rel_path, "ditto_platform"):
        return []
    errors: list[str] = []
    for prefix in BUSINESS_TABLE_PREFIXES:
        for quote in ('"', "'"):
            idx = 0
            search_key = f"{quote}{prefix}"
            while True:
                idx = source.find(search_key, idx)
                if idx == -1:
                    break
                end_idx = source.find(quote, idx + 1)
                if end_idx == -1:
                    idx += 1
                    continue
                full_name = source[idx + 1 : end_idx]
                if full_name not in PLATFORM_PREFIX_ALLOWLIST:
                    msg = (
                        f"{rel_path}: platform has business "
                        f"prefix {quote}{prefix}...{quote} "
                        f"({full_name!r})"
                    )
                    errors.append(msg)
                idx = end_idx + 1
    return errors


def check_production_no_analysis(source: str, rel_path: str) -> list[str]:
    """Check production packages do not import ditto_analysis."""
    if not _is_package_source(rel_path, *PRODUCTION_PACKAGES):
        return []
    if any(pattern in rel_path for pattern in PRODUCTION_ANALYSIS_WIRING_ALLOWLIST):
        return []
    if _has_import(source, "ditto_analysis"):
        msg = f"{rel_path}: production imports ditto_analysis (check import-linter)"
        return [msg]
    return []


def check_kernel_no_platform(source: str, rel_path: str) -> list[str]:
    """Check kernel does not import ditto_platform."""
    if not _is_package_source(rel_path, "ditto_kernel"):
        return []
    if _has_import(source, "ditto_platform"):
        msg = f"{rel_path}: kernel imports ditto_platform (must be platform-free)"
        return [msg]
    return []


def _check_per_file(verbose: bool) -> list[str]:
    """Run per-file checks (f-string logging, oversized files, boundary checks)."""
    errors: list[str] = []
    fstring_count = 0
    oversized_count = 0

    for path in iter_source_files():
        if "__pycache__" in path.parts or ".pixi" in path.parts:
            continue

        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue

        rel_path = str(path.relative_to(ROOT))
        line_count = len(source.splitlines())

        fstring_errors = check_fstring_logging(source, rel_path)
        if fstring_errors:
            fstring_count += len(fstring_errors)
            errors.extend(fstring_errors)

        oversized_errors = check_oversized_files(line_count, rel_path)
        if oversized_errors:
            oversized_count += len(oversized_errors)
            errors.extend(oversized_errors)

        errors.extend(check_platform_business_tables(source, rel_path))
        errors.extend(check_production_no_analysis(source, rel_path))
        errors.extend(check_kernel_no_platform(source, rel_path))

    if verbose:
        if fstring_count == 0:
            print("[OK] No f-string logging calls found")
        if oversized_count == 0:
            print("[OK] No oversized files found")

    return errors


def check_ai_rule_stale_references() -> list[str]:
    """Check active AI rule files for stale package references."""
    errors: list[str] = []
    for root in AI_RULE_ROOTS:
        if root.is_file():
            files_to_check = [root]
        elif root.is_dir():
            files_to_check = sorted(root.rglob("*.md"))
            files_to_check.extend(sorted(root.rglob("*.py")))
        else:
            continue

        for path in files_to_check:
            try:
                content = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            rel = str(path.relative_to(ROOT))
            for stale in STALE_AI_RULE_REFERENCES:
                if stale in content:
                    errors.append(f"{rel}: contains stale AI rule reference {stale!r}")
    return errors


def check_package_doc_stale_references() -> list[str]:
    """Check active package docs (CLAUDE.md, README.md) for stale references."""
    errors: list[str] = []
    for root in PACKAGE_DOC_ROOTS:
        if not root.is_dir():
            continue
        files_to_check: list[Path] = []
        for name in ("CLAUDE.md", "README.md"):
            files_to_check.extend(sorted(root.rglob(name)))
        for path in files_to_check:
            try:
                content = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            rel = str(path.relative_to(ROOT))
            for stale in STALE_ACTIVE_PACKAGE_REFERENCES:
                if stale in content:
                    errors.append(f"{rel}: contains stale package reference {stale!r}")
    return errors


_IMPORT_TO_PKG: dict[str, str] = {
    "ditto_kernel": "kernel",
    "ditto_platform": "platform",
    "ditto_data": "data",
    "ditto_features": "features",
    "ditto_strategy": "strategy",
    "ditto_portfolio": "portfolio",
    "ditto_risk": "risk",
    "ditto_execution": "execution",
    "ditto_backtest": "backtest",
    "ditto_analysis": "analysis",
    "ditto_application": "application",
    "ditto_apps": "apps",
}

_PKG_TO_DEP = {v: f"ditto-{v}" for v in _IMPORT_TO_PKG.values()}


def _scan_pkg_imports(src_dir: Path, pkg_name: str) -> set[str]:
    """Scan actual internal ditto-* imports from a package's src/."""
    actual: set[str] = set()
    for py_file in src_dir.rglob("*.py"):
        if "__pycache__" in py_file.parts:
            continue
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"))
        except (OSError, SyntaxError):
            continue
        for node in ast.walk(tree):
            mods: list[str] = []
            if isinstance(node, ast.Import):
                mods = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                mods = [node.module]
            for mod in mods:
                dep = _IMPORT_TO_PKG.get(mod.split(".")[0])
                if dep and dep != pkg_name:
                    actual.add(_PKG_TO_DEP[dep])
    return actual


def _check_version_mismatch(
    pyproject: Path,
    src_dir: Path,
    pkg_dir_name: str,
    pyproject_version: str | None,
    root: Path,
) -> list[str]:
    """Check _version.py matches pyproject.toml version."""
    if not pyproject_version:
        return []
    version_file = src_dir / pkg_dir_name.replace("-", "_") / "_version.py"
    if not version_file.exists():
        return []
    for line in version_file.read_text(encoding="utf-8").splitlines():
        if line.startswith("__version__"):
            src_ver = line.split("=")[1].strip().strip("\"'")
            if src_ver != pyproject_version:
                msg = (
                    f"{pyproject.relative_to(root)}:"
                    f" version {pyproject_version}"
                    f" != {version_file.relative_to(root)} {src_ver}"
                )
                return [msg]
            break
    return []


def check_package_metadata(root: Path) -> list[str]:
    """Check pyproject.toml deps match actual source imports."""
    errors: list[str] = []
    for pkg_dir in sorted((root / "packages").iterdir()):
        if not pkg_dir.is_dir():
            continue
        pyproject = pkg_dir / "pyproject.toml"
        src_dir = pkg_dir / "src"
        if not pyproject.exists() or not src_dir.is_dir():
            continue

        actual = _scan_pkg_imports(src_dir, pkg_dir.name)
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        declared = set(data.get("project", {}).get("dependencies", []))

        missing = actual - declared
        stale = declared - actual - {d for d in declared if not d.startswith("ditto-")}
        if missing:
            errors.append(
                f"{pyproject.relative_to(root)}: missing dependencies {sorted(missing)}"
            )
        if stale:
            errors.append(
                f"{pyproject.relative_to(root)}: stale dependencies {sorted(stale)}"
            )

        pv = data.get("project", {}).get("version")
        errors.extend(
            _check_version_mismatch(pyproject, src_dir, pkg_dir.name, pv, root)
        )
    return errors


def _collect(errors: list[str], new: list[str], ok_msg: str, verbose: bool) -> None:
    if new:
        errors.extend(new)
    elif verbose:
        print(ok_msg)


def main() -> int:
    parser = argparse.ArgumentParser(description="Architecture smell checks for Ditto")
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Print verbose output including passing checks",
    )
    args = parser.parse_args()

    errors: list[str] = []

    # Check 1: Missing __init__.py
    _collect(
        errors,
        check_missing_init_py(),
        "[OK] All package directories have __init__.py",
        args.verbose,
    )

    # Check 2: Per-file checks
    errors.extend(_check_per_file(args.verbose))

    # Check: AI rule stale references
    _collect(
        errors,
        check_ai_rule_stale_references(),
        "[OK] No stale AI rule references found",
        args.verbose,
    )

    # Check: Package doc stale references
    _collect(
        errors,
        check_package_doc_stale_references(),
        "[OK] No stale package doc references found",
        args.verbose,
    )

    # Check: Package metadata matches source imports
    _collect(
        errors,
        check_package_metadata(ROOT),
        "[OK] Package metadata matches source imports",
        args.verbose,
    )

    if errors:
        print("\nArchitecture smell check failed:\n")
        for error in errors:
            print(f"  {error}")
        print(f"\nTotal issues: {len(errors)}")
        return 1

    print("Architecture smell check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
