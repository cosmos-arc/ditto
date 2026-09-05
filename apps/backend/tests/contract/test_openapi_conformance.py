"""Property-based conformance checks for side-effect-free system endpoints."""

from __future__ import annotations

import hashlib
from typing import cast

import schemathesis
from ditto_apps.api.app_metadata import BuildMetadata
from ditto_apps.openapi_contract import canonical_openapi_bytes, create_openapi_app
from ditto_platform.foundation import (
    Environment,
    ObservabilitySettings,
    Settings,
    SystemSettings,
)
from hypothesis import HealthCheck, settings
from schemathesis import Case, CheckFunction
from schemathesis.checks import not_a_server_error

_CONTRACT_APP = create_openapi_app(include_debug=False)
_CONTRACT_APP.state.build_metadata = BuildMetadata(
    product_version="0.1.0",
    git_sha="a" * 40,
    api_contract_version="v1",
    api_contract_sha256=hashlib.sha256(
        canonical_openapi_bytes(_CONTRACT_APP.openapi())
    ).hexdigest(),
)
_CONTRACT_APP.state.settings = Settings(
    system=SystemSettings(environment=Environment.TESTING),
    observability=ObservabilitySettings(),
)
_SYSTEM_SCHEMA = schemathesis.openapi.from_asgi(
    "/openapi.json",
    _CONTRACT_APP,
).include(
    method="GET",
    path_regex=r"^/(?:healthz|readyz|api/v1/status)?$",
)


@_SYSTEM_SCHEMA.parametrize()
@settings(
    max_examples=25,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
def test_side_effect_free_system_endpoints_conform_to_openapi(case: Case) -> None:
    """Generated valid and invalid requests must match documented responses."""
    excluded_checks = (
        [cast(CheckFunction, not_a_server_error)] if case.path == "/readyz" else None
    )
    case.call_and_validate(excluded_checks=excluded_checks)
