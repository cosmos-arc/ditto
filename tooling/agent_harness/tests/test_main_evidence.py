"""Main-push evidence chain must fail toward full verification (#351)."""

from __future__ import annotations

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


def _pull(merged: bool = True, merge_sha: str = _COMMIT) -> dict[str, Any]:
    return {
        "number": 42,
        "merged": merged,
        "merge_commit_sha": merge_sha,
        "head": {"sha": _HEAD},
    }


def _install(
    monkeypatch: pytest.MonkeyPatch,
    responder: Callable[[str], Any],
) -> None:
    def fake_gh(*arguments: str) -> Any:
        return responder(arguments[0])

    monkeypatch.setattr("tooling.agent_harness.main_evidence._gh", fake_gh)


def _responder(
    *,
    pulls: list[dict[str, Any]] | None = None,
    pull_detail: dict[str, Any] | None = None,
    workflow_runs: list[dict[str, Any]] | None = None,
    gate_jobs: list[dict[str, Any]] | None = None,
    head_tree: str = "t" * 40,
    main_tree: str = "t" * 40,
) -> Callable[[str], Any]:
    runs = (
        workflow_runs
        if workflow_runs is not None
        else [{"id": 7, "event": "pull_request", "conclusion": "success"}]
    )
    jobs = (
        gate_jobs
        if gate_jobs is not None
        else [{"name": "CI gate", "conclusion": "success"}]
    )
    detail = pull_detail if pull_detail is not None else _pull()

    def respond(endpoint: str) -> Any:
        if endpoint.endswith(f"/commits/{_COMMIT}/pulls"):
            return pulls if pulls is not None else [detail]
        if endpoint.endswith("/pulls/42"):
            return detail
        if "/actions/workflows/ci.yml/runs" in endpoint:
            return {"workflow_runs": runs}
        if "/actions/runs/7/jobs" in endpoint:
            return {"jobs": jobs}
        if endpoint.endswith(f"/git/commits/{_HEAD}"):
            return {"tree": {"sha": head_tree}}
        if endpoint.endswith(f"/git/commits/{_COMMIT}"):
            return {"tree": {"sha": main_tree}}
        raise AssertionError(f"unexpected endpoint {endpoint}")

    return respond


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


def test_unmerged_or_wrong_merge_pr_requires_full(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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


def test_api_failure_requires_full_not_crash(monkeypatch: pytest.MonkeyPatch) -> None:
    from tooling.agent_harness.main_evidence import EvidenceApiError

    def boom(*_args: str) -> Any:
        raise EvidenceApiError("boom")

    monkeypatch.setattr("tooling.agent_harness.main_evidence._gh", boom)
    outcome, reasons = verify(_COMMIT)
    assert outcome == FULL_REQUIRED
    assert any("evidence lookup failed" in r for r in reasons)


def test_live_repo_helper_reads_env(monkeypatch: pytest.MonkeyPatch) -> None:
    import os

    from tooling.agent_harness.main_evidence import _repo

    monkeypatch.setenv("GITHUB_REPOSITORY", "o/r")
    assert _repo() == os.environ["GITHUB_REPOSITORY"]
    monkeypatch.delenv("GITHUB_REPOSITORY")
    assert _repo() == "cosmos-arc/ditto"


def test_foreign_ci_gate_name_cannot_spoof_verification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """#351 评审 P1：绑定 ci.yml 真实 run 的 job 结论——同名他源不能冒充."""
    _install(
        monkeypatch,
        _responder(gate_jobs=[{"name": "CI gate", "conclusion": "failure"}]),
    )
    outcome, reasons = verify(_COMMIT)
    assert outcome == FULL_REQUIRED
    assert any("CI gate did not succeed" in r for r in reasons)


def test_no_successful_ci_yml_run_requires_full(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ci.yml 无 event=pull_request 且成功的 run（只有其他来源同名检查）→ 全量."""
    _install(
        monkeypatch,
        _responder(
            workflow_runs=[{"id": 7, "event": "pull_request", "conclusion": "failure"}]
        ),
    )
    outcome, _ = verify(_COMMIT)
    assert outcome == FULL_REQUIRED


def test_timeout_normalizes_to_full_required(monkeypatch: pytest.MonkeyPatch) -> None:
    """#351 评审 P2：进程超时归一为 full-required，不炸 job。"""
    import subprocess as sp

    def boom(*_args: str, **_kwargs: object) -> Any:
        raise sp.TimeoutExpired(cmd="gh", timeout=60)

    monkeypatch.setattr("tooling.agent_harness.main_evidence.subprocess.run", boom)
    outcome, reasons = verify(_COMMIT)
    assert outcome == FULL_REQUIRED
    assert any("lookup failed" in r for r in reasons)
