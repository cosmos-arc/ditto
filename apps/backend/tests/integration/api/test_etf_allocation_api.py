"""ETF allocation save, retry, revision and restore through HTTP and SQLite."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

from dishka import Provider, Scope, make_async_container, provide
from dishka.integrations.fastapi import setup_dishka
from ditto_application.commands.paper_session import PaperSessionCommandReceipt
from ditto_application.etf_paper_handoff import ETFPaperHandoff
from ditto_application.paper_contracts import PaperSessionInfo
from ditto_application.processes.portfolio.etf_allocation import ETFAllocationCommand
from ditto_application.queries.etf_candidates import ETFCandidate, ETFField
from ditto_application.queries.metadata import MetadataQueryFacade
from ditto_apps.api.routes.portfolio_comparison import router
from ditto_apps.middleware import configure_exception_handlers
from ditto_platform.foundation import SQLitePool
from ditto_strategy.storage.sqlite.services.strategy_artifact_service import (
    StrategyArtifactService,
)
from ditto_strategy.storage.sqlite.strategy_artifact_store import (
    SQLiteStrategyArtifactReader,
    SQLiteStrategyArtifactWriter,
)
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _app(path: Path) -> tuple[FastAPI, SQLitePool]:
    pool = SQLitePool(str(path))
    writer = SQLiteStrategyArtifactWriter(pool)
    writer.init_schema()
    metadata = MagicMock(spec=MetadataQueryFacade)
    field = ETFField(
        value="000300.SH",
        unit=None,
        observed_on="2026-09-01",
        published_at="2026-09-01T07:00:00Z",
        source="recorded",
        source_snapshot_id="snapshot:recorded:etf",
        eligibility="RECORDED_REFERENCE_ONLY",
        missing_reason=None,
    )
    metadata.list_etf_candidates.return_value = [
        ETFCandidate(
            instrument_id=i,
            ticker=f"51030{i}",
            name=f"ETF {i}",
            exchange="SSE",
            is_active=True,
            fields={"tracking_index": field},
        )
        for i in (1, 2)
    ]
    service = ETFAllocationCommand(
        metadata, StrategyArtifactService(SQLiteStrategyArtifactReader(pool), writer)
    )
    handoff = MagicMock(spec=ETFPaperHandoff)
    handoff.handoff.side_effect = lambda request: PaperSessionCommandReceipt(
        status="created",
        action="start",
        session=PaperSessionInfo(
            session_id=request.session_id,
            account_id=request.account_id,
            strategy_id=f"etf-allocation:{request.allocation_id}",
            trade_date=request.intended_trade_date,
            status="running",
            revision=1,
            created_at=datetime(2026, 9, 2, tzinfo=UTC),
            updated_at=datetime(2026, 9, 2, tzinfo=UTC),
            pause_reason=None,
        ),
    )

    class TestProvider(Provider):
        scope = Scope.APP

        @provide
        def allocation(self) -> ETFAllocationCommand:
            return service

        @provide
        def etf_handoff(self) -> ETFPaperHandoff:
            return handoff

    app = FastAPI()
    configure_exception_handlers(app)
    setup_dishka(container=make_async_container(TestProvider()), app=app)
    app.include_router(router, prefix="/api/v1")
    return app, pool


def _body() -> dict[str, object]:
    return {
        "asof": "2026-09-01",
        "knowledge_cutoff": "2026-09-01T09:00:00Z",
        "source_snapshot_id": "snapshot:recorded:etf",
        "instrument_ids": [1, 2],
        "mode": "equal",
        "cash_weight": "0.2",
        "max_position_weight": "0.5",
        "manual_weights": {},
        "reason": "broad exposure",
    }


def test_http_allocation_retry_revision_and_restore(tmp_path: Path) -> None:
    path = tmp_path / "allocation.sqlite"
    app, pool = _app(path)
    endpoint = "/api/v1/portfolio/etf-allocations/demo/versions"
    try:
        with TestClient(app) as web:
            first = web.post(endpoint, json=_body(), headers={"Idempotency-Key": "one"})
            assert first.status_code == 201, first.text
            first_data = first.json()["data"]
            assert first_data["weights"] == {"1": "0.40000000", "2": "0.40000000"}
            assert first_data["knowledge_cutoff"] == "2026-09-01T09:00:00Z"
            assert first_data["review_status"] == "research_only"
            assert first_data["paper_status"] == "research_only"
            replay = web.post(
                endpoint, json=_body(), headers={"Idempotency-Key": "one"}
            )
            assert replay.status_code == 201
            assert replay.json()["data"] == first_data
            bad = web.post(
                endpoint,
                json={
                    **_body(),
                    "mode": "manual",
                    "manual_weights": {"1": "0.2", "2": "0.5"},
                    "parent_version_id": first_data["version_id"],
                },
                headers={"Idempotency-Key": "bad"},
            )
            assert bad.status_code == 422
            revised = web.post(
                endpoint,
                json={
                    **_body(),
                    "mode": "manual",
                    "manual_weights": {"1": "0.3", "2": "0.5"},
                    "parent_version_id": first_data["version_id"],
                },
                headers={"Idempotency-Key": "two"},
            )
            assert revised.status_code == 201, revised.text
            assert (
                revised.json()["data"]["parent_version_id"] == first_data["version_id"]
            )
            assert len(web.get(endpoint).json()["data"]) == 2
            review = f"{endpoint}/{first_data['version_id']}/review"
            approval = {"action": "approve", "actor": "operator", "reason": "checked"}
            assert (
                web.post(
                    review, json=approval, headers={"Idempotency-Key": "a"}
                ).status_code
                == 409
            )
            submission = {**approval, "action": "submit"}
            assert (
                web.post(
                    review, json=submission, headers={"Idempotency-Key": "s"}
                ).json()["data"]["review_status"]
                == "review_pending"
            )
            approved = web.post(review, json=approval, headers={"Idempotency-Key": "a"})
            assert approved.status_code == 200, approved.text
            assert approved.json()["data"]["review_status"] == "review_approved"
            assert approved.json()["data"]["paper_status"] == "research_only"
            _check_paper_authorization(web, endpoint, first_data["version_id"])
            assert (
                web.post(review, json=approval, headers={"Idempotency-Key": "a"}).json()
                == approved.json()
            )
            assert (
                web.post(
                    review,
                    json={**approval, "reason": "changed"},
                    headers={"Idempotency-Key": "a"},
                ).status_code
                == 409
            )
            invalid_key = web.post(
                review, json=approval, headers={"Idempotency-Key": "bad key"}
            )
            assert invalid_key.status_code == 422
            assert invalid_key.json()["error_code"] == "IDEMPOTENCY_KEY_INVALID"
    finally:
        pool.close_all()
    reopened, pool = _app(path)
    try:
        with TestClient(reopened) as web:
            versions = web.get(endpoint)
            assert versions.status_code == 200
            assert len(versions.json()["data"]) == 2
            assert any(
                item["review_status"] == "review_approved"
                for item in versions.json()["data"]
            )
    finally:
        pool.close_all()


def _check_paper_authorization(web: TestClient, endpoint: str, version_id: str) -> None:
    authorization = f"{endpoint}/{version_id}/paper-authorizations"
    authorization_body = {
        "actor": "operator",
        "reason": "send this version to Paper",
        "account_id": "paper-a",
        "session_id": "paper-session-a",
        "intended_trade_date": "2026-09-03",
    }
    authorized = web.post(
        authorization,
        json=authorization_body,
        headers={"Idempotency-Key": "paper-consent"},
    )
    assert authorized.status_code == 201, authorized.text
    assert authorized.json()["data"]["version_id"] == version_id
    handoff = web.post(
        f"{endpoint}/{version_id}/paper-handoffs",
        json={
            "authorization_id": authorized.json()["data"]["authorization_id"],
            "account_id": "paper-a",
            "session_id": "paper-session-a",
            "signal_date": "2026-09-02",
            "decision_date": "2026-09-02",
            "intended_trade_date": "2026-09-03",
            "knowledge_cutoff": "2026-09-02T08:00:00Z",
            "source_snapshot_id": "snapshot:recorded:market",
        },
        headers={"Idempotency-Key": "paper-handoff"},
    )
    assert handoff.status_code == 201, handoff.text
    assert handoff.json()["data"]["session"]["strategy_id"] == "etf-allocation:demo"
    assert (
        web.post(
            authorization,
            json=authorization_body,
            headers={"Idempotency-Key": "paper-consent"},
        ).json()
        == authorized.json()
    )
    assert (
        web.post(
            authorization,
            json={**authorization_body, "account_id": "paper-b"},
            headers={"Idempotency-Key": "paper-consent"},
        ).status_code
        == 409
    )
