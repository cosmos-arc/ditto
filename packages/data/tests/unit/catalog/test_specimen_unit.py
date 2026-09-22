"""Unit tests for the five-category data specimen evidence record."""

from datetime import UTC, date, datetime

import pytest
from ditto_data.catalog.specimen import (
    SPECIMEN_CATEGORIES,
    DataSpecimen,
    SpecimenProcurement,
    SpecimenSource,
)

ADJUDICATED = datetime(2026, 9, 20, 12, tzinfo=UTC)


def _verified_specimen(**overrides: object) -> DataSpecimen:
    payload: dict[str, object] = {
        "category": "dividend_etf",
        "dataset_id": "dividend",
        "anchor": "510300.SH",
        "sources": (
            SpecimenSource(
                source="tushare",
                provider_snapshot_id="snapshot:tushare:dividend:sha256:a",
                upstream_group=None,
            ),
        ),
        "coverage_from": date(2026, 1, 1),
        "coverage_to": date(2026, 6, 30),
        "knowable_from": datetime(2026, 7, 1, tzinfo=UTC),
        "time_precision": "date",
        "as_of_counterexample": "cutoff before announcement keeps prior value",
        "license_record_ids": ("license:tushare:dividend:sha256:x",),
        "allowed_uses": ("display", "exploration"),
        "verification_status": "verified",
        "adjudicated_by": "chevy",
        "adjudicated_at": ADJUDICATED,
        "evidence_uri": "sqlite-evidence://dividend/specimen",
    }
    payload.update(overrides)
    return DataSpecimen(**payload)


class TestSpecimenIdentity:
    def test_record_is_content_addressed_and_stable(self) -> None:
        first = _verified_specimen()
        second = _verified_specimen()
        assert first.specimen_id.startswith("specimen:dividend_etf:sha256:")
        assert first.specimen_id == second.specimen_id

    def test_distinct_evidence_produces_distinct_identity(self) -> None:
        assert (
            _verified_specimen().specimen_id
            != _verified_specimen(anchor="510500.SH").specimen_id
        )

    def test_payload_round_trip_preserves_record(self) -> None:
        specimen = _verified_specimen()
        restored = DataSpecimen.from_payload(specimen.to_payload())
        assert restored == specimen
        assert restored.specimen_id == specimen.specimen_id


class TestFailClosedConclusions:
    def test_unverified_specimen_cannot_claim_uses(self) -> None:
        with pytest.raises(ValueError, match="cannot claim allowed uses"):
            _verified_specimen(
                verification_status="unverified", allowed_uses=("exploration",)
            )

    def test_unverified_specimen_requires_explicit_gaps(self) -> None:
        with pytest.raises(ValueError, match="explicit gaps"):
            _verified_specimen(verification_status="unverified", allowed_uses=())

    def test_missing_category_specimen_is_explicitly_unverified(self) -> None:
        specimen = DataSpecimen(
            category="cross_border_etf",
            dataset_id="etf_nav",
            anchor="513100.SH",
            sources=(SpecimenSource(source="tushare"),),
            gaps=("REAL_SAMPLE_NOT_COLLECTED",),
            procurement=(
                SpecimenProcurement(option="professional", quote_status="unknown"),
            ),
        )
        assert specimen.verification_status == "unverified"
        assert specimen.allowed_uses == ()
        assert "REAL_SAMPLE_NOT_COLLECTED" in specimen.gaps
        assert "QUOTE_UNKNOWN" in specimen.gaps

    def test_verified_requires_full_evidence_pack(self) -> None:
        with pytest.raises(ValueError, match="verified specimen requires"):
            _verified_specimen(as_of_counterexample=None)
        with pytest.raises(ValueError, match="verified specimen requires"):
            _verified_specimen(coverage_from=None)
        with pytest.raises(ValueError, match="verified specimen requires"):
            _verified_specimen(
                sources=(SpecimenSource(source="tushare"),),
            )

    def test_knowable_time_must_be_timezone_aware(self) -> None:
        with pytest.raises(ValueError, match="timezone-aware"):
            _verified_specimen(knowable_from=datetime(2026, 7, 1))


class TestUpstreamIndependence:
    def test_shared_upstream_cannot_claim_independence(self) -> None:
        with pytest.raises(ValueError, match="distinct declared upstream groups"):
            _verified_specimen(
                sources=(
                    SpecimenSource(
                        source="tushare",
                        provider_snapshot_id="snapshot:tushare:x:sha256:a",
                        upstream_group="tushare-aggregate",
                    ),
                    SpecimenSource(
                        source="fuyao",
                        provider_snapshot_id="snapshot:fuyao:x:sha256:b",
                        upstream_group="tushare-aggregate",
                    ),
                ),
                convention_alignment="aligned",
                upstream_independent=True,
            )

    def test_unknown_upstream_groups_gap_is_structural(self) -> None:
        specimen = _verified_specimen(
            sources=(
                SpecimenSource(
                    source="tushare",
                    provider_snapshot_id="snapshot:tushare:x:sha256:a",
                ),
                SpecimenSource(
                    source="fuyao",
                    provider_snapshot_id="snapshot:fuyao:x:sha256:b",
                ),
            ),
            convention_alignment="aligned",
        )
        assert specimen.upstream_independent is False
        assert "UPSTREAM_INDEPENDENCE_UNPROVEN" in specimen.gaps

    def test_shared_upstream_group_is_recorded_not_hidden(self) -> None:
        specimen = _verified_specimen(
            sources=(
                SpecimenSource(
                    source="tushare",
                    provider_snapshot_id="snapshot:tushare:x:sha256:a",
                    upstream_group="tushare-aggregate",
                ),
                SpecimenSource(
                    source="fuyao",
                    provider_snapshot_id="snapshot:fuyao:x:sha256:b",
                    upstream_group="tushare-aggregate",
                ),
            ),
            convention_alignment="aligned",
        )
        assert specimen.upstream_independent is False
        assert "UPSTREAM_SHARED" in specimen.gaps

    def test_distinct_declared_groups_enable_independence(self) -> None:
        specimen = _verified_specimen(
            sources=(
                SpecimenSource(
                    source="tushare",
                    provider_snapshot_id="snapshot:tushare:x:sha256:a",
                    upstream_group="tushare",
                ),
                SpecimenSource(
                    source="manual",
                    provider_snapshot_id="snapshot:manual:x:sha256:b",
                    upstream_group="exchange-filing",
                ),
            ),
            convention_alignment="aligned",
            upstream_independent=True,
        )
        assert specimen.upstream_independent is True
        assert "UPSTREAM_INDEPENDENCE_UNPROVEN" not in specimen.gaps


class TestConventionsAndProcurement:
    def test_single_source_must_declare_single_source(self) -> None:
        with pytest.raises(ValueError, match="single_source"):
            _verified_specimen(convention_alignment="aligned")

    def test_multi_source_cannot_declare_single_source(self) -> None:
        with pytest.raises(ValueError, match="aligned or divergent"):
            _verified_specimen(
                sources=(
                    SpecimenSource(
                        source="tushare",
                        provider_snapshot_id="snapshot:tushare:x:sha256:a",
                    ),
                    SpecimenSource(source="fuyao"),
                ),
                convention_alignment="single_source",
            )

    def test_divergent_conventions_record_gap_not_silent_substitution(
        self,
    ) -> None:
        specimen = _verified_specimen(
            sources=(
                SpecimenSource(
                    source="tushare",
                    provider_snapshot_id="snapshot:tushare:x:sha256:a",
                ),
                SpecimenSource(
                    source="fuyao",
                    provider_snapshot_id="snapshot:fuyao:x:sha256:b",
                ),
            ),
            convention_alignment="divergent",
        )
        assert "CONVENTION_DIVERGENCE" in specimen.gaps

    def test_unknown_quotes_are_recorded_not_invented(self) -> None:
        specimen = _verified_specimen(
            procurement=(
                SpecimenProcurement(option="in_budget", quote_status="recorded"),
                SpecimenProcurement(option="professional", quote_status="unknown"),
            ),
        )
        assert "QUOTE_UNKNOWN" in specimen.gaps


class TestCatalogBoundaries:
    def test_all_five_categories_are_addressable(self) -> None:
        assert SPECIMEN_CATEGORIES == (
            "financial_restatement",
            "delisted_security",
            "index_rebalance",
            "dividend_etf",
            "cross_border_etf",
        )

    def test_unknown_category_rejected(self) -> None:
        invalid_category = "intraday_l2"
        with pytest.raises(ValueError, match="category"):
            _verified_specimen(category=invalid_category)

    def test_duplicate_sources_rejected(self) -> None:
        with pytest.raises(ValueError, match="duplicate"):
            _verified_specimen(
                sources=(
                    SpecimenSource(source="tushare", provider_snapshot_id="a"),
                    SpecimenSource(source="tushare", provider_snapshot_id="b"),
                ),
                convention_alignment="aligned",
            )
