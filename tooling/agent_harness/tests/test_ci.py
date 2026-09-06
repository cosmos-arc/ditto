"""Exercise the same scope selection and result aggregation used by hosted CI."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from collections.abc import Mapping
from pathlib import Path

import yaml

from tooling.agent_harness.ci import REQUIRED_JOBS, required_jobs


def gate_failures(required: set[str], results: Mapping[str, object]) -> bool:
    workflow = yaml.safe_load(
        (Path(__file__).resolve().parents[3] / ".github/workflows/ci.yml").read_text()
    )
    script = workflow["jobs"]["ci-gate"]["steps"][0]["run"]
    completed = subprocess.run(
        ["bash", "-c", script],
        env={
            **os.environ,
            "REQUIRED_JOBS": json.dumps(sorted(required)),
            "NEEDS_JSON": json.dumps(results),
        },
        capture_output=True,
        text=True,
        check=False,
    )
    return completed.returncode != 0


class CiTests(unittest.TestCase):
    def test_scope_preserves_shared_and_risk_checks(self) -> None:
        assert required_jobs(["packages/data/AGENTS.md"]) == {
            "repository-policy",
            "security-supply-chain",
        }
        assert "backend-tests" in required_jobs(
            ["packages/risk/src/ditto_risk/rules.py"]
        )
        assert "system-e2e" in required_jobs(["contracts/openapi/v1.json"])
        assert "web-quality" in required_jobs(["apps/web/src/app.tsx"])
        for path in ["pixi.lock", "tooling/dev/system.py", "unknown.bin"]:
            assert required_jobs([path]) == REQUIRED_JOBS
        assert required_jobs(["docs/guide.md"], full=True) == REQUIRED_JOBS

    def test_real_selector_checks_both_git_modes(self) -> None:
        repo = Path(__file__).resolve().parents[3]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)

            def git(*args: str) -> str:
                return subprocess.check_output(
                    ["git", *args], cwd=root, text=True
                ).strip()

            git("init", "--quiet")
            git("config", "user.name", "Scope test")
            git("config", "user.email", "scope@example.invalid")
            document = root / "README.md"
            document.write_text("base\n")
            git("add", ".")
            git("commit", "--quiet", "-m", "base")
            base = git("rev-parse", "HEAD")
            document.write_text("updated\n")
            git("add", ".")
            git("commit", "--quiet", "-m", "docs")
            for executable in (False, True):
                if executable:
                    document.chmod(0o755)
                    git("add", ".")
                    git("commit", "--quiet", "-m", "executable")
                output = root / "output.txt"
                output.unlink(missing_ok=True)
                subprocess.run(
                    [sys.executable, "-m", "tooling.agent_harness.ci", "select"],
                    cwd=root,
                    env={
                        **os.environ,
                        "PYTHONPATH": str(repo),
                        "GITHUB_EVENT_NAME": "pull_request",
                        "CHECK_BASE_SHA": base,
                        "GITHUB_SHA": git("rev-parse", "HEAD"),
                        "GITHUB_OUTPUT": str(output),
                    },
                    check=True,
                    capture_output=True,
                )
                selected = json.loads(
                    output.read_text().splitlines()[0].removeprefix("required=")
                )
                assert set(selected) == (
                    REQUIRED_JOBS
                    if executable
                    else {"repository-policy", "security-supply-chain"}
                )

    def test_gate_accepts_only_explicitly_unneeded_skips(self) -> None:
        required = {"repository-policy", "security-supply-chain", "web-quality"}
        results = {
            job: {"result": "success" if job in required else "skipped"}
            for job in REQUIRED_JOBS
        }
        assert not gate_failures(required, results)
        for status in ["failure", "cancelled", "skipped"]:
            results["web-quality"] = {"result": status}
            assert gate_failures(required, results)
        del results["web-quality"]
        assert gate_failures(required, results)
        results["web-quality"] = {"result": "success"}
        results["backend-tests"] = {"result": "failure"}
        assert gate_failures(required, results)
        assert gate_failures(set(), {})
        assert gate_failures({"unknown-job"}, results)
