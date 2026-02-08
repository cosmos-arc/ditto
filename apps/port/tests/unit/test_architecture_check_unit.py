"""Unit tests for architecture boundary checker."""

import importlib.util
import sys
from pathlib import Path

_SCRIPT_PATH = Path(__file__).resolve().parents[4] / "scripts" / "check_architecture.py"
_SPEC = importlib.util.spec_from_file_location("check_architecture", _SCRIPT_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError("Failed to load scripts/check_architecture.py")
_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _MODULE
_SPEC.loader.exec_module(_MODULE)
ArchitectureChecker = _MODULE.ArchitectureChecker


def _write_file(root: Path, relative: str, content: str) -> None:
    file_path = root / relative
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content, encoding="utf-8")


def test_foundation_must_not_depend_on_datahub(tmp_path: Path) -> None:
    """Foundation importing DataHub should fail."""
    _write_file(
        tmp_path,
        "packages/foundation/src/ditto_foundation/bad.py",
        "from ditto_datahub.hub import DataHub\n",
    )

    violations = ArchitectureChecker(tmp_path).run()
    codes = {item.code for item in violations}
    assert "ARCH100" in codes


def test_core_only_allows_datahub_models(tmp_path: Path) -> None:
    """Core importing DataHub implementation should fail."""
    _write_file(
        tmp_path,
        "packages/core/src/ditto_core/bad.py",
        "from ditto_datahub.domains.market import MarketService\n",
    )

    violations = ArchitectureChecker(tmp_path).run()
    codes = {item.code for item in violations}
    assert "ARCH300" in codes


def test_port_non_registry_forbids_sources_store_runtime(tmp_path: Path) -> None:
    """Port non-registry modules cannot import sources/stores/runtime."""
    _write_file(
        tmp_path,
        "apps/port/src/ditto_port/services/bad.py",
        "from ditto_datahub.sources.base import DataSource\n",
    )

    violations = ArchitectureChecker(tmp_path).run()
    codes = {item.code for item in violations}
    assert "ARCH410" in codes


def test_port_registry_allows_dependency_injection_import(tmp_path: Path) -> None:
    """Port registry can import stores for DI construction only."""
    _write_file(
        tmp_path,
        "apps/port/src/ditto_port/registry/provider.py",
        (
            "from dishka import Provider, provide\n"
            "from ditto_datahub.stores.sqlite_client import SQLiteClient\n"
            "\n"
            "class P(Provider):\n"
            "    @provide\n"
            "    def sqlite_client(self, pool: object) -> SQLiteClient:\n"
            "        return SQLiteClient(pool)\n"
        ),
    )

    violations = ArchitectureChecker(tmp_path).run()
    assert not violations


def test_port_registry_forbids_direct_store_usage(tmp_path: Path) -> None:
    """Port registry should not directly call store/source business methods."""
    _write_file(
        tmp_path,
        "apps/port/src/ditto_port/registry/provider.py",
        (
            "from dishka import Provider, provide\n"
            "from ditto_datahub.stores.sqlite_client import SQLiteClient\n"
            "\n"
            "class P(Provider):\n"
            "    @provide\n"
            "    def bad(self, client: SQLiteClient) -> SQLiteClient:\n"
            "        client.execute('SELECT 1')\n"
            "        return client\n"
        ),
    )

    violations = ArchitectureChecker(tmp_path).run()
    codes = {item.code for item in violations}
    assert "ARCH430" in codes


def test_forbid_legacy_sid_identifier_in_python_source(tmp_path: Path) -> None:
    """Legacy sid identifier should fail architecture check."""
    _write_file(
        tmp_path,
        "packages/datahub/src/ditto_datahub/domains/market/bad.py",
        "def bad() -> int:\n    sid = 1\n    return sid\n",
    )

    violations = ArchitectureChecker(tmp_path).run()
    codes = {item.code for item in violations}
    assert "ARCH500" in codes


def test_forbid_legacy_src_code_identifier_in_yaml(tmp_path: Path) -> None:
    """Legacy src_code field should fail architecture check."""
    _write_file(
        tmp_path,
        "config/default/dq_rules/bad.yml",
        "checks:\n  - name: not_null\n    columns: [src_code]\n",
    )

    violations = ArchitectureChecker(tmp_path).run()
    codes = {item.code for item in violations}
    assert "ARCH510" in codes
