from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[5]
_TYPER_INJECTION_REASON = "CLI 命令回调\uff0c参数由 Typer 注入"
_APPROVED_PLR0913_NOQA_LINES: tuple[tuple[str, str], ...] = (
    (
        "apps/backend/src/ditto_apps/cli/commands/data_products.py",
        f"def bootstrap(  # noqa: PLR0913 — {_TYPER_INJECTION_REASON}",
    ),
    (
        "apps/backend/src/ditto_apps/cli/commands/data_products.py",
        f"def license_review(  # noqa: PLR0913 — {_TYPER_INJECTION_REASON}",
    ),
    (
        "apps/backend/src/ditto_apps/cli/commands/data_products.py",
        f"def build_certification(  # noqa: PLR0913 — {_TYPER_INJECTION_REASON}",
    ),
    (
        "apps/backend/src/ditto_apps/cli/commands/factory.py",
        f"def command(  # noqa: PLR0913 — {_TYPER_INJECTION_REASON}",
    ),
    (
        "apps/backend/src/ditto_apps/cli/commands/ops.py",
        f"def factor_ic(  # noqa: PLR0913 — {_TYPER_INJECTION_REASON}",
    ),
    (
        "apps/backend/src/ditto_apps/cli/commands/query/fundamental.py",
        (f"def list_corporate_actions(  # noqa: PLR0913 — {_TYPER_INJECTION_REASON}"),
    ),
    (
        "apps/backend/src/ditto_apps/cli/commands/strategy.py",
        f"def publish_signals(  # noqa: PLR0913 — {_TYPER_INJECTION_REASON}",
    ),
)


def _production_plr0913_noqa_lines() -> tuple[tuple[str, str], ...]:
    lines: list[tuple[str, str]] = []
    production_sources = (
        *(_REPO_ROOT / "packages").glob("*/src/**/*.py"),
        *(_REPO_ROOT / "apps" / "backend" / "src").glob("**/*.py"),
    )
    for path in sorted(production_sources):
        rel_path = str(path.relative_to(_REPO_ROOT))
        for line in path.read_text(encoding="utf-8").splitlines():
            if "# noqa: PLR0913" in line:
                lines.append((rel_path, line.strip()))
    return tuple(lines)


def test_production_plr0913_suppressions_are_bounded_typer_callbacks() -> None:
    assert _production_plr0913_noqa_lines() == _APPROVED_PLR0913_NOQA_LINES
