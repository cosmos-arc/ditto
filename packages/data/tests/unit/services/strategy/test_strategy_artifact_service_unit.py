"""Tests for StrategyArtifactService -- 策略产物 CRUD 与归档生命周期."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, replace

import pytest
from ditto_strategy.models import StrategyArtifactRecord
from ditto_strategy.storage.sqlite.services.strategy_artifact_service import (
    StrategyArtifactService,
)
from pytest_mock import MockerFixture


def _make_artifact(**overrides: object) -> StrategyArtifactRecord:
    """构建测试用 StrategyArtifactRecord."""
    defaults: dict[str, object] = {
        "artifact_id": "art-backtest-001",
        "strategy_id": "strat.momentum_20d",
        "run_id": "run-20260323-001",
        "artifact_type": "backtest_report",
        "file_path": "artifacts/strat.momentum_20d/run-20260323-001/report.parquet",
        "metadata": {"total_return": 0.15, "sharpe": 1.2},
        "status": "active",
        "created_at": "2026-03-23T12:00:00+08:00",
    }
    return StrategyArtifactRecord(**{**defaults, **overrides})


# ── Model Tests ──────────────────────────────────────────────────────────────


class TestStrategyArtifactRecord:
    """StrategyArtifactRecord 模型测试."""

    def test_create_record(self) -> None:
        """正确创建记录."""
        record = _make_artifact()
        assert record.artifact_id == "art-backtest-001"
        assert record.strategy_id == "strat.momentum_20d"
        assert record.run_id == "run-20260323-001"
        assert record.artifact_type == "backtest_report"
        assert record.status == "active"

    def test_default_values(self) -> None:
        """默认值正确."""
        record = StrategyArtifactRecord(
            artifact_id="art-001",
            strategy_id="strat.test",
            run_id="run-001",
            artifact_type="signal_snapshot",
            file_path="/tmp/art.parquet",
        )
        assert record.metadata == {}
        assert record.status == "active"
        assert record.created_at == ""

    def test_record_is_frozen(self) -> None:
        """frozen=True 不可变."""
        record = _make_artifact()
        with pytest.raises(FrozenInstanceError):
            record.status = "archived"  # type: ignore[misc]


# ── Service Tests ────────────────────────────────────────────────────────────


class TestStrategyArtifactService:
    """StrategyArtifactService 服务测试."""

    def test_save_artifact_delegates_to_writer(self, mocker: MockerFixture) -> None:
        """save_artifact() 委托给 writer.save()."""
        artifact = _make_artifact()
        writer = mocker.Mock()
        writer.save = mocker.Mock(return_value=True)
        service = StrategyArtifactService(
            reader=mocker.Mock(),
            writer=writer,
        )

        result = service.save_artifact(artifact)

        assert result is artifact
        writer.save.assert_called_once_with(artifact)

    def test_save_artifact_treats_same_payload_as_idempotent(
        self,
        mocker: MockerFixture,
    ) -> None:
        """Generated time and mutable status do not rewrite immutable evidence."""
        existing = _make_artifact(status="archived", created_at="first")
        retry = replace(existing, status="active", created_at="retry")
        reader = mocker.Mock()
        reader.get = mocker.Mock(return_value=existing)
        writer = mocker.Mock()
        writer.save = mocker.Mock(return_value=False)
        service = StrategyArtifactService(reader=reader, writer=writer)

        result = service.save_artifact(retry)

        assert result is existing
        reader.get.assert_called_once_with(existing.artifact_id)

    def test_get_artifact_delegates_to_reader(self, mocker: MockerFixture) -> None:
        """get_artifact() 委托给 reader.get()."""
        artifact = _make_artifact()
        reader = mocker.Mock()
        reader.get = mocker.Mock(return_value=artifact)
        service = StrategyArtifactService(
            reader=reader,
            writer=mocker.Mock(),
        )

        result = service.get_artifact("art-backtest-001")

        assert result is artifact
        reader.get.assert_called_once_with("art-backtest-001")

    def test_get_artifact_not_found(self, mocker: MockerFixture) -> None:
        """get_artifact() 查询不存在时返回 None."""
        reader = mocker.Mock()
        reader.get = mocker.Mock(return_value=None)
        service = StrategyArtifactService(
            reader=reader,
            writer=mocker.Mock(),
        )

        result = service.get_artifact("art-nonexistent")

        assert result is None
        reader.get.assert_called_once_with("art-nonexistent")

    def test_list_artifacts_delegates_to_reader(self, mocker: MockerFixture) -> None:
        """list_artifacts() 委托给 reader.list_all()."""
        artifacts = [
            _make_artifact(artifact_id="art-001"),
            _make_artifact(artifact_id="art-002"),
        ]
        reader = mocker.Mock()
        reader.list_all = mocker.Mock(return_value=artifacts)
        service = StrategyArtifactService(
            reader=reader,
            writer=mocker.Mock(),
        )

        result = service.list_artifacts()

        assert result == artifacts
        reader.list_all.assert_called_once_with()

    def test_list_by_strategy_delegates_to_reader(self, mocker: MockerFixture) -> None:
        """list_by_strategy() 委托给 reader.list_by_strategy()."""
        artifacts = [
            _make_artifact(artifact_id="art-001", strategy_id="strat.s1"),
            _make_artifact(artifact_id="art-002", strategy_id="strat.s1"),
        ]
        reader = mocker.Mock()
        reader.list_by_strategy = mocker.Mock(return_value=artifacts)
        service = StrategyArtifactService(
            reader=reader,
            writer=mocker.Mock(),
        )

        result = service.list_by_strategy("strat.s1")

        assert result == artifacts
        reader.list_by_strategy.assert_called_once_with("strat.s1")

    def test_archive_artifact_calls_writer(self, mocker: MockerFixture) -> None:
        """archive_artifact() 调用 writer.update_status(artifact_id, 'archived')."""
        writer = mocker.Mock()
        writer.update_status = mocker.Mock(return_value=True)
        service = StrategyArtifactService(
            reader=mocker.Mock(),
            writer=writer,
        )

        result = service.archive_artifact("art-backtest-001")

        assert result is True
        writer.update_status.assert_called_once_with(
            "art-backtest-001",
            "archived",
            expected_current=("active",),
        )

    def test_archive_artifact_not_found(self, mocker: MockerFixture) -> None:
        """archive_artifact() 产物不存在时返回 False."""
        writer = mocker.Mock()
        writer.update_status = mocker.Mock(return_value=False)
        service = StrategyArtifactService(
            reader=mocker.Mock(),
            writer=writer,
        )

        result = service.archive_artifact("art-nonexistent")

        assert result is False
        writer.update_status.assert_called_once_with(
            "art-nonexistent",
            "archived",
            expected_current=("active",),
        )

    def test_claim_and_activate_replacement_delegate_to_writer(
        self,
        mocker: MockerFixture,
    ) -> None:
        """Replacement lifecycle stays behind the artifact service boundary."""
        writer = mocker.Mock()
        writer.claim_replacement = mocker.Mock(return_value=True)
        writer.activate_candidate = mocker.Mock(return_value=True)
        service = StrategyArtifactService(reader=mocker.Mock(), writer=writer)

        claimed = service.claim_replacement("candidate", "active")
        activated = service.activate_candidate(
            "candidate",
            replaced_artifact_id="active",
        )

        assert claimed is True
        assert activated is True
        writer.claim_replacement.assert_called_once_with("candidate", "active")
        writer.activate_candidate.assert_called_once_with(
            "candidate",
            replaced_artifact_id="active",
        )
