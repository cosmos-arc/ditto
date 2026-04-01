"""artifact_writer 单元测试 — Port 层产物序列化。"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import orjson
import pytest
from ditto_engine.backtest.audit import RiskScanRecord
from ditto_engine.backtest.manifest import RunManifest, RunMode
from ditto_engine.backtest.risk.post_trade import RiskActionType, RiskSeverity
from ditto_engine.backtest.statistics import PreTradeDecisionRecord
from ditto_kernel.identity import InstrumentId
from ditto_port.services.strategy.artifact_writer import (
    enrich_record_with_symbol,
    write_backtest_artifacts,
)

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

    @patch("ditto_port.services.strategy.artifact_writer.serialize")
    def test_returns_backtest_report_path(
        self,
        mock_serialize: MagicMock,
        tmp_path: Path,
    ) -> None:
        """返回 dict 至少包含 backtest_report 键。"""
        mock_report = MagicMock()
        mock_report.run_id = "run-001"
        out_dir = tmp_path / "run-001"
        out_dir.mkdir()
        fake_json_path = out_dir / "backtest_report.json"
        fake_json_path.touch()
        mock_serialize.return_value = fake_json_path

        result = write_backtest_artifacts(mock_report, output_dir=out_dir)

        assert "backtest_report" in result
        assert result["backtest_report"] == fake_json_path

    @patch("ditto_port.services.strategy.artifact_writer.serialize")
    def test_passes_output_dir_to_serialize(
        self,
        mock_serialize: MagicMock,
        tmp_path: Path,
    ) -> None:
        """指定 output_dir 时，传递给 serialize。"""
        mock_report = MagicMock()
        mock_report.run_id = "run-001"
        output_dir = tmp_path / "custom"
        output_dir.mkdir()
        mock_serialize.return_value = output_dir / "backtest_report.json"

        write_backtest_artifacts(mock_report, output_dir=output_dir)

        call_args = mock_serialize.call_args
        assert call_args[0][1] == output_dir

    @patch("ditto_port.services.strategy.artifact_writer.serialize")
    def test_uses_temp_dir_when_no_output_dir(
        self,
        mock_serialize: MagicMock,
        tmp_path: Path,
    ) -> None:
        """未指定 output_dir 时，使用默认临时目录。"""
        mock_report = MagicMock()
        mock_report.run_id = "run-xyz"
        output_dir = tmp_path / "ditto" / "run-xyz"
        output_dir.mkdir(parents=True)
        mock_serialize.return_value = output_dir / "backtest_report.json"

        # Patch tempfile.gettempdir to use tmp_path
        with patch("ditto_port.services.strategy.artifact_writer.tempfile") as mock_tmp:
            mock_tmp.gettempdir.return_value = str(tmp_path)
            write_backtest_artifacts(mock_report)

        call_args = mock_serialize.call_args
        passed_dir = call_args[0][1]
        assert "ditto" in str(passed_dir)
        assert "run-xyz" in str(passed_dir)

    @patch("ditto_port.services.strategy.artifact_writer.serialize")
    def test_propagates_serialize_error(
        self,
        mock_serialize: MagicMock,
    ) -> None:
        """serialize 异常时传播（不吞异常）。"""
        mock_report = MagicMock()
        mock_report.run_id = "run-err"
        mock_serialize.side_effect = OSError("disk full")

        with pytest.raises(OSError, match="disk full"):
            write_backtest_artifacts(mock_report)

    @patch("ditto_port.services.strategy.artifact_writer.serialize")
    def test_collects_additional_files(
        self,
        mock_serialize: MagicMock,
        tmp_path: Path,
    ) -> None:
        """serialize 写入的额外文件也包含在返回值中。"""
        mock_report = MagicMock()
        mock_report.run_id = "run-extra"
        out_dir = tmp_path / "run-extra"
        out_dir.mkdir()
        json_path = out_dir / "backtest_report.json"
        json_path.touch()
        # 模拟 serialize 还写了 nav.parquet
        (out_dir / "nav.parquet").touch()
        mock_serialize.return_value = json_path

        result = write_backtest_artifacts(mock_report, output_dir=out_dir)

        assert "backtest_report" in result
        assert "nav" in result
        assert result["nav"] == out_dir / "nav.parquet"

    @patch("ditto_port.services.strategy.artifact_writer.serialize")
    def test_writes_manifest_json_with_artifact_refs(
        self,
        mock_serialize: MagicMock,
        tmp_path: Path,
    ) -> None:
        """提供 manifest 时，写出 manifest.json 并回填 artifact 清单。"""
        mock_report = MagicMock()
        mock_report.run_id = "run-001"
        mock_report.risk_log = ()
        mock_report.pre_trade_log = ()
        out_dir = tmp_path / "run-001"
        out_dir.mkdir()
        json_path = out_dir / "backtest_report.json"
        json_path.touch()
        mock_serialize.return_value = json_path

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
        assert parsed["artifacts"] == ["backtest_report.json", "manifest.json"]

    @patch("ditto_port.services.strategy.artifact_writer.serialize")
    def test_display_map_injects_instrument_symbol_into_risk_log(
        self,
        mock_serialize: MagicMock,
        tmp_path: Path,
    ) -> None:
        """display_map 注入 instrument_symbol 到 risk_log.json。"""
        mock_report = MagicMock()
        mock_report.run_id = "run-display"
        out_dir = tmp_path / "run-display"
        out_dir.mkdir()
        mock_serialize.return_value = out_dir / "backtest_report.json"

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

    @patch("ditto_port.services.strategy.artifact_writer.serialize")
    def test_no_display_map_skips_instrument_symbol(
        self,
        mock_serialize: MagicMock,
        tmp_path: Path,
    ) -> None:
        """不传 display_map 时，审计日志不含 instrument_symbol 字段。"""
        mock_report = MagicMock()
        mock_report.run_id = "run-nodisplay"
        out_dir = tmp_path / "run-nodisplay"
        out_dir.mkdir()
        mock_serialize.return_value = out_dir / "backtest_report.json"

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
