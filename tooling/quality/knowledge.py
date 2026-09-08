"""Validate declared active Markdown links and required machine input locations."""

from __future__ import annotations

import argparse
import re
import tomllib
from pathlib import Path
from urllib.parse import unquote, urlsplit

_LINK = re.compile(r"!?\[[^\]\n]*\]\(\s*(<[^>]+>|[^\s)]+)(?:\s+[^)]*)?\)")
_REFERENCE = re.compile(r"^\s{0,3}\[[^\]]+\]:\s*(<[^>]+>|\S+)", re.MULTILINE)


def _prose(text: str) -> str:
    lines: list[str] = []
    fence = ""
    for line in text.splitlines():
        marker = re.match(r"^\s{0,3}(`{3,}|~{3,})", line)
        if marker:
            token = marker.group(1)
            if not fence:
                fence = token
            elif token[0] == fence[0] and len(token) >= len(fence):
                fence = ""
            continue
        if not fence:
            lines.append(re.sub(r"`+[^`]*`+", "", line))
    return re.sub(r"<!--.*?-->", "", "\n".join(lines), flags=re.DOTALL)


def _patterns(policy: dict[str, object], key: str) -> list[str]:
    values = policy.get(key)
    if not isinstance(values, list) or not values:
        raise ValueError(f"{key} must be a nonempty list")
    patterns: list[str] = []
    for value in values:
        if not isinstance(value, str) or not value or Path(value).is_absolute():
            raise ValueError(f"invalid {key} path: {value!r}")
        if ".." in Path(value).parts:
            raise ValueError(f"{key} path escapes repository: {value}")
        patterns.append(value)
    return patterns


def _declared_files(root: Path, patterns: list[str], errors: list[str]) -> set[Path]:
    files: set[Path] = set()
    for pattern in patterns:
        matches = sorted(root.glob(pattern))
        if not matches:
            errors.append(f"required material missing: {pattern}")
        for path in matches:
            if (
                not path.is_file()
                or path.is_symlink()
                or not path.resolve().is_relative_to(root)
            ):
                errors.append(
                    f"required material is not a regular file: {path.relative_to(root)}"
                )
            else:
                files.add(path)
    return files


def check(root: Path) -> list[str]:
    """Return failures for the explicitly declared current knowledge surface."""
    root = root.resolve()
    policy = tomllib.loads(
        (root / ".knowledge-policy.toml").read_text(encoding="utf-8")
    )
    if policy.get("schema_version") != 1:
        raise ValueError("knowledge policy schema must be 1")
    errors: list[str] = []
    documents = _declared_files(root, _patterns(policy, "active_documents"), errors)
    _declared_files(root, _patterns(policy, "machine_inputs"), errors)
    for document in sorted(documents):
        text = _prose(document.read_text(encoding="utf-8"))
        targets = [match.group(1) for match in _LINK.finditer(text)]
        targets.extend(match.group(1) for match in _REFERENCE.finditer(text))
        for target in targets:
            link = urlsplit(target.strip("<>"))
            if link.scheme or link.netloc or not link.path:
                continue
            path = unquote(link.path)
            destination = (
                root / path.lstrip("/")
                if path.startswith("/")
                else document.parent / path
            ).resolve()
            if not destination.is_relative_to(root) or not destination.exists():
                errors.append(
                    f"{document.relative_to(root)}: unresolved local link {target}"
                )
    return errors


def main() -> int:
    """Run the read-only knowledge gate and report actionable paths."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    try:
        errors = check(args.root)
    except (OSError, ValueError) as error:
        errors = [str(error)]
    for error in errors:
        print(error)
    print(f"knowledge-check: {'FAIL' if errors else 'PASS'}")
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
