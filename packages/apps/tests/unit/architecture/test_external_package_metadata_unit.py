import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[5]))

from scripts.architecture.check_architecture_smells import (
    _external_imports_in_file,
    _scan_external_pkg_imports,
    check_external_package_metadata,
)


def test_external_runtime_dependencies_are_declared() -> None:
    result: list[str] = check_external_package_metadata(Path.cwd())
    assert result == [], "\n".join(result)


def test_opentelemetry_namespace_imports_map_to_specific_distributions(
    tmp_path: Path,
) -> None:
    source = tmp_path / "otel.py"
    source.write_text(
        "\n".join(
            [
                "from opentelemetry import metrics",
                "from opentelemetry.sdk.metrics import MeterProvider",
                "from opentelemetry.exporter.otlp.proto.http.metric_exporter "
                "import OTLPMetricExporter",
            ]
        ),
        encoding="utf-8",
    )

    result = _external_imports_in_file(source, local_modules=set())

    assert result == {
        "opentelemetry-api",
        "opentelemetry-exporter-otlp-proto-http",
        "opentelemetry-sdk",
    }


def test_importerror_guarded_optional_import_is_not_required(tmp_path: Path) -> None:
    source = tmp_path / "optional.py"
    source.write_text(
        "\n".join(
            [
                "try:",
                "    import keyring",
                "except ImportError:",
                "    keyring = None",
                "import fastapi",
            ]
        ),
        encoding="utf-8",
    )

    result = _external_imports_in_file(source, local_modules=set())

    assert result == {"fastapi"}


def test_importerror_guard_that_raises_keeps_import_required(tmp_path: Path) -> None:
    source = tmp_path / "required.py"
    source.write_text(
        "\n".join(
            [
                "try:",
                "    from filelock import FileLock, Timeout",
                "except ImportError as e:",
                "    raise ImportError('filelock is required') from e",
            ]
        ),
        encoding="utf-8",
    )

    result = _external_imports_in_file(source, local_modules=set())

    assert result == {"filelock"}


def test_testing_source_helpers_are_not_runtime_imports(tmp_path: Path) -> None:
    src_dir = tmp_path / "src"
    pkg_dir = src_dir / "sample"
    pkg_dir.mkdir(parents=True)
    (pkg_dir / "__init__.py").write_text("", encoding="utf-8")
    (pkg_dir / "runtime.py").write_text("import fastapi\n", encoding="utf-8")
    (pkg_dir / "testing.py").write_text("import duckdb\n", encoding="utf-8")

    result = _scan_external_pkg_imports(src_dir)

    assert result == {"fastapi"}


def test_platform_scan_includes_filelock_runtime_dependency() -> None:
    result = _scan_external_pkg_imports(Path.cwd() / "packages" / "platform" / "src")

    assert "filelock" in result
