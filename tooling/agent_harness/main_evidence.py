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
import io
import json
import os
import subprocess
import zipfile
from pathlib import Path
from typing import Any

VERIFIED = "verified"
FULL_REQUIRED = "full-required"


class EvidenceApiError(RuntimeError):
    """GitHub API evidence lookup failed."""


def _gh(*arguments: str) -> Any:
    """Call gh api; normalize process/decoding failures into EvidenceApiError."""
    try:
        proc = subprocess.run(
            ["gh", "api", *arguments],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError) as error:
        raise EvidenceApiError(f"gh api invocation failed: {error}") from error
    if proc.returncode != 0:
        raise EvidenceApiError(
            f"gh api {' '.join(arguments[:2])} failed: {proc.stderr.strip()[:400]}"
        )
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as error:
        raise EvidenceApiError(f"gh api returned malformed JSON: {error}") from error


def _gh_raw(endpoint: str) -> bytes:
    """Download a binary endpoint (artifact zip); failures normalize."""
    try:
        proc = subprocess.run(
            ["gh", "api", endpoint],
            capture_output=True,
            timeout=120,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError) as error:
        raise EvidenceApiError(f"gh api invocation failed: {error}") from error
    if proc.returncode != 0:
        raise EvidenceApiError(
            f"gh api {endpoint[:80]} failed: {proc.stderr.decode()[:200]}"
        )
    return proc.stdout


def _tested_commit_from_artifacts(run_id: int) -> str | None:
    """从 run 产物取被测提交（#351 评审 P1）：REST 无 merge 提交字段，
    shard manifest 记录的 commit=$GITHUB_SHA 才是实测对象。无产物
    （如 web-only PR）→ None → 全量。"""
    artifacts = _gh(f"repos/{_repo()}/actions/runs/{run_id}/artifacts?per_page=100")
    for artifact in artifacts.get("artifacts", []):
        if not str(artifact.get("name", "")).startswith("tested-commit-"):
            continue
        artifact_id = artifact.get("id")
        if not isinstance(artifact_id, int):
            continue
        blob = _gh_raw(f"repos/{_repo()}/actions/artifacts/{artifact_id}/zip")
        with zipfile.ZipFile(io.BytesIO(blob)) as archive:
            for name in archive.namelist():
                if name.endswith("tested-commit"):
                    commit = archive.read(name).decode("utf-8").strip()
                    if commit:
                        return commit
    return None


def _repo() -> str:
    return os.environ.get("GITHUB_REPOSITORY", "cosmos-arc/ditto")


def _merged_pr_for(commit_sha: str) -> dict[str, Any]:
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


def _latest_pr_run(head_sha: str) -> dict[str, Any] | None:
    """该 PR head 最新的 pull_request run（#351 评审：陈旧成功不能冒充——
    close/reopen 不改 head 但产生新 run，最新 run 失败即不通过）。"""
    runs = _gh(
        f"repos/{_repo()}/actions/workflows/ci.yml/runs"
        + f"?head_sha={head_sha}&event=pull_request&per_page=10"
    )
    candidates = [
        run
        for run in runs.get("workflow_runs", [])
        if run.get("event") == "pull_request" and isinstance(run.get("id"), int)
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda run: run["id"])


def _tested_gate_result(run: dict[str, Any]) -> tuple[bool, str | None]:
    """绑定 ci.yml 真实 run 的 CI gate job 结论；返回 (成功, 被测 merge SHA).

    名字相同的其他 App/工作流 check 不能冒充（#351 评审 P1）。PR run
    实测的是 refs/pull/<n>/merge 提交——run.head_sha 即被测 SHA，树比较
    必须用它而非 PR head（被测树才是验证对象）。
    """
    if run.get("conclusion") != "success":
        return False, None
    run_id = run.get("id")
    if not isinstance(run_id, int):
        return False, None
    jobs = _gh(f"repos/{_repo()}/actions/runs/{run_id}/jobs?per_page=100")
    gate_ok = any(
        job.get("name") == "CI gate" and job.get("conclusion") == "success"
        for job in jobs.get("jobs", [])
    )
    if not gate_ok:
        return False, None
    return True, _tested_commit_from_artifacts(run_id)


def verify(commit_sha: str) -> tuple[str, list[str]]:
    """Return (outcome, reasons); any doubt resolves to full-required."""
    reasons: list[str] = []

    def full(extra: str) -> tuple[str, list[str]]:
        return FULL_REQUIRED, [*reasons, extra]

    try:
        pull = _merged_pr_for(commit_sha)
        if not pull:
            return full("no merged pull request is associated with the commit")
        head_sha = pull.get("head", {}).get("sha")
        if not isinstance(head_sha, str):
            return full("merged pull request exposes no head sha")
        reasons.append(
            f"pr #{pull.get('number')} head {head_sha[:12]} merged at this commit"
        )
        latest = _latest_pr_run(head_sha)
        gate_ok, tested_sha = (
            _tested_gate_result(latest) if latest is not None else (False, None)
        )
        if latest is None or not gate_ok or tested_sha is None:
            return full("CI gate did not succeed in the latest ci.yml run")
        reasons.append(
            f"CI gate succeeded in ci.yml run {latest['id']} (tested {tested_sha[:12]})"
        )
        tested_tree, main_tree = _tree_oid(tested_sha), _tree_oid(commit_sha)
        if tested_tree != main_tree:
            mismatch = f"{tested_tree[:12]} != {main_tree[:12]}"
            return full(f"tested tree != final main tree ({mismatch})")
        reasons.append(f"tested tree == final main tree ({main_tree[:12]})")
    except Exception as error:
        label = (
            "evidence lookup failed"
            if isinstance(error, EvidenceApiError)
            else "unexpected evidence error"
        )
        return full(f"{label}: {error}")
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
