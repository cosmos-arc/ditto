"""Exercise the repository knowledge gate through its public CLI."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "knowledge.py"


def test_active_navigation_and_machine_inputs_fail_closed(tmp_path: Path) -> None:
    (tmp_path / ".knowledge-policy.toml").write_text(
        'schema_version = 1\nactive_documents = ["README.md"]\n'
        'machine_inputs = ["fixtures/baseline.sql"]\n',
        encoding="utf-8",
    )
    (tmp_path / "README.md").write_text("[Guide](guide.md)\n", encoding="utf-8")
    (tmp_path / "fixtures").mkdir()
    baseline = tmp_path / "fixtures/baseline.sql"
    baseline.write_text("SELECT 1;\n", encoding="utf-8")
    result = subprocess.run(  # noqa: S603 - fixed interpreter and repository CLI
        [sys.executable, str(SCRIPT), "--root", str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "guide.md" in result.stdout
    (tmp_path / "guide.md").write_text("Guide\n", encoding="utf-8")
    result = subprocess.run(  # noqa: S603 - fixed interpreter and repository CLI
        [sys.executable, str(SCRIPT), "--root", str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    baseline.unlink()
    result = subprocess.run(  # noqa: S603 - fixed interpreter and repository CLI
        [sys.executable, str(SCRIPT), "--root", str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "fixtures/baseline.sql" in result.stdout


def test_reference_links_are_checked_but_examples_and_history_are_not(
    tmp_path: Path,
) -> None:
    (tmp_path / ".knowledge-policy.toml").write_text(
        'schema_version = 1\nactive_documents = ["README.md"]\n'
        'machine_inputs = ["baseline.json"]\n',
        encoding="utf-8",
    )
    (tmp_path / "baseline.json").write_text("{}", encoding="utf-8")
    (tmp_path / "history.md").write_text("Pixi [old](gone.md)", encoding="utf-8")
    readme = tmp_path / "README.md"
    readme.write_text(
        "Discussion of Pixi remains valid. [guide][current]\n"
        "[current]: <guide with spaces.md>\n"
        "```md\n[example](missing.md)\n```\n",
        encoding="utf-8",
    )
    result = subprocess.run(  # noqa: S603 - fixed repository CLI
        [sys.executable, str(SCRIPT), "--root", str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "guide with spaces.md" in result.stdout
    assert "missing.md" not in result.stdout
    (tmp_path / "guide with spaces.md").write_text("Guide", encoding="utf-8")
    result = subprocess.run(  # noqa: S603 - fixed repository CLI
        [sys.executable, str(SCRIPT), "--root", str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_machine_input_cannot_escape_through_a_parent_symlink(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    (root / ".knowledge-policy.toml").write_text(
        'schema_version = 1\nactive_documents = ["README.md"]\n'
        'machine_inputs = ["inputs/baseline.json"]\n',
        encoding="utf-8",
    )
    (root / "README.md").write_text("Guide", encoding="utf-8")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "baseline.json").write_text("{}", encoding="utf-8")
    (root / "inputs").symlink_to(outside, target_is_directory=True)
    result = subprocess.run(  # noqa: S603 - fixed repository CLI
        [sys.executable, str(SCRIPT), "--root", str(root)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "inputs/baseline.json" in result.stdout
