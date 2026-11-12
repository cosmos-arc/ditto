"""Real HTTP research judgment routes over an isolated SQLite store."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from dishka import Provider, Scope, make_async_container, provide
from dishka.integrations.fastapi import setup_dishka
from ditto_analysis.storage.sqlite.research import SQLiteResearchJudgmentStore
from ditto_application.processes.research.record_research_judgment import (
    RecordResearchJudgment,
)
from ditto_application.queries.research_judgments import (
    ResearchJudgmentQueryService,
)
from ditto_apps.api.routes.research_judgment_routes import router
from ditto_apps.middleware import configure_exception_handlers
from ditto_apps.registry.research_judgment import (
    AnalysisResearchJudgmentFactory,
    AnalysisResearchJudgmentStoreAdapter,
)
from ditto_platform.foundation import SQLiteClient, SQLitePool
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _app(path: Path) -> tuple[FastAPI, SQLitePool]:
    pool = SQLitePool(str(path))
    client = SQLiteClient(pool)
    store = SQLiteResearchJudgmentStore(client)
    store.init_schema()
    recording_minutes = iter(range(5, 60))

    def _clock() -> datetime:
        return datetime(2026, 11, 10, 15, next(recording_minutes), tzinfo=UTC)

    class TestProvider(Provider):
        scope = Scope.APP

        @provide
        def record_process(self) -> RecordResearchJudgment:
            return RecordResearchJudgment(
                factory=AnalysisResearchJudgmentFactory(),
                recorder=AnalysisResearchJudgmentStoreAdapter(store),
                clock=_clock,
            )

        @provide
        def judgment_query(self) -> ResearchJudgmentQueryService:
            return ResearchJudgmentQueryService(
                AnalysisResearchJudgmentStoreAdapter(store)
            )

    app = FastAPI()
    configure_exception_handlers(app)
    setup_dishka(container=make_async_container(TestProvider()), app=app)
    app.include_router(router, prefix="/api/v1")
    return app, pool


def _body() -> dict[str, object]:
    return {
        "run_ids": ["sys-fx-nav-001", "sys-fx-nav-002"],
        "judgment": "同口径可比; 001 回撤更浅但收益略低, 次日优先观察放量修复",
    }


def test_http_judgment_record_reopen_and_run_identity_freeze(
    tmp_path: Path,
) -> None:
    app, pool = _app(tmp_path / "judgments.sqlite")
    try:
        with TestClient(app, raise_server_exceptions=False) as web:
            created = web.post("/api/v1/research/judgments", json=_body())
            assert created.status_code == 201, created.text
            data = created.json()["data"]
            assert data["judgment_id"].startswith("research-judgment:sha256:")
            assert data["run_ids"] == ["sys-fx-nav-001", "sys-fx-nav-002"]
            assert data["strategy_id"] is None
            assert data["strategy_version"] is None
            # Exact replay is an idempotent no-op (content addressing).
            replay = web.post("/api/v1/research/judgments", json=_body())
            assert replay.status_code == 201
            assert replay.json()["data"] == data
            # Edits append as separate immutable entries.
            revised = web.post(
                "/api/v1/research/judgments",
                json={**_body(), "judgment": "修订: 先核对 002 的费用口径"},
            )
            assert revised.status_code == 201
            assert revised.json()["data"]["judgment_id"] != data["judgment_id"]
            listed = web.get("/api/v1/research/judgments")
            assert listed.status_code == 200, listed.text
            assert [item["judgment_id"] for item in listed.json()["data"]] == [
                revised.json()["data"]["judgment_id"],
                data["judgment_id"],
            ]
            # The saved conclusion reopens by its exact identity and keeps
            # its run bindings; newer runs never rewrite it.
            reopened = web.get(f"/api/v1/research/judgments/{data['judgment_id']}")
            assert reopened.status_code == 200
            assert reopened.json()["data"]["run_ids"] == [
                "sys-fx-nav-001",
                "sys-fx-nav-002",
            ]
            missing = web.get(
                "/api/v1/research/judgments/research-judgment:sha256:" + "0" * 64
            )
            assert missing.status_code == 404
            # Half strategy references and bad formats fail closed.
            invalid_strategy = web.post(
                "/api/v1/research/judgments",
                json={**_body(), "strategy_version": 2},
            )
            assert invalid_strategy.status_code == 422
            duplicate_runs = web.post(
                "/api/v1/research/judgments",
                json={**_body(), "run_ids": ["sys-fx-nav-001", "sys-fx-nav-001"]},
            )
            assert duplicate_runs.status_code == 422
            blank = web.post(
                "/api/v1/research/judgments",
                json={**_body(), "judgment": " "},
            )
            assert blank.status_code == 422
    finally:
        pool.close_all()
    # A clean restart over the same SQLite file reopens the same judgments.
    reopened_app, reopened_pool = _app(tmp_path / "judgments.sqlite")
    try:
        with TestClient(reopened_app) as web:
            listed = web.get("/api/v1/research/judgments")
            assert listed.status_code == 200
            assert len(listed.json()["data"]) == 2
    finally:
        reopened_pool.close_all()


def test_http_judgment_carries_the_follow_up_strategy_reference(
    tmp_path: Path,
) -> None:
    app, pool = _app(tmp_path / "judgments.sqlite")
    try:
        with TestClient(app, raise_server_exceptions=False) as web:
            created = web.post(
                "/api/v1/research/judgments",
                json={
                    **_body(),
                    "strategy_id": "sys-fx-etf-rotation",
                    "strategy_version": 2,
                },
            )
            assert created.status_code == 201, created.text
            data = created.json()["data"]
            assert data["strategy_id"] == "sys-fx-etf-rotation"
            assert data["strategy_version"] == 2
            # The strategy reference changes the content identity.
            plain = web.post("/api/v1/research/judgments", json=_body())
            assert plain.status_code == 201
            assert plain.json()["data"]["judgment_id"] != data["judgment_id"]
    finally:
        pool.close_all()
