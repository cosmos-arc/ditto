"""GitHub CI selection and fail-closed aggregation using the local scope policy.

#538 双层门禁：阻断合并的快速门（质量/类型/分片/coverage 与 PIT、OpenAPI
红线）与异步深度层（平台/容器/安全全量/系统 E2E/容量慢车道）。深度层红由
merge freeze 兜底：main 上深度层未消红期间快速门拒绝新合并。路径分类与
fail-closed 升级留在本层（turbo 只承担图/缓存事实，对未知路径 fail-open，
兜底职责在此，#526 四条件之一）。
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from collections.abc import Sequence
from pathlib import Path

from tooling.agent_harness.hook import classify_diff
from tooling.agent_harness.impact_scope import (
    is_backend_source_path,
    is_web_source_path,
)

FAST_JOBS = frozenset(
    {
        "skill-validation",
        "repository-policy",
        "security-quick",
        "backend-quality",
        "backend-types",
        "marker-dump",
        "backend-shards",
        "backend-tests",
        "architecture-harness",
        "api-contract",
        "release-policy",
        "web-quality",
        "web-build",
    }
)
DEEP_JOBS = frozenset(
    {
        "platform-smoke",
        "container-smoke",
        "system-e2e",
        "backend-capacity",
        "web-prototype",
        "security-full",
    }
)
_ALWAYS = {"repository-policy", "security-quick"}
_FAST_WEB = {"web-quality", "web-build", "api-contract"}
_DEEP_WEB = {"web-prototype", "system-e2e", "security-full"}
_FAST_BACKEND = {
    "backend-quality",
    "backend-types",
    "marker-dump",
    "backend-shards",
    "backend-tests",
    "architecture-harness",
    "api-contract",
    "web-build",
}
_DEEP_BACKEND = {"backend-capacity", "system-e2e", "security-full"}


def _tiers(paths: Sequence[str], *, full: bool) -> tuple[set[str], set[str]]:
    """Resolve the (fast, deep) job pair a changed scope owes; unknowns go full."""
    level = classify_diff(paths)
    if full:
        return set(FAST_JOBS), set(DEEP_JOBS)
    if level == "skills":
        return _ALWAYS | {"skill-validation"}, set()
    if level in {"docs", "none"}:
        return set(_ALWAYS), set()
    if level == "web" and all(map(is_web_source_path, paths)):
        return _ALWAYS | _FAST_WEB, set(_DEEP_WEB)
    if level in {"backend", "backend-tests"} and all(
        map(is_backend_source_path, paths)
    ):
        return _ALWAYS | _FAST_BACKEND, set(_DEEP_BACKEND)
    # Contracts, toolchain, security, unknown and high-risk paths use all gates.
    return set(FAST_JOBS), set(DEEP_JOBS)


def required_jobs(paths: Sequence[str], *, full: bool = False) -> set[str]:
    """Blocking fast-gate jobs owed by a changed scope; unknowns take the full gate."""
    return _tiers(paths, full=full)[0]


def deep_jobs(paths: Sequence[str], *, full: bool = False) -> set[str]:
    """Async deep-layer jobs for the same scope; red there freezes new merges."""
    return _tiers(paths, full=full)[1]


def _emit(required: set[str], deep: set[str]) -> None:
    full = required == set(FAST_JOBS) and deep == set(DEEP_JOBS)
    output = (
        f"required={json.dumps(sorted(required))}\ndeep={json.dumps(sorted(deep))}\n"
        f"full={str(full).lower()}\n"
    )
    with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as stream:
        stream.write(output)
    print(output, end="")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("select",))
    parser.parse_args()
    event = os.environ.get("GITHUB_EVENT_NAME", "")
    if event == "push":
        # push 到 main 沿用 PR 已验证的等价内容（#351：由 main_evidence
        # 机器核验身份链——合并 PR 关联/head CI gate 成功/tested tree ==
        # final tree）；核验未通过或缺失时退回全量。
        if os.environ.get("MAIN_EVIDENCE") == "verified":
            required, deep = set(_ALWAYS), {"platform-smoke"}
        else:
            required, deep = set(FAST_JOBS), set(DEEP_JOBS)
        _emit(required, deep)
        return 0
    full = event != "pull_request"
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
    required, deep = _tiers(paths, full=full)
    _emit(required, deep)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
