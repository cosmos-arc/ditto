#!/usr/bin/env python3
"""Read-only architecture smell checks for Ditto.

Checks only stable, low-noise smells that are already agreed upon and cleaned up:

1. f-string logging calls in source code (use lazy formatting instead)
2. Missing __init__.py in Python package directories
3. Oversized source files (>800 lines)

Usage:
    python scripts/architecture/check_architecture_smells.py
    python scripts/architecture/check_architecture_smells.py --verbose
"""

from __future__ import annotations

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

SRC_ROOTS = [
    ROOT / "packages",
    ROOT / "interfaces",
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


def iter_source_files() -> list[Path]:
    """Collect all Python source files under SRC_ROOTS."""
    files: list[Path] = []
    for root in SRC_ROOTS:
        files.extend(root.glob("**/src/**/*.py"))
    return sorted(files)


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
                # Skip __pycache__, .pixi, egg-info directories
                if any(
                    skip in py_dir.name
                    for skip in ("__pycache__", ".pixi", ".egg-info", "egg-info")
                ):
                    continue
                init_file = py_dir / "__init__.py"
                if not init_file.exists():
                    # Only flag directories that contain .py files (i.e. are packages)
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


def _check_per_file(verbose: bool) -> list[str]:
    """Run per-file checks (f-string logging, oversized files)."""
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

    if verbose:
        if fstring_count == 0:
            print("[OK] No f-string logging calls found")
        if oversized_count == 0:
            print("[OK] No oversized files found")

    return errors


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
    init_errors = check_missing_init_py()
    if init_errors:
        errors.extend(init_errors)
    elif args.verbose:
        print("[OK] All package directories have __init__.py")

    # Check 2: Per-file checks
    errors.extend(_check_per_file(args.verbose))

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
