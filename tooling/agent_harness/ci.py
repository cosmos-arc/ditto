"""GitHub CI selection and fail-closed aggregation using the local scope policy."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from collections.abc import Sequence
from pathlib import Path

from tooling.agent_harness.hook import classify_diff

REQUIRED_JOBS = frozenset(
    {
        "skill-validation",
        "repository-policy",
        "delivery-policy",
        "backend-shards",
        "web-build",
        "web-prototype",
        "backend-quality",
        "backend-types",
        "backend-tests",
        "architecture-harness",
        "web-quality",
        "api-contract",
        "system-e2e",
        "release-cohort",
        "container-smoke",
        "platform-smoke",
        "security-supply-chain",
    }
)
_ALWAYS = {"repository-policy", "delivery-policy", "security-supply-chain"}


def required_jobs(paths: Sequence[str], *, full: bool = False) -> set[str]:
    """Select every proof required by a changed scope; unknowns take the full gate."""
    level = classify_diff(paths)
    if full:
        return set(REQUIRED_JOBS)
    if level == "skills":
        return _ALWAYS | {"skill-validation"}
    if level in {"docs", "none"}:
        return set(_ALWAYS)
    if level == "web" and all(
        path.startswith(
            ("apps/web/src/", "apps/web/tests/", "apps/web/prototype/", "docs/")
        )
        and path.endswith((".ts", ".tsx", ".css", ".md", ".rst"))
        for path in paths
    ):
        return _ALWAYS | {
            "web-quality",
            "web-prototype",
            "web-build",
            "api-contract",
            "system-e2e",
        }
    if level in {"backend", "backend-tests"} and all(
        path.endswith((".py", ".md", ".rst"))
        and path.startswith(("packages/", "apps/backend/", "docs/"))
        for path in paths
    ):
        return _ALWAYS | {
            "backend-quality",
            "backend-types",
            "backend-shards",
            "backend-tests",
            "architecture-harness",
            "api-contract",
            "system-e2e",
            "web-build",
            "platform-smoke",
        }
    # Contracts, toolchain, security, unknown and high-risk paths use all gates.
    return set(REQUIRED_JOBS)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("select",))
    parser.parse_args()
    full = os.environ.get("GITHUB_EVENT_NAME") != "pull_request"
    paths: list[str] = []
    if not full:
        # Disable rename folding so both sides and both modes are checked.
        raw = (
            subprocess.check_output(
                [
                    "git",
                    "diff",
                    "--raw",
                    "-z",
                    "--no-renames",
                    os.environ["CHECK_BASE_SHA"],
                    os.environ["GITHUB_SHA"],
                ]
            )
            .decode()
            .split("\0")
        )
        for index in range(0, len(raw) - 1, 2):
            header, path = raw[index : index + 2]
            paths.append(path)
            modes = header.split()[:2]
            if any(mode.lstrip(":") not in {"100644", "000000"} for mode in modes):
                full = True
    required = required_jobs(paths, full=full)
    analysis = bool(required - _ALWAYS - {"skill-validation"})
    output = (
        f"required={json.dumps(sorted(required))}\nanalysis={str(analysis).lower()}\n"
        f"full={str(required == set(REQUIRED_JOBS)).lower()}\n"
    )
    with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as stream:
        stream.write(output)
    print(output, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
