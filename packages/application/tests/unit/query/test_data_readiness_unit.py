"""R2 bundle and per-dataset readiness tests."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

from ditto_application.queries.data_readiness import (
    R2_P0_DATASETS,
    R2_P1_DATASETS,
    DataReadinessQueryFacade,
    DatasetReadinessRequirement,
    PartitionHealth,
)


def _active_report(
    *,
    complete_from: date = date(2015, 1, 1),
    target_to: date = date(2026, 7, 18),
) -> MagicMock:
    report = MagicMock()
    report.report_id = "certification:calendar:1"
    report.coverage.complete_from = complete_from
    report.coverage.target_to = target_to
    report.coverage.unapproved_gaps = ()
    report.evidence.snapshot_ids = ("snapshot:calendar:2026-07-18",)
    report.evidence.pit_replay_results = (
        MagicMock(name="universe-replay", passed=True),
    )
    report.evidence.pit_replay_results[0].name = "universe-replay"
    return report


def test_ready_requires_promoted_maturity_interval_profile_snapshot_and_health() -> (
    None
):
    certification_reader = MagicMock()
    certification_reader.get_active_report.return_value = _active_report()
    facade = DataReadinessQueryFacade(certification_reader=certification_reader)

    report = facade.assess(
        profile="r2-modern-a-share-v1",
        requirements=(
            DatasetReadinessRequirement(
                dataset_id="calendar",
                required_from=date(2026, 7, 1),
                required_to=date(2026, 7, 18),
                expected_snapshot_ids=("snapshot:calendar:2026-07-18",),
                requires_pit_universe=True,
            ),
        ),
        partition_health={
            "calendar": PartitionHealth(
                status="ready",
                snapshot_id="snapshot:calendar:2026-07-18",
            )
        },
    )

    assert report.status == "ready"
    assert report.datasets[0].status == "ready"
    assert report.datasets[0].reason_codes == ()


def test_readiness_fails_closed_with_dataset_date_and_reason_codes() -> None:
    certification_reader = MagicMock()
    certification_reader.get_active_report.return_value = _active_report(
        complete_from=date(2026, 7, 10)
    )
    facade = DataReadinessQueryFacade(certification_reader=certification_reader)

    report = facade.assess(
        profile="r2-modern-a-share-v1",
        requirements=(
            DatasetReadinessRequirement(
                dataset_id="calendar",
                required_from=date(2026, 7, 1),
                required_to=date(2026, 7, 18),
                expected_snapshot_ids=("snapshot:different",),
            ),
        ),
        partition_health={"calendar": PartitionHealth(status="blocked")},
    )

    dataset = report.datasets[0]
    assert report.status == "blocked"
    assert dataset.dataset_id == "calendar"
    assert dataset.required_from == date(2026, 7, 1)
    assert set(dataset.reason_codes) == {
        "CERTIFIED_INTERVAL_MISSING",
        "SOURCE_SNAPSHOT_MISMATCH",
        "PARTITION_HEALTH_BLOCKED",
    }


def test_experimental_dataset_is_not_accepted_without_maturity_promotion() -> None:
    certification_reader = MagicMock()
    certification_reader.get_active_report.return_value = _active_report()
    facade = DataReadinessQueryFacade(certification_reader=certification_reader)

    report = facade.assess(
        profile="r2-modern-a-share-v1",
        requirements=(
            DatasetReadinessRequirement(
                dataset_id="stock_daily",
                required_from=date(2026, 7, 18),
                required_to=date(2026, 7, 18),
            ),
        ),
    )

    assert report.datasets[0].reason_codes == ("DATASET_MATURITY_BLOCKED",)


def test_missing_profile_certification_fails_closed() -> None:
    certification_reader = MagicMock()
    certification_reader.get_active_report.return_value = None
    facade = DataReadinessQueryFacade(certification_reader=certification_reader)

    report = facade.assess(
        profile="r2-modern-a-share-v1",
        requirements=(
            DatasetReadinessRequirement(
                dataset_id="calendar",
                required_from=date(2026, 7, 18),
                required_to=date(2026, 7, 18),
            ),
        ),
    )

    assert report.datasets[0].reason_codes == ("CERTIFICATION_MISSING",)


def test_p0_and_p1_bundles_cover_the_19_products_without_overlap() -> None:
    assert len(R2_P0_DATASETS) == 12
    assert len(R2_P1_DATASETS) == 7
    assert set(R2_P0_DATASETS).isdisjoint(R2_P1_DATASETS)
