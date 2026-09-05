"""Unit contracts for immutable candidate evidence drill-down routes."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import cast
from unittest.mock import MagicMock

import pytest
from ditto_application.exceptions import AppProcessError
from ditto_application.processes.experiments.candidate_evidence_reader import (
    CandidateEvidencePage,
    CandidateEvidenceReader,
    CandidateEvidenceResourceKind,
)
from ditto_apps.api.errors import ConflictError, UnprocessableEntityError
from ditto_apps.api.routes import research_candidate_routes as routes
from ditto_apps.models.common import APIResponse
from ditto_apps.models.research import (
    CandidateExclusionPageResponse,
    CandidateFactorContributionPageResponse,
    CandidateSelectionPageResponse,
)

pytestmark = pytest.mark.asyncio

_RouteResult = (
    CandidateSelectionPageResponse
    | CandidateExclusionPageResponse
    | CandidateFactorContributionPageResponse
)
_CandidateRouteError = ConflictError | UnprocessableEntityError
_Route = Callable[..., Awaitable[APIResponse[_RouteResult]]]


@pytest.fixture(autouse=True)
def _inline_candidate_route_bridge(monkeypatch: pytest.MonkeyPatch) -> None:
    async def run_inline(
        func: Callable[..., object], /, *args: object, **kwargs: object
    ) -> object:
        return func(*args, **kwargs)

    monkeypatch.setattr(routes, "run_blocking", run_inline)


def _unwrap(route: Callable[..., object]) -> _Route:
    return cast(_Route, getattr(route, "__dishka_orig_func__", route))


def _page(item: dict[str, object]) -> CandidateEvidencePage:
    return CandidateEvidencePage(
        candidate_id="candidate-1",
        experiment_id="experiment-1",
        artifact_id="candidate-evidence-bundle-v1-abc",
        content_hash="a" * 64,
        items=(item,),
        next_cursor="opaque-next",
    )


@pytest.mark.parametrize(
    ("route", "kind", "item", "expected_type"),
    [
        (
            routes.get_candidate_selections,
            CandidateEvidenceResourceKind.SELECTIONS,
            {
                "validation_fold_ordinal": 2,
                "fold_id": "fold-2",
                "trade_date": "2026-07-30",
                "instrument_id": 600000,
                "score": 1.25,
                "rank": 1,
                "selected": True,
                "evidence_hash": "b" * 64,
            },
            CandidateSelectionPageResponse,
        ),
        (
            routes.get_candidate_exclusions,
            CandidateEvidenceResourceKind.EXCLUSIONS,
            {
                "validation_fold_ordinal": 2,
                "fold_id": "fold-2",
                "trade_date": "2026-07-30",
                "instrument_id": "000001.SZ",
                "stage": "liquidity_filter",
                "reason_code": "insufficient_liquidity",
                "message": "below threshold",
                "evidence_hash": "c" * 64,
            },
            CandidateExclusionPageResponse,
        ),
        (
            routes.get_candidate_factor_contributions,
            CandidateEvidenceResourceKind.FACTOR_CONTRIBUTIONS,
            {
                "validation_fold_ordinal": 2,
                "fold_id": "fold-2",
                "trade_date": "2026-07-30",
                "instrument_id": 600000,
                "factor_id": "momentum_20",
                "contribution": 0.75,
                "rank": 1,
                "selected": True,
                "evidence_hash": "d" * 64,
            },
            CandidateFactorContributionPageResponse,
        ),
    ],
)
async def test_candidate_routes_preserve_bundle_identity_and_typed_items(
    route: Callable[..., object],
    kind: CandidateEvidenceResourceKind,
    item: dict[str, object],
    expected_type: type[_RouteResult],
) -> None:
    reader = MagicMock(spec=CandidateEvidenceReader)
    reader.read_page.return_value = _page(item)

    response = await _unwrap(route)(
        candidate_id="candidate-1",
        reader=reader,
        experiment_id="experiment-1",
        cursor="opaque-current",
        limit=7,
    )

    reader.read_page.assert_called_once_with(
        experiment_id="experiment-1",
        candidate_id="candidate-1",
        resource_kind=kind,
        cursor="opaque-current",
        limit=7,
    )
    assert isinstance(response.data, expected_type)
    assert response.data.artifact_id == "candidate-evidence-bundle-v1-abc"
    assert response.data.content_hash == "a" * 64
    assert response.data.next_cursor == "opaque-next"
    assert len(response.data.items) == 1


@pytest.mark.parametrize(
    ("code", "expected_error"),
    [
        ("INVALID_CANDIDATE_EVIDENCE_CURSOR", UnprocessableEntityError),
        ("EVIDENCE_STALE", ConflictError),
    ],
)
async def test_candidate_route_maps_cursor_failures_exactly(
    code: str,
    expected_error: type[_CandidateRouteError],
) -> None:
    reader = MagicMock(spec=CandidateEvidenceReader)
    reader.read_page.side_effect = AppProcessError(
        "candidate evidence read failed",
        details={"code": code},
    )

    with pytest.raises(expected_error) as exc_info:
        await _unwrap(routes.get_candidate_selections)(
            candidate_id="candidate-1",
            reader=reader,
            experiment_id="experiment-1",
            cursor="bad-cursor",
            limit=20,
        )

    assert exc_info.value.error_code == code
