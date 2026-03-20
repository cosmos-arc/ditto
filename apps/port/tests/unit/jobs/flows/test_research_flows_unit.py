"""Unit tests for research dataset Prefect flows."""

from __future__ import annotations

from ditto_core.engine.research import DatasetSnapshot, KnownAtPolicy
from ditto_port.jobs.flows.research import research_dataset_build_flow
from pytest_mock import MockerFixture


def _prefect_runner(entrypoint):
    return getattr(entrypoint, "func", getattr(entrypoint, "fn", entrypoint))


RESEARCH_DATASET_BUILD_FLOW_RUNNER = _prefect_runner(research_dataset_build_flow)


class TestResearchDatasetBuildFlow:
    """Tests for research dataset build flow."""

    def test_research_dataset_build_flow_delegates_to_facade(
        self,
        mocker: MockerFixture,
    ) -> None:
        """Flow should delegate dataset build to the research facade."""
        bundle = mocker.MagicMock()
        snapshot = DatasetSnapshot(
            snapshot_id="rds-001",
            dataset_id="research.alpha_beta",
            dataset_spec_version=1,
            spine_snapshot_id="rsp-001",
            start="2026-03-10",
            end="2026-03-11",
            row_count=2,
            data_path="derived/research/datasets/research.alpha_beta/snapshots/rds-001/data.parquet",
            manifest_hash="manifest-001",
            known_at_policy=KnownAtPolicy.SAMPLE_TIME,
            effective_cutoff=None,
            resolved_versions={"factor.alpha": 2},
            resolved_inputs=(
                {
                    "derived_id": "factor.alpha",
                    "version": 2,
                    "artifact_path": "derived/artifacts/series/factor.alpha/v2",
                },
            ),
            source_snapshot_ids=("market:20260311-001",),
            builder_version="unified-derived-research-v1",
            created_at="2026-03-14T12:00:00+08:00",
        )
        bundle.research_dataset_facade.build.return_value = snapshot
        bundle.research_dataset_facade.load_build_report.return_value = {
            "row_count": 2,
            "spine_row_count": 2,
            "null_counts": {"factor.alpha": 0},
            "resolved_versions": {"factor.alpha": 2},
            "known_at_policy": "sample_time",
        }
        context = mocker.MagicMock()
        context.__enter__.return_value = bundle
        context.__exit__.return_value = None
        mocker.patch(
            "ditto_port.jobs.flows.research.create_materialization_bundle",
            return_value=context,
        )

        result = RESEARCH_DATASET_BUILD_FLOW_RUNNER(
            dataset_id="research.alpha_beta",
            start="2026-03-10",
            end="2026-03-11",
        )

        bundle.research_dataset_facade.build.assert_called_once_with(
            dataset_id="research.alpha_beta",
            start="2026-03-10",
            end="2026-03-11",
            version_overrides=None,
            explicit_cutoff=None,
        )
        bundle.research_dataset_facade.load_build_report.assert_called_once_with(
            snapshot
        )
        assert result["summary"]["snapshot_id"] == "rds-001"

    def test_research_dataset_build_flow_returns_snapshot_and_summary(
        self,
        mocker: MockerFixture,
    ) -> None:
        """Flow should expose both snapshot results and build summary."""
        bundle = mocker.MagicMock()
        snapshot = DatasetSnapshot(
            snapshot_id="rds-002",
            dataset_id="research.alpha_beta",
            dataset_spec_version=1,
            spine_snapshot_id="rsp-002",
            start="2026-03-11",
            end="2026-03-11",
            row_count=1,
            data_path="derived/research/datasets/research.alpha_beta/snapshots/rds-002/data.parquet",
            manifest_hash="manifest-002",
            known_at_policy=KnownAtPolicy.EXPLICIT_CUTOFF,
            effective_cutoff="2026-03-11",
            resolved_versions={"factor.alpha": 3},
            resolved_inputs=(
                {
                    "derived_id": "factor.alpha",
                    "version": 3,
                    "artifact_path": "derived/artifacts/series/factor.alpha/v3",
                },
            ),
            source_snapshot_ids=("market:20260311-001",),
            builder_version="unified-derived-research-v1",
            created_at="2026-03-14T12:00:00+08:00",
        )
        bundle.research_dataset_facade.build.return_value = snapshot
        bundle.research_dataset_facade.load_build_report.return_value = {
            "row_count": 1,
            "spine_row_count": 1,
            "null_counts": {"factor.alpha": 0},
            "resolved_versions": {"factor.alpha": 3},
            "known_at_policy": "explicit_cutoff",
        }
        context = mocker.MagicMock()
        context.__enter__.return_value = bundle
        context.__exit__.return_value = None
        mocker.patch(
            "ditto_port.jobs.flows.research.create_materialization_bundle",
            return_value=context,
        )

        result = RESEARCH_DATASET_BUILD_FLOW_RUNNER(
            dataset_id="research.alpha_beta",
            start="2026-03-11",
            end="2026-03-11",
            version_overrides={"factor.alpha": 3},
            explicit_cutoff="2026-03-11",
        )

        assert result["results"][0]["snapshot_id"] == "rds-002"
        assert result["summary"] == {
            "dataset_id": "research.alpha_beta",
            "snapshot_id": "rds-002",
            "row_count": 1,
            "spine_row_count": 1,
            "null_counts": {"factor.alpha": 0},
            "resolved_versions": {"factor.alpha": 3},
            "known_at_policy": "explicit_cutoff",
        }
