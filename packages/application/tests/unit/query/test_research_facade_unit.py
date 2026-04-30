"""Tests for ResearchDatasetFacade -- 封装 research snapshot 构建、导出与加载."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import polars as pl
from ditto_analytics.research.domain import DatasetSnapshot, KnownAtPolicy
from ditto_application.query.research import ResearchDatasetFacade, _sanitize_table_name


def _make_snapshot(**overrides: object) -> DatasetSnapshot:
    """构造一个带默认值的 DatasetSnapshot."""
    defaults: dict[str, object] = {
        "snapshot_id": "rds-abc123",
        "dataset_id": "test_dataset",
        "dataset_spec_version": 1,
        "spine_snapshot_id": "rsp-xyz456",
        "start": "2024-01-01",
        "end": "2024-06-30",
        "row_count": 100,
        "data_path": (
            "derived/research/datasets/test_dataset/snapshots/rds-abc123/data.parquet"
        ),
        "manifest_hash": "deadbeef",
        "known_at_policy": KnownAtPolicy.SAMPLE_TIME,
        "effective_cutoff": None,
    }
    defaults.update(overrides)
    return DatasetSnapshot(**defaults)  # type: ignore[arg-type]


def _make_facade() -> ResearchDatasetFacade:
    """构造一个所有依赖均为 MagicMock 的 ResearchDatasetFacade."""
    return ResearchDatasetFacade(
        metadata_service=MagicMock(
            spec=["list_calendar_range", "get_universe"],
        ),
        research_catalog_service=MagicMock(
            spec=[
                "get_dataset_spec",
                "get_spine_spec",
                "save_spine_snapshot",
                "save_dataset_snapshot",
            ],
        ),
        artifact_reader=MagicMock(
            spec=["read_frame", "resolve_serving_version"],
        ),
        research_artifact_service=MagicMock(
            spec=[
                "read_parquet",
                "write_parquet",
                "read_json",
                "write_json",
                "resolve_artifact_relative_path",
                "read_source_snapshot_ids",
            ],
        ),
    )


# ========== export delegation ==========


class TestResearchFacadeExportCsv:
    """ResearchDatasetFacade.export -- fmt=csv 时调用 write_csv."""

    def test_writes_csv(self, tmp_path: Path) -> None:
        """验证 fmt="csv" 时读取 parquet 并调用 write_csv."""
        facade = _make_facade()
        df = pl.DataFrame({"a": [1, 2], "b": [3, 4]})
        facade._artifact_service.read_parquet.return_value = df  # type: ignore[attr-defined]
        snapshot = _make_snapshot()
        csv_path = tmp_path / "out.csv"

        facade.export(snapshot, fmt="csv", path=csv_path)

        facade._artifact_service.read_parquet.assert_called_once_with(
            snapshot.data_path
        )  # type: ignore[attr-defined]
        assert csv_path.exists()
        written = pl.read_csv(str(csv_path))
        assert written.shape == (2, 2)
        assert "a" in written.columns
        assert "b" in written.columns


class TestResearchFacadeExportSqlite:
    """ResearchDatasetFacade.export -- fmt=sqlite 时调用 _export_sqlite."""

    def test_writes_sqlite(self, tmp_path: Path) -> None:
        """验证 fmt="sqlite" 时读取 parquet 并写入 SQLite."""
        import sqlite3

        facade = _make_facade()
        df = pl.DataFrame({"x": [10, 20], "y": [30.0, 40.0]})
        facade._artifact_service.read_parquet.return_value = df  # type: ignore[attr-defined]
        snapshot = _make_snapshot(dataset_id="my_ds")
        db_path = tmp_path / "out.db"

        facade.export(snapshot, fmt="sqlite", path=db_path)

        facade._artifact_service.read_parquet.assert_called_once_with(
            snapshot.data_path
        )  # type: ignore[attr-defined]
        assert db_path.exists()
        assert db_path.stat().st_size > 0
        conn = sqlite3.connect(str(db_path))
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        conn.close()
        assert len(tables) == 1
        assert tables[0][0] == "my_ds"


class TestResearchFacadeExportUnsupported:
    """ResearchDatasetFacade.export -- 不支持的格式抛 ValueError."""

    def test_raises_on_unknown_format(self, tmp_path: Path) -> None:
        """验证不支持的格式抛出 ValueError."""
        import pytest

        facade = _make_facade()
        snapshot = _make_snapshot()

        with pytest.raises(ValueError, match="不支持的导出格式") as exc_info:
            facade.export(snapshot, fmt="parquet", path=tmp_path / "out.parquet")
        assert "parquet" in str(exc_info.value)


# ========== load_build_report delegation ==========


class TestResearchFacadeLoadBuildReport:
    """ResearchDatasetFacade.load_build_report -- 读取 JSON 构建报告."""

    def test_reads_build_report(self) -> None:
        """验证通过 artifact_service 读取 build_report.json."""
        facade = _make_facade()
        expected_report: dict[str, object] = {"row_count": 100, "builder_version": "v1"}
        facade._artifact_service.read_json.return_value = expected_report  # type: ignore[attr-defined]
        snapshot = _make_snapshot(
            data_path="derived/research/datasets/test_dataset/snapshots/rds-abc123/data.parquet",
        )

        result = facade.load_build_report(snapshot)

        expected_relative = (
            "derived/research/datasets/test_dataset"
            "/snapshots/rds-abc123/build_report.json"
        )
        facade._artifact_service.read_json.assert_called_once_with(expected_relative)  # type: ignore[attr-defined]
        assert result == expected_report
        assert result["row_count"] == 100


# ========== SQL injection tests ==========


class TestSanitizeTableNameValid:
    """_sanitize_table_name -- 正常 ID 通过."""

    def test_passes_valid_name(self) -> None:
        """验证合法的字母数字下划线名称原样通过."""
        result = _sanitize_table_name("my_dataset_v2")
        assert result == "my_dataset_v2"
        assert result.startswith("my_")

    def test_passes_leading_underscore(self) -> None:
        """验证以下划线开头的名称通过."""
        result = _sanitize_table_name("_private")
        assert result == "_private"
        assert result.startswith("_")


class TestSanitizeTableNameWithHyphens:
    """_sanitize_table_name -- 带连字符的 ID 被正确转换."""

    def test_converts_hyphens(self) -> None:
        """验证连字符被替换为下划线."""
        result = _sanitize_table_name("my-dataset-name")
        assert result == "my_dataset_name"
        assert "-" not in result


class TestSanitizeTableNameRejectsInjection:
    """_sanitize_table_name -- 恶意 ID 抛 ValueError."""

    def test_rejects_sql_injection(self) -> None:
        """验证包含 SQL 注入字符的 ID 被拒绝."""
        import pytest

        with pytest.raises(ValueError, match="Invalid dataset_id") as exc_info:
            _sanitize_table_name('"; DROP TABLE --')
        assert "DROP" in str(exc_info.value) or ";" in str(exc_info.value)

    def test_rejects_numeric_start(self) -> None:
        """验证以数字开头的 ID 被拒绝."""
        import pytest

        with pytest.raises(ValueError, match="Invalid dataset_id") as exc_info:
            _sanitize_table_name("123bad")
        assert "123bad" in str(exc_info.value)

    def test_rejects_empty(self) -> None:
        """验证空字符串被拒绝."""
        import pytest

        with pytest.raises(ValueError, match="Invalid dataset_id") as exc_info:
            _sanitize_table_name("")
        assert "dataset_id" in str(exc_info.value)

    def test_rejects_semicolon(self) -> None:
        """验证包含分号的 ID 被拒绝."""
        import pytest

        with pytest.raises(ValueError, match="Invalid dataset_id") as exc_info:
            _sanitize_table_name("table;drop")
        assert "table;drop" in str(exc_info.value)


# ========== build error handling ==========


class TestResearchFacadeBuildDatasetNotFound:
    """ResearchDatasetFacade.build -- dataset spec 不存在时抛 DerivedNotFoundError."""

    def test_raises_when_spec_missing(self) -> None:
        """验证 catalog 返回 None 时抛出 DerivedNotFoundError."""
        import pytest
        from ditto_data.errors import DerivedNotFoundError

        facade = _make_facade()
        facade._research_catalog_service.get_dataset_spec.return_value = None  # type: ignore[attr-defined]

        with pytest.raises(DerivedNotFoundError) as exc_info:
            facade.build(
                dataset_id="nonexistent",
                start="2024-01-01",
                end="2024-06-30",
            )
        assert "nonexistent" in str(exc_info.value)
