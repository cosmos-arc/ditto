from __future__ import annotations

import json
import tempfile
import tomllib
import unittest
from pathlib import Path

from scripts.agent_harness.sync_skills import compare_trees
from scripts.agent_harness.validate import parse_frontmatter, validate

ROOT = Path(__file__).resolve().parents[3]


class SkillMirrorTests(unittest.TestCase):
    def test_missing_and_drifted_skill_files_fail_comparison(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            mirror = root / "mirror"
            source.mkdir()
            mirror.mkdir()
            (source / "SKILL.md").write_text("canonical\n", encoding="utf-8")

            assert compare_trees(source, mirror) == [
                "missing from Claude mirror: SKILL.md"
            ]

            (mirror / "SKILL.md").write_text("drift\n", encoding="utf-8")
            assert compare_trees(source, mirror) == ["content drift: SKILL.md"]

    def test_equal_skill_trees_pass(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            mirror = root / "mirror"
            source.mkdir()
            mirror.mkdir()
            for tree in (source, mirror):
                (tree / "SKILL.md").write_text("same\n", encoding="utf-8")
            assert compare_trees(source, mirror) == []


class FormatFixtureTests(unittest.TestCase):
    def test_frontmatter_json_and_toml_fixtures(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            skill = root / "SKILL.md"
            skill.write_text(
                (
                    "---\n"
                    "name: fixture-skill\n"
                    "description: fixture trigger\n"
                    "---\n\n"
                    "# Fixture\n"
                ),
                encoding="utf-8",
            )
            assert parse_frontmatter(skill) == {
                "name": "fixture-skill",
                "description": "fixture trigger",
            }
            assert json.loads('{"hooks": {}}') == {"hooks": {}}
            parsed = tomllib.loads('[tasks]\ncheck = "true"\n')
            assert parsed["tasks"]["check"] == "true"

    def test_repository_harness_configs_are_valid(self) -> None:
        assert validate() == []

    def test_codex_post_tool_hook_covers_apply_patch(self) -> None:
        config = json.loads(
            (ROOT / ".codex" / "hooks.json").read_text(encoding="utf-8")
        )
        matchers = {
            entry.get("matcher", "") for entry in config["hooks"]["PostToolUse"]
        }

        assert any("apply_patch" in matcher.split("|") for matcher in matchers)


if __name__ == "__main__":
    unittest.main()
