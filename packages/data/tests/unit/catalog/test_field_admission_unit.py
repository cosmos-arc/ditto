"""Unit tests for field admission temporal visibility rules."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime

from ditto_data.catalog.field_admission import FieldUsageScope, field_reasons
from ditto_data.catalog.field_evidence import CertifiedField


def _field(**overrides: object) -> CertifiedField:
    base = CertifiedField(
        field="amount",
        snapshot_id="snapshot:tushare:stock_daily:sha256:abc",
        instrument_ids=(600000,),
        covered_from=date(2026, 9, 18),
        covered_to=date(2026, 9, 18),
        available_at=datetime(2026, 9, 18, 1, tzinfo=UTC),
        publication_at=datetime(2026, 9, 18, 1, tzinfo=UTC),
        time_precision="timestamp",
        evidence_uri="evidence://field/amount",
    )
    return replace(base, **overrides)


def _scope(**overrides: object) -> FieldUsageScope:
    base = FieldUsageScope(
        consumer_field="",
        consumer_input_hash=None,
        instrument_ids=(600000,),
        required_from=date(2026, 9, 18),
        required_to=date(2026, 9, 18),
        knowledge_cutoff=datetime(2026, 9, 18, 8, tzinfo=UTC),
        publication_cutoff=datetime(2026, 9, 18, 8, tzinfo=UTC),
    )
    return replace(base, **overrides)


class TestFieldReasonsObservedAt:
    """Local first observation bounds knowledge visibility, not publication."""

    def test_observed_after_knowledge_cutoff_is_not_visible(self) -> None:
        field = _field(observed_at=datetime(2026, 9, 18, 9, tzinfo=UTC))

        reasons = field_reasons(field, _scope())

        assert "TIME_NOT_VISIBLE" in reasons

    def test_observed_within_knowledge_cutoff_stays_visible(self) -> None:
        field = _field(observed_at=datetime(2026, 9, 18, 7, tzinfo=UTC))

        reasons = field_reasons(field, _scope())

        assert "TIME_NOT_VISIBLE" not in reasons

    def test_observed_after_publication_cutoff_does_not_block_publication(
        self,
    ) -> None:
        field = _field(observed_at=datetime(2026, 9, 19, tzinfo=UTC))

        reasons = field_reasons(
            field, _scope(knowledge_cutoff=datetime(2026, 9, 20, tzinfo=UTC))
        )

        assert "TIME_NOT_VISIBLE" not in reasons
