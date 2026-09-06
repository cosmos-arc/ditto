from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import yaml


def test_artifact_dag_builds_before_consumption_and_propagates_failure(
    tmp_path: Path,
) -> None:
    task = shutil.which("task")
    assert task is not None, "Install the Task version in .task-version"
    root = Path(__file__).resolve().parents[3]
    document = yaml.safe_load((root / "Taskfile.yml").read_text())
    leaf = tmp_path / "leaf.py"
    leaf.write_text(
        "import sys\nfrom pathlib import Path\n"
        "name = sys.argv[1]\n"
        "with Path('order').open('a') as log: log.write(name + '\\n')\n"
        "if name == 'web-build': Path('built').touch()\n"
        "if name == 'artifact-gate': assert Path('built').is_file()\n"
        "if Path('fail').exists() and name == 'web-lint': sys.exit(17)\n"
    )
    for name, definition in document["tasks"].items():
        definition.pop("dir", None)
        definition["cmds"] = [
            command
            if isinstance(command, dict)
            else f"{json.dumps(sys.executable)} leaf.py {name}"
            for command in definition["cmds"]
        ]
    (tmp_path / "Taskfile.yml").write_text(yaml.safe_dump(document))
    for fails in (True, False, False):
        if fails:
            (tmp_path / "fail").touch()
        else:
            (tmp_path / "fail").unlink(missing_ok=True)
        (tmp_path / "order").unlink(missing_ok=True)
        result = subprocess.run(
            [task, "artifact-gate"], cwd=tmp_path, capture_output=True, check=False
        )
        order = (tmp_path / "order").read_text().splitlines()
        if fails:
            assert result.returncode != 0
            assert "web-build" not in order
            assert "artifact-gate" not in order
        else:
            assert result.returncode == 0, result.stderr
            assert order.index("web-build") < order.index("artifact-gate")
