"""Exercise the branch protection ruleset assertion used by CI."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

from tooling.agent_harness.branch_protection import (
    REQUIRED_CHECK,
    REQUIRED_RULES,
    evaluate,
)

REPO = Path(__file__).resolve().parents[3]


def default_rules() -> list[dict[str, object]]:
    """Rules shaped like the live ditto-main ruleset fetched on 2026-09-09."""
    return [
        {"type": "deletion"},
        {"type": "non_fast_forward"},
        {
            "type": "pull_request",
            "parameters": {"required_approving_review_count": 0},
        },
        {
            "type": "required_status_checks",
            "parameters": {
                "required_status_checks": [{"context": REQUIRED_CHECK}],
                "strict_required_status_checks_policy": True,
            },
        },
        {"type": "required_linear_history"},
    ]


def active_ruleset(**overrides: object) -> dict[str, object]:
    ruleset: dict[str, object] = {
        "id": 1,
        "name": "ditto-main",
        "target": "branch",
        "enforcement": "active",
        "conditions": {"ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}},
        "bypass_actors": [],
        "rules": default_rules(),
    }
    ruleset.update(overrides)
    return ruleset


def status_checks_rules(context: str | None, strict: bool) -> list[dict[str, object]]:
    """Rules whose status-check rule carries the given context and strictness."""
    parameters = (
        None
        if context is None
        else {
            "required_status_checks": [{"context": context}],
            "strict_required_status_checks_policy": strict,
        }
    )
    return [
        {"type": "deletion"},
        {"type": "non_fast_forward"},
        {"type": "pull_request"},
        {"type": "required_status_checks", "parameters": parameters},
    ]


def run_check(payload: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "tooling.agent_harness.branch_protection",
            "check",
            "--payload",
            str(payload),
        ],
        cwd=REPO,
        env={**os.environ, "PYTHONPATH": str(REPO)},
        capture_output=True,
        text=True,
        check=False,
    )


class EvaluateTests(unittest.TestCase):
    def test_live_ruleset_shape_passes(self) -> None:
        assert evaluate([active_ruleset()]) == []

    def test_no_active_branch_ruleset_is_reported(self) -> None:
        assert evaluate([]) == ["no active branch ruleset protects the default branch"]
        assert evaluate([active_ruleset(enforcement="evaluate")]) == [
            "no active branch ruleset protects the default branch"
        ]
        assert evaluate(
            [
                active_ruleset(
                    conditions={
                        "ref_name": {
                            "include": ["refs/heads/feature/*"],
                            "exclude": [],
                        }
                    }
                )
            ]
        ) == ["no active branch ruleset protects the default branch"]
        for conditions in (
            {"ref_name": "refs/heads/*"},
            {"ref_name": {"include": [], "exclude": []}},
        ):
            with self.subTest(conditions=conditions):
                assert evaluate([active_ruleset(conditions=conditions)]) == [
                    "no active branch ruleset protects the default branch"
                ]

    def test_each_missing_rule_is_reported(self) -> None:
        rules = default_rules()
        for missing in REQUIRED_RULES:
            with self.subTest(missing=missing):
                pruned = [rule for rule in rules if rule["type"] != missing]
                violations = evaluate(
                    [
                        active_ruleset(
                            rules=[*pruned, {"type": "required_linear_history"}]
                        )
                    ]
                )
                expected = [f"missing rule: {missing}"]
                if missing == "required_status_checks":
                    expected.append(
                        f"required status check {REQUIRED_CHECK!r} is not required"
                    )
                assert violations == expected

    def test_rules_compose_across_active_rulesets(self) -> None:
        rules = default_rules()
        split = [
            active_ruleset(
                name="a", rules=[rule for rule in rules if rule["type"] != "deletion"]
            ),
            active_ruleset(
                name="b", id=2, rules=[{"type": "deletion"}], conditions=None
            ),
        ]
        assert evaluate(split) == []

    def test_required_check_and_strict_policy_are_reported(self) -> None:
        wrong_context = active_ruleset(rules=status_checks_rules("other job", False))
        assert evaluate([wrong_context]) == [
            f"required status check {REQUIRED_CHECK!r} is not required"
        ]
        lax_strict = active_ruleset(rules=status_checks_rules(REQUIRED_CHECK, False))
        assert evaluate([lax_strict]) == [
            "required status checks are not strict (branch must be up to date)"
        ]

    def test_bypass_actors_are_reported(self) -> None:
        bypassed = active_ruleset(
            bypass_actors=[{"actor_id": 1, "bypass_mode": "always"}]
        )
        assert evaluate([bypassed]) == [
            "bypass actors configured: actor_id=1 mode=always; "
            "removing them requires a deliberate probe update"
        ]

    def test_malformed_rules_are_reported(self) -> None:
        malformed = active_ruleset(rules=status_checks_rules(None, True))
        assert evaluate([malformed]) == [
            f"required status check {REQUIRED_CHECK!r} is not required"
        ]


class CliTests(unittest.TestCase):
    def test_check_reads_payload_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            payload = Path(temporary) / "rulesets.json"
            payload.write_text(json.dumps([active_ruleset()]), encoding="utf-8")
            completed = run_check(payload)
            assert completed.returncode == 0, completed.stderr

    def test_check_fails_closed_on_violating_payload(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            payload = Path(temporary) / "rulesets.json"
            payload.write_text(json.dumps([]), encoding="utf-8")
            completed = run_check(payload)
            assert completed.returncode == 1
            assert "no active branch ruleset" in completed.stderr


def test_required_check_name_matches_ci_workflow() -> None:
    workflow = yaml.safe_load((REPO / ".github/workflows/ci.yml").read_text())
    assert workflow["jobs"]["ci-gate"]["name"] == REQUIRED_CHECK
