"""Production Agent routes plus the production cohort handshake for browser E2E.

The underlying acceptance app owns real SQLite persistence and production Agent
handlers. This test-only composition adds the normal system-status router and an
exact loopback CORS origin so the immutable production Web build can bootstrap.
"""

from __future__ import annotations

from apps.backend.tests.live_acceptance_app import app
from ditto_apps.api.app_metadata import BuildMetadata
from ditto_apps.api.routes.system import router as system_router
from ditto_apps.config.runtime import resolve_cors_origins
from ditto_apps.openapi_contract import canonical_contract_sha256
from ditto_platform.foundation import (
    Environment,
    ObservabilitySettings,
    Settings,
    SystemSettings,
)
from fastapi.middleware.cors import CORSMiddleware

app.state.build_metadata = BuildMetadata.from_environment(
    generated_contract_sha256=canonical_contract_sha256()
)
app.state.settings = Settings(
    system=SystemSettings(environment=Environment.TESTING),
    observability=ObservabilitySettings(
        log_level="WARNING",
        tracing_enabled=False,
        tracing_exporter="none",
        metrics_enabled=False,
        metrics_exporter="none",
    ),
)
app.include_router(system_router)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(resolve_cors_origins()),
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "X-Trace-ID"],
)
