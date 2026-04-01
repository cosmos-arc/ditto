"""Unit tests for Phase 3 materialization Prefect flows."""

from __future__ import annotations

from ditto_engine.engine.publication_safety import CertificationStage
from ditto_port.jobs.flows.materialization import (
    certify_publication_flow,
    daily_materialization_flow,
    deprecate_publication_flow,
    promote_publication_flow,
    repair_from_invalidation_flow,
    rollback_publication_flow,
    shadow_compare_flow,
    shadow_publish_flow,
)
from ditto_port.services.derived.cascade_protocol import RepairBatchResult
from pytest_mock import MockerFixture


def _prefect_runner(entrypoint):
    return getattr(entrypoint, "func", getattr(entrypoint, "fn", entrypoint))


DAILY_MATERIALIZATION_FLOW_RUNNER = _prefect_runner(daily_materialization_flow)
REPAIR_FROM_INVALIDATION_FLOW_RUNNER = _prefect_runner(repair_from_invalidation_flow)
SHADOW_PUBLISH_FLOW_RUNNER = _prefect_runner(shadow_publish_flow)
SHADOW_COMPARE_FLOW_RUNNER = _prefect_runner(shadow_compare_flow)
CERTIFY_PUBLICATION_FLOW_RUNNER = _prefect_runner(certify_publication_flow)
PROMOTE_PUBLICATION_FLOW_RUNNER = _prefect_runner(promote_publication_flow)
ROLLBACK_PUBLICATION_FLOW_RUNNER = _prefect_runner(rollback_publication_flow)
DEPRECATE_PUBLICATION_FLOW_RUNNER = _prefect_runner(deprecate_publication_flow)


class TestDailyMaterializationFlow:
    """Tests for daily materialization flow."""

    def test_flow_calls_service_for_durable_profiles(
        self,
        mocker: MockerFixture,
    ) -> None:
        """Flow should request durable materialization from the bundle service."""
        bundle = mocker.MagicMock()
        bundle.materialization_service.materialize_daily.return_value = (
            {"derived_id": "factor.alpha_simple"},
        )
        context = mocker.MagicMock()
        context.__enter__.return_value = bundle
        context.__exit__.return_value = None
        mocker.patch(
            "ditto_port.jobs.flows.materialization.create_materialization_bundle",
            return_value=context,
        )

        result = DAILY_MATERIALIZATION_FLOW_RUNNER(trade_date="2026-03-13")

        bundle.materialization_service.materialize_daily.assert_called_once_with(
            trade_date="2026-03-13",
            mode="incremental",
            derived_ids=None,
        )
        assert result["summary"]["materialized_count"] == 1


class TestRepairFromInvalidationFlow:
    """Tests for invalidation repair flow."""

    def test_flow_repairs_pending_invalidations(self, mocker: MockerFixture) -> None:
        """Repair flow should delegate to the invalidation service."""
        bundle = mocker.MagicMock()
        bundle.invalidation_service.repair_batch.return_value = RepairBatchResult(
            repaired=(
                {"derived_id": "factor.alpha_simple"},
                {"derived_id": "factor.alpha_other"},
            ),
            failed=(),
        )
        context = mocker.MagicMock()
        context.__enter__.return_value = bundle
        context.__exit__.return_value = None
        mocker.patch(
            "ditto_port.jobs.flows.materialization.create_materialization_bundle",
            return_value=context,
        )

        result = REPAIR_FROM_INVALIDATION_FLOW_RUNNER(limit=20)

        bundle.invalidation_service.repair_batch.assert_called_once_with(batch_size=20)
        assert result["summary"]["repaired_count"] == 2
        assert result["summary"]["failed_count"] == 0


class TestPublicationFlows:
    """Tests for publication orchestration flows."""

    def test_shadow_publish_flow_delegates_to_publication_facade(
        self,
        mocker: MockerFixture,
    ) -> None:
        """Shadow publish flow should register the active candidate slot."""
        bundle = mocker.MagicMock()
        bundle.publication_facade.shadow_publish.return_value = {"candidate_version": 3}
        context = mocker.MagicMock()
        context.__enter__.return_value = bundle
        context.__exit__.return_value = None
        mocker.patch(
            "ditto_port.jobs.flows.materialization.create_materialization_bundle",
            return_value=context,
        )

        result = SHADOW_PUBLISH_FLOW_RUNNER(
            derived_id="factor.alpha_publish",
            candidate_version=3,
            baseline_version=2,
        )

        bundle.publication_facade.shadow_publish.assert_called_once_with(
            derived_id="factor.alpha_publish",
            candidate_version=3,
            baseline_version=2,
        )
        assert result["summary"] == {
            "derived_id": "factor.alpha_publish",
            "candidate_version": 3,
            "baseline_version": 2,
        }

    def test_shadow_compare_flow_delegates_to_publication_facade(
        self,
        mocker: MockerFixture,
    ) -> None:
        """Shadow compare flow should call the publication facade."""
        bundle = mocker.MagicMock()
        bundle.publication_facade.run_shadow_compare.return_value = {
            "report_id": "diff-001"
        }
        context = mocker.MagicMock()
        context.__enter__.return_value = bundle
        context.__exit__.return_value = None
        mocker.patch(
            "ditto_port.jobs.flows.materialization.create_materialization_bundle",
            return_value=context,
        )

        result = SHADOW_COMPARE_FLOW_RUNNER(
            derived_id="factor.alpha_publish",
            start="2026-03-10",
            end="2026-03-11",
        )

        bundle.publication_facade.run_shadow_compare.assert_called_once_with(
            derived_id="factor.alpha_publish",
            start="2026-03-10",
            end="2026-03-11",
            candidate_version=None,
            baseline_version=None,
        )
        assert result["summary"]["derived_id"] == "factor.alpha_publish"

    def test_certify_publication_flow_delegates_to_publication_facade(
        self,
        mocker: MockerFixture,
    ) -> None:
        """Certification flow should call the publication facade."""
        bundle = mocker.MagicMock()
        bundle.publication_facade.certify.return_value = {"report_id": "cert-001"}
        context = mocker.MagicMock()
        context.__enter__.return_value = bundle
        context.__exit__.return_value = None
        mocker.patch(
            "ditto_port.jobs.flows.materialization.create_materialization_bundle",
            return_value=context,
        )

        result = CERTIFY_PUBLICATION_FLOW_RUNNER(
            derived_id="factor.alpha_publish",
            version=3,
            stage=CertificationStage.PUBLISH_READY.value,
        )

        bundle.publication_facade.certify.assert_called_once_with(
            derived_id="factor.alpha_publish",
            version=3,
            stage=CertificationStage.PUBLISH_READY,
        )
        assert result["summary"]["version"] == 3

    def test_promote_publication_flow_delegates_to_publication_facade(
        self,
        mocker: MockerFixture,
    ) -> None:
        """Promote flow should call the publication facade."""
        bundle = mocker.MagicMock()
        bundle.publication_facade.promote.return_value = {"version": 3}
        context = mocker.MagicMock()
        context.__enter__.return_value = bundle
        context.__exit__.return_value = None
        mocker.patch(
            "ditto_port.jobs.flows.materialization.create_materialization_bundle",
            return_value=context,
        )

        result = PROMOTE_PUBLICATION_FLOW_RUNNER(
            derived_id="factor.alpha_publish",
            candidate_version=3,
        )

        bundle.publication_facade.promote.assert_called_once_with(
            derived_id="factor.alpha_publish",
            candidate_version=3,
        )
        assert result["summary"]["candidate_version"] == 3

    def test_rollback_flow_switches_primary_to_previous_version(
        self,
        mocker: MockerFixture,
    ) -> None:
        """Rollback flow should move the primary pointer to the target version."""
        bundle = mocker.MagicMock()
        bundle.publication_facade.rollback.return_value = {"version": 2}
        context = mocker.MagicMock()
        context.__enter__.return_value = bundle
        context.__exit__.return_value = None
        mocker.patch(
            "ditto_port.jobs.flows.materialization.create_materialization_bundle",
            return_value=context,
        )

        result = ROLLBACK_PUBLICATION_FLOW_RUNNER(
            derived_id="factor.alpha_publish",
            target_version=2,
        )

        bundle.publication_facade.rollback.assert_called_once_with(
            derived_id="factor.alpha_publish",
            target_version=2,
        )
        assert result["summary"] == {
            "derived_id": "factor.alpha_publish",
            "target_version": 2,
        }

    def test_deprecate_flow_marks_candidate_offline(
        self,
        mocker: MockerFixture,
    ) -> None:
        """Deprecate flow should mark the version offline via the facade."""
        bundle = mocker.MagicMock()
        bundle.publication_facade.deprecate.return_value = {"version": 2}
        context = mocker.MagicMock()
        context.__enter__.return_value = bundle
        context.__exit__.return_value = None
        mocker.patch(
            "ditto_port.jobs.flows.materialization.create_materialization_bundle",
            return_value=context,
        )

        result = DEPRECATE_PUBLICATION_FLOW_RUNNER(
            derived_id="factor.alpha_publish",
            version=2,
        )

        bundle.publication_facade.deprecate.assert_called_once_with(
            derived_id="factor.alpha_publish",
            version=2,
        )
        assert result["summary"] == {
            "derived_id": "factor.alpha_publish",
            "version": 2,
        }
