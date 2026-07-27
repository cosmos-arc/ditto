"""
BacktestReportSerializer 单元测试 — JSON 输出格式兼容 replay 反序列化.

覆盖：
  - period 输出为 dict {"start": ..., "end": ...}（非 list）
  - rebalance_freq 字段存在
  - nav_series 字段存在
"""

from __future__ import annotations

from types import MappingProxyType
from typing import ClassVar

import orjson
import polars as pl
import pytest
from ditto_application.exceptions import AppProcessError
from ditto_backtest.manifest import RunManifest, RunMode
from ditto_backtest.statistics import (
    AggregatedTradeStatistics,
    AlphaStatistics,
    BacktestReport,
)
from ditto_kernel.identity import InstrumentId
from ditto_kernel.time_semantics import (
    DEFAULT_PIT_TIME_COLUMN,
    PIT_POLICY_FAIL_CLOSED,
)
from ditto_portfolio.accounting import AccountView, CashBook, Position
from ditto_strategy.alpha.selection_evidence import (
    ExclusionEvidence,
    ExclusionReason,
    FactorContributionEvidence,
    InitialUniverseEvidence,
    SelectionEvidence,
    SelectionEvidenceLog,
)

# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------


def _make_report(
    *,
    run_id: str = "test-run-001",
    period: tuple[str, str] = ("2026-01-01", "2026-03-31"),
    initial_cash: float = 1_000_000.0,
    final_nav: float = 1_050_000.0,
    nav_series: tuple[tuple[str, float], ...] = (
        ("2026-01-01", 1_000_000.0),
        ("2026-01-02", 1_005_000.0),
        ("2026-01-03", 1_050_000.0),
    ),
    final_account_state: AccountView | None = None,
) -> BacktestReport:
    """构建真实 BacktestReport 实例（仅填充必要字段）."""
    return BacktestReport(
        run_id=run_id,
        period=period,
        initial_cash=initial_cash,
        final_nav=final_nav,
        trade_stats=(),
        portfolio_stats=(),
        aggregated_trade_stats=AggregatedTradeStatistics(
            total_trades=0,
            long_trades=0,
            short_trades=0,
            win_trades=0,
            loss_trades=0,
            win_rate=0.0,
            profit_factor=0.0,
            avg_win=0.0,
            avg_loss=0.0,
            avg_win_loss_ratio=0.0,
            max_consecutive_wins=0,
            max_consecutive_losses=0,
            avg_holding_days=0.0,
            median_holding_days=0.0,
            best_trade=0.0,
            worst_trade=0.0,
            avg_trade_return_pct=0.0,
        ),
        alpha_stats=AlphaStatistics(
            annualized_return=0.0,
            annualized_volatility=0.0,
            sharpe_ratio=0.0,
            sortino_ratio=0.0,
            max_drawdown=0.0,
            max_drawdown_duration_days=0,
            calmar_ratio=0.0,
            information_ratio=None,
            tracking_error=None,
            beta=None,
            alpha_annualized=None,
            total_turnover=0.0,
            avg_turnover_per_rebalance=0.0,
            total_fees=0.0,
            net_return_after_cost=0.0,
            cost_drag=0.0,
        ),
        nav_series=nav_series,
        trade_log=(),
        fill_log=(),
        final_account_state=final_account_state,
    )


def _make_account_view() -> AccountView:
    """构建可序列化的最终账户状态样本."""
    instrument_id = InstrumentId(510300)
    position = Position(
        instrument_id=instrument_id,
        quantity=1000,
        available_quantity=1000,
        average_cost=3.5,
        market_value=3500.0,
        unrealized_pnl=0.0,
        realized_pnl=125.0,
        total_fees=8.0,
    )
    return AccountView(
        positions=MappingProxyType({instrument_id: position}),
        cash=CashBook(available=1_046_500.0, settled=1_046_500.0, frozen=0.0),
        total_value=1_050_000.0,
        nav=1_050_000.0,
        exposure=3500.0,
    )


# ---------------------------------------------------------------------------
# period 格式测试
# ---------------------------------------------------------------------------


class TestPeriodFormat:
    """period 字段应为 dict {"start": ..., "end": ...} 格式."""

    def test_period_is_dict_not_list(self) -> None:
        """序列化后 period 应为 dict，replay 按 .get('start') 读取."""
        from ditto_application.processes.execution.backtest_serialization import (
            serialize_report,
        )

        report = _make_report(period=("2026-01-01", "2026-06-30"))
        json_bytes, _ = serialize_report(report)
        data = orjson.loads(json_bytes)

        period = data["period"]
        assert isinstance(period, dict), (
            f"period 应为 dict, 实际为 {type(period).__name__}"
        )
        assert period["start"] == "2026-01-01"
        assert period["end"] == "2026-06-30"

    def test_period_dict_keys_match_tuple(self) -> None:
        """period dict 的 start/end 应与 report.period 元组对应."""
        from ditto_application.processes.execution.backtest_serialization import (
            serialize_report,
        )

        report = _make_report(period=("2025-06-15", "2025-12-31"))
        json_bytes, _ = serialize_report(report)
        data = orjson.loads(json_bytes)

        assert data["period"]["start"] == report.period[0]
        assert data["period"]["end"] == report.period[1]


# ---------------------------------------------------------------------------
# rebalance_freq 字段测试
# ---------------------------------------------------------------------------


class TestRebalanceFreq:
    """JSON 应包含 rebalance_freq 字段."""

    def test_rebalance_freq_present(self) -> None:
        """序列化后 JSON 应包含 rebalance_freq 字段."""
        from ditto_application.processes.execution.backtest_serialization import (
            serialize_report,
        )

        report = _make_report()
        json_bytes, _ = serialize_report(report)
        data = orjson.loads(json_bytes)

        assert "rebalance_freq" in data, "JSON 应包含 rebalance_freq 字段"

    def test_rebalance_freq_default_daily(self) -> None:
        """默认 rebalance_freq 应为 'daily'."""
        from ditto_application.processes.execution.backtest_serialization import (
            serialize_report,
        )

        report = _make_report()
        json_bytes, _ = serialize_report(report)
        data = orjson.loads(json_bytes)

        assert data["rebalance_freq"] == "daily"


class TestPitPolicyReporting:
    """backtest_report.json should expose PIT policy for audit/replay."""

    def test_report_includes_pit_policy_from_manifest(self) -> None:
        """When a manifest is available, report JSON mirrors its PIT policy."""
        from ditto_application.processes.execution.backtest_serialization import (
            serialize_report,
        )

        manifest = RunManifest(
            run_id="run-pit-report",
            strategy_id="momentum-etf",
            strategy_version="2026.01",
            mode=RunMode.BACKTEST,
            created_at="2026-01-31T00:00:00Z",
            spec_hash="a" * 64,
            base_spec_hash="b" * 64,
            parameter_hash="4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945",
            effective_parameters=(),
            research_snapshot_id=None,
            research_snapshot_manifest_hash=None,
            knowledge_lag_days=2,
        )

        json_bytes, _ = serialize_report(_make_report(), manifest=manifest)
        data = orjson.loads(json_bytes)

        assert data["pit_policy"] == {
            "time_column": DEFAULT_PIT_TIME_COLUMN,
            "policy": PIT_POLICY_FAIL_CLOSED,
            "unsafe_time_policy": "",
            "knowledge_lag_days": 2,
        }


class TestFinalAccountStateReporting:
    """backtest_report.json should include final account state proof source."""

    def test_report_includes_final_account_state_payload(self) -> None:
        """When report has final account state, JSON contains stable payload."""
        from ditto_application.processes.execution.backtest_serialization import (
            serialize_report,
        )

        account_view = _make_account_view()
        json_bytes, _ = serialize_report(
            _make_report(final_account_state=account_view),
        )
        data = orjson.loads(json_bytes)

        account_state = data["final_account_state"]
        assert account_state["nav"] == 1_050_000.0
        assert account_state["cash_available"] == 1_046_500.0
        assert account_state["positions"] == [
            {
                "instrument_id": 510300,
                "quantity": 1000,
                "available_quantity": 1000,
                "average_cost": 3.5,
                "market_value": 3500.0,
                "unrealized_pnl": 0.0,
                "realized_pnl": 125.0,
                "total_fees": 8.0,
            },
        ]


class TestResumeProvenanceReporting:
    """backtest_report.json should expose restored-run provenance."""

    def test_report_includes_resume_provenance_when_provided(self) -> None:
        """Resume child reports should say which checkpoint restored them."""
        from ditto_application.processes.execution.backtest_serialization import (
            serialize_report,
        )

        json_bytes, _ = serialize_report(
            _make_report(),
            resume_provenance={
                "from_run_id": "run-original",
                "checkpoint_trade_date": "2025-01-31",
                "checkpoint_completed_days": 21,
                "checkpoint_total_days": 60,
                "checkpoint_nav": 1_020_000.0,
                "checkpoint_order_count": 4,
                "checkpoint_fill_count": 4,
                "account_state_hash": "sha256:account",
                "settlement_state_hash": "sha256:settlement",
                "runtime_state_hash": "sha256:runtime",
            },
        )
        data = orjson.loads(json_bytes)

        assert data["resume_provenance"] == {
            "from_run_id": "run-original",
            "checkpoint_trade_date": "2025-01-31",
            "checkpoint_completed_days": 21,
            "checkpoint_total_days": 60,
            "checkpoint_nav": 1_020_000.0,
            "checkpoint_order_count": 4,
            "checkpoint_fill_count": 4,
            "account_state_hash": "sha256:account",
            "settlement_state_hash": "sha256:settlement",
            "runtime_state_hash": "sha256:runtime",
        }


# ---------------------------------------------------------------------------
# nav_series 字段测试
# ---------------------------------------------------------------------------


class TestNavSeries:
    """JSON 应包含 nav_series 字段."""

    def test_nav_series_present(self) -> None:
        """序列化后 JSON 应包含 nav_series 字段."""
        from ditto_application.processes.execution.backtest_serialization import (
            serialize_report,
        )

        report = _make_report()
        json_bytes, _ = serialize_report(report)
        data = orjson.loads(json_bytes)

        assert "nav_series" in data, "JSON 应包含 nav_series 字段"

    def test_nav_series_values_match_report(self) -> None:
        """nav_series 应只包含数值列表（不含日期）."""
        from ditto_application.processes.execution.backtest_serialization import (
            serialize_report,
        )

        nav_data = (
            ("2026-01-01", 1_000_000.0),
            ("2026-01-02", 1_005_000.0),
            ("2026-01-03", 1_050_000.0),
        )
        report = _make_report(nav_series=nav_data)
        json_bytes, _ = serialize_report(report)
        data = orjson.loads(json_bytes)

        expected = [v for _, v in nav_data]
        assert data["nav_series"] == expected

    def test_nav_series_none_when_empty(self) -> None:
        """nav_series 为空时，JSON 中应为 None."""
        from ditto_application.processes.execution.backtest_serialization import (
            serialize_report,
        )

        report = _make_report(nav_series=())
        json_bytes, _ = serialize_report(report)
        data = orjson.loads(json_bytes)

        assert data["nav_series"] is None


# ---------------------------------------------------------------------------
# Round-trip 兼容性测试
# ---------------------------------------------------------------------------


class TestRoundTripCompatibility:
    """序列化输出与 replay 反序列化期望格式兼容."""

    def test_replay_can_extract_start_end_from_period(self) -> None:
        """replay._build_config 通过 period.get('start') 读取日期."""
        from ditto_application.processes.execution.backtest_serialization import (
            serialize_report,
        )

        report = _make_report(period=("2026-01-15", "2026-04-10"))
        json_bytes, _ = serialize_report(report)
        data = orjson.loads(json_bytes)

        # 模拟 replay._build_config 中的读取方式
        period = data.get("period", {})
        start = period.get("start", "")
        end = period.get("end", "")

        assert start == "2026-01-15"
        assert end == "2026-04-10"

    def test_replay_can_extract_rebalance_freq(self) -> None:
        """replay._extract_rebalance_freq 通过 report.get('rebalance_freq') 读取."""
        from ditto_application.processes.execution.backtest_serialization import (
            serialize_report,
        )

        report = _make_report()
        json_bytes, _ = serialize_report(report)
        data = orjson.loads(json_bytes)

        # 模拟 replay._extract_rebalance_freq 的读取方式
        freq = data.get("rebalance_freq")
        assert isinstance(freq, str), "rebalance_freq 应为字符串"
        assert freq, "rebalance_freq 应为非空"

    def test_replay_can_extract_nav_series(self) -> None:
        """replay._extract_nav 通过 report.get('nav_series') 读取."""
        from ditto_application.processes.execution.backtest_serialization import (
            serialize_report,
        )

        nav_data = (
            ("2026-01-01", 1.0),
            ("2026-01-02", 1.01),
            ("2026-01-03", 1.02),
        )
        report = _make_report(nav_series=nav_data)
        json_bytes, _ = serialize_report(report)
        data = orjson.loads(json_bytes)

        # 模拟 replay._extract_nav 的读取方式
        nav_data_from_json = data.get("nav_series")
        assert nav_data_from_json is not None
        assert [float(v) for v in nav_data_from_json] == [1.0, 1.01, 1.02]


class TestSelectionEvidenceTables:
    """R3 selection evidence has stable optional columnar artifacts."""

    _EXPECTED_SCHEMAS: ClassVar[dict[str, pl.Schema]] = {
        "initial_universe_evidence": pl.Schema(
            {
                "run_id": pl.String,
                "trade_date": pl.String,
                "instrument_id": pl.String,
                "instrument_id_kind": pl.String,
                "ordinal": pl.Int64,
            },
        ),
        "exclusion_evidence": pl.Schema(
            {
                "run_id": pl.String,
                "trade_date": pl.String,
                "instrument_id": pl.String,
                "instrument_id_kind": pl.String,
                "stage": pl.String,
                "reason_code": pl.String,
                "message": pl.String,
            },
        ),
        "selection_evidence": pl.Schema(
            {
                "run_id": pl.String,
                "trade_date": pl.String,
                "instrument_id": pl.String,
                "instrument_id_kind": pl.String,
                "score": pl.Float64,
                "rank": pl.Int64,
                "selected": pl.Boolean,
            },
        ),
        "factor_contribution_evidence": pl.Schema(
            {
                "run_id": pl.String,
                "trade_date": pl.String,
                "instrument_id": pl.String,
                "instrument_id_kind": pl.String,
                "factor_name": pl.String,
                "raw_value": pl.Float64,
                "processed_value": pl.Float64,
                "normalized_value": pl.Float64,
                "weight": pl.Float64,
                "contribution": pl.Float64,
                "factor_signal_score": pl.Float64,
                "rank": pl.Int64,
                "selected": pl.Boolean,
            },
        ),
    }

    def test_public_serializer_emits_exactly_four_empty_existing_tables(
        self,
    ) -> None:
        from ditto_application.processes.execution.backtest_serialization import (
            serialize_selection_evidence,
        )

        tables = serialize_selection_evidence(
            "test-run-001",
            SelectionEvidenceLog(),
        )

        assert set(tables) == set(self._EXPECTED_SCHEMAS)
        for table_name, expected_schema in self._EXPECTED_SCHEMAS.items():
            assert tables[table_name].is_empty()
            assert tables[table_name].schema == expected_schema

    @staticmethod
    def _single_event_log(
        event: (
            InitialUniverseEvidence
            | ExclusionEvidence
            | SelectionEvidence
            | FactorContributionEvidence
        ),
    ) -> SelectionEvidenceLog:
        if type(event) is InitialUniverseEvidence:
            return SelectionEvidenceLog(initial_universe=(event,))
        if type(event) is ExclusionEvidence:
            return SelectionEvidenceLog(exclusions=(event,))
        if type(event) is SelectionEvidence:
            return SelectionEvidenceLog(selections=(event,))
        return SelectionEvidenceLog(factor_contributions=(event,))

    @pytest.mark.parametrize(
        ("event", "field_name", "poisoned_value"),
        [
            (
                InitialUniverseEvidence("2026-03-22", 1, 1),
                "trade_date",
                "20260322",
            ),
            (
                InitialUniverseEvidence("2026-03-22", 1, 1),
                "instrument_id",
                True,
            ),
            (
                InitialUniverseEvidence("2026-03-22", 1, 1),
                "ordinal",
                0,
            ),
            (
                ExclusionEvidence(
                    "2026-03-22",
                    1,
                    "selection",
                    ExclusionReason.BELOW_TOP_K,
                ),
                "stage",
                " ",
            ),
            (
                ExclusionEvidence(
                    "2026-03-22",
                    1,
                    "selection",
                    ExclusionReason.BELOW_TOP_K,
                ),
                "reason_code",
                "below_top_k",
            ),
            (
                ExclusionEvidence(
                    "2026-03-22",
                    1,
                    "selection",
                    ExclusionReason.BELOW_TOP_K,
                ),
                "message",
                7,
            ),
            (
                SelectionEvidence("2026-03-22", 1, 0.5, 1, True),
                "instrument_id",
                "",
            ),
            (
                SelectionEvidence("2026-03-22", 1, 0.5, 1, True),
                "score",
                float("inf"),
            ),
            (
                SelectionEvidence("2026-03-22", 1, 0.5, 1, True),
                "rank",
                0,
            ),
            (
                SelectionEvidence("2026-03-22", 1, 0.5, 1, True),
                "selected",
                1,
            ),
            (
                FactorContributionEvidence(
                    "2026-03-22",
                    1,
                    "momentum",
                    0.5,
                    0.5,
                    0.5,
                    1.0,
                    0.5,
                    0.5,
                    1,
                    True,
                ),
                "factor_name",
                "",
            ),
            (
                FactorContributionEvidence(
                    "2026-03-22",
                    1,
                    "momentum",
                    0.5,
                    0.5,
                    0.5,
                    1.0,
                    0.5,
                    0.5,
                    1,
                    True,
                ),
                "weight",
                float("nan"),
            ),
            (
                FactorContributionEvidence(
                    "2026-03-22",
                    1,
                    "momentum",
                    0.5,
                    0.5,
                    0.5,
                    1.0,
                    0.5,
                    0.5,
                    1,
                    True,
                ),
                "rank",
                0,
            ),
            (
                FactorContributionEvidence(
                    "2026-03-22",
                    1,
                    "momentum",
                    0.5,
                    0.5,
                    0.5,
                    1.0,
                    0.5,
                    0.5,
                    1,
                    True,
                ),
                "selected",
                1,
            ),
        ],
        ids=(
            "compact-trade-date",
            "boolean-instrument-id",
            "non-positive-ordinal",
            "blank-stage",
            "untyped-reason",
            "non-text-message",
            "empty-instrument-id",
            "non-finite-score",
            "non-positive-rank",
            "non-boolean-selected",
            "blank-factor-name",
            "non-finite-weight",
            "non-positive-factor-rank",
            "non-boolean-factor-selected",
        ),
    )
    def test_public_serializer_rebuilds_and_rejects_poisoned_events(
        self,
        event: (
            InitialUniverseEvidence
            | ExclusionEvidence
            | SelectionEvidence
            | FactorContributionEvidence
        ),
        field_name: str,
        poisoned_value: object,
    ) -> None:
        from ditto_application.processes.execution.backtest_serialization import (
            serialize_selection_evidence,
        )

        log = self._single_event_log(event)
        object.__setattr__(event, field_name, poisoned_value)

        with pytest.raises(AppProcessError) as exc_info:
            serialize_selection_evidence("test-run-001", log)

        assert exc_info.value.details["reason"] == "invalid_selection_evidence_log"

    def test_public_serializer_rejects_poisoned_log_collections(self) -> None:
        from ditto_application.processes.execution.backtest_serialization import (
            serialize_selection_evidence,
        )

        log = SelectionEvidenceLog()
        object.__setattr__(log, "selections", (object(),))

        with pytest.raises(AppProcessError) as exc_info:
            serialize_selection_evidence("test-run-001", log)

        assert exc_info.value.details["reason"] == "invalid_selection_evidence_log"

    def test_public_serializer_rebuilds_log_level_invariants(self) -> None:
        from ditto_application.processes.execution.backtest_serialization import (
            serialize_selection_evidence,
        )

        exclusion = ExclusionEvidence(
            "2026-03-22",
            1,
            "selection",
            ExclusionReason.BELOW_TOP_K,
        )
        selection = SelectionEvidence(
            "2026-03-22",
            1,
            0.5,
            1,
            False,
        )
        log = SelectionEvidenceLog(
            exclusions=(exclusion,),
            selections=(selection,),
        )
        object.__setattr__(selection, "selected", True)

        with pytest.raises(AppProcessError) as exc_info:
            serialize_selection_evidence("test-run-001", log)

        assert exc_info.value.details["reason"] == "invalid_selection_evidence_log"

    def test_empty_evidence_log_emits_all_stable_empty_schemas(self) -> None:
        from ditto_application.processes.execution.backtest_serialization import (
            serialize_report,
        )

        _, tables = serialize_report(
            _make_report(),
            selection_evidence=SelectionEvidenceLog(),
        )

        for table_name, expected_schema in self._EXPECTED_SCHEMAS.items():
            assert table_name in tables
            assert tables[table_name].is_empty()
            assert tables[table_name].schema == expected_schema

    def test_omitted_evidence_preserves_existing_table_surface(self) -> None:
        from ditto_application.processes.execution.backtest_serialization import (
            serialize_report,
        )

        _, tables = serialize_report(_make_report())

        assert set(tables) == {"nav"}
        assert not (set(tables) & set(self._EXPECTED_SCHEMAS))

    def test_multi_day_evidence_serializes_trade_date_in_every_table(self) -> None:
        from ditto_application.processes.execution.backtest_serialization import (
            serialize_report,
        )

        trade_dates = ("2026-03-22", "2026-03-23")
        log = SelectionEvidenceLog(
            initial_universe=tuple(
                InitialUniverseEvidence(
                    trade_date=trade_date,
                    instrument_id=1,
                    ordinal=1,
                )
                for trade_date in trade_dates
            ),
            exclusions=tuple(
                ExclusionEvidence(
                    trade_date=trade_date,
                    instrument_id=1,
                    stage="selection",
                    reason_code=ExclusionReason.BELOW_TOP_K,
                )
                for trade_date in trade_dates
            ),
            selections=tuple(
                SelectionEvidence(
                    trade_date=trade_date,
                    instrument_id=1,
                    score=0.5,
                    rank=2,
                    selected=False,
                )
                for trade_date in trade_dates
            ),
            factor_contributions=tuple(
                FactorContributionEvidence(
                    trade_date=trade_date,
                    instrument_id=1,
                    factor_name="momentum",
                    raw_value=0.5,
                    processed_value=0.5,
                    normalized_value=0.5,
                    weight=1.0,
                    contribution=0.5,
                    factor_signal_score=0.5,
                    rank=2,
                    selected=False,
                )
                for trade_date in trade_dates
            ),
        )

        _, tables = serialize_report(_make_report(), selection_evidence=log)

        for table_name in self._EXPECTED_SCHEMAS:
            assert tables[table_name]["trade_date"].to_list() == list(trade_dates)

    def test_populated_evidence_uses_stable_names_without_overwriting_report_tables(
        self,
    ) -> None:
        from ditto_application.processes.execution.backtest_serialization import (
            serialize_report,
        )

        log = SelectionEvidenceLog(
            initial_universe=(
                InitialUniverseEvidence(
                    trade_date="2026-03-22",
                    instrument_id=1,
                    ordinal=1,
                ),
                InitialUniverseEvidence(
                    trade_date="2026-03-22",
                    instrument_id="000002.SZ",
                    ordinal=2,
                ),
            ),
            exclusions=(
                ExclusionEvidence(
                    trade_date="2026-03-22",
                    instrument_id="000002.SZ",
                    stage="selection",
                    reason_code=ExclusionReason.BELOW_TOP_K,
                ),
            ),
            selections=(
                SelectionEvidence(
                    trade_date="2026-03-22",
                    instrument_id=1,
                    score=0.9,
                    rank=1,
                    selected=True,
                ),
                SelectionEvidence(
                    trade_date="2026-03-22",
                    instrument_id="000002.SZ",
                    score=0.5,
                    rank=2,
                    selected=False,
                ),
            ),
            factor_contributions=(
                FactorContributionEvidence(
                    trade_date="2026-03-22",
                    instrument_id=1,
                    factor_name="momentum",
                    raw_value=0.12,
                    processed_value=1.1,
                    normalized_value=1.0,
                    weight=0.6,
                    contribution=0.6,
                    factor_signal_score=0.8,
                    rank=1,
                    selected=True,
                ),
            ),
        )

        _, tables = serialize_report(_make_report(), selection_evidence=log)

        assert "nav" in tables
        assert set(self._EXPECTED_SCHEMAS) <= set(tables)
        assert tables["initial_universe_evidence"].to_dicts() == [
            {
                "run_id": "test-run-001",
                "trade_date": "2026-03-22",
                "instrument_id": "1",
                "instrument_id_kind": "integer",
                "ordinal": 1,
            },
            {
                "run_id": "test-run-001",
                "trade_date": "2026-03-22",
                "instrument_id": "000002.SZ",
                "instrument_id_kind": "string",
                "ordinal": 2,
            },
        ]
        assert tables["exclusion_evidence"]["reason_code"].to_list() == [
            "below_top_k",
        ]
        assert tables["factor_contribution_evidence"]["selected"].to_list() == [
            True,
        ]
