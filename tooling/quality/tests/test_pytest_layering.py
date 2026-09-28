"""Directory layering rule: component-exact, priority-stable, entry-stable."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from tooling.quality.pytest_layering import layer_markers_for

REPO_ROOT = Path(__file__).resolve().parents[3]

_TREE_FILES = {
    "packages/alpha/tests/unit/test_a.py": "def test_one():\n    assert True\n",
    "packages/alpha/tests/integration/test_b.py": (
        "def test_two():\n    assert True\n"
    ),
    "packages/data/tests/integration/test_g.py": (
        "def test_seven():\n    assert True\n"
    ),
    "packages/beta/tests/unit/deep/test_c.py": ("def test_three():\n    assert True\n"),
    "apps/backend/tests/contract/test_d.py": ("def test_four():\n    assert True\n"),
    "apps/backend/tests/e2e/test_e.py": "def test_five():\n    assert True\n",
    "tooling/demo/tests/test_f.py": "def test_six():\n    assert True\n",
}


def test_layer_markers_follow_directory_components() -> None:
    repo = Path("/repo")
    assert layer_markers_for(
        Path("/repo/packages/data/tests/unit/storage/test_x.py"), repo
    ) == ("unit",)
    # data 树经 #226 审计解除层级 serial；未审计 owner 仍保留。
    assert layer_markers_for(
        Path("/repo/packages/data/tests/integration/test_x.py"), repo
    ) == ("integration",)
    assert layer_markers_for(
        Path("/repo/packages/kernel/tests/integration/test_x.py"), repo
    ) == (
        "integration",
        "serial",
    )
    assert layer_markers_for(
        Path("/repo/apps/backend/tests/contract/test_x.py"), repo
    ) == ("integration",)
    assert layer_markers_for(Path("/repo/apps/backend/tests/e2e/test_x.py"), repo) == (
        "e2e",
    )
    assert layer_markers_for(
        Path("/repo/apps/backend/tests/registry/test_x.py"), repo
    ) == ("unit",)
    assert layer_markers_for(Path("/repo/tooling/quality/tests/test_x.py"), repo) == (
        "unit",
    )


def test_integration_component_wins_over_unit_on_mixed_paths() -> None:
    repo = Path("/repo")
    assert layer_markers_for(
        Path("/repo/x/tests/unit/integration/test_x.py"), repo
    ) == (
        "integration",
        "serial",
    )


def test_file_name_substrings_never_decide_the_layer() -> None:
    repo = Path("/repo")
    assert layer_markers_for(
        Path("/repo/x/tests/unit/test_x_integration.py"), repo
    ) == ("unit",)
    assert layer_markers_for(Path("/repo/x/tests/test_x_unit.py"), repo) == ("unit",)


def test_checkout_ancestors_never_decide_the_layer() -> None:
    repo = Path("/checkouts/ditto")
    assert layer_markers_for(
        Path("/tmp/integration/ditto/packages/kernel/tests/unit/test_x.py"), repo
    ) == ("unit",)
    assert layer_markers_for(
        Path("/checkouts/ditto/packages/kernel/tests/integration/test_x.py"), repo
    ) == (
        "integration",
        "serial",
    )
    # 检出祖先本身叫 tests 也不能充当 tests 根。
    assert layer_markers_for(
        Path("/tmp/tests/integration/ditto/scripts/acceptance/test_x.py"),
        Path("/tmp/tests/integration/ditto"),
    ) == ("unit",)
    assert layer_markers_for(
        Path("/home/unit/work/ditto/scripts/acceptance/test_x.py"),
        Path("/home/unit/work/ditto"),
    ) == ("unit",)


def _make_tree(root: Path) -> None:
    (root / "conftest.py").write_text(
        'pytest_plugins = ["tooling.quality.pytest_layering"]\n', encoding="utf-8"
    )
    for relative, body in _TREE_FILES.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")


def _collect(root: Path, args: list[str], dump: Path) -> dict[str, list[str]]:
    existing = os.environ.get("PYTHONPATH")
    pythonpath = (
        str(REPO_ROOT) if not existing else f"{REPO_ROOT}{os.pathsep}{existing}"
    )
    environment = {
        **os.environ,
        "PYTHONPATH": pythonpath,
        "MARKER_DUMP": str(dump),
    }
    proc = subprocess.run(  # noqa: S603 - fixed interpreter and pytest args
        [
            sys.executable,
            "-m",
            "pytest",
            *args,
            "-p",
            "tooling.quality.pytest_marker_dump",
            "--collect-only",
            "-q",
            "--no-header",
        ],
        cwd=root,
        env=environment,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(dump.read_text(encoding="utf-8"))


def test_same_nodeid_marks_stable_across_entries(tmp_path: Path) -> None:
    """单文件/owner/全仓/分片式四类入口逐 nodeid 同标记。"""
    root = tmp_path / "repo"
    root.mkdir()
    _make_tree(root)
    entries = [
        ("single", ["packages/alpha/tests/integration/test_b.py"]),
        ("owner", ["packages/alpha/tests"]),
        ("full", []),
        (
            "shard",
            ["-o", "addopts=", "--import-mode=importlib", "-m", "not snapshot"],
        ),
    ]
    dumps = {
        name: _collect(root, args, tmp_path / f"{name}.json") for name, args in entries
    }
    reference = dumps["full"]
    assert len(reference) == len(_TREE_FILES)

    expected = {
        "packages/alpha/tests/unit/test_a.py": {"unit"},
        "packages/alpha/tests/integration/test_b.py": {"integration", "serial"},
        "packages/data/tests/integration/test_g.py": {"integration"},
        "packages/beta/tests/unit/deep/test_c.py": {"unit"},
        "apps/backend/tests/contract/test_d.py": {"integration"},
        "apps/backend/tests/e2e/test_e.py": {"e2e"},
        "tooling/demo/tests/test_f.py": {"unit"},
    }
    for path, marks in expected.items():
        for nodeid, collected in reference.items():
            if nodeid.startswith(path + "::"):
                assert set(collected) >= marks, (nodeid, collected)

    for name, dump in dumps.items():
        shared = set(dump) & set(reference)
        assert shared, name
        for nodeid in shared:
            assert dump[nodeid] == reference[nodeid], (name, nodeid)


def test_serial_audit_opt_out_is_component_exact() -> None:
    """#226/#359：审计登记树解除层级 serial，边界外一律保留。"""
    repo = Path("/repo")
    assert layer_markers_for(
        Path("/repo/packages/data/tests/integration/test_x.py"), repo
    ) == ("integration",)
    assert layer_markers_for(
        Path("/repo/packages/data/tests/integration/runtime/storage/test_x.py"), repo
    ) == ("integration",)
    # 第二批登记（#359）：application 与 backtest 解除。
    assert layer_markers_for(
        Path("/repo/packages/application/tests/integration/process/test_x.py"), repo
    ) == ("integration",)
    assert layer_markers_for(
        Path("/repo/packages/backtest/tests/integration/test_x.py"), repo
    ) == ("integration",)
    # 近邻名不匹配层级规则本身（组件精确），树前缀更无从谈起。
    assert layer_markers_for(
        Path("/repo/packages/data/tests/integration-x/test_x.py"), repo
    ) == ("unit",)
    assert layer_markers_for(
        Path("/repo/packages/data-x/tests/integration/test_x.py"), repo
    ) == ("integration", "serial")
    assert layer_markers_for(
        Path("/repo/packages/analysis/tests/integration/test_x.py"), repo
    ) == ("integration", "serial")
    assert layer_markers_for(
        Path("/repo/packages/platform/tests/integration/test_x.py"), repo
    ) == ("integration", "serial")
    # 混合 unit/integration 路径不在被审计树内，保守保留 serial。
    assert layer_markers_for(
        Path("/repo/packages/data/tests/unit/integration/test_x.py"), repo
    ) == ("integration", "serial")


def test_real_repo_serial_audit_lifts_only_the_audited_trees() -> None:
    """钉死真实仓库：只有登记树解除（data/application/backtest），其余保留。"""
    files = sorted(
        {
            *REPO_ROOT.glob("packages/*/tests/integration/**/test_*.py"),
            *REPO_ROOT.glob("apps/*/tests/integration/**/test_*.py"),
        },
    )
    assert files
    lifted: set[str] = set()
    serial_owners: set[str] = set()
    for path in files:
        markers = layer_markers_for(path, REPO_ROOT)
        relative = path.relative_to(REPO_ROOT).as_posix()
        owner = relative.split("/", 2)[1]
        assert markers in {("integration",), ("integration", "serial")}, relative
        if relative.startswith(
            (
                "packages/application/tests/integration/",
                "packages/backtest/tests/integration/",
                "packages/data/tests/integration/",
            )
        ):
            assert markers == ("integration",), relative
            lifted.add(owner)
        else:
            assert markers == ("integration", "serial"), relative
            serial_owners.add(owner)
    assert lifted == {"application", "backtest", "data"}
    assert {"analysis", "platform", "strategy"} <= serial_owners


def test_explicit_serial_marker_survives_the_opt_out(tmp_path: Path) -> None:
    """审计树内显式 @pytest.mark.serial 仍生效：树级回退口（#226 恢复策略）。"""
    root = tmp_path / "repo"
    root.mkdir()
    _make_tree(root)
    escape = root / "packages/data/tests/integration/test_opt_in.py"
    escape.write_text(
        "import pytest\n\n"
        "@pytest.mark.serial\n"
        "def test_opted_back_in():\n    assert True\n",
        encoding="utf-8",
    )
    dump = _collect(root, [], tmp_path / "escape.json")
    marks = next(
        collected
        for nodeid, collected in dump.items()
        if nodeid.startswith("packages/data/tests/integration/test_opt_in.py::")
    )
    assert "integration" in marks
    assert "serial" in marks
