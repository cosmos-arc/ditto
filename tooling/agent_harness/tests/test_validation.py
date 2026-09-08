from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest.mock import patch

import tooling.agent_harness.validate as validate_module
from tooling.agent_harness.sync_skills import TreeEntry, compare_trees
from tooling.agent_harness.validate import (
    load_skill_registry,
    parse_frontmatter,
    validate,
)

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

    def test_file_kind_and_executable_mode_must_match(self) -> None:
        source = Path("source")
        mirror = Path("mirror")
        symlink = {"SKILL.md": TreeEntry("symlink", b"target", False)}
        regular = {"SKILL.md": TreeEntry("file", b"same", False)}
        executable = {"SKILL.md": TreeEntry("file", b"same", True)}

        with patch(
            "tooling.agent_harness.sync_skills.tree_files",
            side_effect=(symlink, regular),
        ):
            assert compare_trees(source, mirror) == ["kind drift: SKILL.md"]
        with patch(
            "tooling.agent_harness.sync_skills.tree_files",
            side_effect=(executable, regular),
        ):
            assert compare_trees(source, mirror) == ["executable mode drift: SKILL.md"]


class SkillRegistryTests(unittest.TestCase):
    def test_registry_is_the_skill_inventory_source_of_truth(self) -> None:
        registry = load_skill_registry(ROOT / ".agents" / "skills" / "registry.toml")

        discovered = {
            path.parent.name for path in (ROOT / ".agents/skills").glob("*/SKILL.md")
        }
        assert set(registry) == discovered
        assert registry["ditto-pit-safety"] == "backend"


class FormatFixtureTests(unittest.TestCase):
    def test_cli_accepts_supported_skill_and_host_extensions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for relative in (
                "AGENTS.md",
                "CLAUDE.md",
                "pyproject.toml",
                "bunfig.toml",
                "package.json",
                "apps/web/package.json",
                ".claude/settings.json",
                ".codex/hooks.json",
                ".zcode/config.json",
            ):
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / relative, target)
            for relative in (
                "tooling/agent_harness",
                ".agents/skills",
                ".claude/skills",
            ):
                shutil.copytree(ROOT / relative, root / relative)
            for path in [
                *(ROOT / "packages").glob("*/AGENTS.md"),
                ROOT / "apps/backend/AGENTS.md",
                ROOT / "apps/web/AGENTS.md",
                ROOT / "contracts/AGENTS.md",
            ]:
                target = root / path.relative_to(ROOT)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, target)
                shutil.copyfile(
                    path.with_name("CLAUDE.md"), target.with_name("CLAUDE.md")
                )
            for tree in (".agents", ".claude"):
                skill = root / tree / "skills/ditto-pit-safety/SKILL.md"
                skill.write_text(
                    skill.read_text().replace(
                        "name: ditto-pit-safety",
                        "name: ditto-pit-safety\nlicense: MIT\n"
                        "metadata:\n  revision: 1\n  tags:\n    - pit",
                    )
                )
            for tree in (".agents", ".claude"):
                (root / tree / "skills/ditto-pit-safety/agents/openai.yaml").unlink()
            settings = root / ".claude/settings.json"
            config = json.loads(settings.read_text())
            config["enabledPlugins"]["another-supported-plugin@example"] = True
            # Splitting the same required event coverage is a valid host composition.
            entries = config["hooks"]["PreToolUse"]
            original = entries.pop()
            for matcher in original["matcher"].split("|"):
                entries.append({**original, "matcher": matcher})
            settings.write_text(json.dumps(config))
            research = root / "docs/research/skill-history.md"
            research.parent.mkdir(parents=True)
            research.write_text("Historical discussion of super" + "powers: usage.\n")
            result = subprocess.run(
                [sys.executable, str(root / "tooling/agent_harness/validate.py")],
                cwd=root,
                capture_output=True,
                text=True,
                check=False,
            )
            assert result.returncode == 0, result.stdout + result.stderr
            # Actual instruction sources remain subject to legacy dependency checks.
            instructions = root / "AGENTS.md"
            original_instructions = instructions.read_text()
            instructions.write_text(
                original_instructions + "\nUse super" + "powers:run\n"
            )
            legacy = subprocess.run(
                [sys.executable, str(root / "tooling/agent_harness/validate.py")],
                cwd=root,
                capture_output=True,
                text=True,
                check=False,
            )
            assert legacy.returncode != 0
            assert "legacy workflow dependency in AGENTS.md" in legacy.stdout
            instructions.write_text(original_instructions)
            # A prose-only skill edit must fail the same CLI used by the PR job.
            skill = root / ".agents/skills/ditto-pit-safety/SKILL.md"
            original_skill = skill.read_text()
            skill.write_text(original_skill + "\nA new PIT instruction.\n")
            drifted = subprocess.run(
                [sys.executable, str(root / "tooling/agent_harness/validate.py")],
                cwd=root,
                capture_output=True,
                text=True,
                check=False,
            )
            assert drifted.returncode != 0
            assert "content drift" in drifted.stdout + drifted.stderr
            skill.write_text(original_skill)
            restored = subprocess.run(
                [sys.executable, str(root / "tooling/agent_harness/validate.py")],
                cwd=root,
                capture_output=True,
                text=True,
                check=False,
            )
            assert restored.returncode == 0, restored.stdout + restored.stderr
            for relative in (
                ".codex/hooks.json",
                ".claude/settings.json",
                ".zcode/config.json",
            ):
                config_path = root / relative
                original_text = config_path.read_text()
                broken = json.loads(original_text)
                container = broken["hooks"]
                if relative == ".zcode/config.json":
                    container = container["events"]
                for entry in container["PreToolUse"]:
                    for hook in entry["hooks"]:
                        hook["command"] = hook["command"].replace('"', "'")
                config_path.write_text(json.dumps(broken))
                rejected = subprocess.run(
                    [sys.executable, str(root / "tooling/agent_harness/validate.py")],
                    cwd=root,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                assert rejected.returncode != 0, (
                    "single quotes disable required shell expansion"
                )
                config_path.write_text(original_text)

    def test_root_workspace_manifest_is_not_ignored(self) -> None:
        result = subprocess.run(
            ["git", "check-ignore", "--no-index", "package.json"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 1, result.stdout

    def test_legacy_scan_uses_tracked_and_nonignored_untracked_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            (root / ".gitignore").write_text("build/\nnode_modules/\n")
            for relative in (
                "build/results.json",
                "apps/web/node_modules/lib.js",
                "new.py",
                "tracked.py",
            ):
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("super" + "powers: forbidden")
            subprocess.run(["git", "add", "tracked.py"], cwd=root, check=True)
            with patch.object(validate_module, "ROOT", root):
                errors: list[str] = []
                validate_module._validate_legacy_content(errors)
            assert sorted(errors) == [
                "legacy workflow dependency in new.py",
                "legacy workflow dependency in tracked.py",
            ]

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

    def test_all_hosts_pre_tool_hooks_cover_structured_writes(self) -> None:
        expected = {
            "claude": {"Bash", "Edit", "Write"},
            "codex": {"Bash", "Edit", "Write", "apply_patch"},
            "zcode": {"Bash", "Edit", "Write"},
        }
        paths = {
            "claude": ROOT / ".claude" / "settings.json",
            "codex": ROOT / ".codex" / "hooks.json",
            "zcode": ROOT / ".zcode" / "config.json",
        }

        for host, path in paths.items():
            with self.subTest(host=host):
                config = json.loads(path.read_text(encoding="utf-8"))
                entries = validate_module._host_event_entries(
                    config["hooks"], host, "PreToolUse"
                )
                assert isinstance(entries, list)
                covered = {
                    tool
                    for entry in entries
                    if any(
                        f"--host {host} --event pre-tool" in hook["command"]
                        for hook in entry["hooks"]
                    )
                    for tool in entry["matcher"].split("|")
                }
                assert expected[host] <= covered

    def test_zcode_hook_contract_requires_enabled_and_nested_events(self) -> None:
        command = validate_module._HOST_COMMAND_BASE["zcode"]
        config: dict[str, object] = {
            "hooks": {
                "events": {
                    "PreToolUse": [
                        {
                            "matcher": "Bash|Edit|Write",
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": command
                                    + " --host zcode --event pre-tool",
                                    "timeout": 10,
                                }
                            ],
                        }
                    ],
                    "PostToolUse": [
                        {
                            "matcher": "Edit|Write",
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": command
                                    + " --host zcode --event post-tool",
                                    "timeout": 10,
                                }
                            ],
                        }
                    ],
                    "Stop": [
                        {
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": command + " --host zcode --event stop",
                                    "timeout": 3,
                                }
                            ]
                        }
                    ],
                }
            }
        }

        disabled: list[str] = []
        validate_module._validate_host_hook_contract(config, "zcode", disabled)
        assert any("enabled" in error for error in disabled)

        hooks = config["hooks"]
        assert isinstance(hooks, dict)
        hooks["enabled"] = True
        enabled: list[str] = []
        validate_module._validate_host_hook_contract(config, "zcode", enabled)
        assert enabled == []

    def test_inert_host_hook_entries_are_rejected(self) -> None:
        config: dict[str, object] = {
            "hooks": {
                "PreToolUse": [],
                "PostToolUse": [
                    {
                        "matcher": "Edit|Write|apply_patch",
                        "hooks": [{"type": "command", "command": "", "timeout": 0}],
                    }
                ],
                "Stop": [],
            }
        }
        errors: list[str] = []

        validate_module._validate_host_hook_contract(config, "codex", errors)

        assert any("PreToolUse" in error for error in errors)
        assert any("PostToolUse" in error for error in errors)
        assert any("Stop" in error for error in errors)

    def test_descriptive_text_cannot_masquerade_as_a_hook_command(self) -> None:
        config = json.loads(
            (ROOT / ".codex" / "hooks.json").read_text(encoding="utf-8")
        )
        config["hooks"]["PostToolUse"][0]["hooks"][0]["command"] = (
            "echo tooling/agent_harness/hook.py --host codex --event post-tool"
        )
        errors: list[str] = []

        validate_module._validate_host_hook_contract(config, "codex", errors)

        assert any("PostToolUse" in error for error in errors)

    def test_capability_instruction_inventory_uses_exact_names(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            packages = root / "packages"
            packages.mkdir()
            for index in range(12):
                package = packages / f"wrong-{index}"
                package.mkdir()
                (package / "AGENTS.md").write_text("fixture\n", encoding="utf-8")
            errors: list[str] = []

            validate_module._validate_capability_inventory(root, errors)

            assert any("missing capability instructions" in error for error in errors)
            assert any(
                "unexpected capability instructions" in error for error in errors
            )

    def test_capability_inventory_rejects_package_without_instructions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            packages = root / "packages"
            for name in validate_module.EXPECTED_CAPABILITIES:
                package = packages / name
                package.mkdir(parents=True)
                (package / "AGENTS.md").write_text("fixture\n", encoding="utf-8")
            rogue = packages / "rogue"
            rogue.mkdir()
            (rogue / "pyproject.toml").write_text(
                '[project]\nname = "rogue"\n', encoding="utf-8"
            )
            errors: list[str] = []

            validate_module._validate_capability_inventory(root, errors)

            assert any("rogue" in error for error in errors)

    def test_bun_only_policy_finds_nonignored_manager_files_anywhere(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "apps" / "web").mkdir(parents=True)
            (root / "apps" / "web" / "pnpm-workspace.yaml").write_text(
                "packages: []\n", encoding="utf-8"
            )
            errors: list[str] = []

            validate_module._validate_bun_only(root, errors)

            assert errors == [
                "forbidden package-manager file: apps/web/pnpm-workspace.yaml"
            ]

    def test_bun_only_policy_rejects_nested_or_legacy_bun_locks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "apps" / "web").mkdir(parents=True)
            (root / "apps" / "web" / "bun.lock").write_text(
                "fixture\n", encoding="utf-8"
            )
            (root / "bun.lockb").write_text("fixture\n", encoding="utf-8")
            errors: list[str] = []

            validate_module._validate_bun_only(root, errors)

            assert errors == [
                "forbidden package-manager file: apps/web/bun.lock",
                "forbidden package-manager file: bun.lockb",
            ]

    def test_bun_only_git_scan_excludes_ignored_untracked_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            (root / ".gitignore").write_text("ignored/\n", encoding="utf-8")
            (root / "ignored").mkdir()
            (root / "ignored" / "pnpm-lock.yaml").write_text(
                "ignored\n", encoding="utf-8"
            )
            errors: list[str] = []

            validate_module._validate_bun_only(root, errors)

            assert errors == []

    def test_bun_only_git_scan_keeps_unstaged_deletions_in_index_scope(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            forbidden = root / "package-lock.json"
            forbidden.write_text("{}\n", encoding="utf-8")
            subprocess.run(["git", "add", "package-lock.json"], cwd=root, check=True)
            forbidden.unlink()
            errors: list[str] = []

            validate_module._validate_bun_only(root, errors)

            assert errors == ["forbidden package-manager file: package-lock.json"]
            subprocess.run(["git", "add", "-u"], cwd=root, check=True)
            errors.clear()
            validate_module._validate_bun_only(root, errors)
            assert errors == []


if __name__ == "__main__":
    unittest.main()
