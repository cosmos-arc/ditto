"""Prove sharded evidence cannot lose tests or combine stale coverage."""

import hashlib
import json
from pathlib import Path

import pytest

from tooling.quality.test_shards import ShardError, partition, verify_manifests


def _inventory_of(files: dict[str, int]) -> list[tuple[str, bool]]:
    return [
        (f"{name}::test_{i}", i % 2 == 0)
        for name, count in files.items()
        for i in range(count)
    ]


def test_partition_is_complete_deterministic_and_file_affine() -> None:
    """#326：每 nodeid 恰好一次、纯函数确定、同文件不跨片（fixture 亲和）。"""
    inventory = _inventory_of({f"pkg/tests/test_{name}.py": 3 for name in "abcdefgh"})
    # 权重全部低于单片预算（60% 阈值），不触发巨文件拆分——本测试只考察亲和
    durations = {f"pkg/tests/test_{name}.py": 10.0 for name in "abcdefgh"}
    parts = [partition(inventory, i, 4, durations) for i in range(4)]
    assert sorted(item for part in parts for item in part) == sorted(inventory)
    # 确定性：同输入重算逐字节一致
    assert parts == [partition(inventory, i, 4, durations) for i in range(4)]
    # 文件亲和：任一文件的全部用例都在同一片
    for name in durations:
        homes = {
            shard
            for shard, part in enumerate(parts)
            if any(item[0].startswith(name + "::") for item in part)
        }
        assert len(homes) == 1, name


def test_partition_balances_by_duration_weight() -> None:
    """时长权重驱动均衡（全串行=成本与权重一致的简化形态）。"""
    inventory = [
        (f"pkg/tests/test_w{i}.py::test_{j}", True) for i in range(6) for j in range(2)
    ]
    durations = {
        f"pkg/tests/test_w{i}.py": float(w) for i, w in enumerate((4, 4, 4, 3, 3, 3))
    }
    parts = [partition(inventory, i, 3, durations) for i in range(3)]
    loads = sorted(
        sum(durations[item[0].split("::")[0]] for item in part) for part in parts
    )
    assert loads[-1] / loads[0] <= 1.2


def test_serial_records_cost_more_than_parallel_for_balance() -> None:
    """#326 评审：串行道 -n 0 全价；并行道 loadfile 下整文件单元不被 /4 低估。"""
    from tooling.quality.test_shards import _bucket_wall

    # 单个 400s 并行文件占满一个 worker：max(400, 400/4)=400 而非 100
    assert _bucket_wall(0.0, {"a.py": 400.0}) == 400.0
    # 4 个 100s 小文件摊在 4 个 worker：max(100, 400/4)=100
    assert _bucket_wall(0.0, {f"f{i}.py": 100.0 for i in range(4)}) == 100.0
    # 串行道全价叠加
    assert _bucket_wall(50.0, {f"f{i}.py": 100.0 for i in range(4)}) == 150.0
    # 同文件堆叠按合并足迹计价（loadfile 同文件单 worker）
    assert _bucket_wall(0.0, {"a.py": 300.0}) == 300.0


def test_filename_containing_split_marker_stays_whole() -> None:
    """#326 评审：合法文件名含 #split 不被误判为拆分单元。"""
    inventory = [
        ("pkg/tests/test_foo#split0.py::test_ok", False),
        ("pkg/tests/test_a.py::test_a", False),
        ("pkg/tests/test_b.py::test_b", False),
    ]
    durations = {
        "pkg/tests/test_foo#split0.py": 1.0,
        "pkg/tests/test_a.py": 1.0,
        "pkg/tests/test_b.py": 1.0,
    }
    parts = [partition(inventory, i, 2, durations) for i in range(2)]
    assert sorted(item for part in parts for item in part) == sorted(inventory)


def test_refresh_rejects_unresolvable_junit(tmp_path: Path) -> None:
    """#326 评审：junit 匹配但无任何用例解析到 root 下时必须失败关闭。"""
    from tooling.quality.test_shards import ShardError, refresh_durations

    junit = tmp_path / "junit.xml"
    junit.write_text(
        '<testsuites><testsuite tests="1" errors="0" failures="0">'
        '<testcase classname="nowhere.tests.test_x" name="test_one" time="1.0"/>'
        "</testsuite></testsuites>",
        encoding="utf-8",
    )
    with pytest.raises(ShardError, match="no testcase resolved"):
        refresh_durations([str(junit)], tmp_path / "durations.json", root=tmp_path)


def test_oversized_file_splits_but_assignment_stays_complete() -> None:
    """#326：巨文件（>单片预算 60%）按 nodeid 轮询拆分，分配仍确定完整。"""
    inventory = _inventory_of(
        {
            "pkg/tests/test_huge.py": 60,
            "pkg/tests/test_a.py": 2,
            "pkg/tests/test_b.py": 2,
        }
    )
    durations = {
        "pkg/tests/test_huge.py": 100.0,
        "pkg/tests/test_a.py": 1.0,
        "pkg/tests/test_b.py": 1.0,
    }
    parts = [partition(inventory, i, 4, durations) for i in range(4)]
    assert sorted(item for part in parts for item in part) == sorted(inventory)
    assert parts == [partition(inventory, i, 4, durations) for i in range(4)]
    huge_homes = {
        shard
        for shard, part in enumerate(parts)
        if any(item[0].startswith("pkg/tests/test_huge.py::") for item in part)
    }
    assert len(huge_homes) == 4  # 巨文件跨片拆分
    small_a = {
        shard
        for shard, part in enumerate(parts)
        if any(item[0].startswith("pkg/tests/test_a.py::") for item in part)
    }
    assert len(small_a) == 1  # 普通文件仍整文件


def test_partition_falls_back_to_default_weight_without_manifest() -> None:
    """缺清单/缺文件：默认 0.4s×用例数估重，分配仍确定且完整。"""
    inventory = _inventory_of({"pkg/tests/test_new.py": 4, "pkg/tests/test_old.py": 2})
    parts = [partition(inventory, i, 2, durations={}) for i in range(2)]
    assert sorted(item for part in parts for item in part) == sorted(inventory)
    assert parts == [partition(inventory, i, 2, durations={}) for i in range(2)]


def test_refresh_durations_merges_junit_totals(tmp_path: Path) -> None:
    """#326：刷新聚合文件级时长并落盘可重读。"""
    from tooling.quality.test_shards import refresh_durations

    module = tmp_path / "pkg/tests/unit/test_x.py"
    module.parent.mkdir(parents=True)
    module.write_text("def test_one():\n    pass\n", encoding="utf-8")
    junit = tmp_path / "junit-0-False.xml"
    junit.write_text(
        '<testsuites><testsuite tests="1" errors="0" failures="0">'
        '<testcase classname="pkg.tests.unit.test_x" name="test_one" time="2.5"/>'
        "</testsuite></testsuites>",
        encoding="utf-8",
    )
    manifest = tmp_path / "durations.json"
    merged = refresh_durations([str(junit)], manifest, root=tmp_path)
    assert merged == {"pkg/tests/unit/test_x.py": 2.5}
    rerun = refresh_durations([str(junit)], manifest, root=tmp_path)
    assert rerun == merged


@pytest.mark.parametrize(
    "corruption",
    [
        None,
        "missing",
        "duplicate",
        "commit",
        "selection",
        "inventory",
        "coverage",
        "status",
    ],
)
def test_combine_rejects_incomplete_or_stale_proof(
    tmp_path: Path, corruption: str | None
) -> None:
    inventory = [("a.py::test_a", False), ("b.py::test_b", True)]
    for index in range(2):
        data = tmp_path / f".coverage.shard-{index}"
        data.write_bytes(b"coverage data")
        report = {
            "index": index,
            "count": 2,
            "commit": "current",
            "status": "passed",
            "inventory": inventory,
            "selected": partition(inventory, index, 2),
            "coverage_sha256": hashlib.sha256(data.read_bytes()).hexdigest(),
        }
        if index == 1:
            if corruption == "missing":
                continue
            if corruption == "duplicate":
                report["index"] = 0
            if corruption == "commit":
                report["commit"] = "stale"
            if corruption == "selection":
                report["selected"] = []
            if corruption == "inventory":
                report["inventory"] = [["different", False]]
            if corruption == "coverage":
                data.write_bytes(b"changed")
            if corruption == "status":
                report["status"] = "failed"
        (tmp_path / f"shard-{index}.json").write_text(json.dumps(report))
    if corruption:
        with pytest.raises(ShardError):
            verify_manifests(tmp_path, "current", 2)
    else:
        assert len(verify_manifests(tmp_path, "current", 2)) == 2


def test_real_shards_preserve_serial_lane_and_merge_coverage(tmp_path: Path) -> None:
    """Exercise actual pytest selection, workers, coverage files and aggregation."""
    import os
    import subprocess
    import sys

    repo = Path(__file__).resolve().parents[3]
    (tmp_path / "pyproject.toml").write_text(
        '[tool.pytest.ini_options]\nmarkers=["serial: process isolated", '
        '"capacity: slow lane"]\n'
        '[tool.coverage.run]\nbranch=true\nsource=["calc"]\n'
    )
    (tmp_path / "calc.py").write_text(
        'def classify(n):\n    return "positive" if n > 0 else "other"\n'
    )
    (tmp_path / "test_calc.py").write_text(
        "import os, pytest\nfrom calc import classify\n"
        'def test_positive():\n    assert classify(1) == "positive"\n'
        "@pytest.mark.serial\ndef test_serial():\n"
        '    assert "PYTEST_XDIST_WORKER" not in os.environ\n'
        '    assert classify(0) == "other"\n'
        "@pytest.mark.capacity\ndef test_capacity_lane():\n"
        '    assert classify(2) == "positive"\n'
    )
    environment = {
        **{
            key: value
            for key, value in os.environ.items()
            if not key.startswith(("COV", "PYTEST_XDIST"))
        },
        "PYTHONPATH": f"{repo}{os.pathsep}{tmp_path}",
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
        "PYTEST_PLUGINS": "pytest_cov.plugin,xdist.plugin",
    }
    output = tmp_path / "build" / "test-shards"
    for mode, index in [("run", 0), ("run", 1), ("capacity", 0), ("combine", 0)]:
        subprocess.run(  # noqa: S603 - fixed modules over an isolated synthetic suite
            [
                sys.executable,
                "-m",
                "tooling.quality.test_shards",
                mode,
                "--count",
                "2",
                "--index",
                str(index),
                "--commit",
                "current",
                "--output",
                str(output.relative_to(tmp_path)),
            ],
            cwd=tmp_path,
            env=environment,
            check=True,
            capture_output=True,
            text=True,
        )
    report = json.loads((tmp_path / "coverage.json").read_text())
    assert report["totals"]["missing_lines"] == 0
    assert report["totals"]["missing_branches"] == 0


def test_generated_contract_ids_are_selected_after_collection(tmp_path: Path) -> None:
    """Schemathesis IDs must survive selection and missing IDs must fail closed."""
    import os
    import subprocess
    import sys

    repo = Path(__file__).resolve().parents[3]
    test_file = "apps/backend/tests/contract/test_openapi_conformance.py"
    selection = tmp_path / "selected.txt"
    selection.write_text(
        test_file
        + "::test_side_effect_free_system_endpoints_conform_to_openapi[GET /]\n"
    )
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("COV", "PYTEST_XDIST"))
    }
    environment["PYTHON_KEYRING_BACKEND"] = "keyring.backends.null.Keyring"
    command = [
        sys.executable,
        "-m",
        "pytest",
        "-o",
        "addopts=",
        "--import-mode=importlib",
        "-n",
        "2",
        "-q",
        "--no-cov",
        "-p",
        "tooling.quality.pytest_inventory",
        "--selection-input",
        str(selection),
        test_file,
    ]
    result = subprocess.run(  # noqa: S603 - fixed repository contract test
        command, cwd=repo, env=environment, capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "1 passed" in result.stdout
    selection.write_text(test_file + "::missing_generated_case\n")
    rejected = subprocess.run(  # noqa: S603 - same test with invalid selection
        command, cwd=repo, env=environment, capture_output=True, text=True, check=False
    )
    assert rejected.returncode != 0
