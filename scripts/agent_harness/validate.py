#!/usr/bin/env python3
"""Validate Ditto's slim dual-host agent harness."""

from __future__ import annotations

import json
import re
import sys
import tomllib
from pathlib import Path

try:
    from .sync_skills import compare_trees
except ImportError:  # Direct script execution.
    from sync_skills import compare_trees


ROOT = Path(__file__).resolve().parents[2]
EXPECTED_SKILLS = {
    "ditto-architecture-change",
    "ditto-change-review",
    "ditto-pit-safety",
    "ditto-quality-eval",
    "ditto-test-first",
}
LEGACY_PATHS = (
    ".claude/rules",
    ".claude/commands",
    ".claude/checklists",
    ".factory",
)
BANNED_WORKFLOW = re.compile(
    "|".join(
        (
            "super" + "powers:",
            "python-" + "development:",
            "unit-" + "testing:",
        )
    )
)
MAX_TEXT_BYTES = 2_000_000
ROOT_AGENTS_MAX_LINES = 150
ROOT_CLAUDE_MAX_LINES = 10
PACKAGE_COUNT = 13
PACKAGE_AGENTS_MAX_LINES = 60
PACKAGE_CLAUDE_MAX_LINES = 3
SKILL_MAX_LINES = 120
HOOK_EVENTS = {"PreToolUse", "PostToolUse", "Stop"}


def parse_frontmatter(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not lines or lines[0] != "---":
        raise ValueError("missing opening frontmatter delimiter")
    try:
        end = lines.index("---", 1)
    except ValueError as error:
        raise ValueError("missing closing frontmatter delimiter") from error
    values: dict[str, str] = {}
    for line in lines[1:end]:
        if not line.strip():
            continue
        if ":" not in line:
            raise ValueError(f"invalid frontmatter line: {line}")
        key, value = line.split(":", 1)
        values[key.strip()] = value.strip().strip('"')
    return values


def _line_count(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())


def _text_files() -> list[Path]:
    excluded_roots = {".git", ".pixi", ".cache", "node_modules", "artifacts"}
    files: list[Path] = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.stat().st_size > MAX_TEXT_BYTES:
            continue
        relative = path.relative_to(ROOT)
        if relative.parts and relative.parts[0] in excluded_roots:
            continue
        if (
            relative.parts
            and relative.parts[0] == "docs"
            and "archive" in relative.parts[:3]
        ):
            continue
        files.append(path)
    return files


def _validate_instruction_files(errors: list[str]) -> None:
    if _line_count(ROOT / "AGENTS.md") > ROOT_AGENTS_MAX_LINES:
        errors.append("root AGENTS.md exceeds 150 lines")
    root_wrapper = (ROOT / "CLAUDE.md").read_text(encoding="utf-8").strip()
    if (
        root_wrapper != "@AGENTS.md"
        or _line_count(ROOT / "CLAUDE.md") > ROOT_CLAUDE_MAX_LINES
    ):
        errors.append("root CLAUDE.md must be a thin @AGENTS.md wrapper")

    packages = sorted(path.parent for path in (ROOT / "packages").glob("*/AGENTS.md"))
    if len(packages) != PACKAGE_COUNT:
        errors.append(
            f"expected {PACKAGE_COUNT} package AGENTS.md files, found {len(packages)}"
        )
    for package in packages:
        agents = package / "AGENTS.md"
        wrapper = package / "CLAUDE.md"
        if _line_count(agents) > PACKAGE_AGENTS_MAX_LINES:
            errors.append(f"{agents.relative_to(ROOT)} exceeds 60 lines")
        if (
            not wrapper.is_file()
            or wrapper.read_text(encoding="utf-8").strip() != "@AGENTS.md"
        ):
            errors.append(f"{wrapper.relative_to(ROOT)} is not an @AGENTS.md wrapper")
        elif _line_count(wrapper) > PACKAGE_CLAUDE_MAX_LINES:
            errors.append(f"{wrapper.relative_to(ROOT)} exceeds 3 lines")


def _skill_names(source: Path) -> set[str]:
    if not source.is_dir():
        return set()
    return {path.name for path in source.iterdir() if path.is_dir()}


def _validate_skill(name: str, source: Path, errors: list[str]) -> None:
    skill = source / name
    skill_file = skill / "SKILL.md"
    metadata_file = skill / "agents" / "openai.yaml"
    if not skill_file.is_file():
        errors.append(f"{name}: missing SKILL.md")
        return
    try:
        frontmatter = parse_frontmatter(skill_file)
    except ValueError as error:
        errors.append(f"{name}: {error}")
        return
    if set(frontmatter) != {"name", "description"}:
        errors.append(f"{name}: frontmatter must contain only name and description")
    if frontmatter.get("name") != name:
        errors.append(f"{name}: frontmatter name does not match directory")
    if not frontmatter.get("description"):
        errors.append(f"{name}: description is empty")
    if _line_count(skill_file) > SKILL_MAX_LINES:
        errors.append(f"{name}: SKILL.md exceeds 120 lines")
    if not metadata_file.is_file():
        errors.append(f"{name}: missing agents/openai.yaml")
        return
    metadata = metadata_file.read_text(encoding="utf-8")
    if "$" + name not in metadata:
        errors.append(f"{name}: openai.yaml default prompt must mention $" + name)


def _validate_skills(errors: list[str]) -> None:
    source = ROOT / ".agents" / "skills"
    skill_names = _skill_names(source)
    if skill_names != EXPECTED_SKILLS:
        errors.append(
            f"expected skills {sorted(EXPECTED_SKILLS)}, found {sorted(skill_names)}"
        )
    for name in sorted(skill_names):
        _validate_skill(name, source, errors)

    errors.extend(compare_trees())


def _validate_legacy_content(errors: list[str]) -> None:
    for relative in LEGACY_PATHS:
        if (ROOT / relative).exists():
            errors.append(f"legacy harness path still exists: {relative}")

    for path in _text_files():
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if BANNED_WORKFLOW.search(text):
            errors.append(f"legacy workflow dependency in {path.relative_to(ROOT)}")


def _load_json(path: Path, errors: list[str]) -> dict[str, object] | None:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as error:
        errors.append(f"invalid or missing JSON {path.relative_to(ROOT)}: {error}")
        return None
    if not isinstance(loaded, dict):
        errors.append(f"JSON root must be an object: {path.relative_to(ROOT)}")
        return None
    return loaded


def _validate_hook_target(path: Path, errors: list[str]) -> None:
    if path.is_file() and "scripts/agent_harness/hook.py" not in path.read_text(
        encoding="utf-8"
    ):
        errors.append(f"{path.relative_to(ROOT)} does not target the shared hook")


def _event_matchers(config: dict[str, object], event: str) -> set[str]:
    hooks = config.get("hooks")
    if not isinstance(hooks, dict):
        return set()
    entries = hooks.get(event)
    if not isinstance(entries, list):
        return set()
    return {
        matcher
        for entry in entries
        if isinstance(entry, dict)
        and isinstance((matcher := entry.get("matcher")), str)
    }


def _validate_host_configs(errors: list[str]) -> None:
    settings_path = ROOT / ".claude" / "settings.json"
    codex_path = ROOT / ".codex" / "hooks.json"
    settings = _load_json(settings_path, errors)
    codex = _load_json(codex_path, errors)

    if settings is not None:
        plugins = settings.get("enabledPlugins")
        enabled = (
            {name for name, value in plugins.items() if value}
            if isinstance(plugins, dict)
            else set()
        )
        if enabled != {"pyright-lsp@claude-plugins-official"}:
            errors.append(
                f"Claude must enable only pyright-lsp, found {sorted(enabled)}"
            )
        permissions = settings.get("permissions")
        if (
            not isinstance(permissions, dict)
            or permissions.get("defaultMode") != "default"
        ):
            errors.append("Claude permissions.defaultMode must be default")
        hooks = settings.get("hooks")
        if not isinstance(hooks, dict) or set(hooks) != HOOK_EVENTS:
            errors.append(
                "Claude settings must define PreToolUse, PostToolUse, and Stop hooks"
            )

    if codex is not None:
        hooks = codex.get("hooks")
        if not isinstance(hooks, dict) or set(hooks) != HOOK_EVENTS:
            errors.append("Codex hooks must define PreToolUse, PostToolUse, and Stop")
        post_matchers = _event_matchers(codex, "PostToolUse")
        if not any("apply_patch" in matcher.split("|") for matcher in post_matchers):
            errors.append("Codex PostToolUse must match apply_patch")

    _validate_hook_target(settings_path, errors)
    _validate_hook_target(codex_path, errors)
    hook_script = ROOT / "scripts" / "agent_harness" / "hook.py"
    if not hook_script.is_file():
        errors.append("shared hook target is missing")


def _validate_toml(errors: list[str]) -> None:
    for path in (ROOT / "pixi.toml", ROOT / "pyproject.toml"):
        try:
            tomllib.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, tomllib.TOMLDecodeError) as error:
            errors.append(f"invalid TOML {path.relative_to(ROOT)}: {error}")


def validate() -> list[str]:
    errors: list[str] = []
    _validate_instruction_files(errors)
    _validate_skills(errors)
    _validate_legacy_content(errors)
    _validate_host_configs(errors)
    _validate_toml(errors)
    return errors


def main() -> int:
    errors = validate()
    if errors:
        print("Harness validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("Harness validation passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
