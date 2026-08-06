"""
Unit tests for BacktestRunHandler + Cancel/Retry Handlers.

Tests parameter validation, factor pre-compilation, RunRecord creation,
error handling, and cancel/retry status guards.
"""

from __future__ import annotations

from dataclasses import asdict, replace
from unittest.mock import Mock

import pytest
from ditto_application.commands.backtest import (
    BacktestRunCommand,
    BacktestRunHandler,
    BacktestRunResult,
    CancelRunCommand,
    CancelRunHandler,
    CostConfig,
    ResumeRunCommand,
    ResumeRunHandler,
    RetryRunCommand,
    RetryRunHandler,
    parse_candidate_parameters,
)
from ditto_application.exceptions import AppCommandError, AppProcessError
from ditto_application.processes.execution.strategy_types import RunLifecycleService
from ditto_kernel.strategy import ImpactModel
from ditto_strategy.alpha.parameters import CandidateParameter, legacy_parameter_path
from ditto_strategy.alpha.specs import (
    ParamConstraint,
    ScorerSpec,
    SelectorSpec,
    StrategySpec,
)
from ditto_strategy.models import StrategySpecRecord
from ditto_strategy.runs.models import StrategyRunCheckpointRecord, StrategyRunRecord
from ditto_strategy.storage.sqlite.services.strategy_run_service import (
    StrategyRunCheckpointStore,
    StrategyRunLifecycleStore,
)


@pytest.fixture
def mock_catalog_service() -> Mock:
    """Mock StrategyCatalogService."""
    svc = Mock()
    record = _catalog_record(
        strategy_id="momentum-etf",
        signal_expressions=("ts_mean(close, 20)",),
        signal_weights=(1.0,),
    )
    svc.get_active_published.return_value = record
    svc.get_spec.return_value = record
    return svc


def _catalog_record(
    *,
    strategy_id: str,
    signal_expressions: tuple[str, ...] = (),
    signal_weights: tuple[float | str, ...] = (),
) -> StrategySpecRecord:
    spec = StrategySpec(
        strategy_id=strategy_id,
        name=strategy_id,
        template="etf_rotation",
        universe="csi_etf_broad",
        asset_class="etf",
        scorer=ScorerSpec(method="rank"),
        selector=SelectorSpec(method="top_k", params={"k": 3}),
        params={"top_k": 3},
        param_constraints=(
            ParamConstraint(
                name="top_k",
                dtype="int",
                min_value=1,
                max_value=10,
                step=1,
            ),
        ),
        signal_expressions=signal_expressions,
        signal_weights=tuple(
            value for value in signal_weights if isinstance(value, float)
        ),
        required_datasets=("etf_daily",),
    )
    payload = asdict(spec)
    payload["signal_expressions"] = list(signal_expressions)
    if signal_weights:
        payload["signal_weights"] = list(signal_weights)
    return StrategySpecRecord(
        strategy_id=strategy_id,
        name=strategy_id,
        spec_json=payload,
        version=7,
    )


@pytest.fixture
def mock_run_service() -> Mock:
    """Mock RunLifecycleService."""
    return Mock(spec=RunLifecycleService)


@pytest.fixture
def mock_factor_bridge() -> Mock:
    """Mock FactorBridge."""
    bridge = Mock()
    bridge.compile_and_validate.return_value = Mock()  # CompiledExpressions
    return bridge


@pytest.fixture
def handler(
    mock_catalog_service: Mock,
    mock_run_service: Mock,
    mock_factor_bridge: Mock,
) -> BacktestRunHandler:
    """Create handler with mocked dependencies."""
    return BacktestRunHandler(
        catalog_service=mock_catalog_service,
        run_service=mock_run_service,
        factor_bridge=mock_factor_bridge,
    )


def _make_command(**overrides) -> BacktestRunCommand:
    """Build a default valid command with optional overrides."""
    defaults = {
        "strategy_id": "momentum-etf",
        "start_date": "2025-01-01",
        "end_date": "2025-03-31",
        "initial_cash": 1_000_000.0,
        "parameter_overrides": (),
    }
    defaults.update(overrides)
    return BacktestRunCommand(**defaults)


def _make_run_record(**overrides) -> StrategyRunRecord:
    """Build a default StrategyRunRecord with optional overrides."""
    defaults = {
        "run_id": "abc123",
        "strategy_id": "momentum-etf",
        "strategy_version": "1",
        "mode": "backtest",
        "status": "pending",
        "config_json": "",
    }
    defaults.update(overrides)
    return StrategyRunRecord(**defaults)


def _make_checkpoint_record(**overrides) -> StrategyRunCheckpointRecord:
    """Build a default StrategyRunCheckpointRecord with optional overrides."""
    defaults = {
        "run_id": "abc123",
        "strategy_id": "momentum-etf",
        "strategy_version": "1",
        "mode": "backtest",
        "completed_trade_date": "2025-01-31",
        "resume_from": "2025-02-03",
        "completed_days": 21,
        "total_days": 60,
        "nav": 1_020_000.0,
        "order_count": 4,
        "fill_count": 4,
        "account_state_json": (
            '{"cash_available":920000.0,"cash_settled":900000.0,'
            '"cash_frozen":20000.0,"positions":[]}'
        ),
        "account_state_hash": "sha256:account-state",
        "settlement_state_json": (
            '{"frozen_quantities":[{"instrument_id":1,'
            '"quantity":1000,"settle_date":"2026-03-03"}]}'
        ),
        "settlement_state_hash": "sha256:settlement-state",
        "runtime_state_json": (
            '{"delayed_signals":[{"cash_target":0.5,'
            '"positions":[{"instrument_id":1,"target_weight":0.5}],'
            '"queue_index":0,"run_id":"abc123","strategy_id":"momentum-etf",'
            '"trade_date":"2025-01-31"}],'
            '"pending_orders":[{"average_fill_price":null,'
            '"client_order_id":"order-001","direction":"buy",'
            '"filled_price":null,"filled_quantity":0,"instrument_id":1,'
            '"leaves_quantity":300,"order_type":"market","price":null,'
            '"quantity":300,"status":"submitted","stop_price":null,'
            '"trade_date":"2025-01-31"}]}'
        ),
        "runtime_state_hash": "sha256:runtime-state",
    }
    defaults.update(overrides)
    return StrategyRunCheckpointRecord(**defaults)


class TestBacktestRunHandler:
    """Tests for BacktestRunHandler.handle()."""

    def test_successful_run_creates_record(
        self,
        handler: BacktestRunHandler,
        mock_run_service: Mock,
        mock_factor_bridge: Mock,
    ) -> None:
        """Successful flow: validate → compile → create record → return result."""
        cmd = _make_command()

        result = handler.handle(cmd)

        # Factor expressions were compiled
        mock_factor_bridge.compile_and_validate.assert_called_once()

        # RunRecord was created with PENDING status
        mock_run_service.create_run.assert_called_once()
        call_kwargs = mock_run_service.create_run.call_args
        assert call_kwargs.kwargs["strategy_id"] == "momentum-etf"
        assert call_kwargs.kwargs["strategy_version"] == "7"
        assert call_kwargs.kwargs["mode"] == "backtest"

        # Result has run_id
        assert isinstance(result, BacktestRunResult)
        assert result.run_id
        assert result.status == "pending"
        assert result.strategy_version == 7

        import orjson

        config_data = orjson.loads(call_kwargs.kwargs["config_json"])
        assert config_data["strategy_version"] == 7
        assert config_data["candidate_parameters"] == []
        assert config_data["effective_parameters"] == [
            {
                "path": legacy_parameter_path("top_k"),
                "value": 3,
            },
        ]
        assert "parameter_overrides" not in config_data

    def test_run_config_records_experimental_data_opt_in(
        self,
        handler: BacktestRunHandler,
        mock_run_service: Mock,
    ) -> None:
        """RunRecord config_json exposes the maturity opt-in for audit/retry."""
        cmd = _make_command(allow_experimental_data=True)

        handler.handle(cmd)

        import orjson

        call_kwargs = mock_run_service.create_run.call_args.kwargs
        config_data = orjson.loads(call_kwargs["config_json"])
        assert config_data["allow_experimental_data"] is True

    def test_strategy_not_found_raises(
        self,
        handler: BacktestRunHandler,
        mock_catalog_service: Mock,
    ) -> None:
        """Strategy not found raises ValueError."""
        mock_catalog_service.get_spec.return_value = None

        cmd = _make_command(strategy_id="nonexistent")

        with pytest.raises(AppCommandError, match="Strategy not found"):
            handler.handle(cmd)

    def test_invalid_date_range_raises(
        self,
        handler: BacktestRunHandler,
    ) -> None:
        """End date before start date raises ValueError."""
        cmd = _make_command(start_date="2025-06-01", end_date="2025-01-01")

        with pytest.raises(AppCommandError, match="日期范围无效"):
            handler.handle(cmd)

    def test_invalid_date_format_raises(
        self,
        handler: BacktestRunHandler,
    ) -> None:
        """Invalid date format raises ValueError."""
        cmd = _make_command(start_date="not-a-date")

        with pytest.raises(AppCommandError, match="日期格式无效"):
            handler.handle(cmd)

    def test_factor_compile_failure_raises(
        self,
        handler: BacktestRunHandler,
        mock_factor_bridge: Mock,
        mock_run_service: Mock,
    ) -> None:
        """Factor compilation failure raises typed process error, no record created."""
        mock_factor_bridge.compile_and_validate.side_effect = AppProcessError(
            "编译失败 (signal_0): unknown function 'bad_func'"
        )

        cmd = _make_command()

        with pytest.raises(AppProcessError, match="编译失败"):
            handler.handle(cmd)

        # No RunRecord should be created when compilation fails
        mock_run_service.create_run.assert_not_called()

    def test_parameter_overrides_passed(
        self,
        handler: BacktestRunHandler,
        mock_run_service: Mock,
    ) -> None:
        """Legacy wire overrides are parsed once into typed canonical candidates."""
        cmd = _make_command(parameter_overrides=("lookback=30",))

        with pytest.raises(AppCommandError, match="not registered"):
            handler.handle(cmd)

        mock_run_service.create_run.assert_not_called()

    def test_registered_parameter_override_is_bound_before_run_creation(
        self,
        handler: BacktestRunHandler,
        mock_run_service: Mock,
    ) -> None:
        """A valid typed candidate and its canonical identity are persisted."""
        cmd = _make_command(parameter_overrides=("top_k=2",))

        result = handler.handle(cmd)

        assert result.candidate_parameters == (
            CandidateParameter(path=legacy_parameter_path("top_k"), value=2),
        )
        import orjson

        config = orjson.loads(
            mock_run_service.create_run.call_args.kwargs["config_json"]
        )
        assert config["candidate_parameters"] == [
            {"path": legacy_parameter_path("top_k"), "value": 2}
        ]
        assert config["effective_parameters"] == [
            {"path": legacy_parameter_path("top_k"), "value": 2}
        ]
        assert len(config["base_spec_hash"]) == 64
        assert len(config["spec_hash"]) == 64
        assert len(config["parameter_hash"]) == 64

    def test_explicit_strategy_version_uses_exact_catalog_query(
        self,
        handler: BacktestRunHandler,
        mock_catalog_service: Mock,
    ) -> None:
        """An explicit command version never resolves a moving latest pointer."""
        handler.handle(_make_command(strategy_version=7))

        mock_catalog_service.get_active_published.assert_not_called()
        mock_catalog_service.get_spec.assert_called_once_with("momentum-etf", 7)

    def test_implicit_version_is_locked_by_exact_second_read(
        self,
        handler: BacktestRunHandler,
        mock_catalog_service: Mock,
    ) -> None:
        """Latest published selection is immediately frozen by exact version read."""
        handler.handle(_make_command())

        mock_catalog_service.get_active_published.assert_called_once_with(
            "momentum-etf"
        )
        mock_catalog_service.get_spec.assert_called_once_with("momentum-etf", 7)

    @pytest.mark.parametrize("explicit_version", [None, 7])
    def test_exact_catalog_read_cannot_substitute_a_different_version(
        self,
        handler: BacktestRunHandler,
        mock_catalog_service: Mock,
        mock_run_service: Mock,
        explicit_version: int | None,
    ) -> None:
        """The exact-read contract fails closed if a catalog returns another row."""
        selected = mock_catalog_service.get_active_published.return_value
        mock_catalog_service.get_spec.return_value = replace(selected, version=8)

        with pytest.raises(AppCommandError, match="exact published"):
            handler.handle(_make_command(strategy_version=explicit_version))

        mock_run_service.create_run.assert_not_called()

    def test_no_signal_expressions_skips_compile(
        self,
        handler: BacktestRunHandler,
        mock_catalog_service: Mock,
        mock_factor_bridge: Mock,
        mock_run_service: Mock,
    ) -> None:
        """Strategy without signal_expressions skips factor compilation."""
        record = _catalog_record(strategy_id="simple-strategy")
        mock_catalog_service.get_active_published.return_value = record
        mock_catalog_service.get_spec.return_value = record

        cmd = _make_command(strategy_id="simple-strategy")
        result = handler.handle(cmd)

        mock_factor_bridge.compile_and_validate.assert_not_called()
        assert isinstance(result, BacktestRunResult)

    def test_invalid_signal_weight_raises_app_command_error(
        self,
        handler: BacktestRunHandler,
        mock_catalog_service: Mock,
        mock_factor_bridge: Mock,
        mock_run_service: Mock,
    ) -> None:
        """Invalid signal weight values raise typed command errors."""
        record = _catalog_record(
            strategy_id="bad-weights",
            signal_expressions=("close",),
            signal_weights=("not-a-number",),
        )
        mock_catalog_service.get_active_published.return_value = record
        mock_catalog_service.get_spec.return_value = record

        with pytest.raises(AppCommandError, match="signal_weights") as exc_info:
            handler.handle(_make_command(strategy_id="bad-weights"))

        assert exc_info.value.details == {
            "strategy_id": "bad-weights",
            "field": "signal_weights",
            "index": 0,
            "value": "not-a-number",
        }
        mock_factor_bridge.compile_and_validate.assert_not_called()
        mock_run_service.create_run.assert_not_called()


class TestBacktestRunCommand:
    """Tests for BacktestRunCommand DTO."""

    def test_frozen_command(self) -> None:
        """Command is frozen."""
        cmd = _make_command()
        with pytest.raises(AttributeError):
            cmd.strategy_id = "changed"  # type: ignore[misc]

    def test_default_values(self) -> None:
        """Command has correct defaults."""
        cmd = BacktestRunCommand(
            strategy_id="test",
            start_date="2025-01-01",
            end_date="2025-03-31",
        )
        assert cmd.initial_cash == 1_000_000.0
        assert cmd.parameter_overrides == ()
        assert cmd.strategy_version is None
        assert cmd.cost_config is None
        assert cmd.allow_experimental_data is False


class TestParseCandidateParameters:
    """Legacy ``key=value`` syntax is normalized only at the command boundary."""

    def test_parses_exact_json_scalar_types_and_legacy_paths(self) -> None:
        assert parse_candidate_parameters(
            (
                "count=3",
                "ratio=0.25",
                "enabled=true",
                'label="candidate"',
                "method=score_weight",
            )
        ) == (
            CandidateParameter(path=legacy_parameter_path("count"), value=3),
            CandidateParameter(path=legacy_parameter_path("ratio"), value=0.25),
            CandidateParameter(path=legacy_parameter_path("enabled"), value=True),
            CandidateParameter(path=legacy_parameter_path("label"), value="candidate"),
            CandidateParameter(
                path=legacy_parameter_path("method"), value="score_weight"
            ),
        )

    def test_preserves_full_canonical_path(self) -> None:
        path = legacy_parameter_path("top/k")
        assert parse_candidate_parameters((f"{path}=2",)) == (
            CandidateParameter(path=path, value=2),
        )

    @pytest.mark.parametrize(
        "raw",
        [
            "missing-separator",
            "=1",
            "name=",
            "name=null",
            "name=[]",
            "name={}",
            "name=NaN",
        ],
    )
    def test_rejects_malformed_or_non_scalar_values(self, raw: str) -> None:
        with pytest.raises(AppCommandError):
            parse_candidate_parameters((raw,))

    def test_rejects_duplicate_paths_after_normalization(self) -> None:
        with pytest.raises(AppCommandError, match="duplicate"):
            parse_candidate_parameters(("top_k=2", "top_k=3"))


class TestBacktestRunResultCostConfig:
    """Tests for BacktestRunResult.cost_config field."""

    def test_result_without_cost_config(self, handler: BacktestRunHandler) -> None:
        """无 cost_config 的命令返回 cost_config=None 的 result."""
        cmd = _make_command()
        result = handler.handle(cmd)
        assert result.cost_config is None

    def test_result_with_cost_config(self, handler: BacktestRunHandler) -> None:
        """有 cost_config 的命令透传到 result."""
        cost_cfg = CostConfig(
            commission_rate=0.0005,
            commission_min=10.0,
            stamp_duty_rate=0.002,
            slippage_bps=3.0,
            impact_model=ImpactModel.VOLUME_SHARE,
        )
        cmd = _make_command(cost_config=cost_cfg)
        result = handler.handle(cmd)
        assert result.cost_config is not None
        assert result.cost_config.commission_rate == 0.0005
        assert result.cost_config.commission_min == 10.0
        assert result.cost_config.stamp_duty_rate == 0.002
        assert result.cost_config.slippage_bps == 3.0
        assert result.cost_config.impact_model == ImpactModel.VOLUME_SHARE


# ---------------------------------------------------------------------------
# T26: Cancel / Retry Handler Tests
# ---------------------------------------------------------------------------


class TestCancelRunHandler:
    """Tests for CancelRunHandler — status guard + mark_cancelled."""

    def test_cancel_pending_run(self) -> None:
        """取消 pending 状态的运行成功."""
        run_svc = Mock(spec=StrategyRunLifecycleStore)
        run_svc.get_run.return_value = _make_run_record(status="pending")
        handler = CancelRunHandler(run_service=run_svc)

        handler.handle(CancelRunCommand(run_id="abc123"))

        run_svc.mark_cancelled.assert_called_once_with("abc123")

    def test_cancel_running_run(self) -> None:
        """取消 running 状态的运行成功."""
        run_svc = Mock(spec=StrategyRunLifecycleStore)
        run_svc.get_run.return_value = _make_run_record(status="running")
        handler = CancelRunHandler(run_service=run_svc)

        handler.handle(CancelRunCommand(run_id="abc123"))

        run_svc.mark_cancelled.assert_called_once_with("abc123")

    def test_cancel_completed_rejected(self) -> None:
        """completed 状态不允许取消."""
        run_svc = Mock(spec=StrategyRunLifecycleStore)
        run_svc.get_run.return_value = _make_run_record(status="completed")
        handler = CancelRunHandler(run_service=run_svc)

        with pytest.raises(AppCommandError, match="Cannot cancel"):
            handler.handle(CancelRunCommand(run_id="abc123"))
        run_svc.mark_cancelled.assert_not_called()

    def test_cancel_failed_rejected(self) -> None:
        """failed 状态不允许取消."""
        run_svc = Mock(spec=StrategyRunLifecycleStore)
        run_svc.get_run.return_value = _make_run_record(status="failed")
        handler = CancelRunHandler(run_service=run_svc)

        with pytest.raises(AppCommandError, match="Cannot cancel"):
            handler.handle(CancelRunCommand(run_id="abc123"))

    def test_cancel_not_found(self) -> None:
        """运行不存在抛 ValueError."""
        run_svc = Mock(spec=StrategyRunLifecycleStore)
        run_svc.get_run.return_value = None
        handler = CancelRunHandler(run_service=run_svc)

        with pytest.raises(AppCommandError, match="Run not found"):
            handler.handle(CancelRunCommand(run_id="missing"))


class TestRetryRunHandler:
    """Tests for RetryRunHandler — status guard + config_json 传递."""

    def test_retry_failed_run(self) -> None:
        """重试 failed 状态的运行创建新 run 并传递 config_json."""
        run_svc = Mock(spec=StrategyRunLifecycleStore)
        run_svc.get_run.return_value = _make_run_record(
            status="failed",
            config_json='{"start_date":"2025-01-01"}',
        )
        handler = RetryRunHandler(run_service=run_svc)

        new_id = handler.handle(RetryRunCommand(run_id="abc123"))

        # 创建新运行并传递 config_json
        run_svc.create_run.assert_called_once()
        call_kwargs = run_svc.create_run.call_args.kwargs
        assert call_kwargs["strategy_id"] == "momentum-etf"
        assert call_kwargs["parent_run_id"] == "abc123"
        assert call_kwargs["config_json"] == '{"start_date":"2025-01-01"}'
        assert new_id  # 返回非空 new_run_id

    def test_retry_cancelled_run(self) -> None:
        """重试 cancelled 状态的运行成功."""
        run_svc = Mock(spec=StrategyRunLifecycleStore)
        run_svc.get_run.return_value = _make_run_record(status="cancelled")
        handler = RetryRunHandler(run_service=run_svc)

        new_id = handler.handle(RetryRunCommand(run_id="abc123"))
        assert new_id

    def test_retry_pending_rejected(self) -> None:
        """pending 状态不允许重试."""
        run_svc = Mock(spec=StrategyRunLifecycleStore)
        run_svc.get_run.return_value = _make_run_record(status="pending")
        handler = RetryRunHandler(run_service=run_svc)

        with pytest.raises(AppCommandError, match="Cannot retry"):
            handler.handle(RetryRunCommand(run_id="abc123"))
        run_svc.create_run.assert_not_called()

    def test_retry_running_rejected(self) -> None:
        """running 状态不允许重试."""
        run_svc = Mock(spec=StrategyRunLifecycleStore)
        run_svc.get_run.return_value = _make_run_record(status="running")
        handler = RetryRunHandler(run_service=run_svc)

        with pytest.raises(AppCommandError, match="Cannot retry"):
            handler.handle(RetryRunCommand(run_id="abc123"))

    def test_retry_not_found(self) -> None:
        """运行不存在抛 ValueError."""
        run_svc = Mock(spec=StrategyRunLifecycleStore)
        run_svc.get_run.return_value = None
        handler = RetryRunHandler(run_service=run_svc)

        with pytest.raises(AppCommandError, match="Run not found"):
            handler.handle(RetryRunCommand(run_id="missing"))

    def test_retry_preserves_strategy_version(self) -> None:
        """重试保留原始 strategy_version."""
        run_svc = Mock(spec=StrategyRunLifecycleStore)
        run_svc.get_run.return_value = _make_run_record(
            status="failed",
            strategy_version="2",
        )
        handler = RetryRunHandler(run_service=run_svc)

        handler.handle(RetryRunCommand(run_id="abc123"))

        call_kwargs = run_svc.create_run.call_args.kwargs
        assert call_kwargs["strategy_version"] == "2"


class TestResumeRunHandler:
    """Tests for ResumeRunHandler — checkpoint guard + resumed config."""

    def test_resume_cancelled_run_from_checkpoint(self) -> None:
        """可恢复 checkpoint 应创建 child run，并从 resume_from 继续提交。"""
        run_svc = Mock(spec=StrategyRunLifecycleStore)
        checkpoint_svc = Mock(spec=StrategyRunCheckpointStore)
        run_svc.get_run.return_value = _make_run_record(
            status="cancelled",
            config_json=(
                '{"start_date":"2025-01-01","end_date":"2025-03-31",'
                '"initial_cash":1000000.0,"parameter_overrides":["top_k=3"],'
                '"allow_experimental_data":true}'
            ),
        )
        checkpoint_svc.get_latest_checkpoint.return_value = _make_checkpoint_record()
        handler = ResumeRunHandler(
            run_service=run_svc,
            checkpoint_reader=checkpoint_svc,
        )

        new_id = handler.handle(ResumeRunCommand(run_id="abc123"))

        run_svc.create_run.assert_called_once()
        call_kwargs = run_svc.create_run.call_args.kwargs
        assert call_kwargs["strategy_id"] == "momentum-etf"
        assert call_kwargs["strategy_version"] == "1"
        assert call_kwargs["mode"] == "backtest"
        assert call_kwargs["parent_run_id"] == "abc123"
        assert new_id

        import orjson

        config = orjson.loads(call_kwargs["config_json"])
        assert config["start_date"] == "2025-02-03"
        assert config["end_date"] == "2025-03-31"
        assert config["initial_cash"] == 1_000_000.0
        assert config["parameter_overrides"] == ["top_k=3"]
        assert config["allow_experimental_data"] is True
        assert config["resume_from_run_id"] == "abc123"
        assert config["resume_checkpoint_trade_date"] == "2025-01-31"
        assert config["resume_checkpoint_completed_days"] == 21
        assert config["resume_checkpoint_nav"] == 1_020_000.0
        assert config["resume_account_state_json"] == (
            '{"cash_available":920000.0,"cash_settled":900000.0,'
            '"cash_frozen":20000.0,"positions":[]}'
        )
        assert config["resume_account_state_hash"] == "sha256:account-state"
        assert config["resume_settlement_state_json"] == (
            '{"frozen_quantities":[{"instrument_id":1,'
            '"quantity":1000,"settle_date":"2026-03-03"}]}'
        )
        assert config["resume_settlement_state_hash"] == "sha256:settlement-state"
        assert config["resume_runtime_state_json"] == (
            '{"delayed_signals":[{"cash_target":0.5,'
            '"positions":[{"instrument_id":1,"target_weight":0.5}],'
            '"queue_index":0,"run_id":"abc123","strategy_id":"momentum-etf",'
            '"trade_date":"2025-01-31"}],'
            '"pending_orders":[{"average_fill_price":null,'
            '"client_order_id":"order-001","direction":"buy",'
            '"filled_price":null,"filled_quantity":0,"instrument_id":1,'
            '"leaves_quantity":300,"order_type":"market","price":null,'
            '"quantity":300,"status":"submitted","stop_price":null,'
            '"trade_date":"2025-01-31"}]}'
        )
        assert config["resume_runtime_state_hash"] == "sha256:runtime-state"

    def test_resume_failed_run_from_checkpoint(self) -> None:
        """failed 状态也允许从 checkpoint 恢复。"""
        run_svc = Mock(spec=StrategyRunLifecycleStore)
        checkpoint_svc = Mock(spec=StrategyRunCheckpointStore)
        run_svc.get_run.return_value = _make_run_record(
            status="failed",
            config_json='{"start_date":"2025-01-01","end_date":"2025-03-31"}',
        )
        checkpoint_svc.get_latest_checkpoint.return_value = _make_checkpoint_record()
        handler = ResumeRunHandler(
            run_service=run_svc,
            checkpoint_reader=checkpoint_svc,
        )

        new_id = handler.handle(ResumeRunCommand(run_id="abc123"))

        assert new_id
        run_svc.create_run.assert_called_once()

    def test_resume_rejects_missing_checkpoint(self) -> None:
        """没有 checkpoint 的运行不能伪装成 resume。"""
        run_svc = Mock(spec=StrategyRunLifecycleStore)
        checkpoint_svc = Mock(spec=StrategyRunCheckpointStore)
        run_svc.get_run.return_value = _make_run_record(
            status="cancelled",
            config_json='{"start_date":"2025-01-01","end_date":"2025-03-31"}',
        )
        checkpoint_svc.get_latest_checkpoint.return_value = None
        handler = ResumeRunHandler(
            run_service=run_svc,
            checkpoint_reader=checkpoint_svc,
        )

        with pytest.raises(AppCommandError, match="No resumable checkpoint"):
            handler.handle(ResumeRunCommand(run_id="abc123"))
        run_svc.create_run.assert_not_called()

    def test_resume_rejects_final_checkpoint(self) -> None:
        """最终 checkpoint 没有 resume_from，不能再恢复。"""
        run_svc = Mock(spec=StrategyRunLifecycleStore)
        checkpoint_svc = Mock(spec=StrategyRunCheckpointStore)
        run_svc.get_run.return_value = _make_run_record(
            status="cancelled",
            config_json='{"start_date":"2025-01-01","end_date":"2025-03-31"}',
        )
        checkpoint_svc.get_latest_checkpoint.return_value = _make_checkpoint_record(
            resume_from=None,
        )
        handler = ResumeRunHandler(
            run_service=run_svc,
            checkpoint_reader=checkpoint_svc,
        )

        with pytest.raises(AppCommandError, match="No resumable checkpoint"):
            handler.handle(ResumeRunCommand(run_id="abc123"))
        run_svc.create_run.assert_not_called()

    def test_resume_pending_rejected(self) -> None:
        """pending 状态不允许恢复。"""
        run_svc = Mock(spec=StrategyRunLifecycleStore)
        checkpoint_svc = Mock(spec=StrategyRunCheckpointStore)
        run_svc.get_run.return_value = _make_run_record(status="pending")
        handler = ResumeRunHandler(
            run_service=run_svc,
            checkpoint_reader=checkpoint_svc,
        )

        with pytest.raises(AppCommandError, match="Cannot resume"):
            handler.handle(ResumeRunCommand(run_id="abc123"))
        checkpoint_svc.get_latest_checkpoint.assert_not_called()
        run_svc.create_run.assert_not_called()

    def test_resume_not_found(self) -> None:
        """运行不存在抛 typed command error。"""
        run_svc = Mock(spec=StrategyRunLifecycleStore)
        checkpoint_svc = Mock(spec=StrategyRunCheckpointStore)
        run_svc.get_run.return_value = None
        handler = ResumeRunHandler(
            run_service=run_svc,
            checkpoint_reader=checkpoint_svc,
        )

        with pytest.raises(AppCommandError, match="Run not found"):
            handler.handle(ResumeRunCommand(run_id="missing"))
