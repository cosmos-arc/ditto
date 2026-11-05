"""#686 批D：backfill CLI 面（命令顺序+帮助首行）金样守卫.

收敛 39 个包装器为直接注册后，注册顺序即 --help 命令面板顺序，
帮助文本来自工厂 description——本测试把 main 收敛前的面板逐字钉住。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from ditto_apps.cli.commands.backfill.capital import app as capital_app
from ditto_apps.cli.commands.backfill.fundamental import app as fundamental_app
from ditto_apps.cli.commands.backfill.macro import app as macro_app
from ditto_apps.cli.commands.backfill.market import app as market_app
from ditto_apps.cli.commands.backfill.metadata import app as metadata_app
from typer.testing import CliRunner

_APPS = {
    "market": market_app,
    "fundamental": fundamental_app,
    "capital": capital_app,
    "macro": macro_app,
    "metadata": metadata_app,
}

_GOLDEN_PATH = Path(__file__).with_name("backfill_cli_face_golden.json")
_EXPECTED = json.loads(_GOLDEN_PATH.read_text(encoding="utf-8"))


@pytest.mark.parametrize("group", sorted(_EXPECTED))
def test_backfill_group_face_matches_golden(group: str) -> None:
    """命令注册顺序与每命令帮助首行与 main 基线逐字一致."""
    app = _APPS[group]
    expected = _EXPECTED[group]

    assert [cmd.name for cmd in app.registered_commands] == expected["order"]

    runner = CliRunner()
    for name in expected["order"]:
        result = runner.invoke(app, [name, "--help"])
        assert result.exit_code == 0
        lines = [ln.strip() for ln in result.output.splitlines() if ln.strip()]
        usage_idx = next(i for i, ln in enumerate(lines) if ln.startswith("Usage:"))
        assert lines[usage_idx + 1] == expected["help"][name], (group, name)
