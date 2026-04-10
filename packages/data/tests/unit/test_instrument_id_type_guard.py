"""Guard: service/api/model 层不应出现 instrument_id: str.

Regression test — if this fails, someone has re-introduced instrument_id: str
in the internal query/service/api/model layers. All internal instrument_id
should be int or InstrumentId.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

# Directories to scan for instrument_id: str violations (relative to repo root)
SCANNED_DIRS: list[str] = [
    "packages/data/src/ditto_data/services/",
    "packages/data/src/ditto_data/models/",
    "interfaces/src/ditto_interfaces/api/",
    "interfaces/src/ditto_interfaces/models/",
]

# Regex: instrument_id annotated as str type (not return types, not docstrings)
# Matches patterns like: instrument_id: str, instrument_id: str | None, etc.
_VIOLATION_RE = re.compile(r"instrument_id\s*:\s*str\b")

# Patterns that are legitimate (source_ticker boundaries, type ignores, etc.)
EXCLUDED_PATTERNS: list[str] = [
    "source_ticker",
    "index_id",
    "# type: ignore",
    "TYPE_CHECKING",
]


def _scan_dir(dir_path: Path) -> list[str]:
    """Scan a directory tree for instrument_id: str violations."""
    violations: list[str] = []
    for py_file in sorted(dir_path.rglob("*.py")):
        rel = py_file.relative_to(dir_path)
        if "__pycache__" in rel.parts:
            continue
        lines = py_file.read_text(encoding="utf-8").splitlines()
        for lineno, line in enumerate(lines, 1):
            if _VIOLATION_RE.search(line) and not any(
                exc in line for exc in EXCLUDED_PATTERNS
            ):
                violations.append(f"{rel}:{lineno}: {line.strip()}")
    return violations


@pytest.mark.unit
class TestInstrumentIdTypeGuard:
    """Ensure instrument_id is never typed as str in internal layers."""

    @pytest.mark.parametrize("dir_rel", SCANNED_DIRS)
    def test_no_str_instrument_id_in_public_interfaces(self, dir_rel: str) -> None:
        """Scan Python files for 'instrument_id: str' type annotations."""
        dir_path = Path(dir_rel)
        if not dir_path.is_dir():
            pytest.skip(f"Directory not found: {dir_rel}")

        violations = _scan_dir(dir_path)

        assert not violations, f"Found instrument_id: str in {dir_rel}:\n" + "\n".join(
            violations
        )
