"""Stable application metadata shared by runtime and contract apps."""

from __future__ import annotations

import importlib.metadata
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

from fastapi.routing import APIRoute

APP_TITLE = "Ditto Quant API"
APP_DESCRIPTION = "量化投资系统API"
APP_LICENSE_NAME = "Proprietary - All rights reserved"
APP_LOOPBACK_SERVER_URL = "/"
APP_LOOPBACK_SERVER_DESCRIPTION = "Current local Ditto API origin"
SUPPORTED_API_CONTRACT_VERSION: Final = "v1"
_FULL_GIT_SHA = re.compile(r"^[0-9a-f]{40}$")
_FULL_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_COHORT_ENVIRONMENT_NAMES: Final = (
    "DITTO_PRODUCT_VERSION",
    "DITTO_GIT_SHA",
    "DITTO_API_CONTRACT_VERSION",
    "DITTO_API_CONTRACT_SHA256",
)


def openapi_license_info() -> dict[str, str]:
    """Return the API's truthful non-redistribution license declaration."""
    return {
        "name": APP_LICENSE_NAME,
        "identifier": "LicenseRef-Proprietary",
    }


def openapi_servers() -> list[dict[str, str]]:
    """Return the sole supported HTTP origin for the local workstation."""
    return [
        {
            "url": APP_LOOPBACK_SERVER_URL,
            "description": APP_LOOPBACK_SERVER_DESCRIPTION,
        }
    ]


def _load_app_version() -> str:
    """Return the installed API package version, with a local-dev fallback."""
    try:
        return importlib.metadata.version("ditto-apps")
    except importlib.metadata.PackageNotFoundError:
        return "0+unknown"


APP_VERSION = _load_app_version()


@dataclass(frozen=True, slots=True)
class BuildMetadata:
    """Deployment-supplied product and API contract identity."""

    product_version: str
    git_sha: str
    api_contract_version: str
    api_contract_sha256: str

    def __post_init__(self) -> None:
        """Reject malformed identities even when constructed outside the loader."""
        if not self.product_version.strip():
            raise ValueError("DITTO_PRODUCT_VERSION must be non-empty")
        if self.git_sha != "unknown" and _FULL_GIT_SHA.fullmatch(self.git_sha) is None:
            raise ValueError(
                "DITTO_GIT_SHA must be a full lowercase 40-character Git hash"
            )
        if self.api_contract_version != SUPPORTED_API_CONTRACT_VERSION:
            expected = SUPPORTED_API_CONTRACT_VERSION
            raise ValueError(f"DITTO_API_CONTRACT_VERSION must equal {expected!r}")
        if (
            self.api_contract_sha256 != "unknown"
            and _FULL_SHA256.fullmatch(self.api_contract_sha256) is None
        ):
            raise ValueError(
                "DITTO_API_CONTRACT_SHA256 must be a full lowercase SHA-256"
            )

    @classmethod
    def from_environment(
        cls,
        environ: Mapping[str, str] | None = None,
        *,
        generated_contract_sha256: str | None = None,
        production: bool = False,
    ) -> BuildMetadata:
        """Load immutable build metadata without reading checkout internals."""
        values = os.environ if environ is None else environ
        if production:
            invalid = [
                name
                for name in _COHORT_ENVIRONMENT_NAMES
                if values.get(name, "").strip() in {"", "unknown", "0+unknown"}
            ]
            if invalid:
                raise ValueError(
                    "production requires explicit valid cohort metadata: "
                    + ", ".join(invalid)
                )

        if (
            generated_contract_sha256 is not None
            and _FULL_SHA256.fullmatch(generated_contract_sha256) is None
        ):
            raise ValueError("canonical contract SHA-256 must be full lowercase hex")

        declared_contract_sha256 = values.get("DITTO_API_CONTRACT_SHA256", "").strip()
        if (
            declared_contract_sha256
            and _FULL_SHA256.fullmatch(declared_contract_sha256) is None
        ):
            raise ValueError(
                "DITTO_API_CONTRACT_SHA256 must be a full lowercase SHA-256"
            )
        if declared_contract_sha256 and generated_contract_sha256 is None:
            raise ValueError(
                "cannot verify DITTO_API_CONTRACT_SHA256 without canonical hash"
            )
        if (
            declared_contract_sha256
            and generated_contract_sha256 is not None
            and declared_contract_sha256 != generated_contract_sha256
        ):
            raise ValueError(
                "DITTO_API_CONTRACT_SHA256 does not match the canonical contract"
            )

        return cls(
            product_version=_value(values, "DITTO_PRODUCT_VERSION", APP_VERSION),
            git_sha=_value(values, "DITTO_GIT_SHA", "unknown"),
            api_contract_version=_value(
                values,
                "DITTO_API_CONTRACT_VERSION",
                SUPPORTED_API_CONTRACT_VERSION,
            ),
            api_contract_sha256=_value(
                values,
                "DITTO_API_CONTRACT_SHA256",
                generated_contract_sha256 or "unknown",
            ),
        )


def _value(values: Mapping[str, str], name: str, fallback: str) -> str:
    value = values.get(name, "").strip()
    return value or fallback


def generate_stable_operation_id(route: APIRoute) -> str:
    """Generate tag-scoped OpenAPI operation IDs for frontend clients."""
    tag = str(route.tags[0]) if route.tags else "system"
    return f"{tag.replace('-', '_')}_{route.name}"
