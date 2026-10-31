"""ops audit-price-coverage CLI 单测（#624 / #621 P2）.

mock 容器注入报告服务，验证 --json 输出、失败退出码与参数透传。
"""

from typing import Any
from unittest.mock import MagicMock

import orjson
import pytest
from ditto_apps.cli.commands import ops as ops_module
from ditto_apps.cli.main import app as root_app
from typer.testing import CliRunner

runner = CliRunner()

CONTAINER_PATH = "ditto_apps.cli.commands.ops.make_app_container"

_PASSED_PAYLOAD: dict[str, Any] = {
    "asset_class": "stock",
    "window": ["2014-01-01", "2026-10-29"],
    "passed": True,
    "calendar": {
        "trading_days": 3100,
        "duplicate_days": 0,
        "weekend_days": 0,
        "missing_years": [],
        "years_out_of_bounds": [],
        "yearly_counts": [[2024, 242]],
        "passed": True,
    },
    "session": {
        "roster_total": 5600,
        "securities_with_sessions": 5600,
        "expected_sessions": 10000000,
        "present_sessions": 9900000,
        "failure_gaps": 0,
        "limitation_gaps": 100000,
        "failure_anomalies": 0,
        "bar_sessions": 9900000,
        "adj_factor_checked": True,
        "adj_factor_missing": 0,
        "passed": True,
    },
    "gap_counts": {"suspended": 100000},
    "anomaly_counts": {},
    "top_gap_securities": [
        {"instrument_id": 1000001, "ticker": "000001.SZ", "gaps": 3}
    ],
    "gap_samples": [
        {
            "instrument_id": 1000001,
            "ticker": "000001.SZ",
            "trade_date": "2024-01-03",
            "kind": "suspended",
        }
    ],
}


class _ReportStub:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    @property
    def passed(self) -> bool:
        return self._payload["passed"]

    def to_dict(self) -> dict[str, Any]:
        return self._payload


def _mock_container(report: _ReportStub) -> MagicMock:
    container = MagicMock()
    service = MagicMock()
    service.run.return_value = report
    container.get.return_value = service
    return container


class TestAuditPriceCoverageCommand:
    def test_json_output_and_zero_exit_when_passed(self, mocker: Any) -> None:
        container = _mock_container(_ReportStub(dict(_PASSED_PAYLOAD)))
        mocker.patch(CONTAINER_PATH, return_value=container)

        result = runner.invoke(
            root_app,
            [
                "ops",
                "audit-price-coverage",
                "--start",
                "2014-01-01",
                "--end",
                "2026-10-29",
                "--json",
            ],
        )

        assert result.exit_code == 0
        payload = orjson.loads(result.output)
        assert payload["asset_class"] == "stock"
        assert payload["session"]["expected_sessions"] == 10000000
        assert payload["gap_counts"] == {"suspended": 100000}
        container.get.assert_called_once_with(ops_module.PriceCoverageAuditService)
        container.close.assert_called_once()

    def test_nonzero_exit_when_report_not_passed(self, mocker: Any) -> None:
        payload = dict(_PASSED_PAYLOAD)
        payload["passed"] = False
        payload["gap_counts"] = {"status_trading_no_bar": 5}
        container = _mock_container(_ReportStub(payload))
        mocker.patch(CONTAINER_PATH, return_value=container)

        result = runner.invoke(
            root_app,
            [
                "ops",
                "audit-price-coverage",
                "--start",
                "2014-01-01",
                "--end",
                "2026-10-29",
                "--asset-class",
                "etf",
                "--json",
            ],
        )

        assert result.exit_code == 1
        body = orjson.loads(result.output)
        assert body["passed"] is False

    def test_service_error_exits_nonzero_and_closes_container(
        self, mocker: Any
    ) -> None:
        container = _mock_container(_ReportStub(dict(_PASSED_PAYLOAD)))
        container.get.side_effect = RuntimeError("boom")
        mocker.patch(CONTAINER_PATH, return_value=container)

        result = runner.invoke(
            root_app,
            [
                "ops",
                "audit-price-coverage",
                "--start",
                "2014-01-01",
                "--end",
                "2026-10-29",
            ],
        )

        assert result.exit_code == 1
        assert "获取服务失败" in result.output

    def test_request_kwargs_propagated(self, mocker: Any) -> None:
        container = _mock_container(_ReportStub(dict(_PASSED_PAYLOAD)))
        mocker.patch(CONTAINER_PATH, return_value=container)
        service = container.get.return_value
        service.run = MagicMock(return_value=_ReportStub(dict(_PASSED_PAYLOAD)))

        result = runner.invoke(
            root_app,
            [
                "ops",
                "audit-price-coverage",
                "--start",
                "2014-01-01",
                "--end",
                "2026-10-29",
                "--asset-class",
                "etf",
                "--detail-limit",
                "5",
                "--json",
            ],
        )

        assert result.exit_code == 0
        service.run.assert_called_once_with(
            ops_module.PriceCoverageAuditRequest(
                start_date="2014-01-01",
                end_date="2026-10-29",
                asset_class="etf",
                detail_limit=5,
            )
        )


if __name__ == "__main__":
    pytest.main([__file__])


class TestAuditCapitalCoverageCommand:
    """#625 ops audit-capital-coverage：moneyflow/fund_share 档位接线."""

    def test_moneyflow_dataset_and_stock_roster_propagated(self, mocker: Any) -> None:
        payload = dict(_PASSED_PAYLOAD)
        payload["dataset"] = "moneyflow"
        container = _mock_container(_ReportStub(payload))
        mocker.patch(CONTAINER_PATH, return_value=container)
        service = container.get.return_value
        service.run = MagicMock(return_value=_ReportStub(payload))

        result = runner.invoke(
            root_app,
            [
                "ops",
                "audit-capital-coverage",
                "--dataset",
                "moneyflow",
                "--start",
                "2014-01-01",
                "--end",
                "2026-10-29",
                "--json",
            ],
        )

        assert result.exit_code == 0
        service.run.assert_called_once_with(
            ops_module.PriceCoverageAuditRequest(
                start_date="2014-01-01",
                end_date="2026-10-29",
                asset_class="stock",
                dataset="moneyflow",
                detail_limit=20,
            )
        )

    def test_fund_share_defaults_to_etf_roster(self, mocker: Any) -> None:
        payload = dict(_PASSED_PAYLOAD)
        payload["dataset"] = "fund_share"
        payload["asset_class"] = "etf"
        container = _mock_container(_ReportStub(payload))
        mocker.patch(CONTAINER_PATH, return_value=container)
        service = container.get.return_value
        service.run = MagicMock(return_value=_ReportStub(payload))

        result = runner.invoke(
            root_app,
            [
                "ops",
                "audit-capital-coverage",
                "--dataset",
                "fund_share",
                "--start",
                "2014-01-01",
                "--end",
                "2026-10-29",
                "--json",
            ],
        )

        assert result.exit_code == 0
        request = service.run.call_args.args[0]
        assert request.asset_class == "etf"
        assert request.dataset == "fund_share"

    def test_nonzero_exit_when_not_passed(self, mocker: Any) -> None:
        payload = dict(_PASSED_PAYLOAD)
        payload["dataset"] = "moneyflow"
        payload["passed"] = False
        payload["gap_counts"] = {"status_trading_no_bar": 3}
        container = _mock_container(_ReportStub(payload))
        mocker.patch(CONTAINER_PATH, return_value=container)

        result = runner.invoke(
            root_app,
            [
                "ops",
                "audit-capital-coverage",
                "--start",
                "2014-01-01",
                "--end",
                "2026-10-29",
                "--json",
            ],
        )

        assert result.exit_code == 1
        assert orjson.loads(result.output)["passed"] is False
