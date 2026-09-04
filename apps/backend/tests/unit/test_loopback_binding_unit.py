"""Regression guards for unauthenticated API bind addresses."""

from __future__ import annotations

import inspect
import tomllib
from pathlib import Path

import ditto_apps.main as app_main
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[4]


def test_all_bundled_server_entrypoints_are_loopback_only() -> None:
    """Unauthenticated development and direct entrypoints must not bind externally."""
    source = inspect.getsource(app_main)
    pixi_config = (PROJECT_ROOT / "pixi.toml").read_text(encoding="utf-8")

    assert 'address="127.0.0.1:8000"' in source
    assert "--host 127.0.0.1 --port 8000" in pixi_config
    assert "0.0.0.0" not in source  # noqa: S104 - forbidden bind assertion
    assert "0.0.0.0" not in pixi_config  # noqa: S104 - forbidden bind assertion


def test_all_compose_published_ports_are_loopback_only() -> None:
    """Container-internal listeners may communicate, but host ports stay local."""
    compose_paths = (
        PROJECT_ROOT / "deploy" / "docker" / "docker-compose.yml",
        PROJECT_ROOT / "deploy" / "observability" / "docker-compose.yml",
    )

    published_ports: list[str] = []
    for compose_path in compose_paths:
        compose = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
        for service in compose["services"].values():
            published_ports.extend(str(port) for port in service.get("ports", ()))

    assert published_ports
    assert all(port.startswith("127.0.0.1:") for port in published_ports)


def test_container_listeners_use_bridge_interface_behind_loopback_publication() -> None:
    """Container services must be reachable through the bridge, not the host LAN."""
    dockerfile = (PROJECT_ROOT / "deploy" / "docker" / "Dockerfile").read_text(
        encoding="utf-8"
    )
    compose = yaml.safe_load(
        (PROJECT_ROOT / "deploy" / "docker" / "docker-compose.yml").read_text(
            encoding="utf-8"
        )
    )

    assert '"--host", "0.0.0.0"' in dockerfile
    assert "--host 0.0.0.0" in compose["services"]["ditto-api"]["command"]
    assert "--host 0.0.0.0" in compose["services"]["ditto-job"]["command"]


def test_container_data_root_override_matches_application_settings() -> None:
    """Deployment must set the environment variable consumed by ConfigProvider."""
    dockerfile = (PROJECT_ROOT / "deploy" / "docker" / "Dockerfile").read_text(
        encoding="utf-8"
    )
    compose = yaml.safe_load(
        (PROJECT_ROOT / "deploy" / "docker" / "docker-compose.yml").read_text(
            encoding="utf-8"
        )
    )

    assert "DITTO_DATA_ROOT=/app/data" in dockerfile
    assert "DITTO_DATA_DIR" not in dockerfile
    for service_name in ("ditto-api", "ditto-job"):
        environment = compose["services"][service_name]["environment"]
        assert "DITTO_DATA_ROOT=/app/data" in environment
        assert not any(item.startswith("DITTO_DATA_DIR=") for item in environment)


def test_local_prefect_runbook_is_loopback_only() -> None:
    """Bare-metal instructions must not expose unauthenticated Prefect."""
    operations_manual = (PROJECT_ROOT / "docs" / "ops-manual.md").read_text(
        encoding="utf-8"
    )

    assert "prefect server start --host 127.0.0.1 &" in operations_manual
    assert "prefect server start --host 0.0.0.0" not in operations_manual


def test_local_prefect_memory_runtime_declares_lua_dependency() -> None:
    """Prefect's in-memory Docket backend requires fakeredis Lua support."""
    pixi_config = tomllib.loads(
        (PROJECT_ROOT / "pixi.toml").read_text(encoding="utf-8")
    )

    assert pixi_config["dependencies"]["lupa"] == ">=2.1,<3"
