"""Generic helper/utils namespace governance tests."""

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

_CURRENT_GENERIC_HELPER_SOURCE_PATHS = frozenset(
    {
        "packages/application/src/ditto_application/config/helpers.py",
        "packages/application/src/ditto_application/processes/materialization/helpers.py",
        "packages/apps/src/ditto_apps/api/utils/__init__.py",
        "packages/apps/src/ditto_apps/api/utils/identifier.py",
        "packages/apps/src/ditto_apps/cli/utils/__init__.py",
        "packages/apps/src/ditto_apps/cli/utils/identifier.py",
        "packages/apps/src/ditto_apps/cli/utils/output.py",
        "packages/apps/src/ditto_apps/cli/utils/params.py",
        "packages/apps/src/ditto_apps/cli/utils/validation.py",
        "packages/data/src/ditto_data/helpers/__init__.py",
        "packages/data/src/ditto_data/helpers/adjustment.py",
        "packages/data/src/ditto_data/helpers/pit/__init__.py",
        "packages/data/src/ditto_data/helpers/pit/dataframe.py",
        "packages/data/src/ditto_data/helpers/pit/policy.py",
        "packages/data/src/ditto_data/helpers/pit/sql.py",
        "packages/data/src/ditto_data/sources/tushare/utils/__init__.py",
        "packages/data/src/ditto_data/sources/tushare/utils/http_utils.py",
        "packages/data/src/ditto_data/sources/tushare/utils/rate_limiter.py",
        "packages/data/src/ditto_data/utils/__init__.py",
        "packages/data/src/ditto_data/utils/ticker_utils.py",
        "packages/data/src/ditto_data/utils/timezone_utils.py",
    }
)


def test_generic_helper_allowances_are_owned_reasoned_and_current() -> None:
    allowances = _MODULE.GENERIC_HELPER_NAMESPACE_ALLOWANCES  # type: ignore[attr-defined]

    assert allowances
    assert all(allowance.owner for allowance in allowances)
    assert all(allowance.reason for allowance in allowances)
    assert {allowance.path for allowance in allowances} == (
        _CURRENT_GENERIC_HELPER_SOURCE_PATHS
    )


def test_generic_helper_allowlist_matches_existing_python_sources() -> None:
    root = Path(__file__).resolve().parents[5]

    actual = {
        path.relative_to(root).as_posix()
        for path in sorted((root / "packages").glob("*/src/**/*.py"))
        if _MODULE.is_generic_helper_namespace_path(  # type: ignore[attr-defined]
            path.relative_to(root).as_posix()
        )
    }

    assert actual == _CURRENT_GENERIC_HELPER_SOURCE_PATHS


def test_generic_helper_namespace_rejects_unreviewed_new_path() -> None:
    check = _MODULE.check_generic_helper_namespace_allowance  # type: ignore[attr-defined]

    errors = check("packages/features/src/ditto_features/utils/math.py")

    assert errors == [
        "packages/features/src/ditto_features/utils/math.py: "
        "generic helpers/utils namespace requires architecture review; "
        "rename to a semantic module or add an owned, reasoned allowance",
    ]


def test_generic_helper_namespace_allows_semantic_path() -> None:
    check = _MODULE.check_generic_helper_namespace_allowance  # type: ignore[attr-defined]

    errors = check("packages/features/src/ditto_features/evaluation/metrics/ic.py")

    assert errors == []
