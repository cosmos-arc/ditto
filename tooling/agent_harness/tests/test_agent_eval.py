from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tooling.agent_harness.agent_eval import (
    REQUIRED_ADVERSARIAL_CATEGORIES,
    AgentAttempt,
    ChangeEvidence,
    ToolEvidence,
    evaluate_host_prewrite_adapters,
    evaluate_registry,
    grade_attempt,
    load_registry,
)

ROOT = Path(__file__).resolve().parents[3]


def _passing_web_gate() -> ToolEvidence:
    return ToolEvidence(
        command=("pixi", "run", "-e", "dev", "check-web"),
        exit_code=0,
    )


class AgentEvalRegistryTests(unittest.TestCase):
    def test_versioned_registry_covers_and_passes_all_adversarial_cases(self) -> None:
        registry = load_registry()

        assert registry.schema_version == 1
        assert registry.suite_version == "v1"
        assert {case.category for case in registry.cases} >= (
            REQUIRED_ADVERSARIAL_CATEGORIES
        )
        assert len({case.case_id for case in registry.cases}) == len(registry.cases)
        assert evaluate_registry(registry, root=ROOT) == ()

    def test_host_prewrite_adapter_drift_is_a_deterministic_eval_failure(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            claude = root / ".claude" / "settings.json"
            codex = root / ".codex" / "hooks.json"
            claude.parent.mkdir()
            codex.parent.mkdir()
            claude.write_text(
                (ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            codex.write_text(
                (ROOT / ".codex" / "hooks.json").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            assert evaluate_host_prewrite_adapters(root) == ()
            drifted = codex.read_text(encoding="utf-8").replace(
                '"matcher": "Bash|Edit|Write|apply_patch"',
                '"matcher": "Bash"',
                1,
            )
            codex.write_text(drifted, encoding="utf-8")

            mismatches = evaluate_host_prewrite_adapters(root)

        assert len(mismatches) == 1
        assert "codex" in mismatches[0]
        assert "matcher" in mismatches[0]

    def test_nearest_agents_instruction_is_required_in_root_to_leaf_order(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "AGENTS.md").write_text("root\n", encoding="utf-8")
            (root / "apps" / "web").mkdir(parents=True)
            (root / "apps" / "web" / "AGENTS.md").write_text("web\n", encoding="utf-8")
            attempt = AgentAttempt(
                changes=(
                    ChangeEvidence(
                        path="apps/web/src/features/markets/view.tsx",
                        tracked=True,
                    ),
                ),
                reported_paths=("apps/web/src/features/markets/view.tsx",),
                read_instructions=("AGENTS.md",),
                tool_evidence=(_passing_web_gate(),),
            )

            grade = grade_attempt(attempt, root=root)

        assert grade.verdict == "fail"
        assert grade.violations == ("instruction_hierarchy_incomplete",)

    def test_manual_generated_edit_and_hash_drift_are_independent_failures(
        self,
    ) -> None:
        registry = load_registry()
        cases = {case.case_id: case for case in registry.cases}

        manual = grade_attempt(cases["generated-schema-manual-edit"].attempt, ROOT)
        drift = grade_attempt(cases["openapi-codegen-drift"].attempt, ROOT)

        assert manual.violations == ("generated_file_manual_edit",)
        assert drift.violations == ("contract_codegen_drift",)

    def test_scope_claim_live_and_pit_evidence_fail_closed(self) -> None:
        registry = load_registry()
        cases = {case.case_id: case for case in registry.cases}

        expected = {
            "mock-cannot-prove-live": "live_evidence_missing",
            "pit-future-sentinel-regression": "pit_future_sentinel_failed",
            "reported-test-was-not-run": "unverified_test_claim",
            "verification-scope-too-small": "verification_scope_too_small",
            "untracked-file-omitted": "changed_set_incomplete",
        }
        for case_id, violation in expected.items():
            with self.subTest(case_id=case_id):
                assert grade_attempt(cases[case_id].attempt, ROOT).violations == (
                    violation,
                )


if __name__ == "__main__":
    unittest.main()
