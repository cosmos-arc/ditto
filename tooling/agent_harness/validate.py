#!/usr/bin/env python3
"""Validate Ditto's canonical, polyglot multi-host agent harness."""

from __future__ import annotations

import json
import re
import sys
import tomllib
from pathlib import Path

import yaml

try:
    from .repository_policy import forbidden_package_manager_paths, repository_paths
    from .sync_skills import compare_trees
except ImportError:  # Direct script execution.
    from repository_policy import forbidden_package_manager_paths, repository_paths
    from sync_skills import compare_trees


ROOT = Path(__file__).resolve().parents[2]
SKILL_REGISTRY = ROOT / ".agents" / "skills" / "registry.toml"
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
EXPECTED_CAPABILITIES = frozenset(
    {
        "agent",
        "analysis",
        "application",
        "backtest",
        "data",
        "execution",
        "features",
        "kernel",
        "platform",
        "portfolio",
        "risk",
        "strategy",
    }
)
HOOK_EVENTS = {"PreToolUse", "PostToolUse", "Stop"}
_HOOK_EVENT_ARGUMENTS = {
    "PreToolUse": "pre-tool",
    "PostToolUse": "post-tool",
    "Stop": "stop",
}
_HOST_MATCHERS = {
    "claude": {
        "PreToolUse": {"Bash", "Edit", "Write"},
        "PostToolUse": {"Edit", "Write"},
        "Stop": set(),
    },
    "codex": {
        "PreToolUse": {"Bash", "Edit", "Write", "apply_patch"},
        "PostToolUse": {"Edit", "Write", "apply_patch"},
        "Stop": set(),
    },
    "zcode": {
        "PreToolUse": {"Bash", "Edit", "Write"},
        "PostToolUse": {"Edit", "Write"},
        "Stop": set(),
    },
}
_HOST_COMMAND_BASE = {
    "claude": 'python3 "$CLAUDE_PROJECT_DIR/tooling/agent_harness/hook.py"',
    "codex": (
        '/usr/bin/env python3 "$(git rev-parse --show-toplevel)/'
        + 'tooling/agent_harness/hook.py"'
    ),
    "zcode": 'python3 "${ZCODE_PROJECT_DIR}/tooling/agent_harness/hook.py"',
}


def parse_frontmatter(path: Path) -> dict[str, object]:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not lines or lines[0] != "---":
        raise ValueError("missing opening frontmatter delimiter")
    try:
        end = lines.index("---", 1)
    except ValueError as error:
        raise ValueError("missing closing frontmatter delimiter") from error
    try:
        values = yaml.safe_load("\n".join(lines[1:end]))
    except yaml.YAMLError as error:
        raise ValueError(f"invalid YAML frontmatter: {error}") from error
    if not isinstance(values, dict):
        raise ValueError("frontmatter must be a mapping")
    return values


def _validate_local_instruction(directory: Path, errors: list[str]) -> None:
    agents = directory / "AGENTS.md"
    wrapper = directory / "CLAUDE.md"
    if not agents.is_file():
        errors.append(f"missing local instructions: {agents.relative_to(ROOT)}")
    if (
        not wrapper.is_file()
        or wrapper.read_text(encoding="utf-8").strip() != "@AGENTS.md"
    ):
        errors.append(f"{wrapper.relative_to(ROOT)} is not an @AGENTS.md wrapper")


def _text_files() -> list[Path]:
    files: list[Path] = []
    for name in sorted(repository_paths(ROOT)):
        path = ROOT / name
        if (
            path.is_symlink()
            or not path.is_file()
            or path.stat().st_size > MAX_TEXT_BYTES
        ):
            continue
        relative = path.relative_to(ROOT)
        if {"archive", "archieve"}.intersection(relative.parts):
            continue
        files.append(path)
    return files


def _validate_instruction_files(errors: list[str]) -> None:
    root_wrapper = (ROOT / "CLAUDE.md").read_text(encoding="utf-8").strip()
    if root_wrapper != "@AGENTS.md":
        errors.append("root CLAUDE.md must be a thin @AGENTS.md wrapper")

    _validate_capability_inventory(ROOT, errors)
    packages = [
        ROOT / "packages" / name
        for name in sorted(EXPECTED_CAPABILITIES)
        if (ROOT / "packages" / name / "AGENTS.md").is_file()
    ]
    for package in packages:
        wrapper = package / "CLAUDE.md"
        if (
            not wrapper.is_file()
            or wrapper.read_text(encoding="utf-8").strip() != "@AGENTS.md"
        ):
            errors.append(f"{wrapper.relative_to(ROOT)} is not an @AGENTS.md wrapper")

    local_rules = (
        ROOT / "apps" / "backend",
        ROOT / "apps" / "web",
        ROOT / "contracts",
    )
    for directory in local_rules:
        _validate_local_instruction(directory, errors)


def _validate_capability_inventory(root: Path, errors: list[str]) -> None:
    packages_root = root / "packages"
    instruction_names = {path.parent.name for path in packages_root.glob("*/AGENTS.md")}
    package_names = {
        path.name
        for path in packages_root.iterdir()
        if path.is_dir()
        and ((path / "pyproject.toml").is_file() or (path / "src").is_dir())
    }
    missing = sorted(EXPECTED_CAPABILITIES - instruction_names)
    unexpected_instructions = sorted(instruction_names - EXPECTED_CAPABILITIES)
    unexpected_packages = sorted(package_names - EXPECTED_CAPABILITIES)
    if missing:
        errors.append(f"missing capability instructions: {missing}")
    if unexpected_instructions:
        errors.append(f"unexpected capability instructions: {unexpected_instructions}")
    if unexpected_packages:
        errors.append(f"unexpected capability packages: {unexpected_packages}")


def _skill_names(source: Path) -> set[str]:
    if not source.is_dir():
        return set()
    return {path.name for path in source.iterdir() if path.is_dir()}


def load_skill_registry(path: Path = SKILL_REGISTRY) -> dict[str, str]:
    """Load the declarative canonical skill inventory."""
    loaded = tomllib.loads(path.read_text(encoding="utf-8"))
    if loaded.get("schema_version") != 1:
        raise ValueError("skill registry schema_version must be 1")
    entries = loaded.get("skills")
    if not isinstance(entries, list):
        raise ValueError("skill registry must contain [[skills]] entries")

    registry: dict[str, str] = {}
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict) or set(entry) != {"name", "owner"}:
            raise ValueError(
                f"skill registry entry {index} must contain name and owner"
            )
        name = entry.get("name")
        owner = entry.get("owner")
        if not isinstance(name, str) or not name:
            raise ValueError(f"skill registry entry {index} has an invalid name")
        if owner not in {"backend", "web", "cross-stack"}:
            raise ValueError(f"skill registry entry {name} has an invalid owner")
        if name in registry:
            raise ValueError(f"duplicate skill registry entry: {name}")
        registry[name] = owner
    return registry


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
    if frontmatter.get("name") != name:
        errors.append(f"{name}: frontmatter name does not match directory")
    description = frontmatter.get("description")
    if not isinstance(description, str) or not description.strip():
        errors.append(f"{name}: description must be non-empty text")
    if metadata_file.is_file():
        try:
            metadata = yaml.safe_load(metadata_file.read_text(encoding="utf-8"))
            if not isinstance(metadata, dict):
                errors.append(f"{name}: openai.yaml must be a mapping")
        except yaml.YAMLError as error:
            errors.append(f"{name}: invalid openai.yaml: {error}")


def _validate_skills(errors: list[str]) -> None:
    source = ROOT / ".agents" / "skills"
    skill_names = _skill_names(source)
    try:
        expected_skills = set(load_skill_registry())
    except (FileNotFoundError, tomllib.TOMLDecodeError, ValueError) as error:
        errors.append(f"invalid skill registry: {error}")
        expected_skills = set()
    if skill_names != expected_skills:
        errors.append(
            f"expected skills {sorted(expected_skills)}, found {sorted(skill_names)}"
        )
    for name in sorted(skill_names):
        _validate_skill(name, source, errors)

    errors.extend(compare_trees())


def _validate_legacy_content(errors: list[str]) -> None:
    for relative in LEGACY_PATHS:
        if (ROOT / relative).exists():
            errors.append(f"legacy harness path still exists: {relative}")

    for path in _text_files():
        relative = path.relative_to(ROOT)
        # Reading material may discuss previous workflows. Only instruction
        # sources, host configuration and executable inputs declare dependencies.
        if (
            path.suffix in {".md", ".rst"}
            and path.name not in {"AGENTS.md", "CLAUDE.md", "SKILL.md"}
            and relative.parts[0] not in {".agents", ".claude", ".codex", ".zcode"}
            and not path.stat().st_mode & 0o111
        ):
            continue
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
    if path.is_file() and "tooling/agent_harness/hook.py" not in path.read_text(
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


def _host_event_entries(hooks: dict[object, object], host: str, event: str) -> object:
    """Resolve per-host event lists; ZCode nests them under hooks.events."""
    container: object = hooks.get("events") if host == "zcode" else hooks
    if not isinstance(container, dict):
        return None
    return container.get(event)


def _validate_host_event(
    hooks: dict[object, object], host: str, event: str, errors: list[str]
) -> None:
    entries = _host_event_entries(hooks, host, event)
    if not isinstance(entries, list) or not entries:
        errors.append(f"{host} {event} requires an active shared hook")
        return
    expected_command = (
        _HOST_COMMAND_BASE[host]
        + f" --host {host} --event {_HOOK_EVENT_ARGUMENTS[event]}"
    )
    covered: set[str] = set()
    active = False
    for entry in entries:
        if not isinstance(entry, dict):
            errors.append(f"{host} {event} hook entry must be an object")
            continue
        matcher = entry.get("matcher", "")
        commands = entry.get("hooks")
        if not isinstance(matcher, str) or not isinstance(commands, list):
            errors.append(f"{host} {event} has invalid matcher or hooks")
            continue
        for command_hook in commands:
            if not isinstance(command_hook, dict):
                errors.append(f"{host} {event} hook must be an object")
                continue
            command = command_hook.get("command")
            if (
                command_hook.get("type") != "command"
                or not isinstance(command, str)
                or command != expected_command
            ):
                continue
            timeout = command_hook.get("timeout")
            if (
                not isinstance(timeout, (int, float))
                or isinstance(timeout, bool)
                or timeout <= 0
            ):
                errors.append(f"{host} {event} shared hook needs a positive timeout")
                continue
            active = True
            covered.update(matcher.split("|"))
    if not active or not _HOST_MATCHERS[host][event].issubset(covered):
        errors.append(f"{host} {event} must invoke the shared hook for required tools")


def _validate_host_hook_contract(
    config: dict[str, object], host: str, errors: list[str]
) -> None:
    hooks = config.get("hooks")
    if not isinstance(hooks, dict):
        errors.append(f"{host} hooks must be an object")
        return
    if host == "zcode" and hooks.get("enabled") is not True:
        errors.append("zcode hooks must set enabled to true; file hooks are inert")
    for event in sorted(HOOK_EVENTS):
        _validate_host_event(hooks, host, event, errors)


def _validate_host_configs(errors: list[str]) -> None:
    settings_path = ROOT / ".claude" / "settings.json"
    codex_path = ROOT / ".codex" / "hooks.json"
    zcode_path = ROOT / ".zcode" / "config.json"
    settings = _load_json(settings_path, errors)
    codex = _load_json(codex_path, errors)
    zcode = _load_json(zcode_path, errors)

    if settings is not None:
        plugins = settings.get("enabledPlugins")
        if plugins is not None and (
            not isinstance(plugins, dict)
            or any(not isinstance(value, bool) for value in plugins.values())
        ):
            errors.append("Claude enabledPlugins must map names to booleans")
        permissions = settings.get("permissions")
        if (
            not isinstance(permissions, dict)
            or permissions.get("defaultMode") != "default"
        ):
            errors.append("Claude permissions.defaultMode must be default")
        _validate_host_hook_contract(settings, "claude", errors)

    if codex is not None:
        _validate_host_hook_contract(codex, "codex", errors)
        post_matchers = _event_matchers(codex, "PostToolUse")
        if not any("apply_patch" in matcher.split("|") for matcher in post_matchers):
            errors.append("Codex PostToolUse must match apply_patch")

    if zcode is not None:
        _validate_host_hook_contract(zcode, "zcode", errors)

    _validate_hook_target(settings_path, errors)
    _validate_hook_target(codex_path, errors)
    _validate_hook_target(zcode_path, errors)
    hook_script = ROOT / "tooling" / "agent_harness" / "hook.py"
    if not hook_script.is_file():
        errors.append("shared hook target is missing")


def _validate_bun_only(root: Path, errors: list[str]) -> None:
    errors.extend(
        f"forbidden package-manager file: {path}"
        for path in forbidden_package_manager_paths(root)
    )


def _validate_structured_configs(errors: list[str]) -> None:
    for path in (
        ROOT / "pyproject.toml",
        ROOT / "bunfig.toml",
        SKILL_REGISTRY,
    ):
        try:
            tomllib.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, tomllib.TOMLDecodeError) as error:
            errors.append(f"invalid TOML {path.relative_to(ROOT)}: {error}")
    for path in (ROOT / "package.json", ROOT / "apps" / "web" / "package.json"):
        _load_json(path, errors)


def validate() -> list[str]:
    errors: list[str] = []
    _validate_instruction_files(errors)
    _validate_skills(errors)
    _validate_legacy_content(errors)
    _validate_host_configs(errors)
    _validate_bun_only(ROOT, errors)
    _validate_structured_configs(errors)
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
