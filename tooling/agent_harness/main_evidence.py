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


def _policy_job(run: dict[str, Any]) -> dict[str, Any] | None:
    """Find the Repository policy job, scanning earlier attempts when needed.

    `gh run rerun --failed` 不重跑原本成功的 job——默认端点只返回最新
    attempt 的 jobs，policy job 可能只在早期 attempt 里（#352 评审）。
    """
    run_id = run.get("id")
    attempts = run.get("run_attempt") or 1
    if not isinstance(run_id, int):
        return None
    for attempt in range(int(attempts), 0, -1):
        # attempt= 不是 list-jobs 的合法参数；per-attempt 用文档化路由
        jobs = _gh(
            f"repos/{_repo()}/actions/runs/{run_id}"
            + f"/attempts/{attempt}/jobs?per_page=100"
        )
        found = next(
            (j for j in jobs.get("jobs", []) if j.get("name") == "Repository policy"),
            None,
        )
        if found is not None:
            return found
    return None


_MAX_RUN_PAGES = 10


def _push_run_window(
    endpoint: str, limit: int, since: str | None
) -> list[dict[str, Any]]:
    """Fetch push runs until the --since window is covered (#352 评审).

    先取满窗口再过滤：--since 期内的早页不被 --limit 截掉。
    """
    collected: list[dict[str, Any]] = list(
        _gh(f"{endpoint}?branch=main&event=push&per_page={limit}").get(
            "workflow_runs", []
        )
    )
    page = 2
    while since and collected and page <= _MAX_RUN_PAGES:
        oldest = min(str(r.get("created_at") or "") for r in collected)
        if oldest and oldest < since:
            break
        batch = _gh(
            f"{endpoint}?branch=main&event=push&per_page={limit}&page={page}"
        ).get("workflow_runs", [])
        if not batch:
            break
        collected.extend(batch)
        page += 1
    return collected


def observe(limit: int = 20, since: str | None = None) -> list[dict[str, Any]]:
    """Summarize recent main push runs' evidence outcomes (#352 影子观察).

    逐个取 main 上 event=push 的 ci.yml run，从其 Repository policy job
    日志提取 main-evidence outcome——影子观察（≥7 天/10 SHA）可机检复盘。
    """
    endpoint = f"repos/{_repo()}/actions/workflows/ci.yml/runs"
    collected = _push_run_window(endpoint, limit, since)
    runs = {"workflow_runs": collected}
    rows: list[dict[str, Any]] = []
    for run in runs.get("workflow_runs", []):
        sha = run.get("head_sha", "")
        try:
            policy = _policy_job(run)
        except EvidenceApiError as error:
            # 单个历史 run 的 jobs 查询失败不炸整个观察：降级并记原因
            rows.append(
                {
                    "run_id": run.get("id"),
                    "sha": sha[:12],
                    "created_at": run.get("created_at"),
                    "conclusion": run.get("conclusion"),
                    "evidence": "unknown",
                    "reasons": [f"jobs lookup failed: {error}"],
                }
            )
            continue
        outcome = "unknown"
        reasons: list[str] = []
        if policy is not None and isinstance(policy.get("id"), int):
            try:
                proc = subprocess.run(
                    ["gh", "api", f"repos/{_repo()}/actions/jobs/{policy['id']}/logs"],
                    capture_output=True,
                    text=True,
                    timeout=60,
                    check=False,
                )
                if proc.returncode != 0:
                    reasons.append(f"log fetch failed: gh exit {proc.returncode}")
                # Actions 日志行带时间戳前缀——用包含而非 startswith
                for line in proc.stdout.splitlines():
                    outcome_marker = "main-evidence outcome: "
                    if outcome_marker in line:
                        outcome = line.split(outcome_marker, 1)[1].strip()
                    elif "main-evidence: " in line:
                        marker = "main-evidence: "
                        reasons.append(line.split(marker, 1)[1].strip())
            except (subprocess.TimeoutExpired, OSError) as error:
                # 单个历史日志拉取失败不炸整个观察：降级 unknown 并记原因
                reasons.append(f"log fetch failed: {error}")
        rows.append(
            {
                "run_id": run.get("id"),
                "sha": sha[:12],
                "created_at": run.get("created_at"),
                "conclusion": run.get("conclusion"),
                "evidence": outcome,
                "reasons": reasons,
            }
        )
    return rows


def main(argv: list[str] | None = None) -> int:
    """Emit outcome for the workflow; never fail the job on evidence doubt."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("verify", "observe"))
    parser.add_argument("--commit")
    parser.add_argument("--output", help="GITHUB_OUTPUT path for outcome=")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument(
        "--since",
        help="ISO date (YYYY-MM-DD); drop earlier runs (observation start)",
    )
    args = parser.parse_args(argv)
    if args.mode == "observe":
        rows = observe(args.limit, args.since)
        if args.since:
            rows = [row for row in rows if str(row["created_at"] or "") >= args.since]
        for row in rows:
            print(json.dumps(row, ensure_ascii=False, sort_keys=True))
        verified = sum(1 for row in rows if row["evidence"] == VERIFIED)
        distinct = len({row["sha"] for row in rows})
        explainable = {VERIFIED, FULL_REQUIRED}
        unexplained = sum(
            1
            for row in rows
            if row["evidence"] not in explainable or not row.get("reasons")
        )
        dates = sorted(str(row["created_at"]) for row in rows if row["created_at"])
        summary = (
            f"observation: {verified}/{len(rows)} verified, {distinct} distinct SHAs"
        )
        if dates:
            summary += f", span {dates[0][:10]}..{dates[-1][:10]}"
        if unexplained:
            summary += f", {unexplained} unexplained rows"
        print(
            f"{summary} (switch gate: >=10 distinct SHAs over >=7 days, 0 unexplained)"
        )
        return 0
    if not args.commit:
        parser.error("verify requires --commit")
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
