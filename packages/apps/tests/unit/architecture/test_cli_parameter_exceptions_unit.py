from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[5]
_TYPER_INJECTION_REASON = "CLI 命令回调\uff0c参数由 Typer 注入"
_APPROVED_PLR0913_NOQA_LINES: tuple[tuple[str, str], ...] = (
    (
        "packages/apps/src/ditto_apps/cli/commands/factory.py",
        f"def command(  # noqa: PLR0913 — {_TYPER_INJECTION_REASON}",
    ),
    (
        "packages/apps/src/ditto_apps/cli/commands/query/fundamental.py",
        (f"def list_corporate_actions(  # noqa: PLR0913 — {_TYPER_INJECTION_REASON}"),
    ),
)


def _production_plr0913_noqa_lines() -> tuple[tuple[str, str], ...]:
    lines: list[tuple[str, str]] = []
    for path in sorted((_REPO_ROOT / "packages").glob("*/src/**/*.py")):
        rel_path = str(path.relative_to(_REPO_ROOT))
        for line in path.read_text(encoding="utf-8").splitlines():
            if "# noqa: PLR0913" in line:
                lines.append((rel_path, line.strip()))
    return tuple(lines)


def test_production_plr0913_suppressions_are_bounded_typer_callbacks() -> None:
    assert _production_plr0913_noqa_lines() == _APPROVED_PLR0913_NOQA_LINES
