"""Ops CLI 运维命令单元测试."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import orjson
import pytest
from ditto_application.commands.catalog import (
    DatasetMaturityPromotionRevokeResult,
    DatasetPromotionReviewResult,
)
from ditto_application.exceptions import AppQueryError
from ditto_application.queries.catalog import CatalogMaturityPromotionHistoryItem
from ditto_application.queries.evaluation import EvaluationOptions
from ditto_application.queries.promotion_evidence import (
    CriterionEvidence,
    PromotionEvidenceReport,
)
from ditto_apps.cli.main import app
from ditto_features.evaluation.report import (
    FactorEvaluationReport,
    ICSummary,
    LongShortResult,
    PerformanceAttributionResult,
    RegimeICResult,
    TailRiskMetrics,
)
from pytest_mock import MockerFixture
from typer.testing import CliRunner

CONTAINER_PATH = "ditto_apps.cli.commands.ops.make_app_container"


@pytest.fixture
def runner() -> CliRunner:
    """创建 CLI 测试运行器。"""
    return CliRunner()


# ---------------------------------------------------------------------------
# 模拟数据工厂
# ---------------------------------------------------------------------------


def _make_dataset_status(
    dataset: str = "stock_daily",
    latest_date: str | None = "2026-04-14",
    latest_status: str | None = "success",
    record_count: int = 5000,
    dataset_maturity: str | None = None,
    dataset_maturity_warning: str | None = None,
    dataset_promotion_criteria: tuple[str, ...] = (),
    dataset_promotion_status: str | None = None,
    dataset_promotion_missing_criteria: tuple[str, ...] = (),
    dataset_promotion_satisfied_criteria: tuple[str, ...] = (),
    dataset_promotion_rejected_criteria: tuple[str, ...] = (),
    last_attempt: str | None = None,
    catalog_freshness_at: datetime | None = None,
    catalog_storage_uri: str | None = None,
    catalog_schema_hash: str | None = None,
    catalog_row_count: int | None = None,
    catalog_freshness_status: str | None = None,
    catalog_freshness_sla_hours: int | None = None,
) -> Any:
    """创建 DatasetStatus mock 对象。"""
    mock = MagicMock()
    mock.dataset = dataset
    mock.latest_date = latest_date
    mock.latest_status = latest_status
    mock.dataset_maturity = dataset_maturity
    mock.dataset_maturity_warning = dataset_maturity_warning
    mock.dataset_promotion_criteria = dataset_promotion_criteria
    mock.dataset_promotion_status = dataset_promotion_status
    mock.dataset_promotion_missing_criteria = dataset_promotion_missing_criteria
    mock.dataset_promotion_satisfied_criteria = dataset_promotion_satisfied_criteria
    mock.dataset_promotion_rejected_criteria = dataset_promotion_rejected_criteria
    mock.record_count = record_count
    mock.last_attempt = last_attempt
    mock.catalog_freshness_at = catalog_freshness_at
    mock.catalog_storage_uri = catalog_storage_uri
    mock.catalog_schema_hash = catalog_schema_hash
    mock.catalog_row_count = catalog_row_count
    mock.catalog_freshness_status = catalog_freshness_status
    mock.catalog_freshness_sla_hours = catalog_freshness_sla_hours
    return mock


def _make_history_item(
    dataset: str = "stock_daily",
    trade_date: str = "2026-04-14",
    status: str = "success",
    rows: int | None = 100,
    error_message: str | None = None,
    attempts: int = 1,
    last_attempt_at: str | None = None,
) -> Any:
    """创建 HistoryItem mock 对象。"""
    mock = MagicMock()
    mock.dataset = dataset
    mock.trade_date = trade_date
    mock.status = status
    mock.rows = rows
    mock.error_message = error_message
    mock.attempts = attempts
    mock.last_attempt_at = last_attempt_at
    return mock


def _make_l3_check_result(
    dataset: str = "stock_daily",
    trade_date: str = "2026-04-14",
    passed: bool = True,
    issue_count: int = 0,
    alert_count: int = 0,
    error: str | None = None,
) -> Any:
    """创建 L3CheckResult mock 对象。"""
    mock = MagicMock()
    mock.dataset = dataset
    mock.trade_date = trade_date
    mock.passed = passed
    mock.issue_count = issue_count
    mock.alert_count = alert_count
    mock.issues = ()
    mock.error = error
    mock.has_error = error is not None
    return mock


def _mock_container_for_status(facade: Any) -> Any:
    """创建返回 IngestionStatusQueryFacade 的 mock 容器。"""
    mock_container = MagicMock()
    mock_container.get.return_value = facade
    return mock_container


def _mock_container_for_patrol(patrol: Any) -> Any:
    """创建返回 QualityPatrolService 的 mock 容器。"""
    mock_container = MagicMock()
    mock_container.get.return_value = patrol
    return mock_container


def _mock_container_for_promotion_review(handler: Any) -> Any:
    """创建返回 promotion review handler 的 mock 容器。"""
    mock_container = MagicMock()
    mock_container.get.return_value = handler
    return mock_container


def _mock_container_for_ops_object(obj: Any) -> Any:
    """创建返回任意 ops dependency 的 mock 容器。"""
    mock_container = MagicMock()
    mock_container.get.return_value = obj
    return mock_container


# ---------------------------------------------------------------------------
# 帮助命令测试
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestOpsCommandHelp:
    """Ops 命令帮助测试。"""

    def test_ops_group_help_exists(self, runner: CliRunner) -> None:
        """测试 ops 命令组存在。"""
        result = runner.invoke(app, ["ops", "--help"])
        assert result.exit_code == 0
        assert "运维" in result.output

    def test_ops_status_help_exists(self, runner: CliRunner) -> None:
        """测试 ops status 命令帮助存在。"""
        result = runner.invoke(app, ["ops", "status", "--help"])
        assert result.exit_code == 0
        assert "摄取状态" in result.output

    def test_ops_dq_help_exists(self, runner: CliRunner) -> None:
        """测试 ops dq 命令帮助存在。"""
        result = runner.invoke(app, ["ops", "dq", "--help"])
        assert result.exit_code == 0
        assert "质量检查" in result.output


# ---------------------------------------------------------------------------
# status 命令测试
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestStatusCommand:
    """Ops status 命令测试。"""

    def test_status_shows_all_datasets(
        self, runner: CliRunner, mocker: MockerFixture
    ) -> None:
        """测试默认显示所有数据集的摄取状态。"""
        mock_facade = MagicMock()
        mock_facade.get_status.return_value = [
            _make_dataset_status("stock_daily", "2026-04-14", "success", 5000),
            _make_dataset_status("etf_daily", "2026-04-14", "success", 800),
        ]
        container = _mock_container_for_status(mock_facade)
        mocker.patch(CONTAINER_PATH, return_value=container)

        result = runner.invoke(app, ["ops", "status"])

        assert result.exit_code == 0
        assert "stock_daily" in result.output
        assert "etf_daily" in result.output
        mock_facade.get_status.assert_called_once()

    def test_status_with_json_flag(
        self, runner: CliRunner, mocker: MockerFixture
    ) -> None:
        """测试 --json 格式输出。"""
        mock_facade = MagicMock()
        mock_facade.get_status.return_value = [
            _make_dataset_status(
                "stock_daily",
                "2026-04-14",
                "success",
                5000,
                dataset_maturity="experimental",
                dataset_maturity_warning="experimental data requires research opt-in",
                dataset_promotion_criteria=("complete PIT replay coverage",),
                dataset_promotion_status="blocked",
                dataset_promotion_missing_criteria=("complete PIT replay coverage",),
                dataset_promotion_rejected_criteria=("source failover policy missing",),
                catalog_freshness_status="fresh",
                catalog_freshness_sla_hours=36,
            ),
        ]
        container = _mock_container_for_status(mock_facade)
        mocker.patch(CONTAINER_PATH, return_value=container)

        result = runner.invoke(app, ["ops", "status", "--json"])

        assert result.exit_code == 0
        payload = orjson.loads(result.output)
        assert payload["datasets"][0]["dataset"] == "stock_daily"
        assert payload["datasets"][0]["dataset_maturity"] == "experimental"
        assert payload["datasets"][0]["dataset_maturity_warning"] == (
            "experimental data requires research opt-in"
        )
        assert payload["datasets"][0]["dataset_promotion_criteria"] == [
            "complete PIT replay coverage"
        ]
        assert payload["datasets"][0]["dataset_promotion_status"] == "blocked"
        assert payload["datasets"][0]["dataset_promotion_missing_criteria"] == [
            "complete PIT replay coverage"
        ]
        assert payload["datasets"][0]["dataset_promotion_rejected_criteria"] == [
            "source failover policy missing"
        ]
        assert payload["datasets"][0]["catalog_freshness_status"] == "fresh"
        assert payload["maturity_summary"] == [
            {
                "maturity": "experimental",
                "dataset_count": 1,
                "fresh_count": 1,
                "stale_count": 0,
                "missing_count": 0,
                "not_applicable_count": 0,
                "failed_count": 0,
                "warning_count": 1,
                "promotion_ready_count": 0,
                "promotion_blocked_count": 1,
            }
        ]

    def test_status_with_date_filter(
        self, runner: CliRunner, mocker: MockerFixture
    ) -> None:
        """测试指定日期过滤摄取历史。"""
        mock_facade = MagicMock()
        mock_facade.get_history.return_value = [
            _make_history_item("stock_daily", "2026-04-14", "success", 100),
        ]
        container = _mock_container_for_status(mock_facade)
        mocker.patch(CONTAINER_PATH, return_value=container)

        result = runner.invoke(app, ["ops", "status", "--date", "2026-04-14"])

        assert result.exit_code == 0
        assert "stock_daily" in result.output
        assert "2026-04-14" in result.output

    def test_promotion_review_writes_evidence_with_json_output(
        self,
        runner: CliRunner,
        mocker: MockerFixture,
    ) -> None:
        """Promotion review command delegates reviewer evidence to application."""
        handler = MagicMock()
        handler.handle.return_value = DatasetPromotionReviewResult(
            dataset_id="stock_daily",
            reviewed_criterion="complete PIT replay coverage",
            evidence_uri="ditto://evidence/stock_daily/pit",
            reviewed_by="architecture-review",
            passed=True,
            reviewed_at=datetime.fromisoformat("2026-06-01T12:30:00+00:00"),
            promotion_status="blocked",
            missing_criteria=("source failover policy",),
            satisfied_criteria=("complete PIT replay coverage",),
            rejected_criteria=(),
            metadata_promoted=False,
            dataset_maturity_before="experimental",
            dataset_maturity_after="experimental",
        )
        container = _mock_container_for_promotion_review(handler)
        mocker.patch(CONTAINER_PATH, return_value=container)

        result = runner.invoke(
            app,
            [
                "ops",
                "promotion-review",
                "stock_daily",
                "--criterion",
                "complete PIT replay coverage",
                "--evidence-uri",
                "ditto://evidence/stock_daily/pit",
                "--reviewed-by",
                "architecture-review",
                "--notes",
                "PIT replay passed",
                "--json",
            ],
        )

        assert result.exit_code == 0
        payload = orjson.loads(result.output)
        assert payload["dataset_id"] == "stock_daily"
        assert payload["reviewed_criterion"] == "complete PIT replay coverage"
        assert payload["promotion_status"] == "blocked"
        assert payload["missing_criteria"] == ["source failover policy"]
        assert payload["metadata_promoted"] is False
        assert payload["dataset_maturity_after"] == "experimental"
        assert handler.handle.call_args.args[0].dataset_id == "stock_daily"
        assert handler.handle.call_args.args[0].reviewed_by == "architecture-review"
        assert handler.handle.call_args.args[0].notes == "PIT replay passed"

    def test_promotion_history_outputs_json(
        self,
        runner: CliRunner,
        mocker: MockerFixture,
    ) -> None:
        """Promotion history command delegates to application catalog facade."""
        facade = MagicMock()
        facade.list_maturity_promotion_history.return_value = [
            CatalogMaturityPromotionHistoryItem(
                dataset_id="stock_daily",
                action="promoted",
                previous_maturity="experimental",
                next_maturity="initial-focus",
                actor="architecture-review",
                action_at=datetime.fromisoformat("2026-06-01T13:00:00+00:00"),
                evidence_uri="ditto://evidence/stock_daily/runtime-tests",
                notes="all criteria approved",
                revocation_reason=None,
            )
        ]
        container = _mock_container_for_ops_object(facade)
        mocker.patch(CONTAINER_PATH, return_value=container)

        result = runner.invoke(
            app,
            ["ops", "promotion-history", "stock_daily", "--json"],
        )

        assert result.exit_code == 0
        payload = orjson.loads(result.output)
        assert payload["events"][0]["dataset_id"] == "stock_daily"
        assert payload["events"][0]["action"] == "promoted"
        assert payload["events"][0]["next_maturity"] == "initial-focus"
        facade.list_maturity_promotion_history.assert_called_once_with("stock_daily")

    def test_promotion_revoke_removes_override_with_json_output(
        self,
        runner: CliRunner,
        mocker: MockerFixture,
    ) -> None:
        """Promotion revoke command delegates reversal to application handler."""
        handler = MagicMock()
        handler.handle.return_value = DatasetMaturityPromotionRevokeResult(
            dataset_id="stock_daily",
            revoked_by="architecture-review",
            revoked_at=datetime.fromisoformat("2026-06-02T09:00:00+00:00"),
            dataset_maturity_before="initial-focus",
            dataset_maturity_after="experimental",
            evidence_uri="ditto://evidence/stock_daily/runtime-tests",
            revocation_reason="failed_revalidation",
            notes="PIT regression reopened promotion",
        )
        container = _mock_container_for_ops_object(handler)
        mocker.patch(CONTAINER_PATH, return_value=container)

        result = runner.invoke(
            app,
            [
                "ops",
                "promotion-revoke",
                "stock_daily",
                "--revoked-by",
                "architecture-review",
                "--reason",
                "failed_revalidation",
                "--notes",
                "PIT regression reopened promotion",
                "--json",
            ],
        )

        assert result.exit_code == 0
        payload = orjson.loads(result.output)
        assert payload["dataset_id"] == "stock_daily"
        assert payload["revoked_by"] == "architecture-review"
        assert payload["revocation_reason"] == "failed_revalidation"
        assert payload["dataset_maturity_after"] == "experimental"
        assert handler.handle.call_args.args[0].dataset_id == "stock_daily"
        assert handler.handle.call_args.args[0].revoked_by == "architecture-review"
        assert handler.handle.call_args.args[0].revocation_reason == (
            "failed_revalidation"
        )

    def test_status_container_error(
        self, runner: CliRunner, mocker: MockerFixture
    ) -> None:
        """测试容器获取服务失败时输出错误信息。"""
        mock_container = MagicMock()
        mock_container.get.side_effect = RuntimeError("DI 初始化失败")

        mocker.patch(CONTAINER_PATH, return_value=mock_container)

        result = runner.invoke(app, ["ops", "status"])

        assert result.exit_code == 1
        assert "获取服务失败" in result.output


# ---------------------------------------------------------------------------
# dq 命令测试
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestDQCommand:
    """Ops dq 命令测试。"""

    def test_dq_single_dataset(self, runner: CliRunner, mocker: MockerFixture) -> None:
        """测试检查单个数据集。"""
        mock_patrol = MagicMock()
        mock_patrol.check_dataset.return_value = _make_l3_check_result(
            "stock_daily", "2026-04-14", passed=True
        )
        container = _mock_container_for_patrol(mock_patrol)
        mocker.patch(CONTAINER_PATH, return_value=container)

        result = runner.invoke(
            app, ["ops", "dq", "2026-04-14", "--dataset", "stock_daily"]
        )

        assert result.exit_code == 0
        assert "stock_daily" in result.output
        mock_patrol.check_dataset.assert_called_once_with("stock_daily", "2026-04-14")

    def test_dq_multiple_datasets(
        self, runner: CliRunner, mocker: MockerFixture
    ) -> None:
        """测试检查多个核心数据集 (默认行为)。"""
        mock_patrol = MagicMock()
        mock_patrol.check_dataset.side_effect = [
            _make_l3_check_result("etf_daily", "2026-04-14", passed=True),
            _make_l3_check_result(
                "stock_daily", "2026-04-14", passed=False, issue_count=2
            ),
            _make_l3_check_result("index_daily", "2026-04-14", passed=True),
            _make_l3_check_result("adj_factor", "2026-04-14", passed=True),
        ]
        container = _mock_container_for_patrol(mock_patrol)
        mocker.patch(CONTAINER_PATH, return_value=container)

        result = runner.invoke(app, ["ops", "dq", "2026-04-14"])

        assert result.exit_code == 0
        assert "etf_daily" in result.output
        assert "stock_daily" in result.output
        assert "index_daily" in result.output
        assert "adj_factor" in result.output
        assert "3/4" in result.output  # 3 passed out of 4
        assert mock_patrol.check_dataset.call_count == 4

    def test_dq_with_json_flag(self, runner: CliRunner, mocker: MockerFixture) -> None:
        """测试 DQ --json 格式输出。"""
        mock_patrol = MagicMock()
        mock_patrol.check_dataset.return_value = _make_l3_check_result(
            "stock_daily", "2026-04-14", passed=True
        )
        container = _mock_container_for_patrol(mock_patrol)
        mocker.patch(CONTAINER_PATH, return_value=container)

        result = runner.invoke(
            app,
            ["ops", "dq", "2026-04-14", "--dataset", "stock_daily", "--json"],
        )

        assert result.exit_code == 0
        assert '"dataset"' in result.output
        assert '"stock_daily"' in result.output
        assert '"passed"' in result.output

    def test_dq_no_issues(self, runner: CliRunner, mocker: MockerFixture) -> None:
        """测试 DQ 检查无问题通过。"""
        mock_patrol = MagicMock()
        mock_patrol.check_dataset.return_value = _make_l3_check_result(
            "stock_daily", "2026-04-14", passed=True
        )
        container = _mock_container_for_patrol(mock_patrol)
        mocker.patch(CONTAINER_PATH, return_value=container)

        result = runner.invoke(
            app, ["ops", "dq", "2026-04-14", "--dataset", "stock_daily"]
        )

        assert result.exit_code == 0
        assert "stock_daily" in result.output
        assert "1/1" in result.output

    def test_dq_container_error(self, runner: CliRunner, mocker: MockerFixture) -> None:
        """测试 DQ 容器获取服务失败时输出错误信息。"""
        mock_container = MagicMock()
        mock_container.get.side_effect = RuntimeError("DI 初始化失败")

        mocker.patch(CONTAINER_PATH, return_value=mock_container)

        result = runner.invoke(app, ["ops", "dq", "2026-04-14"])

        assert result.exit_code == 1
        assert "获取服务失败" in result.output


@pytest.mark.unit
class TestPromotionCollectCommand:
    """Ops promotion-collect 命令测试。"""

    @staticmethod
    def _sample_report() -> PromotionEvidenceReport:
        return PromotionEvidenceReport(
            dataset_id="stock_daily",
            generated_at=datetime.fromisoformat("2026-06-15T00:00:00+00:00"),
            maturity="experimental",
            criteria=(
                CriterionEvidence(
                    criterion="complete PIT/replay coverage for the dataset",
                    status="needs_review",
                    materials=("catalog reader not available",),
                    suggestion="Provide DataCatalogReader to measure coverage.",
                ),
                CriterionEvidence(
                    criterion=(
                        "document runtime owner, freshness SLA, "
                        "and source failover policy"
                    ),
                    status="measured",
                    materials=("default_source=declared",),
                ),
            ),
        )

    def test_promotion_collect_outputs_markdown_to_stdout(
        self,
        runner: CliRunner,
        mocker: MockerFixture,
    ) -> None:
        mock_collector = MagicMock()
        mock_collector.collect.return_value = self._sample_report()
        container = _mock_container_for_ops_object(mock_collector)
        mocker.patch(CONTAINER_PATH, return_value=container)

        result = runner.invoke(app, ["ops", "promotion-collect", "stock_daily"])

        assert result.exit_code == 0
        assert "Promotion Evidence Report: stock_daily" in result.output
        assert "experimental" in result.output
        assert "runtime owner" in result.output
        mock_collector.collect.assert_called_once_with("stock_daily")

    def test_promotion_collect_writes_output_file(
        self,
        runner: CliRunner,
        mocker: MockerFixture,
        tmp_path: Path,
    ) -> None:
        mock_collector = MagicMock()
        mock_collector.collect.return_value = self._sample_report()
        container = _mock_container_for_ops_object(mock_collector)
        mocker.patch(CONTAINER_PATH, return_value=container)
        output_file = tmp_path / "evidence.md"

        result = runner.invoke(
            app,
            [
                "ops",
                "promotion-collect",
                "stock_daily",
                "--output",
                str(output_file),
            ],
        )

        assert result.exit_code == 0
        assert output_file.exists()
        content = output_file.read_text(encoding="utf-8")
        assert "Promotion Evidence Report: stock_daily" in content

    def test_promotion_collect_unknown_dataset_exits_nonzero(
        self,
        runner: CliRunner,
        mocker: MockerFixture,
    ) -> None:
        mock_collector = MagicMock()
        mock_collector.collect.side_effect = ValueError("Unknown dataset: foo")
        container = _mock_container_for_ops_object(mock_collector)
        mocker.patch(CONTAINER_PATH, return_value=container)

        result = runner.invoke(app, ["ops", "promotion-collect", "foo"])

        assert result.exit_code == 1
        assert "收集失败" in result.output


# ---------------------------------------------------------------------------
# factor-ic 命令测试
# ---------------------------------------------------------------------------


def _make_ic_summary(
    *,
    mean: float = 0.05,
    std: float = 0.1,
    icir: float = 0.5,
    t_stat: float = 2.0,
    p_value: float = 0.04,
    win_rate: float = 0.55,
) -> ICSummary:
    """构造 ICSummary。"""
    return ICSummary(
        mean=mean,
        std=std,
        icir=icir,
        t_stat=t_stat,
        p_value=p_value,
        win_rate=win_rate,
    )


def _make_factor_evaluation_report(
    *,
    factor_id: str = "fx.momentum",
    factor_version: int = 1,
    regime_ic: RegimeICResult | None = None,
    performance_attribution: PerformanceAttributionResult | None = None,
) -> FactorEvaluationReport:
    """构造合成 FactorEvaluationReport, 参考 test_evaluation_unit 构造方式."""
    return FactorEvaluationReport(
        factor_id=factor_id,
        factor_version=factor_version,
        evaluation_period=("2024-01-02", "2024-06-30"),
        holding_period=5,
        n_quantiles=5,
        rank_ic_summary=_make_ic_summary(),
        pearson_ic_summary=_make_ic_summary(mean=0.04, icir=0.4, win_rate=0.53),
        ic_decay=[(1, 0.05), (5, 0.04), (10, 0.03)],
        ic_half_life=10.0,
        ic_autocorrelation=[(1, 0.6), (5, 0.3)],
        quantile_annual_returns={1: 0.02, 2: 0.04, 3: 0.06, 4: 0.08, 5: 0.10},
        long_short=LongShortResult(
            annual_return=0.08,
            annual_volatility=0.12,
            sharpe=0.67,
            portfolio_ir=0.67,
            sortino=0.90,
            max_drawdown=0.05,
            calmar=1.60,
            tail_risk=TailRiskMetrics(
                cvar_95=0.03,
                cvar_99=0.05,
                skewness=-0.2,
                kurtosis=3.1,
                max_single_day_loss=-0.04,
            ),
        ),
        avg_turnover=0.3,
        net_return_after_cost=0.07,
        turnover_adjusted_ir=0.5,
        grinold_kahn_ir=0.6,
        sub_period_ic={"H1": _make_ic_summary(), "H2": _make_ic_summary()},
        n_observations=100,
        n_dates=120,
        computed_at="2024-07-01T00:00:00Z",
        dataset_id="stock_daily",
        catalog_snapshot_id="catalog-snap-001",
        universe="csi_300",
        cost_bps=5.0,
        regime_ic=regime_ic,
        performance_attribution=performance_attribution,
    )


def _make_regime_ic() -> RegimeICResult:
    """构造非空 regime IC 结果。"""
    return RegimeICResult(
        regimes={
            "bull": _make_ic_summary(icir=0.6, win_rate=0.6),
            "bear": _make_ic_summary(icir=0.3, win_rate=0.45),
        },
        regime_labels=[],
        transition_matrix={},
        ic_trend=0.01,
        ic_trend_p_value=0.5,
    )


def _make_performance_attribution() -> PerformanceAttributionResult:
    """构造非空绩效归因结果。"""
    return PerformanceAttributionResult(
        total_return=0.1,
        selection_return=0.05,
        timing_return=0.05,
        interaction_return=0.0,
        annual_alpha=0.05,
        tracking_error=0.02,
        information_ratio=2.5,
        win_rate_by_quantile={1: 0.4, 5: 0.6},
    )


@pytest.mark.unit
class TestFactorIcCommand:
    """Ops factor-ic 命令测试。"""

    def test_factor_ic_outputs_markdown_to_stdout(
        self,
        runner: CliRunner,
        mocker: MockerFixture,
    ) -> None:
        """C1: 默认 stdout 输出 Markdown, evaluate 用 factor_id + version=None."""
        mock_facade = MagicMock()
        mock_facade.evaluate.return_value = _make_factor_evaluation_report()
        container = _mock_container_for_ops_object(mock_facade)
        mocker.patch(CONTAINER_PATH, return_value=container)

        result = runner.invoke(
            app,
            [
                "ops",
                "factor-ic",
                "fx.momentum",
                "--start",
                "2024-01-02",
                "--end",
                "2024-06-30",
            ],
        )

        assert result.exit_code == 0
        assert "Factor IC Report:" in result.output
        assert "Rank IC" in result.output
        mock_facade.evaluate.assert_called_once()
        call_args = mock_facade.evaluate.call_args
        assert call_args.args[0] == "fx.momentum"
        assert call_args.kwargs["version"] is None

    def test_factor_ic_writes_output_file(
        self,
        runner: CliRunner,
        mocker: MockerFixture,
        tmp_path: Path,
    ) -> None:
        """C2: --output 写入文件，文件存在，内容含报告头。"""
        mock_facade = MagicMock()
        mock_facade.evaluate.return_value = _make_factor_evaluation_report()
        container = _mock_container_for_ops_object(mock_facade)
        mocker.patch(CONTAINER_PATH, return_value=container)
        output_file = tmp_path / "report.md"

        result = runner.invoke(
            app,
            [
                "ops",
                "factor-ic",
                "fx.momentum",
                "--start",
                "2024-01-02",
                "--end",
                "2024-06-30",
                "--output",
                str(output_file),
            ],
        )

        assert result.exit_code == 0
        assert output_file.exists()
        content = output_file.read_text(encoding="utf-8")
        assert "Factor IC Report:" in content

    def test_factor_ic_explicit_version(
        self,
        runner: CliRunner,
        mocker: MockerFixture,
    ) -> None:
        """C3: --version 2 → evaluate 调用 version=2。"""
        mock_facade = MagicMock()
        mock_facade.evaluate.return_value = _make_factor_evaluation_report()
        container = _mock_container_for_ops_object(mock_facade)
        mocker.patch(CONTAINER_PATH, return_value=container)

        result = runner.invoke(
            app,
            [
                "ops",
                "factor-ic",
                "fx.momentum",
                "--start",
                "2024-01-02",
                "--end",
                "2024-06-30",
                "--version",
                "2",
            ],
        )

        assert result.exit_code == 0
        call_kwargs = mock_facade.evaluate.call_args.kwargs
        assert call_kwargs["version"] == 2

    def test_factor_ic_error_exits_nonzero(
        self,
        runner: CliRunner,
        mocker: MockerFixture,
    ) -> None:
        """C4: evaluate 抛 AppQueryError → exit_code==1，output 含"诊断失败"。"""
        mock_facade = MagicMock()
        mock_facade.evaluate.side_effect = AppQueryError("no active version")
        container = _mock_container_for_ops_object(mock_facade)
        mocker.patch(CONTAINER_PATH, return_value=container)

        result = runner.invoke(
            app,
            [
                "ops",
                "factor-ic",
                "fx.momentum",
                "--start",
                "2024-01-02",
                "--end",
                "2024-06-30",
            ],
        )

        assert result.exit_code == 1
        assert "诊断失败" in result.output

    def test_factor_ic_regime_flag_propagated(
        self,
        runner: CliRunner,
        mocker: MockerFixture,
    ) -> None:
        """C5: --regime → evaluate 的 options.run_regime_ic==True。"""
        mock_facade = MagicMock()
        mock_facade.evaluate.return_value = _make_factor_evaluation_report()
        container = _mock_container_for_ops_object(mock_facade)
        mocker.patch(CONTAINER_PATH, return_value=container)

        result = runner.invoke(
            app,
            [
                "ops",
                "factor-ic",
                "fx.momentum",
                "--start",
                "2024-01-02",
                "--end",
                "2024-06-30",
                "--regime",
            ],
        )

        assert result.exit_code == 0
        options = mock_facade.evaluate.call_args.kwargs["options"]
        assert isinstance(options, EvaluationOptions)
        assert options.run_regime_ic is True

    def test_factor_ic_renders_regime_section_when_enabled(
        self,
        runner: CliRunner,
        mocker: MockerFixture,
    ) -> None:
        """C6: report 含 regime_ic 非 None + 传 --regime → output 含"Regime IC"。"""
        mock_facade = MagicMock()
        mock_facade.evaluate.return_value = _make_factor_evaluation_report(
            regime_ic=_make_regime_ic(),
        )
        container = _mock_container_for_ops_object(mock_facade)
        mocker.patch(CONTAINER_PATH, return_value=container)

        result = runner.invoke(
            app,
            [
                "ops",
                "factor-ic",
                "fx.momentum",
                "--start",
                "2024-01-02",
                "--end",
                "2024-06-30",
                "--regime",
            ],
        )

        assert result.exit_code == 0
        assert "Regime IC" in result.output

    def test_factor_ic_missing_factor_id_errors(
        self,
        runner: CliRunner,
        mocker: MockerFixture,
    ) -> None:
        """C7: 不传 factor → typer 参数缺失，exit_code != 0。"""
        mock_facade = MagicMock()
        container = _mock_container_for_ops_object(mock_facade)
        mocker.patch(CONTAINER_PATH, return_value=container)

        result = runner.invoke(
            app,
            [
                "ops",
                "factor-ic",
                "--start",
                "2024-01-02",
                "--end",
                "2024-06-30",
            ],
        )

        assert result.exit_code != 0

    def test_factor_ic_markdown_has_all_core_sections(
        self,
        runner: CliRunner,
        mocker: MockerFixture,
    ) -> None:
        """C8: output 含核心章节标题 (IC Summary/Decay/Quantile 等)."""
        mock_facade = MagicMock()
        mock_facade.evaluate.return_value = _make_factor_evaluation_report()
        container = _mock_container_for_ops_object(mock_facade)
        mocker.patch(CONTAINER_PATH, return_value=container)

        result = runner.invoke(
            app,
            [
                "ops",
                "factor-ic",
                "fx.momentum",
                "--start",
                "2024-01-02",
                "--end",
                "2024-06-30",
            ],
        )

        assert result.exit_code == 0
        for section in (
            "Contract",
            "IC Summary",
            "IC Decay",
            "Quantile Returns",
            "Long-Short",
            "Turnover",
            "Overview",
        ):
            assert section in result.output, f"missing section: {section}"

    def test_factor_ic_attribution_flag_propagated(
        self,
        runner: CliRunner,
        mocker: MockerFixture,
    ) -> None:
        """C9: --attribution -> options.run_performance_attribution 为 True."""
        mock_facade = MagicMock()
        mock_facade.evaluate.return_value = _make_factor_evaluation_report()
        container = _mock_container_for_ops_object(mock_facade)
        mocker.patch(CONTAINER_PATH, return_value=container)

        result = runner.invoke(
            app,
            [
                "ops",
                "factor-ic",
                "fx.momentum",
                "--start",
                "2024-01-02",
                "--end",
                "2024-06-30",
                "--attribution",
            ],
        )

        assert result.exit_code == 0
        options = mock_facade.evaluate.call_args.kwargs["options"]
        assert isinstance(options, EvaluationOptions)
        assert options.run_performance_attribution is True

    def test_factor_ic_renders_attribution_section_when_enabled(
        self,
        runner: CliRunner,
        mocker: MockerFixture,
    ) -> None:
        """C10: report 含 performance_attribution + --attribution → output 含章节."""
        mock_facade = MagicMock()
        mock_facade.evaluate.return_value = _make_factor_evaluation_report(
            performance_attribution=_make_performance_attribution(),
        )
        container = _mock_container_for_ops_object(mock_facade)
        mocker.patch(CONTAINER_PATH, return_value=container)

        result = runner.invoke(
            app,
            [
                "ops",
                "factor-ic",
                "fx.momentum",
                "--start",
                "2024-01-02",
                "--end",
                "2024-06-30",
                "--attribution",
            ],
        )

        assert result.exit_code == 0
        assert "Performance Attribution" in result.output

    def test_factor_ic_contract_options_propagated(
        self,
        runner: CliRunner,
        mocker: MockerFixture,
    ) -> None:
        """C11: dataset/catalog/universe/cost options are passed to facade."""
        mock_facade = MagicMock()
        mock_facade.evaluate.return_value = _make_factor_evaluation_report()
        container = _mock_container_for_ops_object(mock_facade)
        mocker.patch(CONTAINER_PATH, return_value=container)

        result = runner.invoke(
            app,
            [
                "ops",
                "factor-ic",
                "fx.momentum",
                "--start",
                "2024-01-02",
                "--end",
                "2024-06-30",
                "--dataset-id",
                "stock_daily",
                "--catalog-snapshot-id",
                "catalog-snap-20240630",
                "--universe",
                "csi_300",
                "--cost-bps",
                "7.5",
            ],
        )

        assert result.exit_code == 0
        options = mock_facade.evaluate.call_args.kwargs["options"]
        assert isinstance(options, EvaluationOptions)
        assert options.dataset_id == "stock_daily"
        assert options.catalog_snapshot_id == "catalog-snap-20240630"
        assert options.universe == "csi_300"
        assert options.cost_bps == 7.5
        assert "stock_daily" in result.output
        assert "catalog-snap-001" in result.output
        assert "csi_300" in result.output
