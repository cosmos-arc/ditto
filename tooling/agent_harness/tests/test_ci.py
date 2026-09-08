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
    def test_skill_changes_select_lightweight_validation(self) -> None:
        for path in (
            ".agents/skills/ditto-pit-safety/SKILL.md",
            ".claude/skills/ditto-pit-safety/SKILL.md",
            ".agents/skills/registry.toml",
        ):
            with self.subTest(path=path):
                assert required_jobs([path, "docs/guide.md"]) == {
                    "repository-policy",
                    "delivery-policy",
                    "security-supply-chain",
                    "skill-validation",
                }

    def test_scope_preserves_shared_and_risk_checks(self) -> None:
        assert required_jobs(["packages/data/AGENTS.md"]) == {
            "repository-policy",
            "delivery-policy",
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
            for kind in ("docs", "skills", "executable"):
                if kind == "skills":
                    skill = root / ".agents/skills/example/SKILL.md"
                    skill.parent.mkdir(parents=True)
                    document.rename(skill)
                    document = skill
                    git("add", ".")
                    git("commit", "--quiet", "-m", "skill")
                if kind == "executable":
                    document.chmod(0o755)
                    git("add", ".")
                    git("commit", "--quiet", "-m", "executable")
                output = root / ".git/ci-output.txt"
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
                    if kind == "executable"
                    else {
                        "repository-policy",
                        "delivery-policy",
                        "security-supply-chain",
                    }
                    | ({"skill-validation"} if kind == "skills" else set())
                )
                assert (
                    f"analysis={str(kind == 'executable').lower()}"
                    in output.read_text()
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


def test_ordinary_scopes_keep_required_cross_stack_proof() -> None:
    web = required_jobs(["apps/web/src/features/watchlist/card.tsx"])
    assert {
        "web-build",
        "web-quality",
        "web-prototype",
        "api-contract",
        "system-e2e",
    } <= web
    assert "backend-shards" not in web
    backend = required_jobs(
        ["packages/platform/src/ditto_platform/foundation/logging.py"]
    )
    assert {
        "backend-shards",
        "backend-tests",
        "api-contract",
        "system-e2e",
        "platform-smoke",
    } <= backend
    assert "container-smoke" not in backend
    for path in [
        "apps/web/package.json",
        "apps/web/vite.config.ts",
        "apps/web/tsconfig.json",
        "uv.lock",
        "packages/platform/pyproject.toml",
        "deploy/docker/Dockerfile",
        ".github/workflows/ci.yml",
    ]:
        assert required_jobs([path]) == REQUIRED_JOBS
