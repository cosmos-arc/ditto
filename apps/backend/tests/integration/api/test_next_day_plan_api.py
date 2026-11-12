"""Real HTTP next-day-plan record/reopen routes over isolated SQLite stores."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from dishka import Provider, Scope, make_async_container, provide
from dishka.integrations.fastapi import setup_dishka
from ditto_analysis.storage.sqlite.research import SQLiteNextDayPlanStore
from ditto_application.processes.markets.record_next_day_plan import RecordNextDayPlan
from ditto_application.queries.next_day_plans import NextDayPlanQueryService
from ditto_apps.api.routes.market import router
from ditto_apps.middleware import configure_exception_handlers
from ditto_apps.registry.next_day_plan import (
    AnalysisNextDayPlanFactory,
    AnalysisNextDayPlanStoreAdapter,
)
from ditto_platform.foundation import SQLiteClient, SQLitePool
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _app(path: Path) -> tuple[FastAPI, SQLitePool]:
    pool = SQLitePool(str(path))
    client = SQLiteClient(pool)
    store = SQLiteNextDayPlanStore(client)
    store.init_schema()
    recording_minutes = iter(range(5, 60))

    def _clock() -> datetime:
        return datetime(2026, 11, 10, 15, next(recording_minutes), tzinfo=UTC)

    class TestProvider(Provider):
        scope = Scope.APP

        @provide
        def record_process(self) -> RecordNextDayPlan:
            return RecordNextDayPlan(
                factory=AnalysisNextDayPlanFactory(),
                recorder=AnalysisNextDayPlanStoreAdapter(store),
                clock=_clock,
            )

        @provide
        def plan_query(self) -> NextDayPlanQueryService:
            return NextDayPlanQueryService(AnalysisNextDayPlanStoreAdapter(store))

    app = FastAPI()
    configure_exception_handlers(app)
    setup_dishka(container=make_async_container(TestProvider()), app=app)
    app.include_router(router, prefix="/api/v1")
    return app, pool


def _body() -> dict[str, object]:
    return {
        "observation_date": "2026-11-10",
        "candidate_notes": [
            {"instrument_id": 600779, "reason": "缩量回踩半年线"},
            {"instrument_id": 510888, "reason": "跟随大盘缩量"},
        ],
        "next_day_plan": "次日开盘观察 600779 放量情况",
    }


def test_http_plan_record_reopen_and_original_date_freeze(tmp_path: Path) -> None:
    app, pool = _app(tmp_path / "plans.sqlite")
    try:
        with TestClient(app, raise_server_exceptions=False) as web:
            created = web.post("/api/v1/market/next-day-plans", json=_body())
            assert created.status_code == 201, created.text
            data = created.json()["data"]
            assert data["plan_id"].startswith("next-day-plan:sha256:")
            assert data["observation_date"] == "2026-11-10"
            assert [item["instrument_id"] for item in data["candidate_notes"]] == [
                600779,
                510888,
            ]
            # Exact replay is an idempotent no-op (content addressing).
            replay = web.post("/api/v1/market/next-day-plans", json=_body())
            assert replay.status_code == 201
            assert replay.json()["data"] == data
            # Revisions append as separate immutable entries.
            revised = web.post(
                "/api/v1/market/next-day-plans",
                json={**_body(), "next_day_plan": "改为观察 510888 折溢价"},
            )
            assert revised.status_code == 201
            assert revised.json()["data"]["plan_id"] != data["plan_id"]
            listed = web.get("/api/v1/market/next-day-plans")
            assert listed.status_code == 200, listed.text
            assert [item["plan_id"] for item in listed.json()["data"]] == [
                revised.json()["data"]["plan_id"],
                data["plan_id"],
            ]
            # The original entry keeps its observation date after revisions.
            reopened = web.get(f"/api/v1/market/next-day-plans/{data['plan_id']}")
            assert reopened.status_code == 200
            assert reopened.json()["data"]["observation_date"] == "2026-11-10"
            assert (
                reopened.json()["data"]["next_day_plan"]
                == "次日开盘观察 600779 放量情况"
            )
            # Listing can filter by one exact original observation date.
            by_date = web.get(
                "/api/v1/market/next-day-plans",
                params={"observation_date": "2026-11-10"},
            )
            assert by_date.status_code == 200
            assert len(by_date.json()["data"]) == 2
            empty_day = web.get(
                "/api/v1/market/next-day-plans",
                params={"observation_date": "2026-11-11"},
            )
            assert empty_day.status_code == 200
            assert empty_day.json()["data"] == []
            missing = web.get(
                "/api/v1/market/next-day-plans/next-day-plan:sha256:" + "0" * 64
            )
            assert missing.status_code == 404
            invalid = web.post(
                "/api/v1/market/next-day-plans",
                json={**_body(), "candidate_notes": []},
            )
            assert invalid.status_code == 422
            bad_reason = web.post(
                "/api/v1/market/next-day-plans",
                json={
                    **_body(),
                    "candidate_notes": [{"instrument_id": 600779, "reason": " "}],
                },
            )
            assert bad_reason.status_code == 422
    finally:
        pool.close_all()
    # A clean restart over the same SQLite file reopens the same plans.
    reopened_app, reopened_pool = _app(tmp_path / "plans.sqlite")
    try:
        with TestClient(reopened_app) as web:
            listed = web.get("/api/v1/market/next-day-plans")
            assert listed.status_code == 200
            assert len(listed.json()["data"]) == 2
    finally:
        reopened_pool.close_all()


def test_http_plan_record_accepts_and_echoes_a_source_judgment_reference(
    tmp_path: Path,
) -> None:
    app, pool = _app(tmp_path / "plans.sqlite")
    judgment_id = "research-judgment:sha256:" + "a" * 64
    try:
        with TestClient(app, raise_server_exceptions=False) as web:
            created = web.post(
                "/api/v1/market/next-day-plans",
                json={**_body(), "source_judgment_id": judgment_id},
            )
            assert created.status_code == 201, created.text
            data = created.json()["data"]
            assert data["source_judgment_id"] == judgment_id
            # The source reference is content: the same plan without it is a
            # different identity (the judgment-conclusion path stays distinct).
            plain = web.post("/api/v1/market/next-day-plans", json=_body())
            assert plain.status_code == 201
            assert plain.json()["data"]["plan_id"] != data["plan_id"]
            assert plain.json()["data"]["source_judgment_id"] is None
            # Reopen by id keeps the source; the saved list exposes it too.
            reopened = web.get(f"/api/v1/market/next-day-plans/{data['plan_id']}")
            assert reopened.status_code == 200
            assert reopened.json()["data"]["source_judgment_id"] == judgment_id
            listed = web.get("/api/v1/market/next-day-plans")
            sourced = [
                item
                for item in listed.json()["data"]
                if item["plan_id"] == data["plan_id"]
            ]
            assert sourced
            assert sourced[0]["source_judgment_id"] == judgment_id
            # 非 judgment 身份的来源值 fail closed（DTO 格式合同）。
            malformed = web.post(
                "/api/v1/market/next-day-plans",
                json={**_body(), "source_judgment_id": "next-day-plan:sha256:x"},
            )
            assert malformed.status_code == 422
    finally:
        pool.close_all()
