"""Application provider governance tests."""

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


def test_application_provider_predicate_matches_provider_modules() -> None:
    predicate = _MODULE.is_application_provider_module_path  # type: ignore[attr-defined]

    assert predicate("packages/application/src/ditto_application/providers.py")
    assert predicate("packages/application/src/ditto_application/providers_market.py")
    assert predicate(
        "packages/application/src/ditto_application/providers_execution.py"
    )
    assert not predicate("packages/application/src/ditto_application/settings.py")
    assert not predicate(
        "packages/application/src/ditto_application/processes/providers.py"
    )
    assert not predicate("packages/apps/src/ditto_apps/providers.py")


def test_application_provider_rejects_os_environ_subscript() -> None:
    check = _MODULE.check_application_provider_no_environment_reads  # type: ignore[attr-defined]

    errors = check(
        "import os\nVALUE = os.environ['DITTO_DATABASE_URL']\n",
        "packages/application/src/ditto_application/providers.py",
    )

    assert errors == [
        "packages/application/src/ditto_application/providers.py: "
        "application provider reads environment via os.environ; "
        "route configuration through apps/platform settings",
    ]


def test_application_provider_rejects_dict_os_environ() -> None:
    check = _MODULE.check_application_provider_no_environment_reads  # type: ignore[attr-defined]

    errors = check(
        "import os\nVALUE = dict(os.environ)\n",
        "packages/application/src/ditto_application/providers.py",
    )

    assert errors == [
        "packages/application/src/ditto_application/providers.py: "
        "application provider reads environment via os.environ; "
        "route configuration through apps/platform settings",
    ]


def test_application_provider_rejects_os_environ_copy() -> None:
    check = _MODULE.check_application_provider_no_environment_reads  # type: ignore[attr-defined]

    errors = check(
        "import os\nVALUE = os.environ.copy()\n",
        "packages/application/src/ditto_application/providers.py",
    )

    assert errors == [
        "packages/application/src/ditto_application/providers.py: "
        "application provider reads environment via os.environ; "
        "route configuration through apps/platform settings",
    ]


def test_application_provider_rejects_os_environ_membership() -> None:
    check = _MODULE.check_application_provider_no_environment_reads  # type: ignore[attr-defined]

    errors = check(
        "import os\nENABLED = 'DITTO' in os.environ\n",
        "packages/application/src/ditto_application/providers.py",
    )

    assert errors == [
        "packages/application/src/ditto_application/providers.py: "
        "application provider reads environment via os.environ; "
        "route configuration through apps/platform settings",
    ]


def test_application_provider_rejects_os_environ_get() -> None:
    check = _MODULE.check_application_provider_no_environment_reads  # type: ignore[attr-defined]

    errors = check(
        "import os\nVALUE = os.environ.get('DITTO_DATABASE_URL')\n",
        "packages/application/src/ditto_application/providers_market.py",
    )

    assert errors == [
        "packages/application/src/ditto_application/providers_market.py: "
        "application provider reads environment via os.environ.get; "
        "route configuration through apps/platform settings",
    ]


def test_application_provider_rejects_os_getenv() -> None:
    check = _MODULE.check_application_provider_no_environment_reads  # type: ignore[attr-defined]

    errors = check(
        "import os\nVALUE = os.getenv('DITTO_DATABASE_URL')\n",
        "packages/application/src/ditto_application/providers_portfolio.py",
    )

    assert errors == [
        "packages/application/src/ditto_application/providers_portfolio.py: "
        "application provider reads environment via os.getenv; "
        "route configuration through apps/platform settings",
    ]


def test_application_provider_rejects_imported_environ_reads() -> None:
    check = _MODULE.check_application_provider_no_environment_reads  # type: ignore[attr-defined]

    errors = check(
        "from os import environ\nA = environ['A']\nB = environ.get('B')\n",
        "packages/application/src/ditto_application/providers_strategy.py",
    )

    assert errors == [
        "packages/application/src/ditto_application/providers_strategy.py: "
        "application provider reads environment via environ; "
        "route configuration through apps/platform settings",
        "packages/application/src/ditto_application/providers_strategy.py: "
        "application provider reads environment via environ.get; "
        "route configuration through apps/platform settings",
    ]


def test_application_provider_rejects_imported_environ_bare_read() -> None:
    check = _MODULE.check_application_provider_no_environment_reads  # type: ignore[attr-defined]

    errors = check(
        "from os import environ\nVALUE = Settings.model_validate(environ)\n",
        "packages/application/src/ditto_application/providers.py",
    )

    assert errors == [
        "packages/application/src/ditto_application/providers.py: "
        "application provider reads environment via environ; "
        "route configuration through apps/platform settings",
    ]


def test_application_provider_rejects_imported_getenv_call() -> None:
    check = _MODULE.check_application_provider_no_environment_reads  # type: ignore[attr-defined]

    errors = check(
        "from os import getenv\nVALUE = getenv('DITTO_DATABASE_URL')\n",
        "packages/application/src/ditto_application/providers.py",
    )

    assert errors == [
        "packages/application/src/ditto_application/providers.py: "
        "application provider reads environment via getenv; "
        "route configuration through apps/platform settings",
    ]


def test_application_provider_checker_ignores_non_provider_paths() -> None:
    check = _MODULE.check_application_provider_no_environment_reads  # type: ignore[attr-defined]

    errors = check(
        "import os\nVALUE = os.environ['DITTO_DATABASE_URL']\n",
        "packages/application/src/ditto_application/settings.py",
    )

    assert errors == []


def test_application_provider_checker_scans_future_provider_modules() -> None:
    check = _MODULE.check_application_provider_no_environment_reads  # type: ignore[attr-defined]

    errors = check(
        "import os\nVALUE = dict(os.environ)\n",
        "packages/application/src/ditto_application/providers_execution.py",
    )

    assert errors == [
        "packages/application/src/ditto_application/providers_execution.py: "
        "application provider reads environment via os.environ; "
        "route configuration through apps/platform settings",
    ]
