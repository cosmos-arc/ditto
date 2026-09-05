"""HTTP request observability contract tests."""

from __future__ import annotations

import asyncio
from collections.abc import Generator
from uuid import UUID

import httpx
import pytest
from ditto_apps.main import app
from ditto_apps.middleware import (
    HTTPObservabilityMiddleware,
    configure_exception_handlers,
)
from ditto_platform.foundation import (
    Environment,
    Metrics,
    ObservabilityConfig,
    get_recorded_spans,
    init,
    logger,
    reset_for_testing,
)
from fastapi import FastAPI
from opentelemetry.trace.status import StatusCode


@pytest.fixture(autouse=True)
def _recording_observability() -> Generator[None]:
    """Give each middleware test isolated, recording OTel providers."""
    reset_for_testing()
    init(
        ObservabilityConfig(
            environment=Environment.TESTING,
            pytest_running=True,
            assertions_enabled=True,
            verbose_logging=False,
            tracing_enabled=True,
            tracing_sample_rate=1.0,
            metrics_enabled=True,
        ),
        force=True,
    )
    yield
    reset_for_testing()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_real_app_correlates_request_span_metrics_and_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The composed app must expose one bounded observability record per request."""
    counter_records: list[tuple[int | float, dict[str, object]]] = []
    duration_records: list[tuple[int | float, dict[str, object]]] = []
    monkeypatch.setattr(
        Metrics.api_requests,
        "add",
        lambda amount, attributes=None: counter_records.append(
            (amount, attributes or {})
        ),
    )
    monkeypatch.setattr(
        Metrics.api_duration,
        "record",
        lambda amount, attributes=None: duration_records.append(
            (amount, attributes or {})
        ),
    )
    inbound_request_id = "123e4567-e89b-42d3-a456-426614174000"

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/healthz",
            headers={"X-Request-ID": inbound_request_id},
        )

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == inbound_request_id
    UUID(response.headers["X-Trace-ID"])
    assert counter_records == [
        (
            1,
            {
                "method": "GET",
                "route": "/healthz",
                "status_code": 200,
            },
        )
    ]
    assert len(duration_records) == 1
    assert duration_records[0][0] >= 0
    assert duration_records[0][1] == counter_records[0][1]

    spans = get_recorded_spans()
    assert [record.name for record in spans] == ["GET /healthz"]
    assert spans[0].kind.name == "SERVER"
    assert spans[0].status.status_code is StatusCode.UNSET
    attributes = dict(spans[0].attributes)
    assert attributes["http.request.method"] == "GET"
    assert attributes["http.route"] == "/healthz"
    assert attributes["http.response.status_code"] == 200
    assert type(attributes["http.response.status_code"]) is int
    assert attributes["ditto.http.outcome"] == "success"
    assert attributes["ditto.request_id"] == inbound_request_id


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "untrusted_request_id",
    [
        "not-a-uuid",
        "123E4567-E89B-42D3-A456-426614174000",
        "123e4567-e89b-42d3-a456-426614174000-extra",
    ],
)
async def test_untrusted_inbound_request_id_is_replaced(
    untrusted_request_id: str,
) -> None:
    """Malformed and non-canonical IDs must never enter logs as correlation IDs."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/healthz",
            headers={"X-Request-ID": untrusted_request_id},
        )

    generated = response.headers["X-Request-ID"]
    assert generated != untrusted_request_id
    assert str(UUID(generated)) == generated


@pytest.mark.unit
@pytest.mark.asyncio
async def test_dynamic_and_unmatched_paths_never_become_metric_dimensions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only router templates or one fixed fallback may label HTTP metrics."""
    records: list[dict[str, object]] = []
    monkeypatch.setattr(
        Metrics.api_requests,
        "add",
        lambda _amount, attributes=None: records.append(attributes or {}),
    )
    test_app = FastAPI()
    test_app.add_middleware(HTTPObservabilityMiddleware)

    @test_app.get("/items/{item_id}")
    async def _item(item_id: str) -> dict[str, str]:
        return {"item_id": item_id}

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=test_app),
        base_url="http://testserver",
    ) as client:
        dynamic = await client.get("/items/attacker-controlled-value")
        missing = await client.get("/missing/attacker-controlled-value")

    assert dynamic.status_code == 200
    assert missing.status_code == 404
    assert [record["route"] for record in records] == [
        "/items/{item_id}",
        "unmatched",
    ]
    assert all("attacker-controlled-value" not in str(record) for record in records)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_request_context_is_bound_to_nested_logs_and_cleared_afterward() -> None:
    """Route logs inherit correlation values without leaking into later work."""
    records: list[dict[str, object]] = []
    sink_id = logger.add(lambda message: records.append(dict(message.record["extra"])))
    test_app = FastAPI()
    test_app.add_middleware(HTTPObservabilityMiddleware)

    @test_app.get("/logged")
    async def _logged() -> dict[str, bool]:
        logger.info("nested route log", event="nested_route_log")
        return {"ok": True}

    inbound_request_id = "123e4567-e89b-42d3-a456-426614174000"
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=test_app),
            base_url="http://testserver",
        ) as client:
            response = await client.get(
                "/logged",
                headers={"X-Request-ID": inbound_request_id},
            )
        logger.info("outside request", event="outside_request")
    finally:
        logger.remove(sink_id)

    nested = next(
        record for record in records if record.get("event") == "nested_route_log"
    )
    outside = next(
        record for record in records if record.get("event") == "outside_request"
    )
    assert nested["request_id"] == inbound_request_id
    assert nested["trace_id"] == response.headers["X-Trace-ID"]
    assert "request_id" not in outside
    assert "trace_id" not in outside


@pytest.mark.unit
@pytest.mark.asyncio
async def test_unhandled_failure_returns_correlated_500_and_closes_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The generic 500 response retains its request/trace correlation evidence."""
    records: list[dict[str, object]] = []
    monkeypatch.setattr(
        Metrics.api_requests,
        "add",
        lambda _amount, attributes=None: records.append(attributes or {}),
    )
    test_app = FastAPI()
    test_app.add_middleware(HTTPObservabilityMiddleware)

    @test_app.get("/fail")
    async def _fail() -> None:
        raise RuntimeError("boom")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=test_app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/fail")

    assert response.status_code == 500
    assert response.json()["request_id"] == response.headers["X-Request-ID"]
    UUID(response.headers["X-Trace-ID"])
    assert records == [
        {
            "method": "GET",
            "route": "/fail",
            "status_code": 500,
        }
    ]
    spans = get_recorded_spans()
    assert [record.name for record in spans] == ["GET /fail"]
    assert spans[0].kind.name == "SERVER"
    assert spans[0].status.status_code is StatusCode.ERROR
    assert spans[0].attributes["http.response.status_code"] == 500
    assert spans[0].attributes["ditto.http.outcome"] == "error"
    assert any(event.name == "exception" for event in spans[0].events)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cancellation_propagates_after_closing_observability_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cancellation remains cooperative while still producing bounded evidence."""
    records: list[dict[str, object]] = []
    monkeypatch.setattr(
        Metrics.api_requests,
        "add",
        lambda _amount, attributes=None: records.append(attributes or {}),
    )
    test_app = FastAPI()
    test_app.add_middleware(HTTPObservabilityMiddleware)

    @test_app.get("/cancel")
    async def _cancel() -> None:
        raise asyncio.CancelledError

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=test_app),
        base_url="http://testserver",
    ) as client:
        with pytest.raises(asyncio.CancelledError):
            await client.get("/cancel")

    assert records == [{"method": "GET", "route": "/cancel", "status_code": 499}]
    spans = get_recorded_spans()
    assert [record.name for record in spans] == ["GET /cancel"]
    assert spans[0].kind.name == "SERVER"
    assert spans[0].status.status_code is StatusCode.ERROR
    assert spans[0].attributes["http.response.status_code"] == 499
    assert spans[0].attributes["ditto.http.outcome"] == "cancelled"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_unknown_method_is_bounded_in_metrics_logs_and_spans(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Untrusted method tokens must not become aggregation dimensions."""
    metric_records: list[dict[str, object]] = []
    log_records: list[dict[str, object]] = []
    monkeypatch.setattr(
        Metrics.api_requests,
        "add",
        lambda _amount, attributes=None: metric_records.append(attributes or {}),
    )
    sink_id = logger.add(
        lambda message: log_records.append(dict(message.record["extra"]))
    )
    test_app = FastAPI()
    configure_exception_handlers(test_app)
    test_app.add_middleware(HTTPObservabilityMiddleware)

    @test_app.get("/known")
    async def _known() -> dict[str, bool]:
        return {"ok": True}

    untrusted_method = "BREACH999"
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=test_app),
            base_url="http://testserver",
        ) as client:
            response = await client.request(untrusted_method, "/known")
    finally:
        logger.remove(sink_id)

    assert response.status_code == 405
    assert metric_records == [
        {"method": "_OTHER", "route": "/known", "status_code": 405}
    ]
    request_logs = [record for record in log_records if "method" in record]
    assert request_logs
    assert all(record["method"] == "_OTHER" for record in request_logs)
    spans = get_recorded_spans()
    assert [record.name for record in spans] == ["_OTHER /known"]
    assert spans[0].kind.name == "SERVER"
    assert spans[0].attributes["http.request.method"] == "_OTHER"
    assert untrusted_method not in str((metric_records, log_records, spans[0]))


@pytest.mark.unit
@pytest.mark.asyncio
async def test_duration_covers_stream_completion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The pure ASGI middleware times the response body, not only its headers."""
    stream_finished = False
    clock_calls = 0
    durations: list[int | float] = []

    def _clock() -> float:
        nonlocal clock_calls
        clock_calls += 1
        if clock_calls == 1:
            return 10.0
        assert stream_finished is True
        return 10.5

    monkeypatch.setattr(
        Metrics.api_duration,
        "record",
        lambda amount, _attributes=None: durations.append(amount),
    )
    test_app = FastAPI()
    test_app.add_middleware(HTTPObservabilityMiddleware, monotonic=_clock)

    async def _body():
        nonlocal stream_finished
        yield b"first"
        stream_finished = True
        yield b"second"

    from starlette.responses import StreamingResponse

    @test_app.get("/stream")
    async def _stream() -> StreamingResponse:
        return StreamingResponse(_body())

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=test_app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/stream")

    assert response.content == b"firstsecond"
    assert durations == [0.5]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_readiness_is_observed_even_when_it_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A 503 readiness response is still correlated and measured by route."""
    records: list[dict[str, object]] = []
    monkeypatch.setattr(
        Metrics.api_requests,
        "add",
        lambda _amount, attributes=None: records.append(attributes or {}),
    )
    app.state.runtime_initialized = False

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/readyz")

    assert response.status_code == 503
    assert UUID(response.headers["X-Request-ID"])
    assert UUID(response.headers["X-Trace-ID"])
    assert records == [{"method": "GET", "route": "/readyz", "status_code": 503}]
