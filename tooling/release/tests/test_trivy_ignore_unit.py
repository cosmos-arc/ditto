"""trivy ignore expiry guard tests."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest

from tooling.release.trivy_ignore import (
    assert_suppressions_current,
    parse_suppression_expiries,
)


def _write(root: Path, text: str) -> Path:
    path = root / ".trivyignore"
    path.write_text(text, encoding="utf-8")
    return path


def test_parses_expiry_annotation_per_cve(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "# reason\n"
        "# exp: 2026-10-14\nCVE-2026-75804\n"
        "# exp: 2026-10-14\nCVE-2026-84782\n",
    )

    assert parse_suppression_expiries(path) == {
        "CVE-2026-75804": date(2026, 10, 14),
        "CVE-2026-84782": date(2026, 10, 14),
    }


def test_current_suppression_passes(tmp_path: Path) -> None:
    path = _write(tmp_path, "# exp: 2026-10-14\nCVE-2026-75804\n")
    today = date(2026, 10, 1)

    assert_suppressions_current(path, today=today)


def test_expired_suppression_fails_closed(tmp_path: Path) -> None:
    path = _write(tmp_path, "# exp: 2026-10-14\nCVE-2026-75804\n")
    today = date(2026, 10, 15)

    with pytest.raises(SystemExit, match="CVE-2026-75804"):
        assert_suppressions_current(path, today=today)


def test_entry_without_deadline_is_rejected(tmp_path: Path) -> None:
    path = _write(tmp_path, "CVE-2026-75804\n")
    today = date(2026, 10, 1)

    with pytest.raises(SystemExit, match="without '# exp:' deadline"):
        assert_suppressions_current(path, today=today)


def test_repository_trivyignore_is_current() -> None:
    """The committed suppressions must all carry a live deadline."""
    repo_root = Path(__file__).resolve().parents[3]
    assert_suppressions_current(repo_root / ".trivyignore", today=date.today())


def test_deadline_is_near_term() -> None:
    """Temporary means near-term: no suppression may run longer than 60 days."""
    repo_root = Path(__file__).resolve().parents[3]
    horizon = date.today() + timedelta(days=60)
    stale = [
        cve
        for cve, exp in parse_suppression_expiries(repo_root / ".trivyignore").items()
        if exp and exp > horizon
    ]
    assert not stale, f"suppressions beyond 60 days need re-approval: {stale}"
