"""Assert the GitHub ruleset protecting main matches the declared merge gate.

CI runs this with the repository-policy job and locally via ``task
harness-check``; both read the same live rulesets API, so there is no
static-config shadow. Changing the ruleset on purpose means updating the
expectations here in the same change.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, NamedTuple

REPO = "cosmos-arc/ditto"
API_BASE = f"https://api.github.com/repos/{REPO}/rulesets"
REQUIRED_CHECK = "CI gate"
REQUIRED_RULES = frozenset(
    {"pull_request", "required_status_checks", "non_fast_forward", "deletion"}
)
_MAIN_REFS = frozenset({"~DEFAULT_BRANCH", "refs/heads/main", "main"})


def _targets_main(ruleset: Mapping[str, Any]) -> bool:
    """Fail closed: malformed or empty ref filters never count as covering main."""
    conditions = ruleset.get("conditions")
    if not isinstance(conditions, Mapping):
        return True
    ref_name = conditions.get("ref_name")
    if ref_name is None:
        return True
    if not isinstance(ref_name, Mapping):
        return False
    include = ref_name.get("include") or []
    exclude = ref_name.get("exclude") or []
    return bool(set(include) & _MAIN_REFS) and not set(exclude) & _MAIN_REFS


def _active_main_rulesets(
    rulesets: Sequence[Mapping[str, Any]],
) -> list[Mapping[str, Any]]:
    return [
        ruleset
        for ruleset in rulesets
        if ruleset.get("target") == "branch"
        and ruleset.get("enforcement") == "active"
        and _targets_main(ruleset)
    ]


def _bypass_description(ruleset: Mapping[str, Any]) -> str:
    actors = [
        f"actor_id={actor.get('actor_id')} mode={actor.get('bypass_mode')}"
        for actor in ruleset.get("bypass_actors") or []
    ]
    return ", ".join(actors)


def _bypass_violations(active: Sequence[Mapping[str, Any]]) -> list[str]:
    violations: list[str] = []
    for ruleset in active:
        if not ruleset.get("bypass_actors"):
            continue
        description = _bypass_description(ruleset)
        violations.append(
            "bypass actors configured: "
            + description
            + "; removing them requires a deliberate probe update"
        )
    return violations


class _RulesScan(NamedTuple):
    present: set[str]
    checks: set[str]
    strict: bool


def _scan_rules(active: Sequence[Mapping[str, Any]]) -> _RulesScan:
    """Collect present rule types, required check contexts, and strictness."""
    present: set[str] = set()
    checks: set[str] = set()
    strict = False
    for ruleset in active:
        for rule in ruleset.get("rules") or []:
            rule_type = rule.get("type")
            if not isinstance(rule_type, str):
                continue
            present.add(rule_type)
            if rule_type != "required_status_checks":
                continue
            parameters = rule.get("parameters")
            if not isinstance(parameters, Mapping):
                continue
            contexts = {
                entry["context"]
                for entry in parameters.get("required_status_checks") or []
                if isinstance(entry, Mapping) and isinstance(entry.get("context"), str)
            }
            if REQUIRED_CHECK in contexts:
                strict = strict or bool(
                    parameters.get("strict_required_status_checks_policy")
                )
            checks |= contexts
    return _RulesScan(present=present, checks=checks, strict=strict)


def evaluate(rulesets: Sequence[Mapping[str, Any]]) -> list[str]:
    """Return rule violations for the rulesets guarding main; empty means protected.

    Accepts full ruleset payloads as returned by the single-ruleset endpoint;
    GitHub composes rules across every active ruleset matching the branch, so
    required rules may be spread over several rulesets.
    """
    active = _active_main_rulesets(rulesets)
    if not active:
        return ["no active branch ruleset protects the default branch"]

    violations = _bypass_violations(active)
    scan = _scan_rules(active)
    violations.extend(
        f"missing rule: {rule}" for rule in sorted(REQUIRED_RULES - scan.present)
    )
    if REQUIRED_CHECK not in scan.checks:
        violations.append(f"required status check {REQUIRED_CHECK!r} is not required")
    elif not scan.strict:
        violations.append(
            "required status checks are not strict (branch must be up to date)"
        )
    return violations


def _fetch(url: str, token: str | None) -> Any:
    request = urllib.request.Request(  # noqa: S310 -- pinned HTTPS API constant above.
        url, headers={"Accept": "application/vnd.github+json"}
    )
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(  # noqa: S310 -- request URL was constrained.
        request, timeout=15
    ) as response:
        return json.loads(response.read().decode())


def live_rulesets(token: str | None) -> list[Any]:
    """Fetch full ruleset payloads; the list endpoint omits the rules themselves."""
    summarized = _fetch(API_BASE, token)
    rulesets: list[Any] = []
    for entry in summarized:
        detail = _fetch(f"{API_BASE}/{entry['id']}", token)
        rulesets.append(detail)
    return rulesets


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("check",))
    parser.add_argument(
        "--payload",
        help="Read full ruleset payloads from a JSON file instead of the live API",
    )
    args = parser.parse_args()

    if args.payload:
        with Path(args.payload).open(encoding="utf-8") as stream:
            rulesets = json.load(stream)
    else:
        token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        try:
            rulesets = live_rulesets(token)
        except (urllib.error.URLError, OSError) as error:
            print(f"failed to read rulesets from {API_BASE}: {error}", file=sys.stderr)
            return 1

    violations = evaluate(rulesets)
    if violations:
        for violation in violations:
            print(violation, file=sys.stderr)
        return 1
    print(f"main branch protection ruleset matches the declared merge gate ({REPO})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
