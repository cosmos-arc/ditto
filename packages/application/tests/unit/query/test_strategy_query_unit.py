"""Tests for StrategyQueryFacade — 封装 StrategyCatalogService 只读查询."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
from unittest.mock import MagicMock

from ditto_application.contracts import (
    StrategyActiveInfo,
    StrategySpecInfo,
    StrategySpecValidationInfo,
    StrategyVersionDiffInfo,
    StrategyVersionInfo,
)
from ditto_application.queries.strategy import StrategyQueryFacade
from ditto_application.strategy_spec_deserialization import (
    canonical_spec_hash_for_record,
)
from ditto_strategy.alpha.seeds import SEED_STRATEGY_SPECS
from ditto_strategy.governance.models import (
    ReviewOutcome,
    StrategyActivePointer,
    StrategyVersion,
    StrategyVersionState,
    StrategyVersionStateRecord,
)
from ditto_strategy.models import StrategySpecRecord


def _make_record(
    strategy_id: str = "s-1",
    name: str = "test",
    version: int = 1,
) -> StrategySpecRecord:
    return StrategySpecRecord(
        strategy_id=strategy_id,
        name=name,
        spec_json={},
        version=version,
    )


def _make_spec_info(
    strategy_id: str = "s-1",
    name: str = "test",
    version: int = 1,
    status: str = "unknown",
) -> StrategySpecInfo:
    return StrategySpecInfo(
        strategy_id=strategy_id,
        name=name,
        spec_json={},
        version=version,
        status=status,
    )


class TestStrategyQueryFacadeListSpecs:
    """StrategyQueryFacade.list_specs 委托 catalog_service 并转换为 StrategySpecInfo."""

    def test_returns_spec_info_from_service(self) -> None:
        service = MagicMock(spec=["list_specs", "get_spec", "list_versions"])
        records = [_make_record("s-1"), _make_record("s-2")]
        service.list_specs.return_value = records
        facade = StrategyQueryFacade(catalog_service=service)

        result = facade.list_specs()

        expected = [_make_spec_info("s-1"), _make_spec_info("s-2")]
        assert result == expected
        service.list_specs.assert_called_once()

    def test_returns_empty_list(self) -> None:
        service = MagicMock(spec=["list_specs", "get_spec", "list_versions"])
        service.list_specs.return_value = []
        facade = StrategyQueryFacade(catalog_service=service)

        result = facade.list_specs()

        assert result == []


class TestStrategyQueryFacadeGetSpec:
    """StrategyQueryFacade.get_spec — 委托 catalog_service 并转换为 StrategySpecInfo."""

    def test_returns_spec_info(self) -> None:
        service = MagicMock(spec=["list_specs", "get_spec", "list_versions"])
        record = _make_record("s-1")
        service.get_spec.return_value = record
        facade = StrategyQueryFacade(catalog_service=service)

        result = facade.get_spec("s-1")

        assert result == _make_spec_info("s-1")
        service.get_spec.assert_called_once_with("s-1", None)

    def test_returns_none_when_not_found(self) -> None:
        service = MagicMock(spec=["list_specs", "get_spec", "list_versions"])
        service.get_spec.return_value = None
        facade = StrategyQueryFacade(catalog_service=service)

        result = facade.get_spec("missing")

        assert result is None
        service.get_spec.assert_called_once_with("missing", None)

    def test_passes_version_to_service(self) -> None:
        service = MagicMock(spec=["list_specs", "get_spec", "list_versions"])
        service.get_spec.return_value = _make_record()
        facade = StrategyQueryFacade(catalog_service=service)

        facade.get_spec("s-1", version=3)

        service.get_spec.assert_called_once_with("s-1", 3)


def _make_version(
    version: int = 1,
    parent: int | None = None,
    *,
    strategy_id: str = "s-1",
    spec_hash: str = "a" * 64,
    created_at: str = "2026-07-25T00:00:00Z",
) -> StrategyVersion:
    return StrategyVersion(
        strategy_id=strategy_id,
        version=version,
        parent_version=parent,
        schema_version=1,
        spec_hash=spec_hash,
        created_at=created_at,
    )


def _make_state(
    version: int = 1,
    state: StrategyVersionState = StrategyVersionState.PUBLISHED,
    review: ReviewOutcome = ReviewOutcome.APPROVED,
) -> StrategyVersionStateRecord:
    return StrategyVersionStateRecord(
        strategy_id="s-1",
        version=version,
        state=state,
        review_outcome=review,
        state_revision=1,
    )


def _make_pointer(version: int = 1, revision: int = 1) -> StrategyActivePointer:
    return StrategyActivePointer(
        strategy_id="s-1",
        active_version=version,
        pointer_revision=revision,
        activation_event_id="e1",
    )


class TestStrategyQueryFacadeListVersions:
    """list_versions projects governance versions + state into StrategyVersionInfo."""

    def test_returns_version_info_from_governance(self) -> None:
        governance_reader = MagicMock(spec=["list_versions", "get_active_pointer"])
        state_reader = MagicMock(spec=["get_state"])
        governance_reader.list_versions.return_value = (_make_version(2, parent=1),)
        state_reader.get_state.return_value = _make_state(2)
        facade = StrategyQueryFacade(
            MagicMock(spec=["list_specs", "get_spec"]),
            version_state_reader=state_reader,
            governance_version_reader=governance_reader,
        )

        result = facade.list_versions("s-1")

        assert result == [
            StrategyVersionInfo(
                strategy_id="s-1",
                version=2,
                parent_version=1,
                spec_hash="a" * 64,
                state="published",
                review_outcome="approved",
                created_at="2026-07-25T00:00:00Z",
            )
        ]
        governance_reader.list_versions.assert_called_once_with("s-1")
        state_reader.get_state.assert_called_once_with("s-1", 2)

    def test_returns_empty_when_no_versions(self) -> None:
        governance_reader = MagicMock(spec=["list_versions", "get_active_pointer"])
        governance_reader.list_versions.return_value = ()
        facade = StrategyQueryFacade(
            MagicMock(spec=["list_specs", "get_spec"]),
            governance_version_reader=governance_reader,
        )

        assert facade.list_versions("s-1") == []

    def test_returns_empty_without_governance_reader(self) -> None:
        facade = StrategyQueryFacade(MagicMock(spec=["list_specs", "get_spec"]))

        assert facade.list_versions("s-1") == []


class TestStrategyQueryFacadeListReviews:
    """list_reviews aggregates state=REVIEW versions, enriched with experiment_id."""

    def test_returns_review_versions_from_governance(self) -> None:
        governance_reader = MagicMock(
            spec=["list_versions", "list_versions_by_state", "get_active_pointer"]
        )
        state_reader = MagicMock(spec=["get_state"])
        governance_reader.list_versions_by_state.return_value = (
            _make_version(2, parent=1),
        )
        state_reader.get_state.return_value = _make_state(
            2, state=StrategyVersionState.REVIEW, review=ReviewOutcome.PENDING
        )
        facade = StrategyQueryFacade(
            MagicMock(spec=["list_specs", "get_spec"]),
            version_state_reader=state_reader,
            governance_version_reader=governance_reader,
        )

        result = facade.list_reviews()

        assert result == [
            StrategyVersionInfo(
                strategy_id="s-1",
                version=2,
                parent_version=1,
                spec_hash="a" * 64,
                state="review",
                review_outcome="pending",
                created_at="2026-07-25T00:00:00Z",
            )
        ]
        governance_reader.list_versions_by_state.assert_called_once_with(
            StrategyVersionState.REVIEW
        )

    def test_enriches_experiment_id_when_resolver_present(self) -> None:
        governance_reader = MagicMock(
            spec=["list_versions", "list_versions_by_state", "get_active_pointer"]
        )
        state_reader = MagicMock(spec=["get_state"])
        governance_reader.list_versions_by_state.return_value = (
            _make_version(2, parent=1),
        )
        state_reader.get_state.return_value = _make_state(
            2, state=StrategyVersionState.REVIEW, review=ReviewOutcome.APPROVED
        )
        resolver = MagicMock(spec=["resolve_experiment_id_by_spec_hash"])
        resolver.resolve_experiment_id_by_spec_hash.return_value = "exp-1"
        facade = StrategyQueryFacade(
            MagicMock(spec=["list_specs", "get_spec"]),
            version_state_reader=state_reader,
            governance_version_reader=governance_reader,
            experiment_resolver=resolver,
        )

        result = facade.list_reviews()

        assert result == [
            StrategyVersionInfo(
                strategy_id="s-1",
                version=2,
                parent_version=1,
                spec_hash="a" * 64,
                state="review",
                review_outcome="approved",
                created_at="2026-07-25T00:00:00Z",
                experiment_id="exp-1",
            )
        ]
        resolver.resolve_experiment_id_by_spec_hash.assert_called_once_with("a" * 64)

    def test_resolver_returning_none_yields_none_experiment_id(self) -> None:
        governance_reader = MagicMock(
            spec=["list_versions", "list_versions_by_state", "get_active_pointer"]
        )
        state_reader = MagicMock(spec=["get_state"])
        governance_reader.list_versions_by_state.return_value = (
            _make_version(2, parent=1),
        )
        state_reader.get_state.return_value = _make_state(
            2, state=StrategyVersionState.REVIEW, review=ReviewOutcome.PENDING
        )
        resolver = MagicMock(spec=["resolve_experiment_id_by_spec_hash"])
        resolver.resolve_experiment_id_by_spec_hash.return_value = None
        facade = StrategyQueryFacade(
            MagicMock(spec=["list_specs", "get_spec"]),
            version_state_reader=state_reader,
            governance_version_reader=governance_reader,
            experiment_resolver=resolver,
        )

        result = facade.list_reviews()

        assert result
        assert result[0].experiment_id is None

    def test_without_resolver_experiment_id_is_none(self) -> None:
        governance_reader = MagicMock(
            spec=["list_versions", "list_versions_by_state", "get_active_pointer"]
        )
        state_reader = MagicMock(spec=["get_state"])
        governance_reader.list_versions_by_state.return_value = (
            _make_version(2, parent=1),
        )
        state_reader.get_state.return_value = _make_state(
            2, state=StrategyVersionState.REVIEW, review=ReviewOutcome.PENDING
        )
        facade = StrategyQueryFacade(
            MagicMock(spec=["list_specs", "get_spec"]),
            version_state_reader=state_reader,
            governance_version_reader=governance_reader,
        )

        result = facade.list_reviews()

        assert result
        assert result[0].experiment_id is None

    def test_skips_versions_without_state_projection(self) -> None:
        governance_reader = MagicMock(
            spec=["list_versions", "list_versions_by_state", "get_active_pointer"]
        )
        state_reader = MagicMock(spec=["get_state"])
        governance_reader.list_versions_by_state.return_value = (
            _make_version(2, parent=1),
        )
        state_reader.get_state.return_value = None
        facade = StrategyQueryFacade(
            MagicMock(spec=["list_specs", "get_spec"]),
            version_state_reader=state_reader,
            governance_version_reader=governance_reader,
        )

        assert facade.list_reviews() == []

    def test_returns_empty_without_governance_reader(self) -> None:
        facade = StrategyQueryFacade(MagicMock(spec=["list_specs", "get_spec"]))

        assert facade.list_reviews() == []


class TestStrategyQueryFacadeGetActive:
    """get_active joins the active pointer with the published payload."""

    def test_returns_pointer_and_payload(self) -> None:
        governance_reader = MagicMock(spec=["list_versions", "get_active_pointer"])
        catalog = MagicMock(spec=["list_specs", "get_spec", "get_active_published"])
        governance_reader.get_active_pointer.return_value = _make_pointer(
            version=2, revision=3
        )
        catalog.get_active_published.return_value = _make_record("s-1", version=2)
        facade = StrategyQueryFacade(
            catalog, governance_version_reader=governance_reader
        )

        result = facade.get_active("s-1")

        assert result is not None
        assert isinstance(result, StrategyActiveInfo)
        assert result.active_version == 2
        assert result.pointer_revision == 3
        assert result.spec.version == 2
        assert result.spec.status == "active"
        catalog.get_active_published.assert_called_once_with("s-1")

    def test_returns_none_when_no_pointer(self) -> None:
        governance_reader = MagicMock(spec=["list_versions", "get_active_pointer"])
        governance_reader.get_active_pointer.return_value = None
        facade = StrategyQueryFacade(
            MagicMock(spec=["list_specs", "get_spec", "get_active_published"]),
            governance_version_reader=governance_reader,
        )

        assert facade.get_active("s-1") is None

    def test_returns_none_without_governance_reader(self) -> None:
        facade = StrategyQueryFacade(MagicMock(spec=["list_specs", "get_spec"]))

        assert facade.get_active("s-1") is None


def _candidate_spec() -> tuple[dict[str, object], str]:
    """合法 candidate spec_json 及其 canonical hash（供 validate/diff 测试）."""
    seed = SEED_STRATEGY_SPECS["seed_stock_selection_rotation"]
    spec_json: dict[str, object] = asdict(seed)
    digest = canonical_spec_hash_for_record(
        StrategySpecRecord(strategy_id=seed.strategy_id, name="", spec_json=spec_json),
    )
    return spec_json, digest


class TestStrategyQueryFacadeValidateSpec:
    """validate_spec 校验 candidate spec_json 并检测变更."""

    def test_valid_candidate_unchanged_when_hash_matches_base(self) -> None:
        candidate, candidate_hash = _candidate_spec()
        governance_reader = MagicMock(spec=["list_versions", "get_active_pointer"])
        governance_reader.list_versions.return_value = (
            _make_version(2, spec_hash=candidate_hash),
        )
        facade = StrategyQueryFacade(
            MagicMock(spec=["list_specs", "get_spec"]),
            governance_version_reader=governance_reader,
        )

        result = facade.validate_spec("s-1", 2, candidate)

        assert result == StrategySpecValidationInfo(
            strategy_id="s-1",
            version=2,
            canonical_hash=candidate_hash,
            base_spec_hash=candidate_hash,
            changed=False,
            valid=True,
            errors=(),
        )

    def test_valid_candidate_changed_when_hash_diverges(self) -> None:
        candidate, candidate_hash = _candidate_spec()
        governance_reader = MagicMock(spec=["list_versions", "get_active_pointer"])
        governance_reader.list_versions.return_value = (
            _make_version(2, spec_hash="b" * 64),
        )
        facade = StrategyQueryFacade(
            MagicMock(spec=["list_specs", "get_spec"]),
            governance_version_reader=governance_reader,
        )

        result = facade.validate_spec("s-1", 2, candidate)

        assert result is not None
        assert result.valid is True
        assert result.changed is True
        assert result.canonical_hash == candidate_hash
        assert result.base_spec_hash == "b" * 64

    def test_invalid_candidate_returns_valid_false_with_errors(self) -> None:
        governance_reader = MagicMock(spec=["list_versions", "get_active_pointer"])
        governance_reader.list_versions.return_value = (
            _make_version(2, spec_hash="b" * 64),
        )
        facade = StrategyQueryFacade(
            MagicMock(spec=["list_specs", "get_spec"]),
            governance_version_reader=governance_reader,
        )

        result = facade.validate_spec("s-1", 2, {"template": "different"})

        assert result is not None
        assert result.valid is False
        assert result.canonical_hash == ""
        assert result.changed is False
        assert len(result.errors) > 0

    def test_returns_none_when_version_not_found(self) -> None:
        governance_reader = MagicMock(spec=["list_versions", "get_active_pointer"])
        governance_reader.list_versions.return_value = ()
        facade = StrategyQueryFacade(
            MagicMock(spec=["list_specs", "get_spec"]),
            governance_version_reader=governance_reader,
        )

        assert facade.validate_spec("s-1", 99, {}) is None

    def test_returns_none_without_governance_reader(self) -> None:
        facade = StrategyQueryFacade(MagicMock(spec=["list_specs", "get_spec"]))

        assert facade.validate_spec("s-1", 2, {}) is None


def _version_record(
    version: int,
    *,
    parent: int | None = None,
    spec_hash: str = "a" * 64,
    spec_json: dict[str, object] | None = None,
) -> StrategySpecRecord:
    """构造含 spec_hash/parent_version/spec_json 的 catalog record."""
    return StrategySpecRecord(
        strategy_id="s-1",
        name="n",
        spec_json={} if spec_json is None else spec_json,
        version=version,
        parent_version=parent,
        spec_hash=spec_hash,
    )


class TestStrategyQueryFacadeDiffVersion:
    """diff_version 计算 version v 相对 parent_version 的 canonical spec 字段级 diff."""

    def test_returns_none_when_version_not_found(self) -> None:
        catalog = MagicMock(spec=["list_specs", "get_spec", "list_versions"])
        catalog.list_versions.return_value = []
        facade = StrategyQueryFacade(catalog)

        assert facade.diff_version("s-1", 99) is None

    def test_first_version_without_parent_returns_empty_diff(self) -> None:
        catalog = MagicMock(spec=["list_specs", "get_spec", "list_versions"])
        catalog.list_versions.return_value = [
            _version_record(1, parent=None, spec_hash="a" * 64),
        ]
        facade = StrategyQueryFacade(catalog)

        result = facade.diff_version("s-1", 1)

        assert result == StrategyVersionDiffInfo(
            strategy_id="s-1",
            version=1,
            parent_version=None,
            base_spec_hash="",
            target_spec_hash="a" * 64,
            changed=False,
            changes=(),
        )

    def test_diff_against_parent_reports_changes(self) -> None:
        parent_json, _ = _candidate_spec()
        child_json = deepcopy(parent_json)
        selector = child_json.get("selector")
        assert isinstance(selector, dict)
        selector["method"] = "top_k_changed"
        catalog = MagicMock(spec=["list_specs", "get_spec", "list_versions"])
        catalog.list_versions.return_value = [
            _version_record(1, parent=None, spec_hash="p" * 64, spec_json=parent_json),
            _version_record(2, parent=1, spec_hash="c" * 64, spec_json=child_json),
        ]
        facade = StrategyQueryFacade(catalog)

        result = facade.diff_version("s-1", 2)

        assert result is not None
        assert result.parent_version == 1
        assert result.base_spec_hash == "p" * 64
        assert result.target_spec_hash == "c" * 64
        assert result.changed is True
        assert len(result.changes) > 0
        catalog.list_versions.assert_called_once_with("s-1")

    def test_equal_hash_short_circuits_to_empty_diff(self) -> None:
        """target/parent 同 spec_hash（同 spec 重发版）→ 空差，不调 payload diff."""
        catalog = MagicMock(spec=["list_specs", "get_spec", "list_versions"])
        catalog.list_versions.return_value = [
            _version_record(1, parent=None, spec_hash="s" * 64),
            _version_record(2, parent=1, spec_hash="s" * 64),
        ]
        facade = StrategyQueryFacade(catalog)

        result = facade.diff_version("s-1", 2)

        assert result is not None
        assert result.changed is False
        assert result.changes == ()
        assert result.base_spec_hash == result.target_spec_hash
