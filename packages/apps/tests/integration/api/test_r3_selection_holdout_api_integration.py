"""HTTP closure for durable candidate selection followed by one-shot holdout."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from unittest.mock import MagicMock

import httpx
import pytest
from dishka import AsyncContainer, Provider, Scope, make_async_container, provide
from dishka.integrations.fastapi import setup_dishka
from ditto_application.commands.candidate_selection import CandidateSelectionHandler
from ditto_application.commands.experiments import (
    ClaimHoldoutCandidateHandler,
    ExperimentControlNotifier,
)
from ditto_application.processes.experiments._evidence_inputs import (
    project_snapshot_manifest,
)
from ditto_application.processes.experiments.candidate_evidence_reader import (
    CandidateEvidenceReader,
    CandidateEvidenceResourceKind,
    encode_candidate_evidence_cursor,
)
from ditto_apps.api.errors import APIError
from ditto_apps.api.routes import research_candidate_routes as candidate_routes
from ditto_apps.api.routes import research_selection_routes as routes
from ditto_apps.middleware import (
    api_error_handler,
    general_exception_handler,
    validation_exception_handler,
)
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from packages.application.tests.integration import (
    r3_evidence_closure_support as golden_support,
)
from packages.application.tests.integration import (
    test_r3_evidence_closure_golden as golden,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_http_selection_replay_and_one_shot_holdout_are_durable(  # noqa: PLR0915
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lane = next(item for item in golden_support.GOLDEN_LANES if item.lane_id == "stock")
    database, reader, writer, launch, assembler, artifact_service = golden._store(
        tmp_path,
        lane=lane,
    )
    coordinator, store, _collector, selection = golden._coordinator_with_collector(
        reader,
        writer,
        launch,
        assembler,
        artifact_service,
    )
    candidate_handler = CandidateSelectionHandler(coordinator)
    candidate_reader = CandidateEvidenceReader(
        scheduler_store=store,
        walk_forward_assembler=assembler,
        artifact_service=artifact_service,
    )
    holdout_handler = ClaimHoldoutCandidateHandler(
        process=coordinator,
        notifier=MagicMock(spec=ExperimentControlNotifier),
    )

    class TestProvider(Provider):
        scope = Scope.APP

        @provide
        def candidate_selection_handler(self) -> CandidateSelectionHandler:
            return candidate_handler

        @provide
        def holdout_claim_handler(self) -> ClaimHoldoutCandidateHandler:
            return holdout_handler

        @provide
        def candidate_evidence_reader(self) -> CandidateEvidenceReader:
            return candidate_reader

    instants = iter(
        golden.NOW + timedelta(seconds=offset)
        for offset in (34, 35, 36, 37, 38, 39, 40, 41, 42, 43)
    )
    monkeypatch.setattr(routes, "mutation_occurred_at", lambda: next(instants))
    container: AsyncContainer = make_async_container(TestProvider())
    app = FastAPI()
    setup_dishka(container=container, app=app)
    app.include_router(routes.router, prefix="/api/v1")
    app.include_router(candidate_routes.router, prefix="/api/v1")
    app.add_exception_handler(APIError, api_error_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, general_exception_handler)
    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://testserver",
    )
    try:
        snapshot = store.load_snapshot(launch.experiment_id)
        preflight = next(
            event
            for event in reader.list_status_events(launch.experiment_id)
            if event.reason_code == "preflight_passed"
        )
        collected = assembler.assemble(
            snapshot,
            project_snapshot_manifest(preflight.detail),
        )
        selected = next(
            candidate for candidate in launch.candidates if not candidate.is_baseline
        )
        holdout_url = (
            f"/api/v1/research/experiments/{launch.experiment_id}/holdout-evaluations"
        )
        not_preselected = await client.post(
            holdout_url,
            json={
                "candidate_id": str(selected.candidate_id),
                "selection_id": "candidate-selection:not-yet-persisted",
                "expected_selection_evidence_hash": str(selection.record.content_hash),
                "expected_candidate_evidence_content_hash": "f" * 64,
                "expected_revision": snapshot.projection.revision,
                "operator_confirmation": "operator reviewed immutable evidence",
                "selection_reason": {
                    "code": "objective_review",
                    "summary": "candidate won the registered objective review",
                },
            },
            headers={"Idempotency-Key": "holdout-http-not-preselected"},
        )
        assert not_preselected.status_code == 422
        assert not_preselected.json()["error_code"] == "CANDIDATE_NOT_PRESELECTED"
        selection_body = {
            "candidate_id": str(selected.candidate_id),
            "rationale": "candidate won the registered objective review",
            "comparison_payload_hash": str(collected.comparison.content_hash),
            "expected_revision": snapshot.projection.revision,
        }
        selection_url = (
            f"/api/v1/research/experiments/{launch.experiment_id}/candidate-selection"
        )
        missing_key = await client.post(selection_url, json=selection_body)
        assert missing_key.status_code == 422

        selection_headers = {"Idempotency-Key": "selection-http-001"}
        first_selection = await client.post(
            selection_url,
            json=selection_body,
            headers=selection_headers,
        )
        replay_selection = await client.post(
            selection_url,
            json=selection_body,
            headers=selection_headers,
        )
        assert first_selection.status_code == replay_selection.status_code == 200
        assert first_selection.json() == replay_selection.json()
        assert (
            len(
                tuple(
                    event
                    for event in reader.list_status_events(launch.experiment_id)
                    if event.reason_code == "candidate_preselected"
                )
            )
            == 1
        )
        second_selection = await client.post(
            selection_url,
            json=selection_body,
            headers={"Idempotency-Key": "selection-http-002"},
        )
        assert second_selection.status_code == 409
        assert second_selection.json()["error_code"] == ("CANDIDATE_SELECTION_CONFLICT")

        selected_receipt = first_selection.json()["data"]
        drilldown_url = (
            f"/api/v1/research/candidates/{selected.candidate_id}/selections"
        )
        first_page = await client.get(
            drilldown_url,
            params={"experiment_id": str(launch.experiment_id), "limit": 1},
        )
        assert first_page.status_code == 200, first_page.text
        first_page_data = first_page.json()["data"]
        assert (
            first_page_data["content_hash"]
            == selected_receipt["candidate_evidence_content_hash"]
        )
        assert len(first_page_data["items"]) == 1
        assert first_page_data["next_cursor"] is not None
        second_page = await client.get(
            drilldown_url,
            params={
                "experiment_id": str(launch.experiment_id),
                "limit": 1,
                "cursor": first_page_data["next_cursor"],
            },
        )
        assert second_page.status_code == 200, second_page.text
        assert second_page.json()["data"]["items"] != first_page_data["items"]
        cross_kind = await client.get(
            f"/api/v1/research/candidates/{selected.candidate_id}/exclusions",
            params={
                "experiment_id": str(launch.experiment_id),
                "cursor": first_page_data["next_cursor"],
            },
        )
        assert cross_kind.status_code == 422
        assert cross_kind.json()["error_code"] == ("INVALID_CANDIDATE_EVIDENCE_CURSOR")
        stale = await client.get(
            drilldown_url,
            params={
                "experiment_id": str(launch.experiment_id),
                "cursor": encode_candidate_evidence_cursor(
                    content_hash="f" * 64,
                    resource_kind=CandidateEvidenceResourceKind.SELECTIONS,
                    offset=1,
                ),
            },
        )
        assert stale.status_code == 409
        assert stale.json()["error_code"] == "EVIDENCE_STALE"
        restarted_reader = CandidateEvidenceReader(
            scheduler_store=store,
            walk_forward_assembler=assembler,
            artifact_service=artifact_service,
        )
        assert restarted_reader.read_page(
            experiment_id=str(launch.experiment_id),
            candidate_id=str(selected.candidate_id),
            resource_kind=CandidateEvidenceResourceKind.SELECTIONS,
            cursor=None,
            limit=1,
        ) == candidate_reader.read_page(
            experiment_id=str(launch.experiment_id),
            candidate_id=str(selected.candidate_id),
            resource_kind=CandidateEvidenceResourceKind.SELECTIONS,
            cursor=None,
            limit=1,
        )

        holdout_body = {
            "candidate_id": str(selected.candidate_id),
            "selection_id": selected_receipt["selection_id"],
            "expected_selection_evidence_hash": str(selection.record.content_hash),
            "expected_candidate_evidence_content_hash": selected_receipt[
                "candidate_evidence_content_hash"
            ],
            "expected_revision": selected_receipt["revision"],
            "operator_confirmation": "operator reviewed immutable evidence",
            "selection_reason": {
                "code": "objective_review",
                "summary": "candidate won the registered objective review",
            },
        }
        stale_holdout = await client.post(
            holdout_url,
            json={
                **holdout_body,
                "expected_candidate_evidence_content_hash": "f" * 64,
            },
            headers={"Idempotency-Key": "holdout-http-stale-evidence"},
        )
        assert stale_holdout.status_code == 422
        assert stale_holdout.json()["error_code"] == "EVIDENCE_STALE"
        holdout_headers = {"Idempotency-Key": "holdout-http-001"}
        first_holdout = await client.post(
            holdout_url,
            json=holdout_body,
            headers=holdout_headers,
        )
        replay_holdout = await client.post(
            holdout_url,
            json=holdout_body,
            headers=holdout_headers,
        )
        assert first_holdout.status_code == replay_holdout.status_code == 200
        assert first_holdout.json() == replay_holdout.json()
        assert (
            first_holdout.json()["data"]["selection_id"]
            == selected_receipt["selection_id"]
        )
        assert (
            len(
                tuple(
                    event
                    for event in reader.list_status_events(launch.experiment_id)
                    if event.reason_code == "holdout_candidate_claimed"
                )
            )
            == 1
        )
        second_holdout = await client.post(
            holdout_url,
            json=holdout_body,
            headers={"Idempotency-Key": "holdout-http-002"},
        )
        assert second_holdout.status_code == 409
        assert second_holdout.json()["error_code"] == "HOLDOUT_ALREADY_CLAIMED"
    finally:
        await client.aclose()
        await container.close()
        database.close_all()
