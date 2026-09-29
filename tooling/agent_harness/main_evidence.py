"""
Machine-verify the PR evidence behind a narrowed main-push CI selection (#351).

push 到 main 的收窄选择此前盲信"PR 已验证等价内容"。本模块把该信任
变成可核验的身份链：合并 PR 关联、PR head 的 CI gate 成功、tested
tree 与最终 main tree 同一。任一环节缺失或不匹配都退回全量验证
（全量始终可执行，优于失败）；tree 同一性同时覆盖 workflow/selector/
toolchain 等全部规则文件——tested tree 即最终 tree 时规则不可能漂移。
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path

VERIFIED = "verified"
FULL_REQUIRED = "full-required"


class EvidenceApiError(RuntimeError):
    """GitHub API evidence lookup failed."""


def _gh(*arguments: str) -> object:
    proc = subprocess.run(
        ["gh", "api", *arguments],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if proc.returncode != 0:
        raise EvidenceApiError(
            f"gh api {' '.join(arguments[:2])} failed: {proc.stderr.strip()[:400]}"
        )
    return json.loads(proc.stdout)


def _repo() -> str:
    return os.environ.get("GITHUB_REPOSITORY", "cosmos-arc/ditto")


def _merged_pr_for(commit_sha: str) -> dict[str, object]:
    pulls = _gh(f"repos/{_repo()}/commits/{commit_sha}/pulls")
    candidates = [p for p in pulls if isinstance(p, dict)]
    for candidate in candidates:
        number = candidate.get("number")
        detail = _gh(f"repos/{_repo()}/pulls/{number}")
        if (
            detail.get("merged") is True
            and detail.get("merge_commit_sha") == commit_sha
        ):
            return detail
    return {}


def _tree_oid(commit_sha: str) -> str:
    commit = _gh(f"repos/{_repo()}/git/commits/{commit_sha}")
    tree = commit.get("tree") or {}
    tree_oid = tree.get("sha")
    if not isinstance(tree_oid, str):
        raise EvidenceApiError(f"commit {commit_sha} has no tree oid")
    return tree_oid


def _ci_gate_succeeded(head_sha: str) -> bool:
    payload = _gh(f"repos/{_repo()}/commits/{head_sha}/check-runs")
    for run in payload.get("check_runs", []):
        completed = run.get("status") == "completed"
        succeeded = run.get("conclusion") == "success"
        if run.get("name") == "CI gate" and completed and succeeded:
            return True
    return False


def verify(commit_sha: str) -> tuple[str, list[str]]:
    """Return (outcome, reasons); any doubt resolves to full-required."""
    reasons: list[str] = []
    try:
        pull = _merged_pr_for(commit_sha)
        if not pull:
            return FULL_REQUIRED, [
                "no merged pull request is associated with the commit"
            ]
        head_sha = pull.get("head", {}).get("sha")
        if not isinstance(head_sha, str):
            return FULL_REQUIRED, ["merged pull request exposes no head sha"]
        reasons.append(
            f"pr #{pull.get('number')} head {head_sha[:12]} merged at this commit"
        )
        if not _ci_gate_succeeded(head_sha):
            reasons.append("CI gate did not succeed on the tested (head) sha")
            return FULL_REQUIRED, reasons
        reasons.append("CI gate succeeded on the tested (head) sha")
        head_tree, main_tree = _tree_oid(head_sha), _tree_oid(commit_sha)
        if head_tree != main_tree:
            mismatch = f"{head_tree[:12]} != {main_tree[:12]}"
            reasons.append(f"tested tree != final main tree ({mismatch})")
            return FULL_REQUIRED, reasons
        reasons.append(f"tested tree == final main tree ({main_tree[:12]})")
    except EvidenceApiError as error:
        return FULL_REQUIRED, [*reasons, f"evidence lookup failed: {error}"]
    return VERIFIED, reasons


def main(argv: list[str] | None = None) -> int:
    """Emit outcome for the workflow; never fail the job on evidence doubt."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("verify",))
    parser.add_argument("--commit", required=True)
    parser.add_argument("--output", help="GITHUB_OUTPUT path for outcome=")
    args = parser.parse_args(argv)
    outcome, reasons = verify(args.commit)
    for reason in reasons:
        print(f"main-evidence: {reason}")
    print(f"main-evidence outcome: {outcome}")
    if args.output:
        with Path(args.output).open("a", encoding="utf-8") as handle:
            handle.write(f"outcome={outcome}\n")
            handle.write("reasons=" + json.dumps(reasons, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
