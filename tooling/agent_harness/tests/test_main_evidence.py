"""Main-push evidence chain must fail toward full verification (#351)."""

from __future__ import annotations

import io
import subprocess as sp
import zipfile
from collections.abc import Callable
from typing import Any

import pytest

from tooling.agent_harness.main_evidence import (
    FULL_REQUIRED,
    VERIFIED,
    verify,
)

_COMMIT = "c" * 40
_HEAD = "a" * 40
_MERGE = "m" * 40


class _RawZip(Exception):
    """Marker for binary (zip) endpoints routed through _gh_raw."""

    def __init__(self, payload: bytes) -> None:
        super().__init__("binary payload")
        self.payload = payload


def _pull(merged: bool = True, merge_sha: str = _COMMIT) -> dict[str, Any]:
    return {
        "number": 42,
        "merged": merged,
        "merge_commit_sha": merge_sha,
        "head": {"sha": _HEAD},
    }


def _shard_zip(commit: str | None) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("tested-commit", commit or "")
    return buffer.getvalue()


def _responder(
    *,
    pulls: list[dict[str, Any]] | None = None,
    pull_detail: dict[str, Any] | None = None,
    workflow_runs: list[dict[str, Any]] | None = None,
    gate_jobs: list[dict[str, Any]] | None = None,
    head_tree: str = "t" * 40,
    main_tree: str = "t" * 40,
    tested_commit: str | None = _MERGE,
    artifacts: list[dict[str, Any]] | None = None,
) -> Callable[[str], Any]:
    runs = (
        workflow_runs
        if workflow_runs is not None
        else [
            {
                "id": 7,
                "event": "pull_request",
                "conclusion": "success",
                "head_sha": _HEAD,
            }
        ]
    )
    jobs = (
        gate_jobs
        if gate_jobs is not None
        else [{"name": "CI gate", "conclusion": "success"}]
    )
    artifact_list = (
        artifacts if artifacts is not None else [{"id": 99, "name": "tested-commit-7"}]
    )
    detail = pull_detail if pull_detail is not None else _pull()

    def route(endpoint: str) -> Any:
        if endpoint.endswith(f"/commits/{_COMMIT}/pulls"):
            return pulls if pulls is not None else [detail]
        if endpoint.endswith("/pulls/42"):
            return detail
        if "/actions/workflows/ci.yml/runs" in endpoint:
            return {"workflow_runs": runs}
        if endpoint.endswith("/artifacts/99/zip"):
            raise _RawZip(_shard_zip(tested_commit))
        if "/actions/runs/" in endpoint and "/jobs" in endpoint:
            return {"jobs": jobs}
        if endpoint.endswith((f"/git/commits/{_MERGE}", f"/git/commits/{_COMMIT}")):
            sha = head_tree if endpoint.endswith(_MERGE) else main_tree
            return {"tree": {"sha": sha}}
        if "/actions/runs/" in endpoint and "/artifacts" in endpoint:
            return {"artifacts": artifact_list}
        raise AssertionError(f"unexpected endpoint: {endpoint}")

    return route


def _install(
    monkeypatch: pytest.MonkeyPatch,
    responder: Callable[[str], Any],
) -> None:
    def fake_gh(*arguments: str) -> Any:
        try:
            return responder(arguments[0])
        except _RawZip as marker:
            raise AssertionError("binary endpoint hit _gh") from marker

    def fake_gh_raw(endpoint: str) -> bytes:
        try:
            responder(endpoint)
        except _RawZip as marker:
            return marker.payload
        raise AssertionError(f"unexpected raw endpoint {endpoint}")

    monkeypatch.setattr("tooling.agent_harness.main_evidence._gh", fake_gh)
    monkeypatch.setattr("tooling.agent_harness.main_evidence._gh_raw", fake_gh_raw)


def test_happy_chain_verifies(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(monkeypatch, _responder())
    outcome, reasons = verify(_COMMIT)
    assert outcome == VERIFIED
    assert any("tested tree == final main tree" in r for r in reasons)


def test_no_associated_pr_requires_full(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(monkeypatch, _responder(pulls=[]))
    outcome, reasons = verify(_COMMIT)
    assert outcome == FULL_REQUIRED
    assert any("no merged pull request" in r for r in reasons)


def test_unmerged_pr_requires_full(monkeypatch: pytest.MonkeyPatch) -> None:
    unmerged = _pull(merged=False)
    _install(monkeypatch, _responder(pulls=[unmerged], pull_detail=unmerged))
    outcome, reasons = verify(_COMMIT)
    assert outcome == FULL_REQUIRED
    assert any("no merged pull request" in r for r in reasons)


def test_failed_ci_gate_requires_full(monkeypatch: pytest.MonkeyPatch) -> None:
    failed_jobs = [{"name": "CI gate", "conclusion": "failure"}]
    _install(monkeypatch, _responder(gate_jobs=failed_jobs))
    outcome, reasons = verify(_COMMIT)
    assert outcome == FULL_REQUIRED
    assert any("CI gate did not succeed" in r for r in reasons)


def test_tree_mismatch_requires_full(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(monkeypatch, _responder(head_tree="a" * 40, main_tree="b" * 40))
    outcome, reasons = verify(_COMMIT)
    assert outcome == FULL_REQUIRED
    assert any("tested tree != final main tree" in r for r in reasons)


def test_stale_success_cannot_override_newer_failed_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """同 head 最新 run 失败时，历史成功不能冒充（close/reopen 场景）."""
    _install(
        monkeypatch,
        _responder(
            workflow_runs=[
                {
                    "id": 7,
                    "event": "pull_request",
                    "conclusion": "success",
                    "head_sha": _HEAD,
                },
                {
                    "id": 8,
                    "event": "pull_request",
                    "conclusion": "failure",
                    "head_sha": _HEAD,
                },
            ],
        ),
    )
    outcome, reasons = verify(_COMMIT)
    assert outcome == FULL_REQUIRED
    assert any("latest ci.yml run" in r for r in reasons)


def test_tree_compared_against_artifact_tested_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """树比较用产物记录的被测提交（merge 提交），非 PR head——
    head 树==main 树但被测 merge 树不同→全量."""
    _install(monkeypatch, _responder(head_tree="x" * 40, main_tree="t" * 40))
    outcome, reasons = verify(_COMMIT)
    assert outcome == FULL_REQUIRED
    assert any("tested tree != final main tree" in r for r in reasons)


def test_no_artifact_evidence_requires_full(monkeypatch: pytest.MonkeyPatch) -> None:
    """无产物记录被测提交（如 web-only PR）→ 无法证明 → 全量."""
    _install(monkeypatch, _responder(artifacts=[]))
    outcome, reasons = verify(_COMMIT)
    assert outcome == FULL_REQUIRED
    assert any("latest ci.yml run" in r for r in reasons)


def test_api_failure_requires_full_not_crash(monkeypatch: pytest.MonkeyPatch) -> None:
    from tooling.agent_harness.main_evidence import EvidenceApiError

    def boom(*_args: str) -> Any:
        raise EvidenceApiError("boom")

    monkeypatch.setattr("tooling.agent_harness.main_evidence._gh", boom)
    outcome, reasons = verify(_COMMIT)
    assert outcome == FULL_REQUIRED
    assert any("evidence lookup failed" in r for r in reasons)


def test_timeout_normalizes_to_full_required(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_args: str, **_kwargs: object) -> Any:
        raise sp.TimeoutExpired(cmd="gh", timeout=60)

    monkeypatch.setattr("tooling.agent_harness.main_evidence.subprocess.run", boom)
    outcome, reasons = verify(_COMMIT)
    assert outcome == FULL_REQUIRED
    assert any("lookup failed" in r for r in reasons)


def test_repo_helper_reads_env(monkeypatch: pytest.MonkeyPatch) -> None:
    import os

    from tooling.agent_harness.main_evidence import _repo

    monkeypatch.setenv("GITHUB_REPOSITORY", "o/r")
    assert _repo() == os.environ["GITHUB_REPOSITORY"]
    monkeypatch.delenv("GITHUB_REPOSITORY")
    assert _repo() == "cosmos-arc/ditto"


def test_observe_parses_evidence_outcome_from_logs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """#352：观察命令从 push run 的 policy job 日志提取证据结论."""
    import tooling.agent_harness.main_evidence as me

    def fake_gh(endpoint: str) -> Any:
        if "/actions/workflows/ci.yml/runs" in endpoint:
            return {
                "workflow_runs": [
                    {
                        "id": 5,
                        "head_sha": _COMMIT,
                        "created_at": "t",
                        "conclusion": "success",
                    }
                ]
            }
        if "/jobs" in endpoint:
            return {"jobs": [{"name": "Repository policy", "id": 77}]}
        raise AssertionError(f"unexpected {endpoint}")

    def fake_logs(*args: str, **kwargs: object) -> Any:
        class P:
            stdout = (
                "2026-09-29T00:00:00Z main-evidence: pr ok\n"
                "2026-09-29T00:00:00Z main-evidence outcome: verified\n"
            )
            returncode = 0

        return P()

    monkeypatch.setattr(me, "_gh", fake_gh)
    monkeypatch.setattr(me.subprocess, "run", fake_logs)
    rows = me.observe(limit=5)
    assert rows == [
        {
            "run_id": 5,
            "sha": _COMMIT[:12],
            "created_at": "t",
            "conclusion": "success",
            "evidence": "verified",
            "reasons": ["pr ok"],
        }
    ]
