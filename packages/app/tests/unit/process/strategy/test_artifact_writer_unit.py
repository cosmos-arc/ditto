"""artifact_writer 单元测试 — Port 层产物序列化。"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import orjson
import polars as pl
import pytest
from ditto_app.process.strategy import (
    enrich_record_with_symbol,
    write_backtest_artifacts,
)
from ditto_engine.backtest.audit import RiskScanRecord
from ditto_engine.backtest.manifest import RunManifest, RunMode
from ditto_engine.backtest.statistics import PreTradeDecisionRecord
from ditto_engine.risk.post_trade import RiskActionType, RiskSeverity
from ditto_kernel.identity import InstrumentId

# ---------------------------------------------------------------------------
# enrich_record_with_symbol
# ---------------------------------------------------------------------------


class TestEnrichRecordWithSymbol:
    """测试 enrich_record_with_symbol 辅助函数。"""

    def test_injects_symbol_for_risk_record(self) -> None:
        """RiskScanRecord 注入 instrument_symbol。"""
        record = RiskScanRecord(
            trade_date="2026-03-24",
            rule_id="max-drawdown",
            instrument_id=InstrumentId(2_000_001),
            scope="instrument",
            severity=RiskSeverity.WARNING,
            action_taken=RiskActionType.REDUCE_POSITION,
            detail="drawdown exceeded",
            current_value=-0.15,
            threshold=-0.10,
        )
        display_map = {InstrumentId(2_000_001): "510300.SH"}

        result = enrich_record_with_symbol(record, display_map)

        assert result["instrument_id"] == 2_000_001
        assert result["instrument_symbol"] == "510300.SH"

    def test_injects_symbol_for_pre_trade_record(self) -> None:
        """PreTradeDecisionRecord 注入 instrument_symbol。"""
        record = PreTradeDecisionRecord(
            trade_date="2026-03-24",
            order_id="ORD-001",
            instrument_id=InstrumentId(2_000_002),
            direction="buy",
            original_quantity=1000,
            final_quantity=800,
            decision="resized",
            reason="lot_size",
            check_sequence=("lot_size",),
        )
        display_map = {InstrumentId(2_000_002): "159915.SZ"}

        result = enrich_record_with_symbol(record, display_map)

        assert result["instrument_id"] == 2_000_002
        assert result["instrument_symbol"] == "159915.SZ"

    def test_missing_id_returns_empty_string(self) -> None:
        """display_map 中无对应 ID 时，instrument_symbol 为空字符串。"""
        record = RiskScanRecord(
            trade_date="2026-03-24",
            rule_id="max-drawdown",
            instrument_id=InstrumentId(9_999_999),
            scope="instrument",
            severity=RiskSeverity.WARNING,
            action_taken=RiskActionType.ALERT,
            detail="test",
            current_value=-0.05,
            threshold=-0.10,
        )
        result = enrich_record_with_symbol(record, {})

        assert result["instrument_symbol"] == ""


# ---------------------------------------------------------------------------
# write_backtest_artifacts
# ---------------------------------------------------------------------------

_FAKE_JSON_BYTES = orjson.dumps({"run_id": "test"})


def _mock_serialize_report(
    return_nav: bool = False,
) -> tuple[bytes, dict[str, pl.DataFrame]]:
    """构造 serialize_report 的 mock 返回值。"""
    tables: dict[str, pl.DataFrame] = {}
    if return_nav:
        tables["nav"] = pl.DataFrame({"trade_date": ["2026-03-20"], "nav": [1.0]})
    return _FAKE_JSON_BYTES, tables


class TestWriteBacktestArtifacts:
    """测试 write_backtest_artifacts 函数。"""

    @staticmethod
    def _make_manifest() -> RunManifest:
        return RunManifest(
            run_id="run-001",
            strategy_id="momentum-etf",
            strategy_version="2026.03",
            mode=RunMode.BACKTEST,
            created_at="2026-03-24T10:00:00Z",
            input_refs=(InstrumentId(2_000_001), InstrumentId(2_000_002)),
            parameter_overrides=("top_k=3",),
            config_hash="cfg-123",
            engine_version="0.2.0",
        )

    @patch("ditto_app.process.strategy_types.serialize_report")
    def test_returns_backtest_report_path(
        self,
        mock_serialize_report: MagicMock,
        tmp_path: Path,
    ) -> None:
        """返回 dict 至少包含 backtest_report 键。"""
        mock_report = MagicMock()
        mock_report.run_id = "run-001"
        mock_serialize_report.return_value = _mock_serialize_report()
        out_dir = tmp_path / "run-001"
        out_dir.mkdir()

        result = write_backtest_artifacts(mock_report, output_dir=out_dir)

        assert "backtest_report" in result
        assert result["backtest_report"].name == "backtest_report.json"

    @patch("ditto_app.process.strategy_types.serialize_report")
    def test_creates_output_dir_when_specified(
        self,
        mock_serialize_report: MagicMock,
        tmp_path: Path,
    ) -> None:
        """指定 output_dir 时，自动创建目录。"""
        mock_report = MagicMock()
        mock_report.run_id = "run-001"
        mock_serialize_report.return_value = _mock_serialize_report()
        output_dir = tmp_path / "custom" / "nested"

        write_backtest_artifacts(mock_report, output_dir=output_dir)

        assert output_dir.exists()
        assert (output_dir / "backtest_report.json").exists()

    @patch("ditto_app.process.strategy_types.serialize_report")
    def test_uses_temp_dir_when_no_output_dir(
        self,
        mock_serialize_report: MagicMock,
        tmp_path: Path,
    ) -> None:
        """未指定 output_dir 时，使用默认临时目录。"""
        mock_report = MagicMock()
        mock_report.run_id = "run-xyz"
        mock_serialize_report.return_value = _mock_serialize_report()

        with patch("ditto_app.process.strategy_types.tempfile") as mock_tmp:
            mock_tmp.gettempdir.return_value = str(tmp_path)
            write_backtest_artifacts(mock_report)

        output_dir = tmp_path / "ditto" / "run-xyz"
        assert output_dir.exists()

    @patch("ditto_app.process.strategy_types.serialize_report")
    def test_propagates_serialize_error(
        self,
        mock_serialize_report: MagicMock,
    ) -> None:
        """serialize_report 异常时传播（不吞异常）。"""
        mock_report = MagicMock()
        mock_report.run_id = "run-err"
        mock_serialize_report.side_effect = OSError("disk full")

        with pytest.raises(OSError, match="disk full"):
            write_backtest_artifacts(mock_report)

    @patch("ditto_app.process.strategy_types.serialize_report")
    def test_collects_parquet_artifacts(
        self,
        mock_serialize_report: MagicMock,
        tmp_path: Path,
    ) -> None:
        """serialize_report 返回的 parquet 表也写入磁盘。"""
        mock_report = MagicMock()
        mock_report.run_id = "run-extra"
        mock_serialize_report.return_value = _mock_serialize_report(return_nav=True)
        out_dir = tmp_path / "run-extra"

        result = write_backtest_artifacts(mock_report, output_dir=out_dir)

        assert "backtest_report" in result
        assert "nav" in result
        assert result["nav"].name == "nav.parquet"

    @patch("ditto_app.process.strategy_types.serialize_report")
    def test_writes_manifest_json_with_artifact_refs(
        self,
        mock_serialize_report: MagicMock,
        tmp_path: Path,
    ) -> None:
        """提供 manifest 时，写出 manifest.json 并回填 artifact 清单。"""
        mock_report = MagicMock()
        mock_report.run_id = "run-001"
        mock_report.risk_log = ()
        mock_report.pre_trade_log = ()
        mock_serialize_report.return_value = _mock_serialize_report()
        out_dir = tmp_path / "run-001"

        result = write_backtest_artifacts(
            mock_report,
            output_dir=out_dir,
            manifest=self._make_manifest(),
        )

        manifest_path = out_dir / "manifest.json"
        assert result["manifest"] == manifest_path
        parsed = orjson.loads(manifest_path.read_bytes())
        assert parsed["strategy_version"] == "2026.03"
        assert parsed["parameter_overrides"] == ["top_k=3"]
        assert "manifest.json" in parsed["artifacts"]

    @patch("ditto_app.process.strategy_types.serialize_report")
    def test_display_map_injects_instrument_symbol_into_risk_log(
        self,
        mock_serialize_report: MagicMock,
        tmp_path: Path,
    ) -> None:
        """display_map 注入 instrument_symbol 到 risk_log.json。"""
        mock_report = MagicMock()
        mock_report.run_id = "run-display"
        mock_serialize_report.return_value = _mock_serialize_report()
        out_dir = tmp_path / "run-display"

        risk_record = RiskScanRecord(
            trade_date="2026-03-24",
            rule_id="max-drawdown",
            instrument_id=InstrumentId(2_000_001),
            scope="instrument",
            severity=RiskSeverity.WARNING,
            action_taken=RiskActionType.ALERT,
            detail="drawdown -8%",
            current_value=-0.08,
            threshold=-0.10,
        )
        mock_report.risk_log = (risk_record,)
        mock_report.pre_trade_log = ()

        display_map = {InstrumentId(2_000_001): "510300.SH"}
        write_backtest_artifacts(
            mock_report,
            output_dir=out_dir,
            display_map=display_map,
        )

        risk_log_path = out_dir / "risk_log.json"
        assert risk_log_path.exists()
        records = orjson.loads(risk_log_path.read_bytes())
        assert len(records) == 1
        assert records[0]["instrument_id"] == 2_000_001
        assert records[0]["instrument_symbol"] == "510300.SH"

    @patch("ditto_app.process.strategy_types.serialize_report")
    def test_no_display_map_skips_instrument_symbol(
        self,
        mock_serialize_report: MagicMock,
        tmp_path: Path,
    ) -> None:
        """不传 display_map 时，审计日志不含 instrument_symbol 字段。"""
        mock_report = MagicMock()
        mock_report.run_id = "run-nodisplay"
        mock_serialize_report.return_value = _mock_serialize_report()
        out_dir = tmp_path / "run-nodisplay"

        risk_record = RiskScanRecord(
            trade_date="2026-03-24",
            rule_id="max-drawdown",
            instrument_id=InstrumentId(2_000_001),
            scope="instrument",
            severity=RiskSeverity.WARNING,
            action_taken=RiskActionType.ALERT,
            detail="test",
            current_value=-0.05,
            threshold=-0.10,
        )
        mock_report.risk_log = (risk_record,)
        mock_report.pre_trade_log = ()

        write_backtest_artifacts(mock_report, output_dir=out_dir)

        risk_log_path = out_dir / "risk_log.json"
        records = orjson.loads(risk_log_path.read_bytes())
        assert "instrument_symbol" not in records[0]
