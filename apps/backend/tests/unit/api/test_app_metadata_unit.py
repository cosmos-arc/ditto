"""Build and API contract metadata tests."""

import pytest
from ditto_apps.api.app_metadata import APP_VERSION, BuildMetadata
from ditto_apps.openapi_contract import configure_openapi, create_openapi_app
from fastapi import FastAPI
from fastapi.routing import APIRoute


def test_build_metadata_uses_deployment_values() -> None:
    metadata = BuildMetadata.from_environment(
        {
            "DITTO_PRODUCT_VERSION": "2026.9.4",
            "DITTO_GIT_SHA": "d" * 40,
            "DITTO_API_CONTRACT_VERSION": "v1",
            "DITTO_API_CONTRACT_SHA256": "a" * 64,
        },
        generated_contract_sha256="a" * 64,
        production=True,
    )

    assert metadata.product_version == "2026.9.4"
    assert metadata.git_sha == "d" * 40
    assert metadata.api_contract_version == "v1"
    assert metadata.api_contract_sha256 == "a" * 64


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"DITTO_GIT_SHA": "deadbeef"}, "DITTO_GIT_SHA"),
        ({"DITTO_GIT_SHA": "D" * 40}, "DITTO_GIT_SHA"),
        ({"DITTO_API_CONTRACT_VERSION": "v1.7"}, "DITTO_API_CONTRACT_VERSION"),
        ({"DITTO_API_CONTRACT_SHA256": "not-a-hash"}, "DITTO_API_CONTRACT_SHA256"),
        ({"DITTO_API_CONTRACT_SHA256": "A" * 64}, "DITTO_API_CONTRACT_SHA256"),
        ({"DITTO_API_CONTRACT_SHA256": "c" * 64}, "canonical contract"),
    ],
)
def test_build_metadata_rejects_invalid_or_drifted_deployment_values(
    override: dict[str, str],
    message: str,
) -> None:
    values = {
        "DITTO_PRODUCT_VERSION": "2026.9.4",
        "DITTO_GIT_SHA": "d" * 40,
        "DITTO_API_CONTRACT_VERSION": "v1",
        "DITTO_API_CONTRACT_SHA256": "a" * 64,
        **override,
    }

    with pytest.raises(ValueError, match=message):
        BuildMetadata.from_environment(
            values,
            generated_contract_sha256="a" * 64,
        )


def test_production_build_metadata_requires_every_explicit_cohort_value() -> None:
    with pytest.raises(ValueError, match="production requires") as failure:
        BuildMetadata.from_environment(
            {},
            generated_contract_sha256="a" * 64,
            production=True,
        )
    for name in (
        "DITTO_PRODUCT_VERSION",
        "DITTO_GIT_SHA",
        "DITTO_API_CONTRACT_VERSION",
        "DITTO_API_CONTRACT_SHA256",
    ):
        assert name in str(failure.value)


@pytest.mark.parametrize(
    "override",
    [
        {"DITTO_PRODUCT_VERSION": "0+unknown"},
        {"DITTO_GIT_SHA": "unknown"},
        {"DITTO_API_CONTRACT_SHA256": "unknown"},
    ],
)
def test_production_build_metadata_rejects_placeholder_identity(
    override: dict[str, str],
) -> None:
    values = {
        "DITTO_PRODUCT_VERSION": "2026.9.4",
        "DITTO_GIT_SHA": "d" * 40,
        "DITTO_API_CONTRACT_VERSION": "v1",
        "DITTO_API_CONTRACT_SHA256": "a" * 64,
        **override,
    }

    with pytest.raises(ValueError, match=r"production.*cohort metadata"):
        BuildMetadata.from_environment(
            values,
            generated_contract_sha256="a" * 64,
            production=True,
        )


def test_explicit_contract_hash_requires_canonical_verification_value() -> None:
    with pytest.raises(ValueError, match="cannot verify DITTO_API_CONTRACT_SHA256"):
        BuildMetadata.from_environment(
            {"DITTO_API_CONTRACT_SHA256": "a" * 64},
        )


def test_build_metadata_has_checkout_independent_fallbacks() -> None:
    metadata = BuildMetadata.from_environment({}, generated_contract_sha256="b" * 64)

    assert metadata.product_version == APP_VERSION
    assert metadata.git_sha == "unknown"
    assert metadata.api_contract_version == "v1"
    assert metadata.api_contract_sha256 == "b" * 64


def test_every_http_operation_has_an_explicit_stable_id() -> None:
    missing = [
        f"{','.join(sorted(route.methods))} {route.path}"
        for route in create_openapi_app(include_debug=True).routes
        if isinstance(route, APIRoute) and route.operation_id is None
    ]

    assert missing == []


def test_openapi_builder_rejects_an_implicit_operation_id() -> None:
    test_app = FastAPI()

    @test_app.get("/implicit")
    async def implicit() -> dict[str, str]:
        return {"status": "forbidden"}

    configure_openapi(test_app)

    with pytest.raises(RuntimeError, match="explicit operation_id"):
        test_app.openapi()


@pytest.mark.parametrize(
    ("first_id", "second_id", "message"),
    [
        ("invalid operation", "valid_operation", "invalid explicit operation_id"),
        ("same_operation", "same_operation", "globally unique"),
    ],
)
def test_openapi_builder_rejects_invalid_or_duplicate_operation_ids(
    first_id: str, second_id: str, message: str
) -> None:
    test_app = FastAPI()

    @test_app.get("/first", operation_id=first_id)
    async def first() -> dict[str, str]:
        return {"status": "ok"}

    @test_app.get("/second", operation_id=second_id)
    async def second() -> dict[str, str]:
        return {"status": "ok"}

    configure_openapi(test_app)
    with pytest.raises(RuntimeError, match=message):
        test_app.openapi()


@pytest.mark.parametrize(
    ("product_version", "contract_hash", "message"),
    [
        ("  ", "unknown", "DITTO_PRODUCT_VERSION"),
        ("1.0.0", "not-a-hash", "DITTO_API_CONTRACT_SHA256"),
    ],
)
def test_direct_build_metadata_construction_validates_identity(
    product_version: str, contract_hash: str, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        BuildMetadata(product_version, "unknown", "v1", contract_hash)


def test_generated_contract_hash_must_be_canonical_sha256() -> None:
    with pytest.raises(ValueError, match="canonical contract SHA-256"):
        BuildMetadata.from_environment({}, generated_contract_sha256="not-a-hash")
