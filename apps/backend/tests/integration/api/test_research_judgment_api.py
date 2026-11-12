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
from ditto_application.queries.strategy import StrategyQueryFacade
from ditto_apps.api.routes.research_judgment_routes import router
from ditto_apps.middleware import configure_exception_handlers
from ditto_apps.registry.research_judgment import (
    AnalysisResearchJudgmentFactory,
    AnalysisResearchJudgmentStoreAdapter,
)
from ditto_platform.foundation import SQLiteClient, SQLitePool
from ditto_strategy.governance.service import GovernanceService
from ditto_strategy.models import StrategySpecRecord
from ditto_strategy.storage.sqlite.services.strategy_catalog_service import (
    StrategyCatalogService,
)
from ditto_strategy.storage.sqlite.strategy_governance_store import (
    SQLiteStrategyGovernanceStore,
)
from ditto_strategy.storage.sqlite.strategy_spec_store import (
    SQLiteStrategySpecReader,
    SQLiteStrategySpecWriter,
)
from fastapi import FastAPI
from fastapi.testclient import TestClient

_STRATEGY_ID = "sys-fx-etf-rotation"
_PUBLISHED_VERSION = 1


def _seed_published_strategy_version(pool: SQLitePool) -> None:
    """Seed one real published strategy version behind the reader port."""
    governance_store = SQLiteStrategyGovernanceStore(pool)
    governance_store.init_schema()
    SQLiteStrategySpecWriter(pool).init_schema()
    if governance_store.get_version(_STRATEGY_ID, _PUBLISHED_VERSION) is not None:
        return  # already seeded by an earlier app instance over the same file
    governance = GovernanceService(governance_store)
    governance.create_draft(
        strategy_id=_STRATEGY_ID,
        version=_PUBLISHED_VERSION,
        spec_record=StrategySpecRecord(
            strategy_id=_STRATEGY_ID,
            name="ETF 轮动-判断验证入口",
            spec_json={"strategy_id": _STRATEGY_ID, "params": {"slow_period": 20}},
        ),
        created_at="2026-11-09T00:00:00Z",
    )
    governance.publish_and_activate(
        strategy_id=_STRATEGY_ID,
        version=_PUBLISHED_VERSION,
        actor="seed",
        reason="test: judgment verification entry",
        decided_at="2026-11-09T00:00:00Z",
    )


def _app(path: Path) -> tuple[FastAPI, SQLitePool]:
    pool = SQLitePool(str(path))
    client = SQLiteClient(pool)
    store = SQLiteResearchJudgmentStore(client)
    store.init_schema()
    _seed_published_strategy_version(pool)
    governance_store = SQLiteStrategyGovernanceStore(pool)
    strategy_query = StrategyQueryFacade(
        catalog_service=StrategyCatalogService(
            reader=SQLiteStrategySpecReader(pool),
            writer=SQLiteStrategySpecWriter(pool),
            active_pointer_reader=governance_store,
            version_state_reader=governance_store,
        ),
        version_state_reader=governance_store,
    )
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
                strategy_version_reader=strategy_query,
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
                    "strategy_id": _STRATEGY_ID,
                    "strategy_version": _PUBLISHED_VERSION,
                },
            )
            assert created.status_code == 201, created.text
            data = created.json()["data"]
            assert data["strategy_id"] == _STRATEGY_ID
            assert data["strategy_version"] == _PUBLISHED_VERSION
            # The strategy reference changes the content identity.
            plain = web.post("/api/v1/research/judgments", json=_body())
            assert plain.status_code == 201
            assert plain.json()["data"]["judgment_id"] != data["judgment_id"]
    finally:
        pool.close_all()


def test_http_judgment_rejects_ghost_strategy_references(tmp_path: Path) -> None:
    """Ghost strategy/version references fail closed before persistence."""
    app, pool = _app(tmp_path / "judgments.sqlite")
    try:
        with TestClient(app, raise_server_exceptions=False) as web:
            ghost_strategy = web.post(
                "/api/v1/research/judgments",
                json={
                    **_body(),
                    "strategy_id": "ghost-strategy",
                    "strategy_version": 7,
                },
            )
            assert ghost_strategy.status_code == 422, ghost_strategy.text
            assert ghost_strategy.json()["error_code"] == "STRATEGY_VERSION_NOT_FOUND"
            ghost_version = web.post(
                "/api/v1/research/judgments",
                json={
                    **_body(),
                    "strategy_id": _STRATEGY_ID,
                    "strategy_version": _PUBLISHED_VERSION + 5,
                },
            )
            assert ghost_version.status_code == 422, ghost_version.text
            assert ghost_version.json()["error_code"] == "STRATEGY_VERSION_NOT_FOUND"
            # Nothing was persisted by the rejected records.
            listed = web.get("/api/v1/research/judgments")
            assert listed.status_code == 200
            assert listed.json()["data"] == []
    finally:
        pool.close_all()
