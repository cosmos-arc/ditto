"""Unit tests for cancel / retry route endpoints.

Tests call Dishka-wrapped route handlers directly so blocking route bridges can
be kept inline and deterministic under Python 3.13.

Coverage:
  - Cancel: status guards (pending/running allowed, completed/failed/cancelled rejected)
  - Cancel: not found → 404
  - Retry: status guards (failed/cancelled allowed, running/completed/pending rejected)
  - Retry: not found → 404
  - Response field validation
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import cast
from unittest.mock import MagicMock

import pytest
from ditto_application.commands.backtest import (
    CancelRunCommand,
    CancelRunHandler,
    ResumeRunCommand,
    ResumeRunHandler,
    RetryRunCommand,
    RetryRunHandler,
)
from ditto_application.exceptions import AppCommandError
from ditto_application.processes.execution.strategy_types import RunLifecycleService
from ditto_application.queries.backtest import (
    BacktestQueryFacade,
    ReplayEvidenceSummary,
    RunSummary,
)
from ditto_apps.api.errors import APIError
from ditto_apps.api.routes.backtest_query_routes import (
    get_replay_evidence_summary,
    get_replay_proof,
    get_report,
)
from ditto_apps.api.routes.backtest_run_routes import cancel_run, resume_run, retry_run
from ditto_apps.models.backtest import (
    BacktestReportResponse,
    CancelRunResponse,
    ResumeRunResponse,
    RetryRunResponse,
)
from ditto_apps.models.common import APIResponse
from ditto_apps.models.lineage import ReplayEvidenceSummaryResponse, ReplayProofResponse

pytestmark = pytest.mark.asyncio

_CancelRoute = Callable[..., Awaitable[APIResponse[CancelRunResponse]]]
_RetryRoute = Callable[..., Awaitable[APIResponse[RetryRunResponse]]]
_ResumeRoute = Callable[..., Awaitable[APIResponse[ResumeRunResponse]]]
_ReportRoute = Callable[..., Awaitable[APIResponse[BacktestReportResponse]]]
_ReplayProofRoute = Callable[..., Awaitable[APIResponse[ReplayProofResponse]]]
_ReplayEvidenceRoute = Callable[
    ...,
    Awaitable[APIResponse[ReplayEvidenceSummaryResponse]],
]

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_cancel_handler() -> MagicMock:
    return MagicMock(spec=CancelRunHandler)


@pytest.fixture
def mock_retry_handler() -> MagicMock:
    return MagicMock(spec=RetryRunHandler)


@pytest.fixture
def mock_resume_handler() -> MagicMock:
    return MagicMock(spec=ResumeRunHandler)


@pytest.fixture
def mock_query_facade() -> MagicMock:
    return MagicMock(spec=BacktestQueryFacade)


@pytest.fixture
def mock_run_service() -> MagicMock:
    return MagicMock(spec=RunLifecycleService)


@pytest.fixture(autouse=True)
def _inline_backtest_route_thread_bridge(monkeypatch: pytest.MonkeyPatch) -> None:
    async def run_inline(
        func: Callable[..., object], /, *args: object, **kwargs: object
    ) -> object:
        return func(*args, **kwargs)

    monkeypatch.setattr(
        "ditto_apps.api.routes.backtest_run_routes.run_blocking", run_inline
    )
    monkeypatch.setattr(
        "ditto_apps.api.routes.backtest_query_routes.run_blocking",
        run_inline,
    )
    monkeypatch.setattr(
        "ditto_apps.api.routes.backtest_run_routes.submit_backtest_flow",
        lambda *, flow_params, on_failure: None,
    )


async def _call_cancel(
    run_id: str,
    handler: CancelRunHandler,
) -> APIResponse[CancelRunResponse]:
    route = cast(_CancelRoute, getattr(cancel_run, "__dishka_orig_func__", cancel_run))
    return await route(run_id=run_id, handler=handler)


async def _call_retry(
    run_id: str,
    facade: BacktestQueryFacade,
    handler: RetryRunHandler,
    run_service: RunLifecycleService,
) -> APIResponse[RetryRunResponse]:
    route = cast(_RetryRoute, getattr(retry_run, "__dishka_orig_func__", retry_run))
    return await route(
        run_id=run_id,
        facade=facade,
        handler=handler,
        run_service=run_service,
    )


async def _call_resume(
    run_id: str,
    facade: BacktestQueryFacade,
    handler: ResumeRunHandler,
    run_service: RunLifecycleService,
) -> APIResponse[ResumeRunResponse]:
    route = cast(_ResumeRoute, getattr(resume_run, "__dishka_orig_func__", resume_run))
    return await route(
        run_id=run_id,
        facade=facade,
        handler=handler,
        run_service=run_service,
    )


async def _call_report(
    run_id: str,
    facade: BacktestQueryFacade,
) -> APIResponse[BacktestReportResponse]:
    route = cast(_ReportRoute, getattr(get_report, "__dishka_orig_func__", get_report))
    return await route(run_id=run_id, facade=facade)


async def _call_replay_proof(
    run_id: str,
    facade: BacktestQueryFacade,
) -> APIResponse[ReplayProofResponse]:
    route = cast(
        _ReplayProofRoute,
        getattr(get_replay_proof, "__dishka_orig_func__", get_replay_proof),
    )
    return await route(run_id=run_id, facade=facade)


async def _call_replay_evidence(
    run_id: str,
    facade: BacktestQueryFacade,
) -> APIResponse[ReplayEvidenceSummaryResponse]:
    route = cast(
        _ReplayEvidenceRoute,
        getattr(
            get_replay_evidence_summary,
            "__dishka_orig_func__",
            get_replay_evidence_summary,
        ),
    )
    return await route(run_id=run_id, facade=facade)


# ---------------------------------------------------------------------------
# Cancel: status guards
# ---------------------------------------------------------------------------


class TestCancelStatusGuard:
    """Cancel 端点 — 状态前置校验."""

    async def test_cancel_running_succeeds(
        self,
        mock_cancel_handler: MagicMock,
    ) -> None:
        """status=running → 200, handler.handle 被调用."""
        mock_cancel_handler.handle.return_value = None
        response = await _call_cancel("run001", mock_cancel_handler)
        mock_cancel_handler.handle.assert_called_once_with(
            CancelRunCommand(run_id="run001"),
        )
        assert response.data.run_id == "run001"
        assert response.data.status == "cancelled"

    async def test_cancel_pending_succeeds(
        self,
        mock_cancel_handler: MagicMock,
    ) -> None:
        """status=pending → 200."""
        mock_cancel_handler.handle.return_value = None
        response = await _call_cancel("run002", mock_cancel_handler)
        assert response.data.run_id == "run002"

    async def test_cancel_completed_rejected(
        self,
        mock_cancel_handler: MagicMock,
    ) -> None:
        """status=completed → 409 Conflict."""
        mock_cancel_handler.handle.side_effect = AppCommandError(
            "Cannot cancel run in 'completed' status"
        )
        with pytest.raises(APIError) as exc_info:
            await _call_cancel("run003", mock_cancel_handler)
        assert exc_info.value.status_code == 409
        assert "completed" in exc_info.value.message

    async def test_cancel_failed_rejected(
        self,
        mock_cancel_handler: MagicMock,
    ) -> None:
        """status=failed → 409 Conflict."""
        mock_cancel_handler.handle.side_effect = AppCommandError(
            "Cannot cancel run in 'failed' status"
        )
        with pytest.raises(APIError) as exc_info:
            await _call_cancel("run004", mock_cancel_handler)
        assert exc_info.value.status_code == 409
        assert "failed" in exc_info.value.message

    async def test_cancel_already_cancelled_rejected(
        self,
        mock_cancel_handler: MagicMock,
    ) -> None:
        """status=cancelled → 409 Conflict."""
        mock_cancel_handler.handle.side_effect = AppCommandError(
            "Cannot cancel run in 'cancelled' status"
        )
        with pytest.raises(APIError) as exc_info:
            await _call_cancel("run005", mock_cancel_handler)
        assert exc_info.value.status_code == 409


# ---------------------------------------------------------------------------
# Cancel: not found
# ---------------------------------------------------------------------------


class TestCancelNotFound:
    """Cancel 端点 — run_id 不存在 → 404."""

    async def test_cancel_not_found(
        self,
        mock_cancel_handler: MagicMock,
    ) -> None:
        """取消不存在的 run → 404."""
        mock_cancel_handler.handle.side_effect = AppCommandError(
            "Run not found: missing"
        )
        with pytest.raises(APIError) as exc_info:
            await _call_cancel("missing", mock_cancel_handler)
        assert exc_info.value.status_code == 404
        assert "not found" in exc_info.value.message.lower()


# ---------------------------------------------------------------------------
# Retry: status guards
# ---------------------------------------------------------------------------


class TestRetryStatusGuard:
    """Retry 端点 — 状态前置校验."""

    async def test_retry_failed_succeeds(
        self,
        mock_retry_handler: MagicMock,
        mock_query_facade: MagicMock,
        mock_run_service: MagicMock,
    ) -> None:
        """status=failed → 202, handler 返回新 run_id."""
        mock_retry_handler.handle.return_value = "run002"
        mock_query_facade.get_run.return_value = RunSummary(
            run_id="run002",
            strategy_id="momentum-etf",
        )
        response = await _call_retry(
            "run001",
            mock_query_facade,
            mock_retry_handler,
            mock_run_service,
        )
        mock_retry_handler.handle.assert_called_once_with(
            RetryRunCommand(run_id="run001"),
        )
        assert response.data.run_id == "run002"
        assert response.data.parent_run_id == "run001"
        assert response.data.status == "pending"

    async def test_retry_cancelled_succeeds(
        self,
        mock_retry_handler: MagicMock,
        mock_query_facade: MagicMock,
        mock_run_service: MagicMock,
    ) -> None:
        """status=cancelled → 202."""
        mock_retry_handler.handle.return_value = "run003"
        mock_query_facade.get_run.return_value = RunSummary(
            run_id="run003",
            strategy_id="momentum-etf",
        )
        response = await _call_retry(
            "run002",
            mock_query_facade,
            mock_retry_handler,
            mock_run_service,
        )
        assert response.data.run_id == "run003"

    async def test_retry_passes_parent_run_id_to_flow(
        self,
        mock_retry_handler: MagicMock,
        mock_query_facade: MagicMock,
        mock_run_service: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """retry 路由应将 parent_run_id 传入 flow_params."""
        submitted: dict[str, object] = {}

        def capture_submit(*, flow_params, on_failure) -> None:
            submitted.update(flow_params)

        monkeypatch.setattr(
            "ditto_apps.api.routes.backtest_run_routes.submit_backtest_flow",
            capture_submit,
        )
        mock_retry_handler.handle.return_value = "run002"
        mock_query_facade.get_run.return_value = RunSummary(
            run_id="run002",
            strategy_id="momentum-etf",
            config_json='{"start_date":"2025-01-01","end_date":"2025-03-31"}',
        )

        await _call_retry(
            "run001",
            mock_query_facade,
            mock_retry_handler,
            mock_run_service,
        )

        assert submitted["parent_run_id"] == "run001"

    async def test_retry_running_rejected(
        self,
        mock_retry_handler: MagicMock,
        mock_query_facade: MagicMock,
        mock_run_service: MagicMock,
    ) -> None:
        """status=running → 409 Conflict."""
        mock_retry_handler.handle.side_effect = AppCommandError(
            "Cannot retry run in 'running' status"
        )
        with pytest.raises(APIError) as exc_info:
            await _call_retry(
                "run003",
                mock_query_facade,
                mock_retry_handler,
                mock_run_service,
            )
        assert exc_info.value.status_code == 409
        assert "running" in exc_info.value.message

    async def test_retry_completed_rejected(
        self,
        mock_retry_handler: MagicMock,
        mock_query_facade: MagicMock,
        mock_run_service: MagicMock,
    ) -> None:
        """status=completed → 409 Conflict."""
        mock_retry_handler.handle.side_effect = AppCommandError(
            "Cannot retry run in 'completed' status"
        )
        with pytest.raises(APIError) as exc_info:
            await _call_retry(
                "run004",
                mock_query_facade,
                mock_retry_handler,
                mock_run_service,
            )
        assert exc_info.value.status_code == 409

    async def test_retry_pending_rejected(
        self,
        mock_retry_handler: MagicMock,
        mock_query_facade: MagicMock,
        mock_run_service: MagicMock,
    ) -> None:
        """status=pending → 409 Conflict."""
        mock_retry_handler.handle.side_effect = AppCommandError(
            "Cannot retry run in 'pending' status"
        )
        with pytest.raises(APIError) as exc_info:
            await _call_retry(
                "run005",
                mock_query_facade,
                mock_retry_handler,
                mock_run_service,
            )
        assert exc_info.value.status_code == 409


# ---------------------------------------------------------------------------
# Retry: not found
# ---------------------------------------------------------------------------


class TestRetryNotFound:
    """Retry 端点 — run_id 不存在 → 404."""

    async def test_retry_not_found(
        self,
        mock_retry_handler: MagicMock,
        mock_query_facade: MagicMock,
        mock_run_service: MagicMock,
    ) -> None:
        """重试不存在的 run → 404."""
        mock_retry_handler.handle.side_effect = AppCommandError(
            "Run not found: missing"
        )
        with pytest.raises(APIError) as exc_info:
            await _call_retry(
                "missing",
                mock_query_facade,
                mock_retry_handler,
                mock_run_service,
            )
        assert exc_info.value.status_code == 404
        assert "not found" in exc_info.value.message.lower()


class TestResumeStatusGuard:
    """Resume 端点 — checkpoint-backed child run 提交。"""

    async def test_resume_cancelled_succeeds_and_submits_resumed_flow(
        self,
        mock_resume_handler: MagicMock,
        mock_query_facade: MagicMock,
        mock_run_service: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """status=cancelled + checkpoint → 202，并提交 resume_from 后的 flow。"""
        submitted: dict[str, object] = {}

        def capture_submit(*, flow_params, on_failure) -> None:
            submitted.update(flow_params)

        monkeypatch.setattr(
            "ditto_apps.api.routes.backtest_run_routes.submit_backtest_flow",
            capture_submit,
        )
        mock_resume_handler.handle.return_value = "run-resume"
        mock_query_facade.get_run.return_value = RunSummary(
            run_id="run-resume",
            strategy_id="momentum-etf",
            config_json=(
                '{"start_date":"2025-02-03","end_date":"2025-03-31",'
                '"initial_cash":1000000.0,"allow_experimental_data":true,'
                '"resume_from_run_id":"run001",'
                '"resume_checkpoint_trade_date":"2025-01-31",'
                '"resume_checkpoint_completed_days":21,'
                '"resume_checkpoint_total_days":60,'
                '"resume_checkpoint_nav":1020000.0,'
                '"resume_checkpoint_order_count":4,'
                '"resume_checkpoint_fill_count":4,'
                '"resume_account_state_hash":"sha256:account",'
                '"resume_settlement_state_hash":"sha256:settlement",'
                '"resume_runtime_state_hash":"sha256:runtime"}'
            ),
        )

        response = await _call_resume(
            "run001",
            mock_query_facade,
            mock_resume_handler,
            mock_run_service,
        )

        mock_resume_handler.handle.assert_called_once_with(
            ResumeRunCommand(run_id="run001"),
        )
        assert response.data.run_id == "run-resume"
        assert response.data.parent_run_id == "run001"
        assert response.data.status == "pending"
        assert submitted["run_id"] == "run-resume"
        assert submitted["strategy_id"] == "momentum-etf"
        assert submitted["start_date"] == "2025-02-03"
        assert submitted["end_date"] == "2025-03-31"
        assert submitted["allow_experimental_data"] is True
        assert submitted["resume_from_run_id"] == "run001"
        assert submitted["resume_checkpoint_trade_date"] == "2025-01-31"
        assert submitted["resume_checkpoint_completed_days"] == 21
        assert submitted["resume_checkpoint_nav"] == 1_020_000.0
        assert submitted["resume_account_state_hash"] == "sha256:account"
        assert submitted["resume_runtime_state_hash"] == "sha256:runtime"

    async def test_resume_passes_parent_run_id_to_flow(
        self,
        mock_resume_handler: MagicMock,
        mock_query_facade: MagicMock,
        mock_run_service: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """resume 路由应将 parent_run_id 传入 flow_params."""
        submitted: dict[str, object] = {}

        def capture_submit(*, flow_params, on_failure) -> None:
            submitted.update(flow_params)

        monkeypatch.setattr(
            "ditto_apps.api.routes.backtest_run_routes.submit_backtest_flow",
            capture_submit,
        )
        mock_resume_handler.handle.return_value = "run-resume"
        mock_query_facade.get_run.return_value = RunSummary(
            run_id="run-resume",
            strategy_id="momentum-etf",
            config_json='{"start_date":"2025-02-03","end_date":"2025-03-31"}',
        )

        await _call_resume(
            "run001",
            mock_query_facade,
            mock_resume_handler,
            mock_run_service,
        )

        assert submitted["parent_run_id"] == "run001"

    async def test_resume_missing_checkpoint_rejected(
        self,
        mock_resume_handler: MagicMock,
        mock_query_facade: MagicMock,
        mock_run_service: MagicMock,
    ) -> None:
        """没有可恢复 checkpoint → 409 Conflict。"""
        mock_resume_handler.handle.side_effect = AppCommandError(
            "No resumable checkpoint for run: run001"
        )

        with pytest.raises(APIError) as exc_info:
            await _call_resume(
                "run001",
                mock_query_facade,
                mock_resume_handler,
                mock_run_service,
            )

        assert exc_info.value.status_code == 409
        assert "checkpoint" in exc_info.value.message

    async def test_resume_not_found(
        self,
        mock_resume_handler: MagicMock,
        mock_query_facade: MagicMock,
        mock_run_service: MagicMock,
    ) -> None:
        """恢复不存在的 run → 404。"""
        mock_resume_handler.handle.side_effect = AppCommandError(
            "Run not found: missing"
        )

        with pytest.raises(APIError) as exc_info:
            await _call_resume(
                "missing",
                mock_query_facade,
                mock_resume_handler,
                mock_run_service,
            )

        assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# Report endpoint
# ---------------------------------------------------------------------------


class TestGetReport:
    """GET /runs/{run_id}/report 端点测试 (F12)."""

    async def test_report_found(
        self,
        mock_query_facade: MagicMock,
    ) -> None:
        """报告存在时返回 200 + JSON data."""
        mock_query_facade.get_report.return_value = {
            "run_id": "run-001",
            "alpha_stats": {"annualized_return": 12.5},
        }
        response = await _call_report("run-001", mock_query_facade)
        assert response.data.run_id == "run-001"
        assert response.data.alpha_stats.annualized_return == 12.5

    async def test_report_not_found(
        self,
        mock_query_facade: MagicMock,
    ) -> None:
        """报告不存在时返回 404."""
        mock_query_facade.get_report.return_value = None
        with pytest.raises(APIError) as exc_info:
            await _call_report("nonexistent", mock_query_facade)
        assert exc_info.value.status_code == 404
        assert "not found" in exc_info.value.message.lower()

    async def test_report_delegates_to_facade(
        self,
        mock_query_facade: MagicMock,
    ) -> None:
        """验证正确委托给 facade.get_report."""
        mock_query_facade.get_report.return_value = {"run_id": "run-001"}
        await _call_report("run-001", mock_query_facade)
        mock_query_facade.get_report.assert_called_once_with("run-001")


# ---------------------------------------------------------------------------
# Replay proof endpoint
# ---------------------------------------------------------------------------


class TestGetReplayProof:
    """GET /runs/{run_id}/replay/proof 端点测试."""

    async def test_replay_proof_found(
        self,
        mock_query_facade: MagicMock,
    ) -> None:
        """proof 存在时返回结构化响应."""
        mock_query_facade.get_replay_proof.return_value = {
            "proof_version": 1,
            "created_at": "2026-06-02T00:00:00Z",
            "original_run_id": "run-original",
            "replay_run_id": "run-replay",
            "is_reproducible": True,
            "nav_correlation": 1.0,
            "max_nav_diff_bps": 0.0,
            "input_data_match": True,
            "manifest_diff": {
                "config_diffs": [],
                "data_diffs": [],
                "version_diffs": [],
                "seed_diffs": [],
                "has_diff": False,
            },
            "fill_match": None,
            "account_state_match": None,
            "fill_comparison": None,
            "account_state_comparison": None,
            "original_resume_provenance": {
                "from_run_id": "run-root",
                "checkpoint_trade_date": "2026-01-31",
                "account_state_hash": "sha256:account",
            },
        }

        response = await _call_replay_proof("run-replay", mock_query_facade)

        assert response.data.replay_run_id == "run-replay"
        assert response.data.original_run_id == "run-original"
        assert response.data.is_reproducible is True
        assert response.data.manifest_diff.has_diff is False
        assert response.data.fill_match is None
        assert response.data.original_resume_provenance == {
            "from_run_id": "run-root",
            "checkpoint_trade_date": "2026-01-31",
            "account_state_hash": "sha256:account",
        }

    async def test_replay_proof_not_found(
        self,
        mock_query_facade: MagicMock,
    ) -> None:
        """proof 不存在时返回 404."""
        mock_query_facade.get_replay_proof.return_value = None

        with pytest.raises(APIError) as exc_info:
            await _call_replay_proof("missing", mock_query_facade)

        assert exc_info.value.status_code == 404
        assert "proof" in exc_info.value.message.lower()


# ---------------------------------------------------------------------------
# Replay evidence summary endpoint
# ---------------------------------------------------------------------------


class TestGetReplayEvidenceSummary:
    """GET /runs/{run_id}/replay/evidence 端点测试."""

    async def test_replay_evidence_summary_found(
        self,
        mock_query_facade: MagicMock,
    ) -> None:
        """summary 存在时返回 restored-report + replay-proof 汇总."""
        resume_provenance = {
            "from_run_id": "run-root",
            "checkpoint_trade_date": "2026-01-31",
            "account_state_hash": "sha256:account",
        }
        mock_query_facade.get_replay_evidence_summary.return_value = (
            ReplayEvidenceSummary(
                run_id="run-replay",
                original_run_id="run-restored",
                replay_run_id="run-replay",
                is_reproducible=True,
                input_data_match=True,
                fill_match=True,
                account_state_match=True,
                report_resume_provenance=resume_provenance,
                proof_resume_provenance=resume_provenance,
                resume_provenance_match=True,
                missing_sections=(),
            )
        )

        response = await _call_replay_evidence("run-replay", mock_query_facade)

        assert response.data.run_id == "run-replay"
        assert response.data.original_run_id == "run-restored"
        assert response.data.replay_run_id == "run-replay"
        assert response.data.is_reproducible is True
        assert response.data.fill_match is True
        assert response.data.account_state_match is True
        assert response.data.report_resume_provenance == resume_provenance
        assert response.data.proof_resume_provenance == resume_provenance
        assert response.data.resume_provenance_match is True
        assert response.data.missing_sections == []

    async def test_replay_evidence_summary_not_found(
        self,
        mock_query_facade: MagicMock,
    ) -> None:
        """summary 不存在时返回 404."""
        mock_query_facade.get_replay_evidence_summary.return_value = None

        with pytest.raises(APIError) as exc_info:
            await _call_replay_evidence("missing", mock_query_facade)

        assert exc_info.value.status_code == 404
        assert "evidence" in exc_info.value.message.lower()
