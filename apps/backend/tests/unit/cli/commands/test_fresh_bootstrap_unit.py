"""Fresh-bootstrap dry-run safety contract."""

from __future__ import annotations

from pathlib import Path

import orjson
import pytest
from ditto_apps.cli.commands import fresh_bootstrap
from ditto_apps.cli.main import app as main_app
from typer.testing import CliRunner


@pytest.mark.parametrize(
    "unsafe_target",
    [
        "/",
        "~",
        "$DITTO_STATE_ROOT",
        "${DITTO_STATE_ROOT}",
        "/tmp/ditto-*",
    ],
)
def test_fresh_bootstrap_rejects_ambiguous_or_broad_targets(
    unsafe_target: str,
) -> None:
    with pytest.raises(fresh_bootstrap.FreshBootstrapTargetError):
        fresh_bootstrap.build_fresh_bootstrap_plan(unsafe_target)


def test_fresh_bootstrap_rejects_home_and_repository_roots(tmp_path: Path) -> None:
    repository = tmp_path / "ditto"
    repository.mkdir()
    (repository / ".git").mkdir()

    with pytest.raises(fresh_bootstrap.FreshBootstrapTargetError):
        fresh_bootstrap.build_fresh_bootstrap_plan(str(Path.home()))
    with pytest.raises(fresh_bootstrap.FreshBootstrapTargetError):
        fresh_bootstrap.build_fresh_bootstrap_plan(str(repository))


def test_fresh_bootstrap_dry_run_is_content_addressed_and_preserves_files(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "runtime" / "ditto"
    metadata = data_root / "metadata" / "metadata.sqlite"
    metadata.parent.mkdir(parents=True)
    metadata.write_bytes(b"runtime-state")
    backup = data_root / "backups" / "keep.sqlite"
    backup.parent.mkdir(parents=True)
    backup.write_bytes(b"backup")

    first = fresh_bootstrap.build_fresh_bootstrap_plan(str(data_root))
    second = fresh_bootstrap.build_fresh_bootstrap_plan(str(data_root))

    assert first.mode == "dry_run"
    assert first.plan_hash == second.plan_hash
    assert first.data_root == data_root.resolve()
    assert [candidate.relative_path for candidate in first.candidates] == [
        "metadata/metadata.sqlite"
    ]
    assert first.candidates[0].size_bytes == len(b"runtime-state")
    assert metadata.read_bytes() == b"runtime-state"
    assert backup.read_bytes() == b"backup"


def test_fresh_bootstrap_cli_defaults_to_json_dry_run(tmp_path: Path) -> None:
    data_root = tmp_path / "runtime" / "ditto"
    sentinel = data_root / "market" / "sentinel.parquet"
    sentinel.parent.mkdir(parents=True)
    sentinel.write_bytes(b"future-data")

    result = CliRunner().invoke(
        main_app,
        ["init", "fresh-bootstrap", "--data-root", str(data_root), "--json"],
    )

    assert result.exit_code == 0, result.output
    payload = orjson.loads(result.stdout)
    assert payload["mode"] == "dry_run"
    assert payload["data_root"] == str(data_root.resolve())
    assert payload["plan_hash"]
    assert payload["candidate_count"] == 1
    assert sentinel.read_bytes() == b"future-data"
