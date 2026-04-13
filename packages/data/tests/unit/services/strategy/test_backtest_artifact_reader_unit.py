"""Tests for BacktestArtifactReader — 回测产物文件读取服务."""

from __future__ import annotations

from pathlib import Path

import orjson
import polars as pl
import pytest
from ditto_data.services.strategy.backtest_artifact_reader import (
    BacktestArtifactReader,
    BacktestArtifactReaderProtocol,
)


def _make_reader() -> BacktestArtifactReader:
    """构造 BacktestArtifactReader 实例."""
    return BacktestArtifactReader()


# =====================================================================
# read_json
# =====================================================================


class TestBacktestArtifactReaderReadJson:
    """BacktestArtifactReader.read_json — JSON 文件读取."""

    def test_read_json_existing_file(self, tmp_path: Path) -> None:
        """JSON 文件存在时正确读取并解析."""
        data = {"run_id": "run-001", "nav": 1_000_000.0}
        json_path = tmp_path / "report.json"
        json_path.write_bytes(orjson.dumps(data))

        reader = _make_reader()
        result = reader.read_json(str(json_path))

        assert result is not None
        assert result["run_id"] == "run-001"
        assert result["nav"] == 1_000_000.0

    def test_read_json_missing_file(self, tmp_path: Path) -> None:
        """JSON 文件不存在时返回 None."""
        missing_path = str(tmp_path / "nonexistent.json")

        reader = _make_reader()
        result = reader.read_json(missing_path)

        assert result is None

    def test_read_json_empty_file(self, tmp_path: Path) -> None:
        """JSON 文件为空时抛出异常 (orjson 行为)，不由 reader 处理."""
        empty_path = tmp_path / "empty.json"
        empty_path.write_text("")

        reader = _make_reader()
        with pytest.raises(orjson.JSONDecodeError):
            reader.read_json(str(empty_path))

    def test_read_json_complex_structure(self, tmp_path: Path) -> None:
        """读取复杂嵌套 JSON 结构."""
        data = {
            "alpha_stats": {
                "sharpe": 1.8,
                "max_drawdown": -0.05,
                "nested": {"a": [1, 2, 3]},
            },
            "period": {"start": "2024-01-01", "end": "2024-03-31"},
        }
        json_path = tmp_path / "complex.json"
        json_path.write_bytes(orjson.dumps(data))

        reader = _make_reader()
        result = reader.read_json(str(json_path))

        assert result is not None
        assert result["alpha_stats"]["sharpe"] == 1.8
        assert result["alpha_stats"]["nested"]["a"] == [1, 2, 3]


# =====================================================================
# read_parquet
# =====================================================================


class TestBacktestArtifactReaderReadParquet:
    """BacktestArtifactReader.read_parquet — Parquet 文件读取."""

    def test_read_parquet_existing_file(self, tmp_path: Path) -> None:
        """Parquet 文件存在时正确读取."""
        df = pl.DataFrame(
            {
                "date": ["2024-01-01", "2024-01-02"],
                "nav": [1_000_000.0, 1_010_000.0],
            }
        )
        parquet_path = tmp_path / "nav.parquet"
        df.write_parquet(parquet_path)

        reader = _make_reader()
        result = reader.read_parquet(str(parquet_path))

        assert result is not None
        assert result.shape == (2, 2)
        assert result["date"].to_list() == ["2024-01-01", "2024-01-02"]
        assert result["nav"].to_list() == [1_000_000.0, 1_010_000.0]

    def test_read_parquet_missing_file(self, tmp_path: Path) -> None:
        """Parquet 文件不存在时返回 None."""
        missing_path = str(tmp_path / "nonexistent.parquet")

        reader = _make_reader()
        result = reader.read_parquet(missing_path)

        assert result is None

    def test_read_parquet_empty_dataframe(self, tmp_path: Path) -> None:
        """读取空 Parquet 文件返回空 DataFrame."""
        schema = {"date": pl.String, "nav": pl.Float64}
        df = pl.DataFrame(schema=schema)
        parquet_path = tmp_path / "empty.parquet"
        df.write_parquet(parquet_path)

        reader = _make_reader()
        result = reader.read_parquet(str(parquet_path))

        assert result is not None
        assert result.shape == (0, 2)


# =====================================================================
# exists
# =====================================================================


class TestBacktestArtifactReaderExists:
    """BacktestArtifactReader.exists — 文件存在性检查."""

    def test_exists_true(self, tmp_path: Path) -> None:
        """文件存在时返回 True."""
        f = tmp_path / "data.json"
        f.write_text("{}")

        reader = _make_reader()
        assert reader.exists(str(f)) is True

    def test_exists_false(self, tmp_path: Path) -> None:
        """文件不存在时返回 False."""
        reader = _make_reader()
        assert reader.exists(str(tmp_path / "missing.json")) is False

    def test_exists_directory(self, tmp_path: Path) -> None:
        """路径是目录而非文件时返回 True（Path.exists 行为）."""
        reader = _make_reader()
        assert reader.exists(str(tmp_path)) is True


# =====================================================================
# Protocol 兼容性
# =====================================================================


class TestBacktestArtifactReaderProtocol:
    """BacktestArtifactReaderProtocol -- 实现类兼容性."""

    def test_reader_satisfies_protocol(self) -> None:
        """BacktestArtifactReader 满足 Protocol 定义 (isinstance 检查)."""
        reader = _make_reader()
        assert isinstance(reader, BacktestArtifactReaderProtocol)

    def test_plain_dict_does_not_satisfy_protocol(self) -> None:
        """普通 dict 不满足 Protocol 定义."""
        assert not isinstance({}, BacktestArtifactReaderProtocol)
