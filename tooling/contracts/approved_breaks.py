"""
Approved versioned breaks — explicit, fail-closed exemptions for oasdiff findings.

Implements the documented Required-check escape path ("an approved versioned
break is documented"): every oasdiff finding must be matched exactly by a
registry entry (rule id + stable fingerprint) that carries an approval
reference. Any unmatched finding still fails the gate; the registry cannot
weaken anything by itself.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import yaml

REGISTRY_SCHEMA = "ditto.approved-breaks.v1"
_TOP_LEVEL_KEYS = frozenset({"schema", "breaks"})
_FINGERPRINT_PATTERN = re.compile(r"^[0-9a-f]{6,32}$")
_RULE_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)+$")
_REQUIRED_KEYS = ("fingerprint", "id", "approved-by", "added")
_ALLOWED_KEYS = frozenset((*_REQUIRED_KEYS, "note"))


class _UniqueKeyLoader(yaml.SafeLoader):
    """SafeLoader that rejects duplicate mapping keys instead of last-wins."""

    def construct_mapping(
        self, node: yaml.Node, deep: bool = False
    ) -> dict[object, object]:
        seen: set[object] = set()
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=deep)
            try:
                duplicate = key in seen
            except TypeError as error:
                raise yaml.constructor.ConstructorError(
                    "while constructing a mapping",
                    node.start_mark,
                    f"found unhashable key {key!r}",
                    key_node.start_mark,
                ) from error
            if duplicate:
                raise yaml.constructor.ConstructorError(
                    "while constructing a mapping",
                    node.start_mark,
                    f"found duplicate key {key!r}",
                    key_node.start_mark,
                )
            seen.add(key)
        return super().construct_mapping(node, deep)


class ApprovedBreaksError(RuntimeError):
    """The approved-breaks registry is malformed."""


@dataclass(frozen=True)
class ApprovedBreak:
    """One registered exemption: an exact (rule id, fingerprint) pair."""

    fingerprint: str
    rule_id: str
    approved_by: str
    added: str
    note: str


@dataclass(frozen=True)
class Finding:
    """One oasdiff breaking/warning finding subject to approval matching."""

    rule_id: str
    fingerprint: str
    text: str


def parse_registry(payload: str) -> list[ApprovedBreak]:
    """Parse and strictly validate the registry document."""
    try:
        # SafeLoader subclass: identical safe constructors plus duplicate-key
        # rejection; ruff cannot see the SafeLoader base through the alias.
        document = yaml.load(payload, Loader=_UniqueKeyLoader)  # noqa: S506
    except yaml.YAMLError as error:
        raise ApprovedBreaksError(
            f"approved-breaks registry is not valid YAML: {error}"
        ) from error
    if not isinstance(document, dict):
        raise ApprovedBreaksError(
            "approved-breaks registry must be a mapping with 'schema' and 'breaks'"
        )
    top_level_unknown = frozenset(map(str, document)) - _TOP_LEVEL_KEYS
    if top_level_unknown:
        raise ApprovedBreaksError(
            "approved-breaks registry has unknown top-level keys: "
            + f"{sorted(top_level_unknown)}"
        )
    if document.get("schema") != REGISTRY_SCHEMA:
        raise ApprovedBreaksError(
            f"approved-breaks registry schema must be {REGISTRY_SCHEMA!r}"
        )
    entries_payload = document.get("breaks")
    if entries_payload is None:
        return []
    if not isinstance(entries_payload, list):
        raise ApprovedBreaksError("approved-breaks 'breaks' must be a list")
    entries: list[ApprovedBreak] = []
    seen: set[tuple[str, str]] = set()
    for position, raw in enumerate(entries_payload):
        entry = _parse_entry(raw, position)
        identity = (entry.rule_id, entry.fingerprint)
        if identity in seen:
            raise ApprovedBreaksError(
                f"approved-breaks entry #{position} duplicates {identity}"
            )
        seen.add(identity)
        entries.append(entry)
    return entries


def _parse_entry(raw: object, position: int) -> ApprovedBreak:
    """Validate one registry mapping at ``position`` against the strict schema."""
    if not isinstance(raw, dict):
        raise ApprovedBreaksError(
            f"approved-breaks entry #{position} must be a mapping"
        )
    unknown = frozenset(raw) - _ALLOWED_KEYS
    if unknown:
        raise ApprovedBreaksError(
            f"approved-breaks entry #{position} has unknown keys: {sorted(unknown)}"
        )
    missing = [
        key
        for key in _REQUIRED_KEYS
        if not isinstance(raw.get(key), str) or not raw[key].strip()
    ]
    if missing:
        raise ApprovedBreaksError(
            f"approved-breaks entry #{position} missing required strings: {missing}"
        )
    fingerprint = raw["fingerprint"]
    rule_id = raw["id"]
    added = raw["added"]
    if not _FINGERPRINT_PATTERN.fullmatch(fingerprint):
        raise ApprovedBreaksError(
            f"approved-breaks entry #{position} fingerprint must be hex: "
            + f"{fingerprint!r}"
        )
    if not _RULE_ID_PATTERN.fullmatch(rule_id):
        raise ApprovedBreaksError(
            f"approved-breaks entry #{position} id must be an oasdiff rule id: "
            + f"{rule_id!r}"
        )
    try:
        parsed_added = date.fromisoformat(added)
    except ValueError:
        raise ApprovedBreaksError(
            f"approved-breaks entry #{position} added is not a real calendar "
            + f"date: {added!r}"
        ) from None
    if parsed_added.isoformat() != added:
        raise ApprovedBreaksError(
            f"approved-breaks entry #{position} added must be YYYY-MM-DD: "
            + f"{added!r}"
        )
    note = raw.get("note", "")
    if not isinstance(note, str):
        raise ApprovedBreaksError(
            f"approved-breaks entry #{position} note must be a string"
        )
    return ApprovedBreak(
        fingerprint=fingerprint,
        rule_id=rule_id,
        approved_by=raw["approved-by"],
        added=added,
        note=note,
    )


def load_registry(path: Path) -> list[ApprovedBreak]:
    """Load the registry; a missing file means no exemptions exist."""
    if not path.is_file():
        return []
    try:
        payload = path.read_bytes().decode("utf-8")
    except UnicodeDecodeError as error:
        raise ApprovedBreaksError(
            f"approved-breaks registry is not valid UTF-8: {error}"
        ) from error
    return parse_registry(payload)


def unapproved(findings: list[Finding], entries: list[ApprovedBreak]) -> list[Finding]:
    """Return findings not covered exactly by a registry entry (injective)."""
    remaining = {(entry.rule_id, entry.fingerprint) for entry in entries}
    rejected: list[Finding] = []
    for finding in findings:
        if (finding.rule_id, finding.fingerprint) in remaining:
            remaining.discard((finding.rule_id, finding.fingerprint))
        else:
            rejected.append(finding)
    return rejected


def approval_line(entry: ApprovedBreak) -> str:
    """Render one consumed exemption for gate output (auditable)."""
    note = f" — {entry.note}" if entry.note else ""
    return (
        f"approved versioned break: {entry.rule_id} fingerprint={entry.fingerprint} "
        f"approved-by={entry.approved_by} added={entry.added}{note}"
    )
