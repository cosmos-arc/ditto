"""
Expiry guard for the temporary trivy CVE suppressions in `.trivyignore`.

Trivy's legacy ignore-file format treats `# exp:` lines as plain comments, so the
gate enforces the deadline itself: any suppression whose `# exp:` date has passed
fails the gate instead of silently suppressing forever (#378).
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

__all__ = ["assert_suppressions_current", "parse_suppression_expiries"]


def parse_suppression_expiries(path: Path) -> dict[str, date | None]:
    """Map each suppressed CVE id to its `# exp:` date (None when unannotated)."""
    expiries: dict[str, date | None] = {}
    pending: date | None = None
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#"):
            marker = line.removeprefix("#").strip().lower()
            if marker.startswith("exp:"):
                pending = date.fromisoformat(marker.removeprefix("exp:").strip())
            continue
        expiries.setdefault(line, pending)
        pending = None
    return expiries


def assert_suppressions_current(path: Path, *, today: date | None = None) -> None:
    """Fail closed when a temporary suppression has outlived its `# exp:` date."""
    current = today or datetime.now(UTC).date()
    expiries = parse_suppression_expiries(path)
    expired = sorted(cve for cve, exp in expiries.items() if exp and exp < current)
    if expired:
        joined = ", ".join(expired)
        raise SystemExit(
            f"temporary trivy suppressions expired ({joined}); "
            "re-decide or remove them in .trivyignore (#378)"
        )
    unannotated = sorted(cve for cve, exp in expiries.items() if exp is None)
    if unannotated:
        joined = ", ".join(unannotated)
        raise SystemExit(
            f".trivyignore entries without '# exp:' deadline ({joined}) are not "
            "allowed; every temporary suppression must carry one (#378)"
        )
