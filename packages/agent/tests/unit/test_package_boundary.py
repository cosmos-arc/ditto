from __future__ import annotations

import configparser
import sys
import tomllib
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).parents[4]
AGENT_PROJECT = REPOSITORY_ROOT / "packages" / "agent" / "pyproject.toml"
IMPORT_LINTER = REPOSITORY_ROOT / ".importlinter"
PIXI_PROJECT = REPOSITORY_ROOT / "pixi.toml"


def _lines(value: str) -> set[str]:
    return {line.strip() for line in value.splitlines() if line.strip()}


def _import_linter() -> configparser.ConfigParser:
    config = configparser.ConfigParser()
    config.read(IMPORT_LINTER, encoding="utf-8")
    return config


def test_agent_imports_successfully() -> None:
    import ditto_agent

    assert ditto_agent.__name__ == "ditto_agent"


def test_agent_root_import_does_not_load_forbidden_packages() -> None:
    before = set(sys.modules)
    import ditto_agent  # noqa: F401

    loaded = set(sys.modules) - before
    forbidden_prefixes = (
        "ditto_analysis",
        "ditto_apps",
        "ditto_backtest",
        "ditto_data",
        "ditto_execution",
        "ditto_features",
        "ditto_portfolio",
        "ditto_risk",
        "ditto_strategy",
    )
    forbidden = {
        module
        for module in loaded
        if any(
            module == prefix or module.startswith(f"{prefix}.")
            for prefix in forbidden_prefixes
        )
    }
    assert not forbidden, f"Agent imported forbidden packages: {sorted(forbidden)}"


def test_agent_dependency_range_is_frozen_in_package_and_pixi_metadata() -> None:
    project = tomllib.loads(AGENT_PROJECT.read_text(encoding="utf-8"))
    assert "openai-agents>=0.20.0,<0.21" in project["project"]["dependencies"]

    pixi = tomllib.loads(PIXI_PROJECT.read_text(encoding="utf-8"))
    assert pixi["pypi-dependencies"]["ditto-agent"] == {
        "path": "packages/agent",
        "editable": True,
    }
    assert pixi["pypi-dependencies"]["openai-agents"] == ">=0.20.0,<0.21"

    try:
        installed = version("openai-agents")
    except PackageNotFoundError as exc:
        message = "openai-agents is absent from the Pixi environment"
        raise AssertionError(message) from exc
    major, minor, *_ = (int(part) for part in installed.split(".")[:2])
    assert (major, minor) == (0, 20)


def test_import_linter_registers_agent_and_bidirectional_boundaries() -> None:
    config = _import_linter()
    roots = _lines(config["importlinter"]["root_packages"])
    assert "ditto_agent" in roots

    expected = {
        "importlinter:contract:agent-capability-isolation": (
            {"ditto_agent.**"},
            {
                "ditto_analysis.**",
                "ditto_backtest.**",
                "ditto_data.**",
                "ditto_execution.**",
                "ditto_features.**",
                "ditto_portfolio.**",
                "ditto_risk.**",
                "ditto_strategy.**",
            },
        ),
        "importlinter:contract:agent-no-apps": (
            {"ditto_agent.**"},
            {"ditto_apps.**"},
        ),
        "importlinter:contract:application-no-agent": (
            {"ditto_application.**"},
            {"ditto_agent.**"},
        ),
        "importlinter:contract:capabilities-no-agent": (
            {
                "ditto_analysis.**",
                "ditto_backtest.**",
                "ditto_data.**",
                "ditto_execution.**",
                "ditto_features.**",
                "ditto_portfolio.**",
                "ditto_risk.**",
                "ditto_strategy.**",
            },
            {"ditto_agent.**"},
        ),
        "importlinter:contract:platform-no-agent": (
            {"ditto_platform.**"},
            {"ditto_agent.**"},
        ),
        "importlinter:contract:apps-agent-physical-adapter-isolation": (
            {"ditto_apps.**"},
            {
                "ditto_agent.models.openai_adapter",
                "ditto_agent.sandbox.**",
                "ditto_agent.storage.sqlite.**",
            },
        ),
    }
    for section, (sources, forbidden) in expected.items():
        assert section in config
        assert sources <= _lines(config[section]["source_modules"])
        assert forbidden <= _lines(config[section]["forbidden_modules"])


def test_agent_is_between_apps_and_application_in_broad_layer_guard() -> None:
    layers = list(
        _lines(_import_linter()["importlinter:contract:layered-architecture"]["layers"])
    )
    # ConfigParser preserves input order, but a set helper intentionally does not.
    raw_layers = [
        line.strip()
        for line in _import_linter()["importlinter:contract:layered-architecture"][
            "layers"
        ].splitlines()
        if line.strip()
    ]
    assert set(layers) == set(raw_layers)
    assert raw_layers.index("ditto_apps") < raw_layers.index("ditto_agent")
    assert raw_layers.index("ditto_agent") < raw_layers.index("ditto_application")
