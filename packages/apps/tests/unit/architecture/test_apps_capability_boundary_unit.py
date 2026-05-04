"""Apps non-registry capability import boundary tests."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

_SCRIPT = (
    Path(__file__).resolve().parents[5]
    / "scripts"
    / "architecture"
    / "check_architecture_smells.py"
)


def _load_module() -> object:
    spec = spec_from_file_location("check_architecture_smells", _SCRIPT)
    if spec is None or spec.loader is None:
        msg = f"Cannot load {_SCRIPT}"
        raise ImportError(msg)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_MODULE = _load_module()


def test_apps_capability_import_guard_reports_non_registry_routes() -> None:
    check = _MODULE.check_apps_non_registry_capability_imports  # type: ignore[attr-defined]

    errors = check(
        "from ditto_data.sources.protocols import MarketFetcher",
        "packages/apps/src/ditto_apps/api/routes/source.py",
    )

    assert errors == [
        "packages/apps/src/ditto_apps/api/routes/source.py: "
        "apps non-registry module imports capability package "
        "'ditto_data.sources.protocols'; use application facades or "
        "registry composition",
    ]


def test_apps_capability_import_guard_allows_registry_composition() -> None:
    check = _MODULE.check_apps_non_registry_capability_imports  # type: ignore[attr-defined]

    errors = check(
        "from ditto_data.services.market_service import MarketService",
        "packages/apps/src/ditto_apps/registry/contexts/query.py",
    )

    assert errors == []


def test_apps_capability_import_guard_allows_prefect_host_quality_exception() -> None:
    check = _MODULE.check_apps_non_registry_capability_imports  # type: ignore[attr-defined]

    errors = check(
        "\n".join(
            (
                "from ditto_data.quality import QualityEngine",
                "from ditto_data.quality.protocols import QualityEngineProtocol",
            )
        ),
        "packages/apps/src/ditto_apps/jobs/context.py",
    )

    assert errors == []


def test_apps_capability_import_guard_limits_prefect_host_exception() -> None:
    check = _MODULE.check_apps_non_registry_capability_imports  # type: ignore[attr-defined]

    errors = check(
        "from ditto_data.services.market_service import MarketService",
        "packages/apps/src/ditto_apps/jobs/context.py",
    )

    assert errors == [
        "packages/apps/src/ditto_apps/jobs/context.py: "
        "apps non-registry module imports capability package "
        "'ditto_data.services.market_service'; use application facades or "
        "registry composition",
    ]
